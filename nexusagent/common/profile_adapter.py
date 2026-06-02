"""Profile Adapter 统一抽象层 — NexusAgent v4.0+

所有子系统级画像适配器必须继承 ProfileAdapter。
提供统一注册机制，消除 main.py 和 orchestrator 中的重复实例化代码。
"""

from __future__ import annotations

import logging
from typing import Any, Dict


class ProfileAdapter:
    """画像适配器抽象基类

    子类覆盖 _adapter_name 即可。
    原有方法 100% 保留，仅增加统一基类。
    """

    _adapter_name: str = ""

    def __init__(self, wrapped: Any) -> None:
        self._wrapped = wrapped
        self._logger = logging.getLogger(f"nexus.{self._adapter_name}.profile")

    @property
    def name(self) -> str:
        return self._adapter_name


class ProfileAdapterRegistry:
    """Profile Adapter 注册中心

    根治目标:
        - main.py 中只需注册，不需逐个管理实例化变量
        - orchestrator 中通过 registry 统一获取
        - 新增子系统时，只需实现 adapter + 1 行注册代码
    """

    def __init__(self) -> None:
        self._adapters: Dict[str, ProfileAdapter] = {}

    def register(self, name: str, adapter: ProfileAdapter) -> None:
        """注册 adapter"""
        self._adapters[name] = adapter
        self._logger = logging.getLogger("nexus.profile_registry")
        self._logger.debug("Registered profile adapter: %s -> %s", name, type(adapter).__name__)

    def get(self, name: str) -> ProfileAdapter | None:
        """按名称获取 adapter"""
        return self._adapters.get(name)

    def has(self, name: str) -> bool:
        """检查是否已注册"""
        return name in self._adapters

    def list_adapters(self) -> list[str]:
        """列出所有已注册 adapter 名称"""
        return list(self._adapters.keys())
