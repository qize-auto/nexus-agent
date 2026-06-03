"""
NexusAgent v4.0+ — Core Bootstrap 统一启动引导

职责:
    1. 将现有核心模块（工具、记忆、执行、安全、编排、认知）注册到 ModuleRegistry
    2. 建立模块依赖拓扑关系
    3. 提供统一的健康检查入口
    4. 向后兼容：不改变现有 NexusAgent.initialize() 的实例化逻辑

设计原则:
    - 声明式注册：ModuleSpec 只描述模块元数据和依赖关系
    - 延迟实例化：真正的资源创建仍由 NexusAgent.initialize() 硬编码完成
    - 健康检查：通过检查模块可导入性和 NexusAgent 内部状态
    - 失败安全：bootstrap 失败不影响现有初始化流程

Usage:
    from nexusagent.core.registry import get_module_registry
    from nexusagent.core.bootstrap import bootstrap_modules

    registry = get_module_registry()
    bootstrap_modules(registry, config)
    registry.initialize_all()
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from nexusagent.core.registry import ModuleSpec, ModuleRegistry, ModuleState

if TYPE_CHECKING:
    from nexusagent.config.settings import AppConfig

logger = logging.getLogger("nexus.core.bootstrap")


# ═══════════════════════════════════════════════════════════════
# _DeclarativeModuleSpec — 声明式模块规格
# ═══════════════════════════════════════════════════════════════

class _DeclarativeModuleSpec(ModuleSpec):
    """
    声明式模块规格 — 用于注册非工具类的核心子系统

    不持有实例引用，只提供元数据和导入检查。
    真正的实例化由 NexusAgent.initialize() 硬编码完成。
    """

    def __init__(
        self,
        name: str,
        module_path: str,
        description: str = "",
        version: str = "1.0.0",
        author: str = "nexusagent",
        dependencies: Optional[List[str]] = None,
        provides_tools: bool = False,
        provides_skills: bool = False,
        provides_adapters: bool = False,
        provides_memory: bool = False,
        tags: Optional[List[str]] = None,
        health_checker: Optional[Callable[[], Dict[str, Any]]] = None,
    ):
        super().__init__()
        self.name = name
        self._module_path = module_path
        self.description = description
        self.version = version
        self.author = author
        self.dependencies = list(dependencies) if dependencies else []
        self.provides_tools = provides_tools
        self.provides_skills = provides_skills
        self.provides_adapters = provides_adapters
        self.provides_memory = provides_memory
        self.tags = list(tags) if tags else []
        self._health_checker = health_checker
        self._import_ok: bool = False

    def on_load(self) -> bool:
        """检查模块是否可导入"""
        try:
            importlib.import_module(self._module_path)
            self._import_ok = True
            return True
        except Exception as e:
            logger.warning("模块 %s 导入失败: %s", self.name, e)
            self._import_ok = False
            return False

    def on_initialize(self) -> bool:
        """声明式模块不需要在 bootstrap 阶段创建实例"""
        # 真正的实例化由 NexusAgent.initialize() 完成
        # 这里只需标记为成功
        return True

    def health_check(self) -> Dict[str, Any]:
        """健康检查 — 检查模块可导入性"""
        status = "healthy" if self._import_ok else "degraded"
        result: Dict[str, Any] = {
            "status": status,
            "state": self._state.name,
            "module_path": self._module_path,
            "import_ok": self._import_ok,
        }
        if self._health_checker:
            try:
                custom = self._health_checker()
                result.update(custom)
            except Exception as e:
                result["health_check_error"] = str(e)
        return result


# ═══════════════════════════════════════════════════════════════
# 模块定义表 — 所有核心模块的元数据
# ═══════════════════════════════════════════════════════════════

_MODULE_DEFINITIONS: List[Dict[str, Any]] = [
    # ── 工具模块 (tools) ──
    {
        "name": "tools.search.web",
        "module_path": "nexusagent.tools.search",
        "description": "SearXNG 聚合搜索工具",
        "provides_tools": True,
        "tags": ["tool", "search", "web"],
    },
    {
        "name": "tools.document.convert",
        "module_path": "nexusagent.tools.document",
        "description": "文档转换工具 (PDF/Office → Markdown)",
        "provides_tools": True,
        "tags": ["tool", "document", "conversion"],
    },
    {
        "name": "tools.rag.retrieve",
        "module_path": "nexusagent.tools.rag",
        "description": "RAG 文档检索工具",
        "provides_tools": True,
        "dependencies": ["memory.vector_store"],
        "tags": ["tool", "rag", "retrieval"],
    },
    {
        "name": "tools.browser.visit",
        "module_path": "nexusagent.tools.browser",
        "description": "网页访问与内容提取工具",
        "provides_tools": True,
        "tags": ["tool", "browser", "web"],
    },
    {
        "name": "tools.file_ops",
        "module_path": "nexusagent.tools.file_ops",
        "description": "文件操作工具",
        "provides_tools": True,
        "tags": ["tool", "file", "filesystem"],
    },
    {
        "name": "tools.shell",
        "module_path": "nexusagent.tools.shell",
        "description": "Shell 命令执行工具",
        "provides_tools": True,
        "tags": ["tool", "shell", "system"],
    },
    {
        "name": "tools.code_edit",
        "module_path": "nexusagent.tools.code_edit",
        "description": "代码编辑工具",
        "provides_tools": True,
        "tags": ["tool", "code", "editor"],
    },
    {
        "name": "tools.code_interpreter",
        "module_path": "nexusagent.tools.code_interpreter",
        "description": "代码解释器工具",
        "provides_tools": True,
        "tags": ["tool", "code", "interpreter"],
    },
    {
        "name": "tools.api_client",
        "module_path": "nexusagent.tools.api_client",
        "description": "API 客户端工具",
        "provides_tools": True,
        "tags": ["tool", "api", "http"],
    },
    {
        "name": "tools.archive",
        "module_path": "nexusagent.tools.archive",
        "description": "归档工具",
        "provides_tools": True,
        "tags": ["tool", "archive", "compression"],
    },
    {
        "name": "tools.database",
        "module_path": "nexusagent.tools.database",
        "description": "数据库查询工具",
        "provides_tools": True,
        "tags": ["tool", "database", "sql"],
    },
    {
        "name": "tools.guard",
        "module_path": "nexusagent.tools.guard",
        "description": "审计日志工具",
        "provides_tools": True,
        "tags": ["tool", "audit", "security"],
    },
    {
        "name": "tools.layer",
        "module_path": "nexusagent.tools.layer",
        "description": "分层处理工具",
        "provides_tools": True,
        "tags": ["tool", "layer", "processing"],
    },
    {
        "name": "tools.chunked_reader",
        "module_path": "nexusagent.execution.chunked_reader",
        "description": "强制分块读取工具",
        "provides_tools": True,
        "tags": ["tool", "reader", "chunking"],
    },
    {
        "name": "tools.memory.self_editing",
        "module_path": "nexusagent.memory.self_editing",
        "description": "记忆自编辑工具",
        "provides_tools": True,
        "dependencies": ["memory.store"],
        "tags": ["tool", "memory", "self-editing"],
    },

    # ── 记忆模块 (memory) ──
    {
        "name": "memory.store",
        "module_path": "nexusagent.memory.store",
        "description": "SQLite 记忆存储",
        "provides_memory": True,
        "tags": ["memory", "storage", "sqlite"],
    },
    {
        "name": "memory.vector_store",
        "module_path": "nexusagent.memory.vector_store",
        "description": "ChromaDB 向量存储",
        "provides_memory": True,
        "tags": ["memory", "vector", "chroma"],
    },
    {
        "name": "memory.hybrid",
        "module_path": "nexusagent.memory.hybrid",
        "description": "混合记忆系统 (Working + Episodic + Semantic)",
        "provides_memory": True,
        "dependencies": ["memory.store", "memory.vector_store"],
        "tags": ["memory", "hybrid", "advanced"],
    },
    {
        "name": "memory.backup",
        "module_path": "nexusagent.memory.backup",
        "description": "记忆系统备份与恢复管理器",
        "provides_memory": True,
        "dependencies": ["memory.store"],
        "tags": ["memory", "backup", "recovery"],
    },
    {
        "name": "memory.compressor",
        "module_path": "nexusagent.memory.compressor",
        "description": "记忆压缩器",
        "provides_memory": True,
        "dependencies": ["memory.store"],
        "tags": ["memory", "compression"],
    },
    {
        "name": "memory.encryption",
        "module_path": "nexusagent.memory.encryption",
        "description": "记忆加密模块",
        "provides_memory": True,
        "tags": ["memory", "encryption", "security"],
    },
    {
        "name": "memory.user_profile",
        "module_path": "nexusagent.memory.user_profile",
        "description": "用户画像管理",
        "provides_memory": True,
        "dependencies": ["memory.store"],
        "tags": ["memory", "profile", "user"],
    },

    # ── 执行模块 (execution) ──
    {
        "name": "execution.react_engine",
        "module_path": "nexusagent.execution.react_engine",
        "description": "ReAct 推理执行引擎",
        "provides_skills": True,
        "dependencies": ["tools.registry"],
        "tags": ["execution", "react", "inference"],
    },
    {
        "name": "execution.error_recovery",
        "module_path": "nexusagent.execution.error_recovery",
        "description": "错误自我纠正引擎",
        "provides_skills": True,
        "dependencies": ["tools.registry"],
        "tags": ["execution", "recovery", "error-handling"],
    },
    {
        "name": "execution.reflexion",
        "module_path": "nexusagent.execution.reflexion",
        "description": "自我反思节点 (Reflexion)",
        "provides_skills": True,
        "tags": ["execution", "reflexion", "self-improvement"],
    },
    {
        "name": "execution.deliberation",
        "module_path": "nexusagent.execution.deliberation",
        "description": "多专家研讨引擎 (5 Expert Deliberation)",
        "provides_skills": True,
        "tags": ["execution", "deliberation", "multi-expert"],
    },
    {
        "name": "execution.tracker",
        "module_path": "nexusagent.execution.tracker",
        "description": "执行追踪器",
        "provides_skills": True,
        "tags": ["execution", "tracking", "monitoring"],
    },
    {
        "name": "execution.anti_compression",
        "module_path": "nexusagent.execution.anti_compression",
        "description": "防偷懒检测器",
        "provides_skills": True,
        "tags": ["execution", "anti-laziness", "quality"],
    },
    {
        "name": "execution.completeness",
        "module_path": "nexusagent.execution.completeness",
        "description": "完整性验证器",
        "provides_skills": True,
        "tags": ["execution", "completeness", "validation"],
    },
    {
        "name": "execution.checkpoint",
        "module_path": "nexusagent.execution.checkpoint",
        "description": "执行检查点",
        "provides_skills": True,
        "tags": ["execution", "checkpoint", "persistence"],
    },
    {
        "name": "execution.state_graph",
        "module_path": "nexusagent.execution.state_graph",
        "description": "状态图构建器",
        "provides_skills": True,
        "tags": ["execution", "state-graph", "workflow"],
    },
    {
        "name": "execution.work_memory",
        "module_path": "nexusagent.execution.work_memory",
        "description": "工作记忆管理",
        "provides_skills": True,
        "tags": ["execution", "work-memory", "cognition"],
    },
    {
        "name": "execution.hitl",
        "module_path": "nexusagent.execution.hitl",
        "description": "人类在环管理器 (HITL)",
        "provides_skills": True,
        "tags": ["execution", "hitl", "human-in-the-loop"],
    },

    # ── 安全模块 (security) ──
    {
        "name": "security.guardrails",
        "module_path": "nexusagent.security.guardrails",
        "description": "安全防护引擎 (Guardrails)",
        "provides_skills": True,
        "tags": ["security", "guardrails", "safety"],
    },
    {
        "name": "security.rbac",
        "module_path": "nexusagent.security.rbac",
        "description": "RBAC 权限控制",
        "provides_skills": True,
        "tags": ["security", "rbac", "access-control"],
    },
    {
        "name": "security.sandbox",
        "module_path": "nexusagent.security.sandbox",
        "description": "沙箱执行环境",
        "provides_skills": True,
        "tags": ["security", "sandbox", "isolation"],
    },
    {
        "name": "security.injection_detector",
        "module_path": "nexusagent.security.injection_detector",
        "description": "注入攻击检测器",
        "provides_skills": True,
        "tags": ["security", "injection", "detection"],
    },
    {
        "name": "security.sanitizer",
        "module_path": "nexusagent.security.sanitizer",
        "description": "输入消毒器",
        "provides_skills": True,
        "tags": ["security", "sanitizer", "input-validation"],
    },

    # ── 编排模块 (orchestration) ──
    {
        "name": "orchestration.orchestrator",
        "module_path": "nexusagent.orchestration.orchestrator",
        "description": "主编排器 (Orchestrator)",
        "provides_skills": True,
        "dependencies": ["execution.react_engine", "security.guardrails", "memory.hybrid"],
        "tags": ["orchestration", "core", "coordinator"],
    },
    {
        "name": "orchestration.swarm",
        "module_path": "nexusagent.agents.swarm",
        "description": "Agent 群体智能 (Swarm)",
        "provides_skills": True,
        "tags": ["orchestration", "swarm", "multi-agent"],
    },
    {
        "name": "orchestration.crew",
        "module_path": "nexusagent.agents.crew",
        "description": "Agent 团队编排 (Crew)",
        "provides_skills": True,
        "tags": ["orchestration", "crew", "team"],
    },
    {
        "name": "orchestration.mirofish",
        "module_path": "nexusagent.orchestration.mirofish",
        "description": "MiroFish 群体智能协作预演引擎",
        "provides_skills": True,
        "tags": ["orchestration", "mirofish", "simulation"],
    },
    {
        "name": "orchestration.scheduler",
        "module_path": "nexusagent.orchestration.scheduler",
        "description": "Cron 任务调度器",
        "provides_skills": True,
        "tags": ["orchestration", "scheduler", "cron"],
    },

    # ── 认知模块 (cognition) ──
    {
        "name": "cognition.dream_engine",
        "module_path": "nexusagent.cognition.dream_engine",
        "description": "梦境引擎 (用户画像后台加工)",
        "provides_skills": True,
        "dependencies": ["memory.hybrid", "memory.user_profile"],
        "tags": ["cognition", "dream", "user-profile"],
    },
    {
        "name": "cognition.user_profiler",
        "module_path": "nexusagent.cognition.user_profiler",
        "description": "用户画像分析器",
        "provides_skills": True,
        "dependencies": ["memory.user_profile"],
        "tags": ["cognition", "profiler", "user-analysis"],
    },
    {
        "name": "cognition.systems",
        "module_path": "nexusagent.cognition.systems",
        "description": "认知系统集合 (HybridSearch, CostEnforcer, ObservabilityLayer)",
        "provides_skills": True,
        "tags": ["cognition", "systems", "advanced"],
    },

    # ── 适配模块 (interface) ──
    {
        "name": "interface.adapter",
        "module_path": "nexusagent.interface.adapter",
        "description": "通道适配器基础",
        "provides_adapters": True,
        "tags": ["interface", "adapter", "channel"],
    },
    {
        "name": "interface.multi_channel",
        "module_path": "nexusagent.interface.multi_channel",
        "description": "多通道适配器 (Telegram/Discord/飞书)",
        "provides_adapters": True,
        "dependencies": ["interface.adapter"],
        "tags": ["interface", "multi-channel", "messaging"],
    },

    # ── 模型模块 (models) ──
    {
        "name": "models.unified_backend",
        "module_path": "nexusagent.models.unified_backend",
        "description": "统一 LLM 后端",
        "provides_skills": True,
        "tags": ["models", "llm", "backend"],
    },
    {
        "name": "models.router",
        "module_path": "nexusagent.models.router",
        "description": "模型路由",
        "provides_skills": True,
        "tags": ["models", "router", "routing"],
    },
    {
        "name": "models.health_monitor",
        "module_path": "nexusagent.models.health_monitor",
        "description": "模型健康监控",
        "provides_skills": True,
        "tags": ["models", "health", "monitoring"],
    },

    # ── 诊断模块 (diagnostics) ──
    {
        "name": "diagnostics.collector",
        "module_path": "nexusagent.diagnostics.collector",
        "description": "诊断数据收集器",
        "provides_skills": True,
        "tags": ["diagnostics", "collector", "telemetry"],
    },
    {
        "name": "diagnostics.report",
        "module_path": "nexusagent.diagnostics.report",
        "description": "诊断报告生成器",
        "provides_skills": True,
        "tags": ["diagnostics", "report", "analysis"],
    },

    # ── 可观测性 (observability) ──
    {
        "name": "observability.tracing",
        "module_path": "nexusagent.observability.tracing",
        "description": "分布式追踪",
        "provides_skills": True,
        "tags": ["observability", "tracing", "telemetry"],
    },
    {
        "name": "observability.metrics",
        "module_path": "nexusagent.observability.metrics",
        "description": "指标收集",
        "provides_skills": True,
        "tags": ["observability", "metrics", "monitoring"],
    },

    # ── 上下文管理 (context) ──
    {
        "name": "context.sliding_window",
        "module_path": "nexusagent.context.sliding_window",
        "description": "滑动窗口上下文管理",
        "provides_skills": True,
        "tags": ["context", "sliding-window", "memory-management"],
    },

    # ── 基准测试 (benchmark) ──
    {
        "name": "benchmark.runner",
        "module_path": "nexusagent.benchmark.runner",
        "description": "性能基准测试运行器",
        "provides_skills": True,
        "tags": ["benchmark", "performance", "testing"],
    },
    {
        "name": "benchmark.report",
        "module_path": "nexusagent.benchmark.report",
        "description": "基准测试报告生成器",
        "provides_skills": True,
        "tags": ["benchmark", "report", "analysis"],
    },
]


# ═══════════════════════════════════════════════════════════════
# Bootstrap API
# ═══════════════════════════════════════════════════════════════

def bootstrap_modules(registry: ModuleRegistry, config: Optional["AppConfig"] = None) -> Dict[str, bool]:
    """
    引导注册所有核心模块到 ModuleRegistry

    Args:
        registry: ModuleRegistry 实例
        config: 可选的应用配置（预留，用于条件注册）

    Returns:
        Dict[str, bool]: 模块名 -> 注册结果
    """
    results: Dict[str, bool] = {}
    for definition in _MODULE_DEFINITIONS:
        spec = _DeclarativeModuleSpec(**definition)
        results[spec.name] = registry.register(spec)

    # 工具注册中心也作为模块注册
    _register_tool_registry(registry)

    logger.info("Bootstrap 完成: %d/%d 模块已注册", sum(results.values()), len(results))
    return results


def _register_tool_registry(registry: ModuleRegistry) -> bool:
    """将 ToolRegistry 本身注册为模块"""
    try:
        from nexusagent.tools.registry import ToolRegistry

        class _ToolRegistryModuleSpec(ModuleSpec):
            def __init__(self):
                super().__init__()
                self.name = "tools.registry"
                self.description = "Nexus Tool Registry — 统一工具注册中心"
                self.version = "1.0.0"
                self.provides_tools = True
                self.tags = ["tool", "registry", "core"]

            def on_load(self) -> bool:
                return True

            def on_initialize(self) -> bool:
                return True

            def health_check(self) -> Dict[str, Any]:
                try:
                    from nexusagent.tools.registry import get_registry
                    reg = get_registry()
                    stats = reg.get_stats()
                    return {
                        "status": "healthy",
                        "total_tools": stats.get("total", 0),
                        "enabled_tools": stats.get("enabled", 0),
                        "sources": stats.get("sources", {}),
                    }
                except Exception as e:
                    return {"status": "unhealthy", "error": str(e)}

        return registry.register(_ToolRegistryModuleSpec())
    except Exception as e:
        logger.warning("ToolRegistry 注册失败: %s", e)
        return False


def get_module_catalog() -> List[Dict[str, Any]]:
    """
    获取模块目录（所有可注册的模块元数据）

    Returns:
        模块定义列表（不包含实例）
    """
    return [
        {
            "name": d["name"],
            "description": d.get("description", ""),
            "dependencies": d.get("dependencies", []),
            "capabilities": {
                "tools": d.get("provides_tools", False),
                "skills": d.get("provides_skills", False),
                "adapters": d.get("provides_adapters", False),
                "memory": d.get("provides_memory", False),
            },
            "tags": d.get("tags", []),
        }
        for d in _MODULE_DEFINITIONS
    ]


def get_builtin_tool_modules() -> List[str]:
    """
    获取内置工具模块的 module_path 列表

    Returns:
        模块路径列表（用于 ToolRegistry._builtin_modules）
    """
    return [
        d["module_path"]
        for d in _MODULE_DEFINITIONS
        if d.get("provides_tools") and d["name"].startswith("tools.")
    ]
