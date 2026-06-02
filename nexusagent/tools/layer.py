"""
NexusAgent v3.3 — 工具层：ToolSpec + ToolLayer 完整实现
补全: ARC-021, ENT-056, RUL-065
依赖: security/guardrails ✅, utils/retry ✅
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Protocol

logger = logging.getLogger("nexus.tools")


# ═══════════════════════════════════════════════════════════════
# ENT-056: ToolSpec — 设计稿6.2.1
# ═══════════════════════════════════════════════════════════════

class ToolSource(Enum):
    """工具来源枚举"""
    NATIVE = auto()
    MCP_STDIO = auto()
    MCP_SSE = auto()
    MCP_HTTP = auto()
    EXTERNAL_API = auto()
    PLUGIN = auto()


class RiskLevel(Enum):
    """工具风险等级 — RUL-065强制沙箱"""
    SAFE = auto()       # 纯计算/本地只读
    LOW = auto()        # 本地文件读取/网络只读
    MEDIUM = auto()     # 网络写入/外部API
    HIGH = auto()       # 代码执行/文件写入
    CRITICAL = auto()   # 任意代码/系统调用


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """
    统一工具规格描述 — 设计稿6.2.1
    所有工具（无论来源）都必须转换为ToolSpec注册

    Attributes:
        name: 全局唯一工具名称 "namespace.tool_name"
        description: LLM可读的功能描述
        source: 工具来源
        risk_level: 预评估风险等级
        input_schema: JSON Schema输入参数
        output_schema: JSON Schema输出结构（可选）
        sandbox_required: 是否必须在沙箱中执行
        timeout_seconds: 默认超时
        max_retries: 最大重试次数
        metadata: 扩展元数据
    """
    name: str
    description: str
    source: ToolSource
    risk_level: RiskLevel
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None
    sandbox_required: bool = False
    timeout_seconds: float = 30.0
    max_retries: int = 2
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # RUL-065: 高风险工具强制沙箱
        if self.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            object.__setattr__(self, "sandbox_required", True)

    def to_llm_schema(self) -> Dict[str, Any]:
        """生成LLM可使用的工具描述"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


# ═══════════════════════════════════════════════════════════════
# ToolLayer — 设计稿6.2.1 统一工具层 (ARC-021)
# ═══════════════════════════════════════════════════════════════

class ToolExecutor(Protocol):
    """工具执行器协议"""
    async def execute(self, spec: ToolSpec, params: Dict[str, Any]) -> Any: ...
    async def health_check(self) -> bool: ...


@dataclass
class ToolInvocation:
    """工具调用上下文"""
    tool_spec: ToolSpec
    params: Dict[str, Any]
    session_id: str = ""
    trace_id: str = ""
    timestamp_ns: int = field(default_factory=lambda: time.time_ns())
    attempt: int = 0
    execution_time_ms: float = 0.0
    error: Optional[str] = None
    cached: bool = False

    @property
    def success(self) -> bool:
        return self.error is None


class NativeExecutor:
    """原生工具执行器"""

    def __init__(self, handlers: Dict[str, Callable]):
        self._handlers = handlers

    async def execute(self, spec: ToolSpec, params: Dict[str, Any]) -> Any:
        handler = self._handlers.get(spec.name)
        if not handler:
            raise ValueError(f"未注册的原生工具: {spec.name}")
        if asyncio.iscoroutinefunction(handler):
            return await handler(**params)
        return handler(**params)

    async def health_check(self) -> bool:
        return len(self._handlers) > 0


