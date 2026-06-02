"""
import shlex
NexusAgent v3.3 — 工具层：MCP 协议客户端（真实 stdio 实现）
补全: ARC-022, NFR-077, ARC-045
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nexus.tools.mcp")


# ═══════════════════════════════════════════════════════════════
# ARC-022: MCP客户端 (stdio协议 — 真实实现)
# ═══════════════════════════════════════════════════════════════

class MCPClient:
    """ARC-022: Model Context Protocol 客户端 — 基于 mcp 包的真实实现

    支持 stdio 传输，自动处理 JSON-RPC 握手、工具发现与调用。
    """

    def __init__(self, server_command: str = "", server_url: str = ""):
        self._command = server_command
        self._url = server_url
        self._connected = False
        self._tools: List[Dict[str, Any]] = []
        self._session = None
        self._exit_stack: Optional[AsyncExitStack] = None

    async def connect(self) -> bool:
        """连接MCP服务器（stdio协议）"""
        try:
            from mcp import StdioServerParameters
            from mcp.client.stdio import stdio_client
            from mcp import ClientSession
        except ImportError as e:
            logger.warning("mcp包未安装: %s", e)
            return False

        if not self._command:
            logger.warning("未配置MCP服务器命令")
            return False

        try:
            # 解析命令（支持 "python script.py" 格式）
            parts = shlex.split(self._command)
            params = StdioServerParameters(command=parts[0], args=parts[1:])

            self._exit_stack = AsyncExitStack()
            read, write = await self._exit_stack.enter_async_context(
                stdio_client(params)
            )
            self._session = await self._exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await self._session.initialize()
            self._connected = True
            logger.info("MCP客户端已连接: %s", self._command)
            return True
        except Exception as e:
            logger.error("MCP连接失败: %s", e)
            self._connected = False
            return False

    async def list_tools(self) -> List[Dict[str, Any]]:
        """获取可用工具列表"""
        if not self._connected or not self._session:
            return [{"name": "mcp.echo", "description": "MCP回显工具（离线模式）"}]

        try:
            result = await self._session.list_tools()
            tools = []
            for tool in result.tools:
                tools.append({
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": tool.inputSchema,
                })
            self._tools = tools
            return tools
        except Exception as e:
            logger.warning("MCP列出工具失败: %s", e)
            return self._tools or [{"name": "mcp.echo", "description": "MCP回显工具"}]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """调用MCP工具"""
        if not self._connected or not self._session:
            return {"tool": name, "args": arguments, "result": "MCP未连接", "error": "offline"}

        try:
            result = await self._session.call_tool(name, arguments)
            # 统一输出格式
            content_text = ""
            for content in result.content:
                if hasattr(content, "text"):
                    content_text += content.text
            return {
                "tool": name,
                "args": arguments,
                "result": content_text,
                "is_error": result.isError if hasattr(result, "isError") else False,
            }
        except Exception as e:
            logger.error("MCP调用工具失败[%s]: %s", name, e)
            return {"tool": name, "args": arguments, "error": str(e)}

    async def disconnect(self) -> None:
        """断开连接并清理资源"""
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception as e:
                logger.debug("MCP断开时异常（可忽略）: %s", e)
        self._session = None
        self._exit_stack = None
        self._connected = False
        logger.info("MCP客户端已断开")

    @property
    def is_connected(self) -> bool:
        return self._connected


# ═══════════════════════════════════════════════════════════════
# NFR-077: 性能基准
# ═══════════════════════════════════════════════════════════════

class PerformanceBaseline:
    """NFR-077: 首次响应<2s基准测试"""
    def __init__(self):
        self._metrics: Dict[str, List[float]] = {}

    async def benchmark_first_response(self, agent_fn, test_input: str = "hello") -> float:
        """测试首次响应时间"""
        start = time.monotonic()
        await agent_fn(test_input)
        elapsed = (time.monotonic() - start) * 1000
        self._metrics.setdefault("first_response_ms", []).append(elapsed)
        return elapsed

    def is_within_sla(self, max_ms: float = 2000) -> bool:
        """检查是否在SLA内(<2s)"""
        values = self._metrics.get("first_response_ms", [])
        if not values:
            return True
        avg = sum(values) / len(values)
        return avg <= max_ms

    def report(self) -> Dict[str, Any]:
        """生成性能报告"""
        return {
            metric: {
                "avg_ms": sum(v) / len(v),
                "max_ms": max(v),
                "count": len(v),
                "within_sla": (sum(v) / len(v)) <= 2000,
            }
            for metric, v in self._metrics.items() if v
        }


# ═══════════════════════════════════════════════════════════════
# ARC-045: 7x24 错峰调度
# ═══════════════════════════════════════════════════════════════

class OffPeakScheduler:
    """ARC-045: 将重任务调度到低负载时段"""
    def __init__(self, peak_hours: tuple = (9, 18)):
        self._peak_start, self._peak_end = peak_hours
        self._deferred: List[asyncio.Task] = []

    def is_peak(self) -> bool:
        hour = time.localtime().tm_hour
        return self._peak_start <= hour < self._peak_end

    async def schedule(self, task_fn, *args, cancel_event: Optional[asyncio.Event] = None) -> Any:
        """智能调度：高峰延迟执行，低谷立即执行

        Args:
            cancel_event: 若设置，可在 sleep 期间通过 event.set() 取消调度
        """
        if self.is_peak():
            if cancel_event is not None:
                try:
                    await asyncio.wait_for(cancel_event.wait(), timeout=300)
                    # 若 event 被 set，说明取消调度
                    raise asyncio.CancelledError(调度被取消)
                except asyncio.TimeoutError:
                    pass  # 正常继续执行
            else:
                await asyncio.sleep(300)  # 延迟5分钟
        return await task_fn(*args) if asyncio.iscoroutinefunction(task_fn) else task_fn(*args)
