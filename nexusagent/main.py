"""
NexusAgent v3.3 — 主入口
来源: 设计稿全13章
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from typing import Any, Dict, Optional, Tuple

from nexusagent.config.settings import get_config, AppConfig
from nexusagent.interface.adapter import (
    ChannelAdapter, ChannelType, MessageEnvelope, MessageType,
    SecurityLevel, UserIdentity,
)
from nexusagent.execution.react_engine import (
    ReActEngine, ReActBudget, ReActResult, ExitReason,
    TaskPriority,
)
from nexusagent.security.guardrails import (
    GuardrailsEngine, ReviewResult, ReviewLevel, TrustScore,
)
from nexusagent.memory.store import MemoryStore
from nexusagent.observability.auto_tracer import trace_span
from nexusagent.execution.mode_switch import StrictModeDetector, ModeDetectionResult


def setup_logging(config: AppConfig) -> None:
    """初始化结构化日志"""
    level = logging.DEBUG if config.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # 抑制第三方库噪音
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


class CLIAdapter(ChannelAdapter):
    """
    CLI通道适配器 — 设计稿第3章
    最简单的通道实现，stdin/stdout交互
    """

    def __init__(self, config: dict):
        super().__init__(ChannelType.CLI, SecurityLevel.CRITICAL, config)
        self._pending_response: Optional[MessageEnvelope] = None

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def send(self, envelope: MessageEnvelope) -> bool:
        self._pending_response = envelope
        return True

    def parse_inbound(self, raw_payload: str) -> Optional[MessageEnvelope]:
        if not raw_payload or raw_payload.strip() == "":
            return None
        return MessageEnvelope(
            channel_type=ChannelType.CLI,
            content=raw_payload.strip(),
            security_level=SecurityLevel.CRITICAL,
        )

    def get_response(self) -> Optional[str]:
        """获取待发送的响应内容"""
        if self._pending_response:
            content = self._pending_response.content
            self._pending_response = None
            return content
        return None


class _CheckpointAdapter:
    """Checkpoint 存储适配器 — 将 MemoryStore 适配为 ReActEngine 的 CheckpointStore 协议"""
    def __init__(self, store):
        self._store = store
    async def save(self, session_id, state):
        await self._store.save_checkpoint(session_id, state)
    async def load(self, session_id):
        return await self._store.load_checkpoint(session_id)


class NexusAgent:
    """
    NexusAgent主类 — 设计稿第2章七层架构
    整合所有七层子系统
    """

    def __init__(self, config: Optional[AppConfig] = None):
        self._config = config or get_config()
        self._memory: Optional[MemoryStore] = None
        self._guardrails: Optional[GuardrailsEngine] = None
        self._trust_scores: dict[str, TrustScore] = {}
        self._engine: Optional[ReActEngine] = None
        self._orchestrator: Optional[Any] = None  # Orchestrator (ARC-008)
        self._router: Optional[Any] = None  # ModelRouter (设计稿第10章)
        self._llm_backends: Dict[str, Any] = {}  # 多模型后端池
        self._response_cache: Dict[str, Tuple[str, float]] = {}  # LRU缓存: key -> (answer, timestamp)
        self._cache_maxsize: int = 128
        self._cache_ttl_seconds: float = 300.0  # 5分钟TTL
        self._audit_logger: Optional[Any] = None
        # v4.0+ 统一模块注册中心
        self._module_registry: Optional[Any] = None
        # v4.0+ 空闲检测器（DreamEngine 空闲自动触发）
        self._idle_detector: Optional[Any] = None
        # v4.0+ 自我进化引擎（可选）
        self._evolution: Optional[Any] = None
        # v4.0+ 严谨执行模式
        self._strict_detector: Optional[StrictModeDetector] = None
        self._strict_workflow: Optional[Any] = None

    async def initialize(self) -> None:
        """初始化所有子系统"""
        # v4.0+ 统一模块注册中心引导（向后兼容：失败不影响现有初始化）
        try:
            from nexusagent.core.registry import get_module_registry
            from nexusagent.core.bootstrap import bootstrap_modules
            self._module_registry = get_module_registry()
            bootstrap_results = bootstrap_modules(self._module_registry, self._config)
            init_results = self._module_registry.initialize_all()
            logging.debug(
                "ModuleRegistry 引导完成: registered=%d initialized=%d",
                sum(bootstrap_results.values()),
                sum(init_results.values()),
            )
        except Exception as e:
            logging.warning("ModuleRegistry 引导失败（回退到现有初始化）: %s", e)
            self._module_registry = None

        # 记忆层（带AES-256加密）
        from nexusagent.memory.encryption import MemoryEncryption
        # v4.0+: 友好引导 — 如果 NEXUS_MASTER_KEY 未设置，自动生成并提示用户保存
        if not os.environ.get("NEXUS_MASTER_KEY"):
            import base64
            auto_key = base64.b64encode(os.urandom(32)).decode()
            os.environ["NEXUS_MASTER_KEY"] = auto_key
            logging.warning(
                "NEXUS_MASTER_KEY 未设置，已自动生成临时密钥。"
                "如需持久化，请将以下密钥保存到环境变量:\n"
                "  export NEXUS_MASTER_KEY=%s",
                auto_key,
            )
        self._encryption = MemoryEncryption()
        self._memory = MemoryStore(
            self._config.memory.db_path,
            encryption=self._encryption,
        )

        # 安全层
        self._guardrails = GuardrailsEngine()

        # RBAC 权限控制（v4.0+ 默认允许所有，需显式启用）
        from nexusagent.security.rbac import RBACEngine
        self._rbac = RBACEngine(default_allow=True)

        # 可选组件（v4.0+ 实验性功能，默认不启用）
        self._cron_scheduler: Optional[Any] = None
        self._heartbeat_monitor: Optional[Any] = None
        self._compliance_engine: Optional[Any] = None
        self._observability_layer: Optional[Any] = None
        if getattr(self._config, "experimental_cron", False):
            from nexusagent.orchestration.scheduler import CronScheduler
            self._cron_scheduler = CronScheduler()
            logger.info("CronScheduler 已启用（实验性）")
        if getattr(self._config, "experimental_observability", False):
            from nexusagent.cognition.systems import ObservabilityLayer
            self._observability_layer = ObservabilityLayer()
            logger.info("ObservabilityLayer 已启用（实验性）")

        # 审计日志 — ARC-013/089
        from nexusagent.tools.guard import AuditLogger
        self._audit_logger = AuditLogger()

        # 成本强制 — RUL-064/NFR-095
        from nexusagent.cognition.systems import CostEnforcer
        self._cost_enforcer = CostEnforcer(
            monthly_limit=self._config.budget.monthly_limit_usd,
            daily_limit=self._config.budget.daily_limit_usd,
            per_task_limit=self._config.budget.per_task_limit_usd,
        )

        # 模型路由 — 设计稿第10章
        from nexusagent.models.router import ModelRouter
        self._router = ModelRouter()

        # 执行层 — 初始化所有 LLM Backend（连接池预热）
        from nexusagent.tools.registry import get_registry

        self._llm_backends = self._init_llm_backends()
        default_llm = self._llm_backends.get(
            self._config.model.default_model,
            self._create_llm(self._config.model.default_provider, self._config.model.default_model),
        )

        # 工具注册中心（v4.0+ 替换 MockToolRegistry）
        tools = get_registry()
        tools.discover_builtin_tools()

        # 上下文滑动窗口管理器（v4.0+）
        from nexusagent.context.sliding_window import SlidingWindow, WindowStrategy
        window_manager = SlidingWindow(
            max_tokens=self._config.react.max_tokens,
            strategy=WindowStrategy.TRUNCATE,
            reserve_tokens=1000,
        )

        checkpoint = _CheckpointAdapter(self._memory)

        # 根据模型设置估算成本（美元/1K tokens）
        cost_map = {
            "deepseek-chat": 0.0015,
            "deepseek-v4-pro": 0.003,
            "moonshot-v1-8k": 0.012,
            "moonshot-v1-32k": 0.024,
            "moonshot-v1-128k": 0.060,
            "openai/gpt-4o-mini": 0.0006,
        }
        cost_per_1k = cost_map.get(self._config.model.default_model, 0.0015)

        # 防偷懒执行保障系统（v4.0+）— 先初始化以传入 ReActEngine
        from nexusagent.execution.tracker import ExecutionTracker
        self._tracker = ExecutionTracker()
        from nexusagent.execution.anti_compression import AntiCompressionDetector
        self._anti_compression = AntiCompressionDetector()
        from nexusagent.execution.completeness import CompletenessValidator
        self._completeness = CompletenessValidator()

        # v4.0+ 错误自我纠正引擎
        from nexusagent.execution.error_recovery import ErrorRecoveryEngine
        self._recovery_engine = ErrorRecoveryEngine(tool_registry=tools)

        self._engine = ReActEngine(
            llm=default_llm,
            tools=tools,
            checkpoint_store=checkpoint,
            budget=ReActBudget(
                max_iterations=self._config.react.max_iterations,
                max_total_tokens=self._config.react.max_tokens,
                max_time_seconds=self._config.react.max_time_seconds,
            ),
            circuit_breaker_threshold=self._config.react.circuit_breaker_errors,
            cost_enforcer=self._cost_enforcer,
            cost_per_1k_tokens=cost_per_1k,
            window_manager=window_manager,
            anti_compression=self._anti_compression,
            completeness_validator=self._completeness,
            recovery_engine=self._recovery_engine,
        )

        # 混合记忆系统（v4.0+）
        from nexusagent.memory.hybrid import HybridMemory
        self._hybrid_memory = HybridMemory(
            db_path=self._config.memory.db_path,
            encryption=self._encryption,
        )

        # v4.0+ 启动时数据完整性检查
        await self._startup_health_check()

        # AgentSwarm 多智能体编排（v4.0+）
        from nexusagent.agents.swarm import AgentSwarm
        self._swarm = AgentSwarm()
        from nexusagent.agents.profile_adapter import SwarmProfileAdapter
        self._swarm_profile_adapter = SwarmProfileAdapter(self._swarm)

        # Profile Adapter 统一注册中心（v4.0+ 根治重复叠加）
        from nexusagent.common.profile_adapter import ProfileAdapterRegistry
        self._profile_adapter_registry = ProfileAdapterRegistry()
        self._profile_adapter_registry.register("swarm", self._swarm_profile_adapter)

        # MiroFish 群体智能协作预演引擎（v4.0+ [MIROFISH-INSPIRED]）
        from nexusagent.orchestration.mirofish import MiroFishScheduler
        self._mirofish = MiroFishScheduler()
        self._mirofish.register_agents([
            ("researcher", "研究员"),
            ("analyst", "分析师"),
            ("writer", "写手"),
            ("critic", "审查员"),
        ])

        # 用户画像系统（v4.0+ 自主进化）
        from nexusagent.memory.user_profile import UserProfileManager
        from nexusagent.cognition.user_profiler import UserProfiler
        from nexusagent.cognition.dream_engine import DreamEngine
        self._profile_mgr = UserProfileManager(
            db_path=self._config.memory.db_path,
            encryption=self._encryption,
        )
        self._profiler = UserProfiler()
        self._dream = DreamEngine(
            profile_manager=self._profile_mgr,
            hybrid_memory=self._hybrid_memory,
        )
        from nexusagent.memory.profile_adapter import MemoryProfileAdapter
        self._memory_profile_adapter = MemoryProfileAdapter(self._hybrid_memory)
        self._profile_adapter_registry.register("memory", self._memory_profile_adapter)

        # 编排层 — ARC-008 Orchestrator集成（含画像系统 + 防偷懒）
        # 工作记忆与画像适配器（v4.0+）
        from nexusagent.execution.work_memory import WorkMemory
        self._work_memory = WorkMemory()
        from nexusagent.execution.profile_adapter import ReActProfileAdapter
        self._react_profile_adapter = ReActProfileAdapter(self._engine)
        self._profile_adapter_registry.register("react", self._react_profile_adapter)

        from nexusagent.security.profile_adapter import GuardrailsProfileAdapter
        self._guardrails_profile_adapter = GuardrailsProfileAdapter(self._guardrails)
        self._profile_adapter_registry.register("guardrails", self._guardrails_profile_adapter)
        from nexusagent.tools.profile_adapter import ToolRegistryProfileAdapter
        self._tools_profile_adapter = ToolRegistryProfileAdapter(tools)
        self._profile_adapter_registry.register("tools", self._tools_profile_adapter)

        # 深度思考与反思系统（v4.0+）
        from nexusagent.execution.deliberation import DeliberationEngine
        self._deliberation = DeliberationEngine(llm_backend=default_llm)
        from nexusagent.execution.reflexion import ReflexionNode
        self._reflexion = ReflexionNode(llm_backend=default_llm)
        from nexusagent.execution.hitl import HITLManager
        self._hitl = HITLManager()

        # AgentCrew 团队编排（v4.0+）
        from nexusagent.agents.crew import AgentCrew
        self._crew = AgentCrew()
        from nexusagent.agents.worker import WorkerAgent
        self._crew.add_workers([
            WorkerAgent("w1", "分析师", "analyst", "财务与市场分析"),
            WorkerAgent("w2", "研究员", "researcher", "信息检索与调研"),
            WorkerAgent("w3", "写手", "writer", "报告撰写与总结"),
        ])

        # StateGraph 构建器（v4.0+ 用于 enhanced 策略）
        from nexusagent.execution.state_graph import StateGraph
        self._state_graph = StateGraph()

        from nexusagent.orchestration.orchestrator import Orchestrator
        self._orchestrator = Orchestrator(
            guardrails=self._guardrails,
            rbac=self._rbac,
            react_engine=self._engine,
            trust_scores=self._trust_scores,
            memory_store=self._memory,
            hybrid_memory=self._hybrid_memory,
            swarm=self._swarm,
            mirofish_scheduler=self._mirofish,
            profile_manager=self._profile_mgr,
            user_profiler=self._profiler,
            execution_tracker=self._tracker,
            anti_compression=self._anti_compression,
            completeness_validator=self._completeness,
            work_memory=self._work_memory,
            profile_adapter_registry=self._profile_adapter_registry,
            swarm_profile_adapter=self._swarm_profile_adapter,
            memory_profile_adapter=self._memory_profile_adapter,
            react_profile_adapter=self._react_profile_adapter,
            guardrails_profile_adapter=self._guardrails_profile_adapter,
            tools_profile_adapter=self._tools_profile_adapter,
            deliberation_engine=self._deliberation,
            reflexion_node=self._reflexion,
            hitl_manager=self._hitl,
            agent_crew=self._crew,
            state_graph_builder=self._state_graph,
        )

        # 编排层画像适配器（需在 Orchestrator 创建后实例化）
        from nexusagent.orchestration.profile_adapter import OrchestratorProfileAdapter
        self._orch_profile_adapter = OrchestratorProfileAdapter(self._orchestrator)
        self._orchestrator.set_profile_adapter("orchestrator", self._orch_profile_adapter)

        # 多通道适配器初始化（根据配置启用）
        self._channel_adapters: Dict[str, Any] = {}
        self._init_channel_adapters()

        # v4.0+ 自我进化引擎（可选，默认 notify 模式）
        try:
            from nexusagent.evolution.engine import EvolutionEngine
            from nexusagent.benchmark.runner import BenchmarkRunner
            from nexusagent.evolution.strategies import (
                PromptOptimizationStrategy,
                ToolMappingStrategy,
                BudgetTuningStrategy,
            )
            evolution_mode = getattr(self._config, "evolution_mode", "notify")
            if evolution_mode != "off":
                self._evolution = EvolutionEngine(
                    config_dir=str(Path.home() / ".nexusagent" / "evolution"),
                    benchmark_runner=BenchmarkRunner(),
                    mode=evolution_mode,
                    cooldown_seconds=21600.0,  # 6 小时冷却期
                )
                self._evolution.register_strategy(PromptOptimizationStrategy())
                self._evolution.register_strategy(ToolMappingStrategy())
                self._evolution.register_strategy(BudgetTuningStrategy())
                logging.info("EvolutionEngine 已启用 (mode=%s)", evolution_mode)
        except Exception as e:
            logging.debug("EvolutionEngine 初始化失败 (可忽略): %s", e)
            self._evolution = None

        # v4.0+ 严谨执行模式初始化
        try:
            from nexusagent.execution.strict_mode import StrictExecutionWorkflow
            self._strict_detector = StrictModeDetector()
            self._strict_workflow = StrictExecutionWorkflow(
                llm_backend=default_llm,
                tool_registry=tools,
                deliberation=self._deliberation if self._config.strict.enable_deliberation else None,
                reflexion=self._reflexion,
                max_clarify_rounds=self._config.strict.max_clarify_rounds,
                max_retry_attempts=self._config.strict.max_retry_attempts,
            )
            logging.info("StrictExecutionWorkflow 已初始化 (mode=%s)", self._config.strict.mode)
        except Exception as e:
            logging.debug("StrictExecutionWorkflow 初始化失败 (可忽略): %s", e)
            self._strict_detector = None
            self._strict_workflow = None

        logging.info("NexusAgent v4.0+ initialized (Anti-Laziness + Profile + MiroFish + Orchestrator + StrictMode)")

    def _init_channel_adapters(self) -> None:
        """根据配置初始化多通道适配器"""
        channels = self._config.channels
        if "telegram" in channels.enabled_channels and channels.telegram.get("token"):
            from nexusagent.interface.multi_channel import TelegramAdapter
            adapter = TelegramAdapter(channels.telegram)
            adapter.register_handler(self._channel_message_handler)
            self._channel_adapters["telegram"] = adapter
            logging.info("Telegram 适配器已注册")
        if "discord" in channels.enabled_channels and channels.discord.get("token"):
            from nexusagent.interface.multi_channel import DiscordAdapter
            adapter = DiscordAdapter(channels.discord)
            adapter.register_handler(self._channel_message_handler)
            self._channel_adapters["discord"] = adapter
            logging.info("Discord 适配器已注册")
        if "feishu" in channels.enabled_channels and channels.feishu.get("webhook_url"):
            from nexusagent.interface.multi_channel import FeishuAdapter
            adapter = FeishuAdapter(channels.feishu)
            adapter.register_handler(self._channel_message_handler)
            self._channel_adapters["feishu"] = adapter
            logging.info("飞书适配器已注册")

    async def _channel_message_handler(self, envelope: Any) -> Any:
        """统一通道消息处理回调"""
        from nexusagent.interface.adapter import MessageEnvelope
        if isinstance(envelope, MessageEnvelope):
            response = await self.process_message(
                user_id=envelope.sender.user_id if envelope.sender else "channel_user",
                message=envelope.content,
                session_id=envelope.session_id,
            )
            envelope.content = response
            return envelope
        return None

    async def start_channels(self) -> None:
        """启动所有已注册的多通道适配器"""
        for name, adapter in self._channel_adapters.items():
            try:
                await adapter.start()
                logging.info("通道 %s 已启动", name)
            except Exception as e:
                logging.warning("通道 %s 启动失败: %s", name, e)

    async def stop_channels(self) -> None:
        """停止所有多通道适配器"""
        for name, adapter in self._channel_adapters.items():
            try:
                await adapter.stop()
                logging.info("通道 %s 已停止", name)
            except Exception as e:
                logging.warning("通道 %s 停止失败: %s", name, e)

    def _init_llm_backends(self) -> Dict[str, Any]:
        """预热所有配置的LLM后端连接池 — 设计稿第10章 / v0.1.0 多模型版"""
        backends: Dict[str, Any] = {}
        # 默认模型
        default_model = self._config.model.default_model
        default_provider = self._config.model.default_provider
        backends[default_model] = self._create_llm(default_provider, default_model)

        # 预加载 Fallback 链中的模型
        fallback_chain = getattr(self._config.model, "fallback_chain", [])
        for entry in fallback_chain:
            if entry == "local":
                continue
            # 格式: "provider/model" 或纯 "model"
            if "/" in entry:
                provider, model = entry.split("/", 1)
            else:
                provider = self._config.model.default_provider
                model = entry
            key = f"{provider}/{model}"
            if key not in backends and model not in backends:
                try:
                    backends[key] = self._create_llm(provider, model)
                except Exception as e:
                    logging.debug("Warm-up failed for %s: %s", key, e)

        return backends

    def _cache_key(self, user_id: str, message: str, session_id: str) -> str:
        """生成缓存键"""
        import hashlib
        raw = f"{user_id}:{session_id}:{message}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:32]

    def _get_cached_response(self, user_id: str, message: str, session_id: str) -> Optional[str]:
        """LRU缓存查询 — SLA < 2s (缓存命中时 < 500ms)"""
        key = self._cache_key(user_id, message, session_id)
        entry = self._response_cache.get(key)
        if entry is None:
            return None
        answer, timestamp = entry
        if time.time() - timestamp > self._cache_ttl_seconds:
            del self._response_cache[key]
            return None
        return answer

    def _set_cached_response(self, user_id: str, message: str, session_id: str, answer: str) -> None:
        """写入LRU缓存（超限时淘汰最旧条目）"""
        key = self._cache_key(user_id, message, session_id)
        self._response_cache[key] = (answer, time.time())
        # 简单LRU淘汰
        while len(self._response_cache) > self._cache_maxsize:
            oldest = min(self._response_cache, key=lambda k: self._response_cache[k][1])
            del self._response_cache[oldest]

    def _select_llm_for_message(self, message: str) -> Any:
        """
        设计稿第10章: 三层模型路由接入
        根据消息内容选择最优LLM后端
        """
        if not self._router:
            return self._engine._llm if self._engine else None

        model_name = self._router.route(content=message, has_pii=False)
        backend = self._llm_backends.get(model_name)
        if backend:
            logging.debug("ModelRouter 选择模型: %s", model_name)
            return backend

        # 回退到默认模型
        logging.debug("ModelRouter 选择的模型 %s 未预热，使用默认", model_name)
        return self._engine._llm if self._engine else None

    @trace_span("nexus.process_message")
    async def process_message(
        self,
        user_id: str,
        message: str,
        session_id: str = "",
    ) -> str:
        """
        处理用户消息 — 设计稿第2章核心数据流
        接入层 → 安全层 → 执行层 → 记忆层
        特性: 本地缓存 + 模型路由
        """
        if not self._orchestrator:
            await self.initialize()

        session_id = session_id or f"session_{user_id}"

        # 1. 本地缓存检查 — SLA 加速
        cached = self._get_cached_response(user_id, message, session_id)
        if cached is not None:
            if self._audit_logger:
                self._audit_logger.log("cache_hit", f"user={user_id}, session={session_id}")
            return cached

        # 2. 模型路由 — 根据消息内容动态选择LLM
        selected_llm = self._select_llm_for_message(message)
        if selected_llm and self._engine:
            self._engine._llm = selected_llm

        # 3. 审计日志
        if self._audit_logger:
            self._audit_logger.log("message_received", f"user={user_id}, model={getattr(selected_llm, '_model', 'default')}, len={len(message)}")

        # 4. v4.0+ 严谨执行模式路由
        strict_result = await self._try_strict_mode(user_id, message, session_id)
        if strict_result is not None:
            self._set_cached_response(user_id, message, session_id, strict_result)
            if self._dream:
                self._trigger_dream_on_idle(user_id)
            return strict_result

        # 5. 使用 Orchestrator 处理完整流程（常规 ReAct 模式）
        result = await self._orchestrator.process(
            user_id=user_id,
            message=message,
            session_id=session_id,
        )

        # 6. 缓存响应
        self._set_cached_response(user_id, message, session_id, result.answer)

        # 7. DreamEngine 空闲自动触发（v4.0+ 画像后台加工）
        if self._dream:
            self._trigger_dream_on_idle(user_id)

        return result.answer

    async def _try_strict_mode(
        self,
        user_id: str,
        message: str,
        session_id: str,
    ) -> Optional[str]:
        """
        尝试以严谨执行模式处理消息

        返回:
            str: 严谨模式生成的报告（Markdown）或澄清提示
            None: 不满足严谨模式条件，回退到常规 ReAct 模式
        """
        if not self._strict_detector or not self._strict_workflow:
            return None

        mode = self._config.strict.mode
        if mode == "chat":
            return None  # 强制对话模式

        detection = self._strict_detector.detect(message)
        if mode == "strict":
            detection.mode = "strict"  # 强制严谨模式

        if detection.mode != "strict":
            return None  # 自动检测判定为对话模式

        logger = logging.getLogger("nexus.main")
        logger.info("严谨模式激活: reason=%s confidence=%.2f", detection.reason, detection.confidence)

        if self._audit_logger:
            self._audit_logger.log("strict_mode_activated", f"user={user_id}, reason={detection.reason}")

        # v4.0+: 前置意图分析，若需要澄清则直接返回提示（避免 StateGraph 内部无法暂停等待用户输入）
        intent = await self._strict_workflow._analyzer.analyze(message)
        if intent.is_task and not intent.is_clear_enough():
            questions = intent.suggested_questions or ["能否请您补充更多细节？"]
            clarify_text = "## 🤔 需求澄清\n\n您的请求有些模糊，为了更准确地帮您完成，请补充以下信息：\n\n"
            for i, q in enumerate(questions, 1):
                clarify_text += f"{i}. {q}\n"
            clarify_text += "\n补充信息后，我将立即为您执行。"
            logger.info("严谨模式: 需求需要澄清，返回 %d 个问题", len(questions))
            return clarify_text

        result = await self._strict_workflow.run(message, session_id=session_id)

        if result.get("mode") == "chat":
            logger.info("严谨模式判定为对话请求，回退到常规模式")
            return None

        report = result.get("report", "")
        if not report:
            report = "## 严谨执行结果\n\n任务已处理，但未生成详细报告。"

        if self._audit_logger:
            self._audit_logger.log(
                "strict_mode_completed",
                f"user={user_id}, success={result.get('success')}, elapsed={result.get('elapsed_seconds', 0):.1f}s",
            )

        return report

    def _trigger_dream_on_idle(self, user_id: str) -> None:
        """
        空闲时触发 DreamEngine 梦境周期

        设计:
            1. 用户发消息时 mark_active()，取消之前的后台等待
            2. 启动后台协程：等待空闲阈值（默认 30s）
            3. 如果期间用户再次发消息，后台协程被取消
            4. 如果确实空闲了，执行 dream_cycle（内部会检查 pending_traits，空则立即返回）
        """
        if self._idle_detector is None:
            from nexusagent.execution.idle_detector import IdleDetector
            self._idle_detector = IdleDetector(idle_seconds=30.0)

        self._idle_detector.mark_active()

        async def _wait_and_trigger() -> None:
            try:
                # 等待空闲阈值
                await asyncio.sleep(self._idle_detector._idle_threshold)
                if not self._idle_detector.is_idle():
                    return  # 期间用户又活跃了
                # 真正空闲，触发 dream_cycle
                await self._trigger_dream(user_id)
            except asyncio.CancelledError:
                logging.debug("DreamEngine 后台等待被取消（用户重新活跃）")
            except Exception as e:
                logging.debug("DreamEngine 空闲触发失败 (可忽略): %s", e)

        task = asyncio.create_task(_wait_and_trigger())
        self._idle_detector.set_background_task(task)

    async def _trigger_dream(self, user_id: str) -> None:
        """后台触发 DreamEngine 梦境周期 — v4.0+"""
        try:
            report = await self._dream.dream_cycle(user_id)
            if report.traits_merged > 0 or report.traits_rejected > 0 or report.traits_staled > 0:
                logging.info(
                    "DreamEngine: %s 完成梦境周期 — merged=%d rejected=%d staled=%d elapsed=%.1fms",
                    user_id,
                    report.traits_merged,
                    report.traits_rejected,
                    report.traits_staled,
                    report.elapsed_ms,
                )
            else:
                logging.debug(
                    "DreamEngine: %s 无待处理画像条目，跳过",
                    user_id,
                )
        except Exception as e:
            logging.debug("DreamEngine 梦境周期失败 (可忽略): %s", e)

    async def _startup_health_check(self) -> None:
        """启动时数据完整性检查 — v4.0+ 生产级保障"""
        import shutil
        from pathlib import Path

        checks = []

        # 1. 检查 SQLite 数据库可读写
        try:
            db_path = Path(self._config.memory.db_path)
            if db_path.exists():
                health = await self._hybrid_memory.health_check()
                checks.append(("memory_db", health["status"] == "healthy"))
                if health["status"] != "healthy":
                    logging.warning("记忆数据库完整性异常: %s", health.get("integrity"))
            else:
                checks.append(("memory_db", True))  # 新数据库会自动创建
        except Exception as e:
            checks.append(("memory_db", False))
            logging.warning("记忆数据库健康检查失败: %s", e)

        # 2. 检查 ChromaDB 可访问
        try:
            from nexusagent.memory.vector_store import ChromaVectorStore
            store = ChromaVectorStore()
            checks.append(("chroma_db", store.is_available()))
        except Exception as e:
            checks.append(("chroma_db", False))
            logging.warning("ChromaDB 检查失败: %s", e)

        # 3. 检查 uploads 目录
        uploads_dir = Path("uploads")
        uploads_dir.mkdir(exist_ok=True)
        checks.append(("uploads_dir", uploads_dir.exists() and os.access(uploads_dir, os.W_OK)))

        # 4. 检查磁盘空间
        try:
            stat = shutil.disk_usage(".")
            free_gb = stat.free / (1024 ** 3)
            checks.append(("disk_space", free_gb > 1.0))
            if free_gb < 1.0:
                logging.warning("磁盘空间不足: %.1f GB 剩余", free_gb)
        except Exception:
            checks.append(("disk_space", True))

        # 5. 检查备份目录
        backup_dir = Path(os.environ.get("NEXUS_BACKUP_DIR", "./backups"))
        backup_dir.mkdir(parents=True, exist_ok=True)
        checks.append(("backup_dir", backup_dir.exists()))

        ok = sum(1 for _, passed in checks if passed)
        total = len(checks)
        logging.info("启动健康检查: %d/%d 通过 (%s)", ok, total,
                     ", ".join(f"{name}={'OK' if passed else 'FAIL'}" for name, passed in checks))

    def reload_llm(self, provider: str, model: str) -> None:
        """运行时热切换 LLM Backend — v0.1.0 多模型版"""
        self._config.model.default_provider = provider
        self._config.model.default_model = model
        llm = self._create_llm(provider, model)
        key = f"{provider}/{model}"
        self._llm_backends[key] = llm
        self._llm_backends[model] = llm
        if self._engine:
            self._engine._llm = llm
            logging.info("LLM hot-swapped: provider=%s model=%s", provider, model)
        else:
            logging.warning("Engine not initialized, cannot hot-swap LLM")

    @property
    def current_llm(self) -> Any:
        """获取当前使用的 LLM Backend（供 WebAdapter 流式输出使用）"""
        return self._engine._llm if self._engine else None

    async def shutdown(self) -> None:
        """优雅关闭"""
        for name, backend in getattr(self, '_llm_backends', {}).items():
            if backend and hasattr(backend, 'close'):
                try:
                    await backend.close()
                except Exception as e:
                    logging.getLogger("nexus.main").debug("LLM backend %s close error (ignorable): %s", name, e)
        if self._memory:
            await self._memory.cleanup_expired()
            self._memory.close()
        await self.stop_channels()
        logging.info("NexusAgent shutdown complete")

    def _create_llm(self, provider: str, model: str):
        """
        创建 LLM Backend 实例 — 统一工厂方法 / v0.1.0 多模型版。
        支持所有已注册 Provider: deepseek, moonshot, kimi, qwen, wenxin,
        glm, xiaomi, openai, anthropic, google, azure, groq, together
        """
        from nexusagent.models.unified_backend import UnifiedLLMBackend
        provider = provider.lower()
        custom_cfg = getattr(self._config.model, "providers", {}).get(provider, {})
        api_key = custom_cfg.get("api_key") or None
        base_url = custom_cfg.get("base_url") or None
        return UnifiedLLMBackend(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )


async def interactive_mode(agent: NexusAgent) -> None:
    """交互式CLI模式 — 设计稿第3章零配置启动"""
    print("╔══════════════════════════════════════════╗")
    print("║   NexusAgent v3.3 — 个人智能体系统      ║")
    print("║   输入 'exit' 或 Ctrl+C 退出             ║")
    print("╚══════════════════════════════════════════╝")
    print()

    user_id = "cli_user"
    session_id = f"session_{id(user_id)}"

    while True:
        try:
            user_input = input(">>> ").strip()
            if user_input.lower() in ("exit", "quit", "q"):
                print("再见。")
                break
            if not user_input:
                continue

            print("思考中...", end="\r")
            response = await agent.process_message(
                user_id=user_id,
                message=user_input,
                session_id=session_id,
            )
            print(f"\n{response}\n")

        except KeyboardInterrupt:
            print("\n再见。")
            break
        except Exception as e:
            logging.error("Error processing message: %s", e, exc_info=True)
            print(f"\n[错误] {e}\n")


async def _run_interactive(args) -> int:
    """交互式模式"""
    config = AppConfig.from_yaml(args.config)
    if args.debug:
        config.debug = True
    setup_logging(config)
    agent = NexusAgent(config)
    await agent.initialize()
    try:
        await interactive_mode(agent)
    finally:
        await agent.shutdown()
    return 0


def _run_doctor(args) -> int:
    """诊断模式"""
    from nexusagent.cli.doctor import main as doctor_main
    return doctor_main()


def _run_tool_cmd(args) -> int:
    """工具管理"""
    from nexusagent.cli.main import cmd_tool
    return cmd_tool(args.subargs or [])


async def main() -> int:
    """主入口 — v4.0+ 支持子命令"""
    parser = argparse.ArgumentParser(
        description="NexusAgent v4.0+ — 个人智能体系统 (8维度集成版)",
    )
    parser.add_argument(
        "--config", type=str, default=None,
        help="配置文件路径",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="启用调试模式",
    )
    subparsers = parser.add_subparsers(dest="command")

    # 默认交互式
    subparsers.add_parser("chat", help="交互式对话（默认）")

    # doctor 诊断
    doctor_parser = subparsers.add_parser("doctor", help="运行环境诊断")

    # tool 管理
    tool_parser = subparsers.add_parser("tool", help="工具管理 (ls/info/search)")
    tool_parser.add_argument("subargs", nargs="*", help="子命令参数")

    args = parser.parse_args()

    if args.command == "doctor":
        return _run_doctor(args)
    elif args.command == "tool":
        return _run_tool_cmd(args)
    else:
        return await _run_interactive(args)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
