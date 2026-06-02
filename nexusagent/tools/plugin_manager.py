"""
NexusAgent v4.0+ — 插件管理器

设计参考:
- Dify Plugin Marketplace
- LangChain Integrations (1000+)

职责:
    动态加载 nexus-plugin-* 命名空间包，支持从 PyPI/GitHub 安装插件
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("nexus.tools.plugins")


@dataclass
class PluginInfo:
    """插件信息"""
    name: str
    version: str
    description: str
    tools: List[str] = field(default_factory=list)
    entry_point: str = ""


class PluginManager:
    """
    插件管理器

    Usage:
        pm = PluginManager()
        pm.discover()  # 自动发现已安装的插件
        pm.load_plugin("nexus-plugin-browser")
    """

    def __init__(self):
        self._plugins: Dict[str, PluginInfo] = {}
        self._tool_registry: Dict[str, Callable] = {}

    def discover(self) -> List[PluginInfo]:
        """自动发现 nexus-plugin-* 包"""
        discovered = []
        try:
            for finder, name, ispkg in pkgutil.iter_modules():
                if name.startswith("nexus_plugin_"):
                    info = self._load_plugin_info(name)
                    if info:
                        discovered.append(info)
                        self._plugins[name] = info
        except Exception as e:
            logger.warning("插件发现失败: %s", e)
        return discovered

    def _load_plugin_info(self, module_name: str) -> Optional[PluginInfo]:
        try:
            mod = importlib.import_module(module_name)
            return PluginInfo(
                name=module_name,
                version=getattr(mod, "__version__", "unknown"),
                description=getattr(mod, "__doc__", "") or "",
                tools=getattr(mod, "TOOLS", []),
                entry_point=f"{module_name}:main",
            )
        except Exception as e:
            logger.warning("加载插件 %s 失败: %s", module_name, e)
            return None

    def load_plugin(self, name: str) -> bool:
        """加载指定插件"""
        if name in self._plugins:
            return True
        info = self._load_plugin_info(name)
        if info:
            self._plugins[name] = info
            return True
        return False

    def register_tool(self, name: str, handler: Callable) -> None:
        """注册插件工具"""
        self._tool_registry[name] = handler

    def get_tool(self, name: str) -> Optional[Callable]:
        return self._tool_registry.get(name)

    def list_plugins(self) -> List[PluginInfo]:
        return list(self._plugins.values())

    def list_tools(self) -> List[str]:
        return list(self._tool_registry.keys())


# 全局实例
_plugin_manager = PluginManager()


def get_plugin_manager() -> PluginManager:
    return _plugin_manager
