"""
NexusAgent v4.0+ — Core Module Registry 统一注册中心

所有模块（工具、技能、适配器、记忆后端）的统一注册与生命周期管理。

设计原则:
    1. 向后兼容: 现有 to_tool_spec + invoke 约定保持不变
    2. 渐进增强: ModuleSpec 作为可选增强层
    3. 生命周期: 加载→初始化→运行→暂停→卸载
    4. 依赖管理: 注册时拓扑排序，防止循环依赖

Usage:
    from nexusagent.core.registry import ModuleRegistry, ModuleSpec, ModuleLifecycle

    class MySkillSpec(ModuleSpec):
        name = "my_skill"
        version = "1.0.0"
        def initialize(self): ...
        def health_check(self): ...

    registry = ModuleRegistry()
    registry.register(MySkillSpec())
    registry.initialize_all()
"""

from __future__ import annotations

import importlib
import inspect
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Type

logger = logging.getLogger("nexus.core.registry")


# ═══════════════════════════════════════════════════════════════
# 模块生命周期枚举
# ═══════════════════════════════════════════════════════════════

class ModuleState(Enum):
    """模块生命周期状态"""
    UNLOADED = auto()   # 已注册但未加载
    LOADING = auto()    # 加载中
    INITIALIZING = auto()  # 初始化中
    RUNNING = auto()    # 正常运行
    PAUSED = auto()     # 已暂停
    UNLOADING = auto()  # 卸载中
    FAILED = auto()     # 加载/初始化失败


# ═══════════════════════════════════════════════════════════════
# ModuleSpec — 标准化模块接口
# ═══════════════════════════════════════════════════════════════

class ModuleSpec(ABC):
    """
    标准化模块规格接口

    所有 NexusAgent 模块（工具、技能、适配器等）均可选择实现此接口
    以获得生命周期管理和健康检查能力。

    对于现有工具类（使用 to_tool_spec 约定的），ToolRegistry 会自动
    将其包装为 SimpleModuleSpec，无需修改现有代码。
    """

    # ── 元数据 ──
    name: str = ""                       # 模块唯一标识
    version: str = "1.0.0"               # 语义化版本
    description: str = ""                # 模块描述
    author: str = ""                     # 作者
    tags: List[str] = []                 # 标签

    # ── 依赖 ──
    dependencies: List[str] = []         # 依赖的模块名
    optional_dependencies: List[str] = []

    # ── 能力声明 ──
    provides_tools: bool = False         # 是否提供工具
    provides_skills: bool = False        # 是否提供技能
    provides_adapters: bool = False      # 是否提供适配器
    provides_memory: bool = False        # 是否提供记忆后端

    # ── 运行时状态 ──
    _state: ModuleState = ModuleState.UNLOADED
    _state_history: List[tuple] = []
    _error_message: str = ""

    def __init__(self):
        # 防御性初始化：从类定义读取列表默认值，避免共享可变对象
        # 若类属性被 dataclass.field 污染（非 list），则回退到空列表
        def _list_from_class(attr: str) -> List:
            val = getattr(type(self), attr, [])
            return list(val) if isinstance(val, list) else []

        self.tags = _list_from_class("tags")
        self.dependencies = _list_from_class("dependencies")
        self.optional_dependencies = _list_from_class("optional_dependencies")
        self._state = ModuleState.UNLOADED
        self._state_history = []
        self._error_message = ""

    # ── 生命周期钩子 ──

    def on_load(self) -> bool:
        """加载钩子 — 导入依赖、读取配置。返回 False 表示加载失败。"""
        return True

    def on_initialize(self) -> bool:
        """初始化钩子 — 创建资源、建立连接。返回 False 表示初始化失败。"""
        return True

    def on_pause(self) -> bool:
        """暂停钩子 — 暂停服务但不释放资源。"""
        return True

    def on_resume(self) -> bool:
        """恢复钩子 — 从暂停状态恢复。"""
        return True

    def on_unload(self) -> None:
        """卸载钩子 — 释放所有资源。"""
        pass

    # ── 健康检查 ──

    def health_check(self) -> Dict[str, Any]:
        """
        健康检查 — 返回模块健康状态

        Returns:
            {"status": "healthy|degraded|unhealthy", "details": {...}}
        """
        return {
            "status": "healthy" if self._state == ModuleState.RUNNING else "unknown",
            "state": self._state.name,
            "error": self._error_message,
        }

    # ── 属性访问 ──

    @property
    def state(self) -> ModuleState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state == ModuleState.RUNNING

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "tags": self.tags,
            "dependencies": self.dependencies,
            "state": self._state.name,
            "capabilities": {
                "tools": self.provides_tools,
                "skills": self.provides_skills,
                "adapters": self.provides_adapters,
                "memory": self.provides_memory,
            },
        }


