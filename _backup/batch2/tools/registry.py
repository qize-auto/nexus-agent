"""
NexusAgent v4.0+ — Nexus Tool Registry 工具注册中心

设计参考:
- Dify Plugin Marketplace: 插件发现 + 安装 + 管理
- LangChain Tool Hub: 1000+ 预置工具 + 自定义工具
- CrewAI Tools: 工具组合 + 依赖注入

职责:
    1. 统一注册内置工具、插件工具、MCP 外部工具
    2. 支持工具元数据（名称、版本、描述、作者、依赖、标签）
    3. 支持工具搜索、过滤、版本管理
    4. 提供 CLI 命令: nexus tool ls/info/search

Usage:
    from nexusagent.tools.registry import ToolRegistry
    registry = ToolRegistry()
    registry.discover_builtin_tools()
    tool = registry.get("browser.visit")
    result = await tool.invoke(url="https://example.com")
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import logging
import pkgutil
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional, Set, Type

logger = logging.getLogger("nexus.tools.registry")


@dataclass
class ToolMetadata:
    """工具元数据"""
    name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = "nexusagent"
    tags: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    source: str = "builtin"  # builtin | plugin | mcp | custom
    source_ref: str = ""     # 插件名 / MCP server URL / 模块路径
    enabled: bool = True


class RegisteredTool:
    """已注册工具包装器"""

    def __init__(self, metadata: ToolMetadata, handler: Callable, instance: Any = None):
        self.metadata = metadata
        self._handler = handler
        self._instance = instance

    async def invoke(self, **kwargs) -> Any:
        """调用工具"""
        try:
            if asyncio.iscoroutinefunction(self._handler):
                return await self._handler(**kwargs)
            else:
                return self._handler(**kwargs)
        except Exception as e:
            logger.warning("工具 %s 调用失败: %s", self.metadata.name, e)
            raise

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.metadata.name,
            "description": self.metadata.description,
            "version": self.metadata.version,
            "author": self.metadata.author,
            "tags": self.metadata.tags,
            "source": self.metadata.source,
            "enabled": self.metadata.enabled,
        }


class ToolRegistry:
    """
    Nexus Tool Registry — 统一工具注册中心

    Usage:
        registry = ToolRegistry()
        registry.discover_builtin_tools()
        registry.discover_plugins()

        # 搜索工具
        tools = registry.search("browser")

        # 获取并调用
        tool = registry.get("browser.visit")
        result = await tool.invoke(url="https://example.com")
    """

    def __init__(self):
        self._tools: Dict[str, RegisteredTool] = {}
        self._tags: Dict[str, Set[str]] = {}  # tag -> set(tool_names)
        self._builtin_modules = [
            "nexusagent.tools.browser",
            "nexusagent.tools.code_interpreter",
            "nexusagent.tools.layer",
            "nexusagent.tools.guard",
            "nexusagent.tools.file_ops",
            "nexusagent.tools.shell",
            "nexusagent.tools.code_edit",
            "nexusagent.tools.api_client",
            "nexusagent.tools.archive",
            "nexusagent.tools.database",
            "nexusagent.execution.chunked_reader",  # v4.0+ 强制分块读取工具
        ]

    # ───────────────────────── 注册 ─────────────────────────

    def register(
        self,
        name: str,
        handler: Callable,
        metadata: Optional[ToolMetadata] = None,
        instance: Any = None,
    ) -> RegisteredTool:
        """注册工具"""
        if metadata is None:
            metadata = ToolMetadata(name=name)
        else:
            metadata.name = name

        tool = RegisteredTool(metadata, handler, instance)
        self._tools[name] = tool

        # 索引标签
        for tag in metadata.tags:
            self._tags.setdefault(tag, set()).add(name)

        logger.debug("注册工具: %s (source=%s)", name, metadata.source)
        return tool

    def unregister(self, name: str) -> bool:
        """注销工具"""
        if name not in self._tools:
            return False
        tool = self._tools.pop(name)
        for tag in tool.metadata.tags:
            self._tags.get(tag, set()).discard(name)
        logger.debug("注销工具: %s", name)
        return True

    def get(self, name: str) -> Optional[RegisteredTool]:
        """获取工具"""
        return self._tools.get(name)

    # ───────────────────────── 发现 ─────────────────────────

    def discover_builtin_tools(self) -> int:
        """自动发现内置工具（幂等：多次调用不会重复注册）"""
        if getattr(self, '_builtin_discovered', False):
            return 0
        count = 0
        for module_name in self._builtin_modules:
            try:
                mod = importlib.import_module(module_name)
                count += self._scan_module_for_tools(mod, source="builtin", source_ref=module_name)
            except Exception as e:
                logger.warning("加载内置模块 %s 失败: %s", module_name, e)
        self._builtin_discovered = True
        return count

    def discover_plugins(self) -> int:
        """自动发现插件工具 (nexus-plugin-*)"""
        count = 0
        try:
            for finder, name, ispkg in pkgutil.iter_modules():
                if name.startswith("nexus_plugin_"):
                    try:
                        mod = importlib.import_module(name)
                        count += self._scan_module_for_tools(mod, source="plugin", source_ref=name)
                    except Exception as e:
                        logger.warning("加载插件 %s 失败: %s", name, e)
        except Exception as e:
            logger.warning("插件发现失败: %s", e)
        return count

    async def discover_mcp_tools(self, server_command: str) -> int:
        """从 MCP 服务器发现工具"""
        try:
            from nexusagent.tools.mcp_client import MCPClient
        except Exception as e:
            logger.warning("MCP 客户端不可用: %s", e)
            return 0

        client = MCPClient(server_command=server_command)
        connected = await client.connect()
        if not connected:
            logger.warning("无法连接 MCP 服务器: %s", server_command)
            return 0

        count = 0
        try:
            tools = await client.list_tools()
            for tool_info in tools:
                name = tool_info.get("name", "")
                if not name:
                    continue
                metadata = ToolMetadata(
                    name=name,
                    description=tool_info.get("description", ""),
                    source="mcp",
                    source_ref=server_command,
                    input_schema=tool_info.get("inputSchema", {}),
                )
                # 包装 MCP 工具调用（使用闭包避免 late-binding 问题）
                def _make_mcp_handler(tool_name: str, mcp_client):
                    async def handler(**kwargs):
                        return await mcp_client.call_tool(tool_name, kwargs)
                    return handler

                self.register(name, _make_mcp_handler(name, client), metadata)
                count += 1
        finally:
            await client.disconnect()

        logger.info("从 MCP 服务器发现 %d 个工具: %s", count, server_command)
        return count

    def _scan_module_for_tools(self, mod: Any, source: str, source_ref: str) -> int:
        """扫描模块中的工具类和方法"""
        count = 0
        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if not inspect.isclass(attr):
                continue
            # 查找带有 to_tool_spec 的类（内置工具约定）
            if hasattr(attr, "to_tool_spec") and callable(getattr(attr, "to_tool_spec")):
                try:
                    instance = attr()
                    spec = instance.to_tool_spec()
                    name = spec.get("name", attr_name.lower())
                    metadata = ToolMetadata(
                        name=name,
                        description=spec.get("description", ""),
                        source=source,
                        source_ref=source_ref,
                        input_schema=spec.get("input_schema", {}),
                        output_schema=spec.get("output_schema", {}),
                    )
                    # 查找 invoke / execute / visit 等默认方法
                    handler = None
                    for method_name in ("invoke", "execute", "visit", "call", "run"):
                        if hasattr(instance, method_name):
                            handler = getattr(instance, method_name)
                            break
                    if handler:
                        self.register(name, handler, metadata, instance)
                        count += 1
                except Exception as e:
                    logger.warning("扫描工具类 %s 失败: %s", attr_name, e)
        return count

    # ───────────────────────── 查询 ─────────────────────────

    def list_tools(self, source: Optional[str] = None, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """列出所有工具"""
        results = []
        for tool in self._tools.values():
            if enabled_only and not tool.metadata.enabled:
                continue
            if source and tool.metadata.source != source:
                continue
            results.append(tool.to_dict())
        return sorted(results, key=lambda x: x["name"])

    def search(self, query: str, tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """搜索工具"""
        query = query.lower()
        results = []
        for tool in self._tools.values():
            if not tool.metadata.enabled:
                continue
            # 标签过滤
            if tags and not any(t in tool.metadata.tags for t in tags):
                continue
            # 文本匹配
            if (query in tool.metadata.name.lower() or
                query in tool.metadata.description.lower() or
                any(query in t.lower() for t in tool.metadata.tags)):
                results.append(tool.to_dict())
        return sorted(results, key=lambda x: x["name"])

    def get_by_tag(self, tag: str) -> List[RegisteredTool]:
        """按标签获取工具"""
        names = self._tags.get(tag, set())
        return [self._tools[n] for n in names if n in self._tools and self._tools[n].metadata.enabled]

    def get_stats(self) -> Dict[str, Any]:
        """获取注册中心统计"""
        sources: Dict[str, int] = {}
        for tool in self._tools.values():
            sources[tool.metadata.source] = sources.get(tool.metadata.source, 0) + 1
        return {
            "total": len(self._tools),
            "enabled": sum(1 for t in self._tools.values() if t.metadata.enabled),
            "sources": sources,
            "tags": {k: len(v) for k, v in self._tags.items()},
        }

    def export_manifest(self) -> str:
        """导出工具清单（JSON）"""
        manifest = {
            "version": "1.0",
            "tools": [t.to_dict() for t in self._tools.values()],
        }
        return json.dumps(manifest, indent=2, ensure_ascii=False)

    # ── 向后兼容: ReActEngine ToolRegistry 协议 ──

    def describe_tools(self) -> List[Dict[str, Any]]:
        """兼容 ReActEngine 的 ToolRegistry 协议"""
        result = []
        for tool in self._tools.values():
            if not tool.metadata.enabled:
                continue
            schema = {
                "name": tool.metadata.name,
                "description": tool.metadata.description,
                "parameters": tool.metadata.input_schema or {"type": "object", "properties": {}},
            }
            result.append(schema)
        return result

    async def execute(self, name: str, arguments: Dict[str, Any]) -> Any:
        """兼容 ReActEngine 的 ToolRegistry 协议"""
        tool = self.get(name)
        if tool is None:
            raise ValueError(f"未注册的工具: {name}")
        return await tool.invoke(**arguments)


# 全局单例
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """获取全局 ToolRegistry 实例（懒加载）"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _registry.discover_builtin_tools()
    return _registry