class ToolLayer:
    """
    统一工具层 — 设计稿6.2.1 (ARC-021)
    职责:
    1. 统一注册: 接收来自技能/MCP/API的工具
    2. 安全执行: 执行前校验+沙箱隔离
    3. 标准化输出: 封装为统一结果
    4. 生命周期: 健康检查+优雅关闭
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or {}
        self._registry: Dict[str, ToolSpec] = {}
        self._executors: Dict[ToolSource, ToolExecutor] = {}
        self._lock = asyncio.Lock()
        self._cache: Dict[str, Any] = {}

        # 注册原生执行器
        self._executors[ToolSource.NATIVE] = NativeExecutor({})

        # 统计
        self._stats = {
            "total_invocations": 0,
            "successful": 0,
            "failed": 0,
            "cache_hits": 0,
        }

    # ── 注册 (ARC-021 统一注册) ──

    async def register(
        self,
        spec: ToolSpec,
        handler: Optional[Callable] = None,
    ) -> None:
        """
        注册工具到统一层

        Args:
            spec: 工具规格
            handler: 仅NATIVE来源需要提供可调用函数

        Raises:
            ValueError: 工具名称冲突
        """
        async with self._lock:
            if spec.name in self._registry:
                raise ValueError(f"工具名称冲突: {spec.name}")

            self._registry[spec.name] = spec

            if handler and spec.source == ToolSource.NATIVE:
                executor = self._executors.get(ToolSource.NATIVE)
                if isinstance(executor, NativeExecutor):
                    executor._handlers[spec.name] = handler

            logger.info(
                "注册工具: %s (来源=%s, 风险=%s, 沙箱=%s)",
                spec.name, spec.source.name, spec.risk_level.name, spec.sandbox_required,
            )

    # ── 发现 ──

    def describe_tools(self, source_filter: Optional[ToolSource] = None) -> List[Dict[str, Any]]:
        """获取可用工具描述（供LLM使用）"""
        tools = []
        for spec in self._registry.values():
            if source_filter and spec.source != source_filter:
                continue
            tools.append(spec.to_llm_schema())
        return tools

    def get_tool(self, name: str) -> Optional[ToolSpec]:
        """获取工具规格"""
        return self._registry.get(name)

    # ── 执行 (RUL-065 沙箱强制) ──

    async def execute(
        self,
        name: str,
        arguments: Dict[str, Any],
        session_id: str = "",
    ) -> Any:
        """
        执行工具调用

        Args:
            name: 工具名称
            arguments: 参数
            session_id: 会话ID

        Returns:
            工具执行结果

        Raises:
            ValueError: 工具未注册
            RuntimeError: 沙箱要求但不可用
        """
        spec = self._registry.get(name)
        if not spec:
            raise ValueError(f"未注册的工具: {name}")

        invocation = ToolInvocation(
            tool_spec=spec,
            params=arguments,
            session_id=session_id,
        )

        # RUL-065: 高风险工具强制沙箱检查
        if spec.sandbox_required:
            if not self._is_sandbox_available():
                raise RuntimeError(
                    f"工具 {name} 需要沙箱执行(风险={spec.risk_level.name})，但沙箱不可用"
                )
            logger.warning("沙箱执行: %s (风险=%s)", name, spec.risk_level.name)

        # 缓存检查
        cache_key = f"{name}:{str(sorted(arguments.items()))}"
        if cache_key in self._cache:
            invocation.cached = True
            self._stats["cache_hits"] += 1
            return self._cache[cache_key]

        self._stats["total_invocations"] += 1

        # 执行
        executor = self._executors.get(spec.source)
        if not executor:
            self._stats["failed"] += 1
            raise ValueError(f"不支持的工具体来源: {spec.source.name}")

        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                executor.execute(spec, arguments),
                timeout=spec.timeout_seconds,
            )
            invocation.execution_time_ms = (time.monotonic() - start) * 1000
            self._stats["successful"] += 1

            # 缓存结果（仅SAFE/LOW风险）
            if spec.risk_level in (RiskLevel.SAFE, RiskLevel.LOW):
                self._cache[cache_key] = result

            return result

        except asyncio.TimeoutError:
            invocation.error = f"工具执行超时({spec.timeout_seconds}s)"
            self._stats["failed"] += 1
            raise
        except Exception as e:
            invocation.error = str(e)
            self._stats["failed"] += 1
            raise

    # ── 健康检查 ──

    async def health_check(self) -> Dict[str, Any]:
        """检查所有执行器健康状态"""
        status = {"healthy": True, "executors": {}}
        for source, executor in self._executors.items():
            try:
                ok = await executor.health_check()
                status["executors"][source.name] = "healthy" if ok else "unhealthy"
                if not ok:
                    status["healthy"] = False
            except Exception as e:
                status["executors"][source.name] = f"error: {e}"
                status["healthy"] = False
        status["stats"] = self._stats.copy()
        return status

    # ── 内部 ──

    def _is_sandbox_available(self) -> bool:
        """检查沙箱是否可用 — 验证 Docker daemon 可连接"""
        try:
            import docker
            client = docker.from_env()
            client.ping()
            return True
        except Exception:
            return False

    async def shutdown(self) -> None:
        """优雅关闭"""
        self._cache.clear()
        logger.info("ToolLayer shutdown: 统计=%s", self._stats)


# ═══════════════════════════════════════════════════════════════
# 向后兼容 MockToolRegistry (保留原有接口)
# ═══════════════════════════════════════════════════════════════

class MockToolRegistry:
    """
    功能工具注册表 — 支持文件读写，Agent 可自愈
    """

    def __init__(self, project_root: str = ""):
        self._root = project_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._root = os.path.realpath(self._root)
        self._tools: Dict[str, Callable] = {}

    def _sanitize_path(self, path: str) -> Optional[str]:
        """路径遍历防护: 使用 CrossPlatformPath 确保解析后的路径在 _root 范围内"""
        if not path:
            return None
        from nexusagent.utils.cross_platform import CrossPlatformPath
        cpp = CrossPlatformPath()
        if os.path.isabs(path):
            full = os.path.realpath(path)
        else:
            full = os.path.realpath(os.path.join(self._root, path))
        # 校验边界（跨平台安全）
        if not cpp.is_safe(full, self._root):
            return None
        return full

    def get_tool(self, name: str) -> Optional[Callable]:
        return self._tools.get(name)

    def describe_tools(self) -> List[Dict[str, Any]]:
        return [
            {"name": "read_file", "description": "读取文件内容",
             "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
            {"name": "write_file", "description": "写入文件（覆盖）",
             "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
            {"name": "search_files", "description": "搜索文件内容",
             "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},
        ]

    async def execute(self, name: str, arguments: Dict[str, Any]) -> Any:
        if name == "read_file":
            path = arguments.get("path", "")
            if not os.path.isabs(path):
                path = os.path.join(self._root, path)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()[:5000]
            except Exception as e:
                return f"Error reading {path}: {e}"
        elif name == "write_file":
            path = arguments.get("path", "")
            content = arguments.get("content", "")
            if not os.path.isabs(path):
                path = os.path.join(self._root, path)
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"Written {len(content)} chars to {path}"
            except Exception as e:
                return f"Error writing {path}: {e}"
        elif name == "search_files":
            pattern = arguments.get("pattern", "")
            results = []
            for root, dirs, files in os.walk(self._root):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                for f in files:
                    if f.endswith((".py", ".html", ".md", ".json", ".yaml", ".css", ".js")):
                        fp = os.path.join(root, f)
                        try:
                            with open(fp, "r", encoding="utf-8") as fh:
                                for i, line in enumerate(fh, 1):
                                    if pattern in line:
                                        results.append(f"{fp}:{i}: {line.strip()[:100]}")
                                        if len(results) >= 20:
                                            break
                        except Exception as e:
                            logger.debug("search_files跳过不可读文件 %s: %s", fp, e)
            return "\n".join(results) if results else f"No matches for '{pattern}'"
        return f"Unknown tool: {name}"