# ═══════════════════════════════════════════════════════════════
# SimpleModuleSpec — 包装现有工具类
# ═══════════════════════════════════════════════════════════════

class SimpleModuleSpec(ModuleSpec):
    """
    将现有工具类（使用 to_tool_spec 约定）包装为 ModuleSpec

    这是向后兼容层 — 现有工具无需修改即可接入 ModuleRegistry。
    """

    def __init__(self, tool_instance: Any, source: str = "builtin"):
        super().__init__()
        self._instance = tool_instance
        self._source = source
        self._tool_spec = tool_instance.to_tool_spec()
        self.name = self._tool_spec.get("name", "unknown.tool")
        self.description = self._tool_spec.get("description", "")
        self.version = getattr(tool_instance, "__version__", "1.0.0")
        self.provides_tools = True

    def health_check(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "state": self._state.name,
            "tool": self.name,
            "source": self._source,
        }


# ═══════════════════════════════════════════════════════════════
# ModuleRegistry — 统一注册中心
# ═══════════════════════════════════════════════════════════════

class ModuleRegistry:
    """
    统一模块注册中心

    管理所有 NexusAgent 模块的生命周期：
    注册 → 加载 → 初始化 → 运行 → 暂停 → 卸载

    与 ToolRegistry 的关系:
        ModuleRegistry 是上层抽象，ToolRegistry 是工具专用注册表。
        ToolRegistry 可以注册到 ModuleRegistry 作为子系统，
        也可以独立运行（向后兼容）。
    """

    def __init__(self):
        self._modules: Dict[str, ModuleSpec] = {}
        self._by_capability: Dict[str, Set[str]] = {
            "tools": set(),
            "skills": set(),
            "adapters": set(),
            "memory": set(),
        }
        self._by_tag: Dict[str, Set[str]] = {}

    # ── 注册 ──

    def register(self, spec: ModuleSpec) -> bool:
        """
        注册模块

        Returns:
            bool: 是否成功注册
        """
        if not spec.name:
            logger.warning("模块注册失败: name 不能为空")
            return False
        if spec.name in self._modules:
            logger.warning("模块 %s 已注册，跳过重复注册", spec.name)
            return False

        self._modules[spec.name] = spec

        # 索引能力
        if spec.provides_tools:
            self._by_capability["tools"].add(spec.name)
        if spec.provides_skills:
            self._by_capability["skills"].add(spec.name)
        if spec.provides_adapters:
            self._by_capability["adapters"].add(spec.name)
        if spec.provides_memory:
            self._by_capability["memory"].add(spec.name)

        # 索引标签
        for tag in spec.tags:
            self._by_tag.setdefault(tag, set()).add(spec.name)

        logger.debug("模块已注册: %s v%s", spec.name, spec.version)
        return True

    def unregister(self, name: str) -> bool:
        """注销模块"""
        if name not in self._modules:
            return False
        spec = self._modules.pop(name)
        for cap_set in self._by_capability.values():
            cap_set.discard(name)
        for tag_set in self._by_tag.values():
            tag_set.discard(name)
        spec.on_unload()
        return True

    def get(self, name: str) -> Optional[ModuleSpec]:
        """获取模块"""
        return self._modules.get(name)

    # ── 生命周期管理 ──

    def load(self, name: str) -> bool:
        """加载单个模块（加载成功后自动初始化）"""
        spec = self._modules.get(name)
        if not spec:
            return False
        if spec.state != ModuleState.UNLOADED:
            return True

        spec._state = ModuleState.LOADING
        try:
            ok = spec.on_load()
            if ok:
                # 加载成功 → 自动完成初始化，确保模块到达 RUNNING 状态
                return self.initialize(name)
            else:
                spec._state = ModuleState.FAILED
                spec._error_message = "on_load 返回 False"
        except Exception as e:
            spec._state = ModuleState.FAILED
            spec._error_message = str(e)
            logger.error("模块 %s 加载失败: %s", name, e)
        return spec.state != ModuleState.FAILED

    def initialize(self, name: str) -> bool:
        """初始化单个模块"""
        spec = self._modules.get(name)
        if not spec:
            return False
        if spec.state != ModuleState.LOADING:
            return spec.state == ModuleState.RUNNING

        spec._state = ModuleState.INITIALIZING
        try:
            ok = spec.on_initialize()
            if ok:
                spec._state = ModuleState.RUNNING
            else:
                spec._state = ModuleState.FAILED
                spec._error_message = "on_initialize 返回 False"
        except Exception as e:
            spec._state = ModuleState.FAILED
            spec._error_message = str(e)
            logger.error("模块 %s 初始化失败: %s", name, e)
        return spec.state == ModuleState.RUNNING

    def load_all(self) -> Dict[str, bool]:
        """按依赖拓扑排序加载所有模块"""
        order = self._resolve_dependencies()
        results = {}
        for name in order:
            results[name] = self.load(name)
        return results

    def initialize_all(self) -> Dict[str, bool]:
        """按依赖拓扑排序初始化所有模块"""
        order = self._resolve_dependencies()
        results = {}
        for name in order:
            if self._modules[name].state == ModuleState.LOADING:
                results[name] = self.initialize(name)
            else:
                results[name] = self._modules[name].state == ModuleState.RUNNING
        return results

    def unload_all(self) -> None:
        """卸载所有模块（逆序）"""
        for name in reversed(list(self._modules.keys())):
            try:
                self._modules[name].on_unload()
                self._modules[name]._state = ModuleState.UNLOADED
            except Exception as e:
                logger.warning("模块 %s 卸载失败: %s", name, e)

    def health_check_all(self) -> Dict[str, Dict[str, Any]]:
        """检查所有模块健康状态"""
        return {
            name: spec.health_check()
            for name, spec in self._modules.items()
        }

    # ── 查询 ──

    def list_modules(self, capability: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出模块"""
        if capability:
            names = self._by_capability.get(capability, set())
            return [self._modules[n].to_dict() for n in names if n in self._modules]
        return [spec.to_dict() for spec in self._modules.values()]

    def search(self, query: str) -> List[Dict[str, Any]]:
        """搜索模块"""
        query = query.lower()
        results = []
        for spec in self._modules.values():
            if (query in spec.name.lower() or
                query in spec.description.lower() or
                any(query in t.lower() for t in spec.tags)):
                results.append(spec.to_dict())
        return results

    def get_by_tag(self, tag: str) -> List[ModuleSpec]:
        """按标签获取模块"""
        names = self._by_tag.get(tag, set())
        return [self._modules[n] for n in names if n in self._modules]

    def get_by_capability(self, capability: str) -> List[ModuleSpec]:
        """按能力类型获取模块

        Args:
            capability: tools | skills | adapters | memory

        Returns:
            具有该能力的模块列表
        """
        names = self._by_capability.get(capability, set())
        return [self._modules[n] for n in names if n in self._modules]

    def get_stats(self) -> Dict[str, Any]:
        """注册中心统计"""
        states: Dict[str, int] = {}
        for spec in self._modules.values():
            s = spec.state.name
            states[s] = states.get(s, 0) + 1
        return {
            "total_modules": len(self._modules),
            "by_capability": {k: len(v) for k, v in self._by_capability.items()},
            "by_state": states,
            "by_tag": {k: len(v) for k, v in self._by_tag.items()},
        }

    # ── 依赖解析 ──

    def _resolve_dependencies(self) -> List[str]:
        """
        拓扑排序解析模块加载顺序

        Raises:
            ValueError: 检测到循环依赖
        """
        visited: Set[str] = set()
        temp_mark: Set[str] = set()
        result: List[str] = []

        def visit(name: str):
            if name in temp_mark:
                cycle = [n for n in temp_mark]
                raise ValueError(f"循环依赖 detected: {' -> '.join(cycle)}")
            if name in visited:
                return
            temp_mark.add(name)
            spec = self._modules.get(name)
            if spec:
                for dep in spec.dependencies:
                    if dep in self._modules:
                        visit(dep)
            temp_mark.remove(name)
            visited.add(name)
            result.append(name)

        for name in list(self._modules.keys()):
            if name not in visited:
                visit(name)

        return result


# ═══════════════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════════════

_registry_instance: Optional[ModuleRegistry] = None


def get_module_registry() -> ModuleRegistry:
    """获取全局 ModuleRegistry 实例（懒加载）"""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ModuleRegistry()
    return _registry_instance
