"""
NexusAgent v3.3 — 编排层：Orchestrator + REVER协议
补全: ARC-008, ARC-010, RUL-057
依赖: execution/react_engine ✅, security/guardrails ✅, memory/store ✅
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

from nexusagent.observability.auto_tracer import trace_span

logger = logging.getLogger("nexus.orchestration")


# ═══════════════════════════════════════════════════════════════
# REVER协议 — 完整五步状态机 (ARC-010, RUL-057)
# Record → Evaluate → Verify → Escalate → Report
# ═══════════════════════════════════════════════════════════════

class REVERStage(Enum):
    """REVER协议五阶段"""
    RECORD = auto()      # 记录失败
    EVALUATE = auto()    # 评估严重性
    VERIFY = auto()      # 验证可恢复性
    ESCALATE = auto()    # 升级处理
    REPORT = auto()      # 报告用户


class Severity(Enum):
    """失败严重性"""
    TRANSIENT = auto()   # 临时错误（可自动重试）
    RECOVERABLE = auto() # 可恢复（需降级策略）
    DEGRADED = auto()    # 降级（部分功能不可用）
    FATAL = auto()       # 致命（需人工介入）


@dataclass
class REVERResult:
    """REVER协议执行结果"""
    stage_reached: REVERStage
    severity: Severity
    retries_attempted: int = 0
    recovered: bool = False
    escalated: bool = False
    user_message: str = ""
    error_detail: str = ""
    timestamp: float = field(default_factory=time.time)
    captured_output: Any = None  # 成功时捕获的操作输出

    @property
    def is_resolved(self) -> bool:
        return self.recovered and not self.escalated


class REVEREngine:
    """
    REVER协议引擎 — 设计稿编排层
    Record→Evaluate→Verify→Escalate→Report

    使用模式:
        engine = REVEREngine(max_retries=3, base_delay=1.0)
        result = await engine.execute(operation, fallback_fn)
        if not result.is_resolved:
            # 报告用户
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        backoff_factor: float = 2.0,
        max_delay: float = 30.0,
    ):
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._backoff_factor = backoff_factor
        self._max_delay = max_delay
        self._error_log: List[REVERResult] = []

    async def execute(
        self,
        operation: Callable[[], Any],
        fallback: Optional[Callable[[], Any]] = None,
        context: str = "",
    ) -> REVERResult:
        """
        执行带REVER保护的操作

        Args:
            operation: 主要操作
            fallback: 降级操作（可选）
            context: 操作描述（用于日志）

        Returns:
            REVERResult: 完整的执行结果
        """
        result = REVERResult(
            stage_reached=REVERStage.RECORD,
            severity=Severity.TRANSIENT,
        )

        # ── Stage 1: RECORD + 指数退避重试 ──
        last_error = None
        captured_output = None
        for attempt in range(self._max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(operation):
                    captured_output = await operation()
                else:
                    captured_output = operation()

                result.recovered = True
                result.stage_reached = REVERStage.VERIFY
                result.retries_attempted = attempt
                # 保存操作输出供上层使用
                result.captured_output = captured_output
                self._error_log.append(result)
                logger.info("REVER[%s]: 操作成功 (尝试%d)", context, attempt + 1)
                return result

            except asyncio.CancelledError:
                raise
            except Exception as e:
                last_error = e
                result.retries_attempted = attempt

                if attempt < self._max_retries:
                    delay = min(
                        self._base_delay * (self._backoff_factor ** attempt),
                        self._max_delay,
                    )
                    logger.warning(
                        "REVER[%s]: 尝试%d/%d 失败: %s, 等待%.1fs",
                        context, attempt + 1, self._max_retries, e, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "REVER[%s]: 全部%d次尝试失败: %s",
                        context, self._max_retries + 1, e,
                    )

        # ── Stage 2: EVALUATE — 评估严重性 ──
        result.stage_reached = REVERStage.EVALUATE
        result.error_detail = str(last_error) if last_error else "未知错误"
        result.severity = self._evaluate_severity(last_error)

        # ── Stage 3: VERIFY — 尝试降级恢复 ──
        result.stage_reached = REVERStage.VERIFY
        if fallback and result.severity in (Severity.TRANSIENT, Severity.RECOVERABLE):
            try:
                if asyncio.iscoroutinefunction(fallback):
                    await fallback()
                else:
                    fallback()
                result.recovered = True
                logger.info("REVER[%s]: 降级恢复成功", context)
                self._error_log.append(result)
                return result
            except Exception as e:
                logger.error("REVER[%s]: 降级也失败: %s", context, e)
                result.error_detail += f"; 降级失败: {e}"

        # ── Stage 4: ESCALATE — 升级 ──
        if result.severity in (Severity.DEGRADED, Severity.FATAL):
            result.stage_reached = REVERStage.ESCALATE
            result.escalated = True
            result.user_message = self._build_user_message(result)

        # ── Stage 5: REPORT — 记录 ──
        result.stage_reached = REVERStage.REPORT
        self._error_log.append(result)
        return result

    def _evaluate_severity(self, error: Optional[Exception]) -> Severity:
        """评估错误严重性"""
        if error is None:
            return Severity.TRANSIENT

        error_type = type(error).__name__
        error_msg = str(error).lower()

        # 网络/超时 → 临时
        if any(kw in error_type.lower() for kw in ("timeout", "connection", "network")):
            return Severity.TRANSIENT

        # 权限/资源 → 可恢复
        if any(kw in error_msg for kw in ("permission", "not found", "rate limit")):
            return Severity.RECOVERABLE

        # 数据损坏 → 降级
        if any(kw in error_msg for kw in ("corrupt", "integrity", "constraint")):
            return Severity.DEGRADED

        # 默认 → 致命
        return Severity.FATAL

    def _build_user_message(self, result: REVERResult) -> str:
        """构建用户可读的错误消息"""
        return (
            f"⚠️ 操作失败，已尝试 {result.retries_attempted + 1} 次。\n"
            f"错误: {result.error_detail[:200]}\n"
            f"严重性: {result.severity.name}"
        )

    def get_error_summary(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的错误摘要"""
        return [
            {
                "severity": r.severity.name,
                "retries": r.retries_attempted,
                "recovered": r.recovered,
                "escalated": r.escalated,
                "timestamp": r.timestamp,
            }
            for r in self._error_log[-limit:]
        ]


# ═══════════════════════════════════════════════════════════════
# Orchestrator — 编排层统一入口 (ARC-008)
# ═══════════════════════════════════════════════════════════════

@dataclass
class OrchestrationResult:
    """编排执行结果"""
    answer: str
    exit_reason: str
    review_passed: bool
    rever_result: Optional[REVERResult] = None
    trust_level: str = "CONFIRM"
    elapsed_ms: float = 0.0
    security_events: List[str] = field(default_factory=list)


class Orchestrator:
    """
    编排层统一入口 — 设计稿第4章
    职责: 串联安全审查→执行→REVER保护→输出审查
    """

    def __init__(
        self,
        guardrails: Any,      # GuardrailsEngine
        react_engine: Any,    # ReActEngine
        trust_scores: Dict[str, Any],  # {user_id: TrustScore}
        memory_store: Any,    # MemoryStore
        hybrid_memory: Any = None,     # HybridMemory (v4.0+)
        swarm: Any = None,             # AgentSwarm (v4.0+)
        mirofish_scheduler: Any = None,  # MiroFishScheduler (v4.0+ [MIROFISH-INSPIRED])
        profile_manager: Any = None,   # UserProfileManager (v4.0+ 画像系统)
        user_profiler: Any = None,     # UserProfiler (v4.0+ 实时提取)
        execution_tracker: Any = None,  # ExecutionTracker (v4.0+ 防偷懒)
        anti_compression: Any = None,   # AntiCompressionDetector (v4.0+ 防偷懒)
        completeness_validator: Any = None,  # CompletenessValidator (v4.0+ 防偷懒)
        work_memory: Any = None,        # WorkMemory (v4.0+ 防偷懒)
        swarm_profile_adapter: Any = None,
        memory_profile_adapter: Any = None,
        react_profile_adapter: Any = None,
        guardrails_profile_adapter: Any = None,
        tools_profile_adapter: Any = None,
        rbac: Any = None,               # RBACEngine (v4.0+ 可选权限控制)
        deliberation_engine: Any = None,
        reflexion_node: Any = None,
        hitl_manager: Any = None,
        agent_crew: Any = None,
        state_graph_builder: Any = None,
    ):
        self._guardrails = guardrails
        self._rbac = rbac
        self._react = react_engine
        self._trust_scores = trust_scores
        self._memory = memory_store
        self._hybrid = hybrid_memory
        self._swarm = swarm
        self._mirofish = mirofish_scheduler
        self._profile_mgr = profile_manager
        self._profiler = user_profiler
        self._tracker = execution_tracker
        self._anti_compression = anti_compression
        self._completeness = completeness_validator
        self._work_memory = work_memory
        self._rever = REVEREngine()
        self._profile_adapters: Dict[str, Any] = {}
        self._swarm_profile_adapter = swarm_profile_adapter
        self._memory_profile_adapter = memory_profile_adapter
        self._react_profile_adapter = react_profile_adapter
        self._guardrails_profile_adapter = guardrails_profile_adapter
        self._tools_profile_adapter = tools_profile_adapter
        self._deliberation = deliberation_engine
        self._reflexion = reflexion_node
        self._hitl = hitl_manager
        self._crew = agent_crew
        self._state_graph = state_graph_builder

    def set_profile_adapter(self, name: str, adapter: Any) -> None:
        """动态注册画像适配器"""
        self._profile_adapters[name] = adapter

    def _is_complex_task(self, message: str) -> tuple:
        """
        检测任务复杂度和推荐调度策略

        Returns:
            (is_complex: bool, recommended_strategy: str)
            strategy: "react" | "swarm" | "mirofish" | "crew" | "enhanced"
        """
        import re

        # Enhanced 触发条件：最高复杂度，需要 deliberation + state_graph 编排
        if self._deliberation and self._reflexion and self._state_graph:
            enhanced_indicators = [
                "深度分析", "全面复盘", "系统性.*评估",
                "多轮.*研讨", "专家.*论证", "战略.*规划",
            ]
            if any(re.search(p, message) for p in enhanced_indicators):
                return True, "enhanced"

        # MiroFish 触发条件：多步骤、跨部门、需要深度协作模拟
        mirofish_indicators = [
            "跨部门", "跨团队", "协同", "协调", "多方",
            "报告生成", "综合分析", "全面评估",
            "调研.*撰写", "分析.*报告", "模拟",
            "沙盘", "推演", "预演",
        ]
        if self._mirofish and any(re.search(p, message) for p in mirofish_indicators):
            return True, "mirofish"

        # Crew 触发条件：团队协作、团队任务
        crew_indicators = [
            "团队", "crew", "协作.*团队", "团队.*协作",
            "分工", "组员", "项目组",
        ]
        if self._crew and any(re.search(p, message) for p in crew_indicators):
            return True, "crew"

        # Swarm 触发条件：多 Agent 并行/协作
        swarm_indicators = [
            "同时", "并且", "和", "以及",
            "分析.*生成", "搜索.*总结", "查询.*计算",
            "多步骤", "复杂任务", "协作",
        ]
        if self._swarm and any(re.search(p, message) for p in swarm_indicators):
            return True, "swarm"

        return False, "react"

    async def _execute_core(
        self,
        message: str,
        session_id: str,
        tracker_task_id: Optional[str],
        strategy: str,
        is_complex: bool,
        profile: Any = None,
    ) -> tuple:
        """
        核心执行逻辑 — 策略选择 + REVER执行 + 输出获取
        Returns: (rever_result, react_text)
        """
        # ── 前置: Deliberation 专家研讨 (v4.0+ 深度思考) ──
        deliberation_context = ""
        if is_complex and self._deliberation:
            try:
                logger.info("[Deliberation] 执行专家研讨: %s", message[:80])
                delib_result = await self._deliberation.deliberate(
                    question=message,
                    context="",
                )
                deliberation_context = (
                    f"\n[专家研讨共识] {delib_result.consensus}\n"
                    f"[关键风险] {', '.join(delib_result.risks[:3])}"
                )
                logger.debug("Deliberation 完成: %d 条意见", len(delib_result.opinions))
            except Exception as e:
                logger.warning("Deliberation 研讨失败 (可忽略): %s", e)

        enhanced_message = message + deliberation_context if deliberation_context else message

        if is_complex and strategy == "enhanced" and self._state_graph:
            logger.info("[Enhanced] 启用 StateGraph 编排执行: %s", message[:80])
            rever_result = await self._rever.execute(
                operation=lambda: self._run_enhanced_graph(enhanced_message, session_id, tracker_task_id),
                context=f"Enhanced[{session_id}]",
            )

        elif is_complex and strategy == "mirofish" and self._mirofish:
            logger.info("[MiroFish] 启用群体智能协作预演: %s", message[:80])
            async def _execute_mirofish():
                mf_result = await self._mirofish.run(
                    task=enhanced_message,
                    max_rounds=5,
                )
                if self._tracker and tracker_task_id:
                    from nexusagent.execution.tracker import Evidence, EvidenceType
                    self._tracker.record_evidence(
                        tracker_task_id,
                        Evidence(
                            evidence_id=f"ev_miro_{int(time.time())}",
                            step_id=self._tracker.get_task(tracker_task_id).plan_steps[0].step_id if self._tracker.get_task(tracker_task_id).plan_steps else "step_0",
                            evidence_type=EvidenceType.LLM_OUTPUT,
                            content=str(mf_result.output)[:500],
                        )
                    )
                    is_complete, missing = self._tracker.validate(tracker_task_id)
                    if not is_complete:
                        from nexusagent.execution.tracker import RetryRequiredException
                        raise RetryRequiredException(
                            reason=f"MiroFish 执行不完整，缺失: {missing}",
                            missing_items=missing,
                            task_context=self._tracker.get_task(tracker_task_id),
                        )
                return mf_result.output

            rever_result = await self._rever.execute(
                operation=_execute_mirofish,
                context=f"MiroFish[{session_id}]",
            )

        elif is_complex and strategy == "crew" and self._crew:
            logger.info("检测到团队任务，启用 AgentCrew: %s", message[:80])
            async def _execute_crew():
                crew_result = await self._crew.execute(
                    task=enhanced_message,
                    tenant_id=session_id,
                    mode="parallel",
                    timeout=120.0,
                )
                if self._tracker and tracker_task_id:
                    from nexusagent.execution.tracker import Evidence, EvidenceType
                    self._tracker.record_evidence(
                        tracker_task_id,
                        Evidence(
                            evidence_id=f"ev_crew_{int(time.time())}",
                            step_id=self._tracker.get_task(tracker_task_id).plan_steps[0].step_id if self._tracker.get_task(tracker_task_id).plan_steps else "step_0",
                            evidence_type=EvidenceType.LLM_OUTPUT,
                            content=str(crew_result.output)[:500],
                        )
                    )
                return crew_result.output

            rever_result = await self._rever.execute(
                operation=_execute_crew,
                context=f"Crew[{session_id}]",
            )

        elif is_complex and strategy == "swarm" and self._swarm:
            logger.info("检测到复杂任务，启用 AgentSwarm: %s", message[:80])
            # 画像驱动的策略选择
            swarm_strategy = "handoff"
            if profile and self._swarm_profile_adapter:
                swarm_strategy = self._swarm_profile_adapter.recommend_strategy(profile)
                specialists = self._swarm_profile_adapter.recommend_specialists(profile, message)
                if specialists:
                    logger.info("Swarm specialists: %s", specialists)
            async def _execute_swarm():
                swarm_result = await self._swarm.run(
                    task=enhanced_message,
                    strategy=swarm_strategy,
                    max_turns=5,
                )
                if self._tracker and tracker_task_id:
                    from nexusagent.execution.tracker import Evidence, EvidenceType
                    self._tracker.record_evidence(
                        tracker_task_id,
                        Evidence(
                            evidence_id=f"ev_swarm_{int(time.time())}",
                            step_id=self._tracker.get_task(tracker_task_id).plan_steps[0].step_id if self._tracker.get_task(tracker_task_id).plan_steps else "step_0",
                            evidence_type=EvidenceType.LLM_OUTPUT,
                            content=str(swarm_result.output)[:500],
                        )
                    )
                return swarm_result.output

            rever_result = await self._rever.execute(
                operation=_execute_swarm,
                context=f"Swarm[{session_id}]",
            )
        else:
            task_ctx = self._tracker.get_task(tracker_task_id) if self._tracker and tracker_task_id else None
            # 画像驱动的工具过滤与排序
            tools_override = None
            if profile and self._tools_profile_adapter:
                all_tools = self._react._tools.describe_tools() if hasattr(self._react, "_tools") else []
                if all_tools:
                    filtered = self._tools_profile_adapter.filter_tools(profile, all_tools)
                    tools_override = self._tools_profile_adapter.sort_tools(profile, filtered)
                    logger.debug("ToolRegistryProfileAdapter: %d -> %d tools", len(all_tools), len(tools_override))

            # 画像驱动的 ReAct 预算和提示词调整 (v4.0+ ReActProfileAdapter)
            budget_override = None
            system_prompt_suffix = ""
            if profile and self._react_profile_adapter:
                adjustments = self._react_profile_adapter.apply(profile)
                from nexusagent.execution.react_engine import ReActBudget
                budget_override = ReActBudget(
                    max_iterations=adjustments["max_iterations"],
                    max_time_seconds=adjustments["max_time_seconds"],
                )
                system_prompt_suffix = adjustments.get("system_prompt_suffix", "")
                logger.debug("ReActProfileAdapter: iter=%d, time=%.0fs",
                             budget_override.max_iterations, budget_override.max_time_seconds)

            async def _execute_react():
                react_result = await self._react.run(
                    session_id=session_id,
                    system_prompt=(
                        "你是NexusAgent，一个本地优先的AI助手。"
                        "你可以使用工具来完成任务。请用中文回复。"
                    ),
                    user_message=enhanced_message,
                    task_context=task_ctx,
                    tools_override=tools_override,
                    budget_override=budget_override,
                    system_prompt_suffix=system_prompt_suffix,
                )
                if self._tracker and tracker_task_id:
                    from nexusagent.execution.tracker import Evidence, EvidenceType
                    for tc in react_result.tools_called:
                        self._tracker.record_evidence(
                            tracker_task_id,
                            Evidence(
                                evidence_id=f"ev_tool_{tc.call_id}",
                                step_id=self._tracker.get_task(tracker_task_id).plan_steps[0].step_id if self._tracker.get_task(tracker_task_id).plan_steps else "step_0",
                                evidence_type=EvidenceType.TOOL_CALL,
                                content=f"{tc.tool_name}: {str(tc.arguments)[:200]}",
                            )
                        )
                    self._tracker.record_evidence(
                        tracker_task_id,
                        Evidence(
                            evidence_id=f"ev_output_{int(time.time())}",
                            step_id=self._tracker.get_task(tracker_task_id).plan_steps[-1].step_id if self._tracker.get_task(tracker_task_id).plan_steps else "step_0",
                            evidence_type=EvidenceType.LLM_OUTPUT,
                            content=str(react_result.answer)[:500],
                        )
                    )
                    is_complete, missing = self._tracker.validate(tracker_task_id)
                    if not is_complete:
                        from nexusagent.execution.tracker import RetryRequiredException
                        raise RetryRequiredException(
                            reason=f"任务执行不完整，缺失步骤: {missing}",
                            missing_items=missing,
                            task_context=self._tracker.get_task(tracker_task_id),
                        )
                return react_result

            rever_result = await self._rever.execute(
                operation=_execute_react,
                context=f"ReAct[{session_id}]",
            )

        # ── 后置: Reflexion 自我反思 (v4.0+ 失败恢复) ──
        if not rever_result.recovered and self._reflexion:
            try:
                logger.info("[Reflexion] 执行失败，启动自我反思: %s", rever_result.error_detail[:80])
                report = await self._reflexion.reflect(
                    error_node=strategy,
                    error=Exception(rever_result.error_detail or "执行失败"),
                    state={"task": message, "strategy": strategy},
                    history=[{"node": strategy, "iteration": rever_result.retries_attempted}],
                )
                logger.info(
                    "[Reflexion] 分析完成: root_cause=%s, retry=%s, strategy=%s",
                    report.root_cause, report.should_retry, report.retry_strategy,
                )
                # 如果建议重试，且还没重试过 reflexion 恢复，再试一次 ReAct
                if report.should_retry and report.retry_strategy in ("retry_same", "retry_alternative"):
                    logger.info("[Reflexion] 触发恢复重试")
                    async def _execute_react_recovery():
                        recovery_prompt = (
                            f"之前执行失败，原因: {report.root_cause}\n"
                            f"建议修复: {report.suggested_fix}\n"
                            f"请重新尝试完成以下任务。"
                        )
                        react_result = await self._react.run(
                            session_id=session_id,
                            system_prompt=recovery_prompt,
                            user_message=enhanced_message,
                            task_context=task_ctx,
                        )
                        return react_result

                    rever_result = await self._rever.execute(
                        operation=_execute_react_recovery,
                        context=f"ReflexionRecovery[{session_id}]",
                    )
            except Exception as e:
                logger.warning("Reflexion 反思失败 (可忽略): %s", e)

        react_text = ""
        if rever_result.recovered:
            captured = rever_result.captured_output
            if captured is not None:
                react_text = getattr(captured, 'answer', '') or str(captured)
            else:
                react_text = "处理完成"
        else:
            react_text = rever_result.user_message or "处理出错"

        return rever_result, react_text

    async def _run_enhanced_graph(self, message: str, session_id: str, tracker_task_id: Optional[str]) -> str:
        """使用 StateGraph 编排 deliberation -> execute -> reflexion 增强流程"""
        from nexusagent.execution.state_graph import StateGraph, END, RunConfig

        g = StateGraph()

        async def deliberation_node(state):
            if not self._deliberation:
                return {}
            result = await self._deliberation.deliberate(
                question=state.get("task", message),
                context=state.get("context", ""),
            )
            return {
                "deliberation": result,
                "consensus": result.consensus,
                "risks": result.risks,
            }

        task_ctx = self._tracker.get_task(tracker_task_id) if self._tracker and tracker_task_id else None
        async def execute_node(state):
            # 使用 ReAct 执行（增强版，附带研讨共识）
            consensus = state.get("consensus", "")
            task = state.get("task", message)
            if consensus:
                task = f"{task}\n[专家共识] {consensus}"
            react_result = await self._react.run(
                session_id=session_id,
                system_prompt="你是NexusAgent，一个本地优先的AI助手。请用中文回复。",
                user_message=task,
                task_context=task_ctx,
            )
            return {"answer": react_result.answer, "react_result": react_result}

        async def reflexion_node(state):
            error = state.get("__error__", {})
            if not error or not self._reflexion:
                return {}
            report = await self._reflexion.reflect(
                error_node=error.get("node", "execute"),
                error=Exception(error.get("error", "未知错误")),
                state=state,
                history=state.get("__history__", []),
            )
            return {
                "__reflection__": {
                    "root_cause": report.root_cause,
                    "should_retry": report.should_retry,
                    "retry_strategy": report.retry_strategy,
                },
                "should_retry": report.should_retry,
            }

        async def route_after_execute(state):
            if "__error__" in state:
                return "reflexion"
            return END

        async def route_after_reflexion(state):
            if state.get("should_retry"):
                return "execute"
            return END

        g.add_node("deliberation", deliberation_node)
        g.add_node("execute", execute_node)
        g.add_node("reflexion", reflexion_node)
        g.set_entry_point("deliberation")
        g.add_edge("deliberation", "execute")
        g.add_conditional_edges("execute", route_after_execute, {"reflexion": "reflexion", END: END})
        g.add_conditional_edges("reflexion", route_after_reflexion, {"execute": "execute", END: END})

        compiled = g.compile()
        result_state = await compiled.ainvoke(
            {"task": message, "context": ""},
            config=RunConfig(thread_id=session_id, max_iterations=10),
        )
        return result_state.get("answer", "")


    @trace_span("nexus.orchestrator.process")
    async def process(
        self,
        user_id: str,
        message: str,
        session_id: str = "",
    ) -> OrchestrationResult:
        """
        完整编排流程

        1. 输入安全审查 (Guardrails双层验证 Layer 1)
        2. 信任积分检查
        3. REVER保护执行 (ReAct循环 / Swarm / MiroFish)
        4. 输出安全审查 (Guardrails双层验证 Layer 2)
        5. 防偷懒验证 (AntiCompression + Completeness)
        6. 记忆持久化
        """
        start = time.monotonic()
        security_events: List[str] = []
        result = OrchestrationResult(answer="", exit_reason="unknown", review_passed=False)

        # ── 0. 画像实时提取 (v4.0+ 用户画像系统) ──
        extracted_signals = []
        if self._profiler and self._profile_mgr:
            try:
                extracted_signals = self._profiler.process_message(
                    user_id=user_id,
                    message=message,
                )
                for sig in extracted_signals:
                    await self._profile_mgr.add_pending_trait(
                        user_id=user_id,
                        category=sig.category,
                        key=sig.key,
                        value=sig.value,
                        confidence=sig.confidence,
                        source=sig.source,
                    )
                if extracted_signals:
                    logger.debug("Orchestrator: %s 提取 %d 条画像信号", user_id, len(extracted_signals))
            except Exception as e:
                logger.warning("画像提取失败 (可忽略): %s", e)

        # ── 1. 输入审查 ──
        input_review = self._guardrails.review(message)
        if input_review.is_denied:
            result.answer = f"[安全审查拒绝] {input_review.reason}"
            result.exit_reason = "security_denied"
            result.elapsed_ms = (time.monotonic() - start) * 1000
            security_events.append(f"DENT: {input_review.reason}")
            result.security_events = security_events
            return result

        if input_review.requires_user_approval:
            security_events.append(f"RED_LIGHT: {input_review.reason}")

            # ── HITL 人工介入 (v4.0+) ──
            # 尝试通过 HITL 获取人工确认，但始终 fallback 到原有 approval 消息，
            # 保持 API 行为不变，避免破坏依赖 requires_approval 响应的调用方。
            if self._hitl:
                try:
                    from nexusagent.execution.hitl import HITLRequest
                    req = HITLRequest(
                        thread_id=session_id,
                        node_name="guardrails_input",
                        question=f"安全审查需要确认: {input_review.reason}",
                        context={"message": message, "reason": input_review.reason},
                        timeout_seconds=0.05,  # 极短超时，纯 fire-and-forget
                    )
                    resp = await self._hitl.request_approval(req)
                    if resp.approved:
                        logger.info("HITL 批准了安全审查请求: %s", session_id)
                        result.review_passed = True
                except Exception as e:
                    logger.debug("HITL 请求失败 (可忽略): %s", e)

            if not result.review_passed:
                result.answer = (
                    f"[安全审查] 操作需要确认。\n"
                    f"原因: {input_review.reason}\n"
                    f"请确认是否继续执行。"
                )
                result.exit_reason = "requires_approval"
                result.elapsed_ms = (time.monotonic() - start) * 1000
                result.security_events = security_events
                return result

        result.review_passed = True

        # ── 2. 信任积分 ──
        trust = self._trust_scores.get(user_id)
        if trust:
            prompt_level = trust.get_prompt_level()
            result.trust_level = prompt_level.name if hasattr(prompt_level, 'name') else str(prompt_level)

        # ── 2.5 RBAC 权限检查（v4.0+ 可选，默认不启用）──
        if hasattr(self, '_rbac') and self._rbac and self._rbac.is_enabled():
            allowed = self._rbac.can_invoke(session_id, user_id, "*")
            if not allowed:
                result.answer = "[权限检查] 您没有权限执行此操作。"
                result.exit_reason = "rbac_denied"
                result.elapsed_ms = (time.monotonic() - start) * 1000
                return result

        # ── 3. REVER保护执行 ──
        # v4.0+: 智能调度策略选择（画像驱动）
        profile = None
        if self._profile_mgr:
            try:
                profile = await self._profile_mgr.load(user_id)
            except Exception as e:
                logger.warning("用户画像加载失败: %s", e)

        is_complex, strategy = self._is_complex_task(message)

        # 画像策略覆盖：如果用户有明确的工作流偏好
        if profile and hasattr(profile.behavioral, 'work_habits'):
            preferred_strategy = profile.behavioral.work_habits.get('preferred_strategy', '')
            if preferred_strategy in ('react', 'swarm', 'mirofish'):
                strategy = preferred_strategy
                is_complex = (strategy != 'react')
                logger.info("画像策略覆盖: %s → %s", user_id, strategy)

        # 画像驱动的编排策略适配
        if profile and self._profile_adapters.get('orchestrator'):
            orch_adapter = self._profile_adapters['orchestrator']
            recommended = orch_adapter.recommend_strategy(profile, message)
            if recommended != strategy:
                strategy = recommended
                is_complex = (strategy != 'react')
                logger.info("画像适配器策略推荐: %s → %s", user_id, strategy)
            # 预算调整
            if hasattr(self._react, '_budget'):
                orch_adapter.apply_budget_adjustments(profile, self._react._budget)

        # 画像驱动的安全审查适配
        if profile and self._guardrails_profile_adapter and hasattr(self._guardrails, 'ml_threshold'):
            adjusted_threshold = self._guardrails_profile_adapter.get_adjusted_ml_threshold(profile)
            self._guardrails.ml_threshold = adjusted_threshold
            logger.debug("画像适配器调整 Guardrails 阈值: %.2f", adjusted_threshold)

        # ── 3.5 执行追踪器：创建任务和计划 (v4.0+ 防偷懒) ──
        tracker_task_id = None
        if self._tracker:
            tracker_task_id = f"task_{session_id}_{int(time.time())}"
            self._tracker.create_task(tracker_task_id, message)
            self._tracker.auto_plan_from_message(tracker_task_id)
            logger.debug("ExecutionTracker: 任务 %s 已创建，计划步骤: %d",
                         tracker_task_id,
                         len(self._tracker.get_task(tracker_task_id).plan_steps))

        # ── 3.6 Anti-Laziness 重试循环 (v4.0+ 防偷懒) ──
        current_message = message
        rever_result = None
        react_text = ""
        max_quality_retries = 2

        # 画像驱动的记忆上下文注入 (v4.0+ MemoryProfileAdapter)
        if profile and self._memory_profile_adapter and self._hybrid:
            try:
                enhanced_query = self._memory_profile_adapter.enhance_query(profile, message)
                related = await self._hybrid.retrieve(enhanced_query, session_id=session_id)
                if related:
                    memory_context = "\n".join([r.content for r in related[:3]])
                    current_message = f"[相关记忆]\n{memory_context}\n\n[用户消息]\n{message}"
                    logger.debug("MemoryProfileAdapter: 注入 %d 条相关记忆", len(related))
            except Exception as e:
                logger.warning("记忆上下文注入失败 (可忽略): %s", e)

        for quality_attempt in range(max_quality_retries + 1):
            rever_result, react_text = await self._execute_core(
                message=current_message,
                session_id=session_id,
                tracker_task_id=tracker_task_id,
                strategy=strategy,
                is_complex=is_complex,
                profile=profile,
            )

            # ── 4. 输出审查 (ARC-039) ──
            output_review = self._guardrails.review_output(react_text)
            if output_review.is_denied:
                result.answer = "[输出审查拒绝] 响应包含不安全内容"
                result.exit_reason = "output_denied"
                security_events.append(f"OUTPUT_DENT: {output_review.reason}")
                result.elapsed_ms = (time.monotonic() - start) * 1000
                result.security_events = security_events
                return result

            # ── 4.5 防偷懒验证 (v4.0+) ──
            validation_issues: List[str] = []
            task_ctx = self._tracker.get_task(tracker_task_id) if self._tracker and tracker_task_id else None

            # AntiCompression 检测
            if self._anti_compression:
                ac_summary = self._anti_compression.get_summary(react_text)
                if ac_summary["is_compressed"]:
                    validation_issues.append(
                        f"Output appears compressed/lazy: {ac_summary['by_pattern']}"
                    )

            # Completeness 验证
            if self._completeness and task_ctx:
                comp_summary = self._completeness.get_summary(task_ctx, react_text)
                if not comp_summary["is_complete"]:
                    validation_issues.extend([
                        f"Completeness: {k} ({v} issues)"
                        for k, v in comp_summary["issues_by_type"].items()
                    ])

            # 保存到 WorkMemory
            if self._work_memory and task_ctx:
                self._work_memory.save_snapshot(
                    task_id=tracker_task_id,
                    task_context=task_ctx,
                    output=react_text,
                    validation_issues=validation_issues,
                    retry_count=quality_attempt,
                )

            if not validation_issues:
                break  # 验证通过

            if quality_attempt < max_quality_retries:
                # 构造增强提示进行重试
                memory_prompt = ""
                if self._work_memory:
                    memory_prompt = self._work_memory.get_memory_for_retry(tracker_task_id)

                current_message = (
                    f"ORIGINAL TASK: {message}\n\n"
                    f"{memory_prompt}\n\n"
                    f"INSTRUCTION: Fix ALL the above issues. "
                    f"Provide a complete, thorough response. "
                    f"Do NOT skip steps, summarize prematurely, or use placeholders."
                )
                logger.warning(
                    "Anti-Laziness: 质量验证失败 (尝试 %d/%d)，触发重试",
                    quality_attempt + 1, max_quality_retries + 1,
                )
            else:
                logger.error(
                    "Anti-Laziness: 质量验证在 %d 次尝试后仍失败，使用最后输出",
                    max_quality_retries + 1,
                )

        result.rever_result = rever_result
        result.answer = react_text
        result.exit_reason = "normal" if (rever_result and rever_result.recovered) else "rever_failed"
        result.elapsed_ms = (time.monotonic() - start) * 1000
        result.security_events = security_events

        # ── 5. 记忆持久化 ──
        try:
            if self._hybrid:
                await self._hybrid.add_recall(
                    content=f"用户: {message}\n助手: {result.answer[:500]}",
                    session_id=session_id,
                    importance=0.6,
                )
            else:
                from nexusagent.memory.store import MemoryEntry
                entry = MemoryEntry(
                    session_id=session_id,
                    memory_type="episodic",
                    content=f"用户: {message}\n助手: {result.answer[:500]}",
                )
                await self._memory.save(entry)
        except Exception as e:
            logger.warning("记忆保存失败: %s", e)

        # ── 6. 更新信任积分 ──
        if trust and rever_result:
            if rever_result.recovered:
                trust.record_success()
            else:
                trust.record_failure(severity=0.8 if rever_result.escalated else 0.3)

        # ── 7. 画像动态属性更新 (v4.0+) ──
        if profile and self._profile_mgr:
            try:
                profile.dynamic.last_activity = time.time()
                profile.dynamic.recent_topics = ([message[:30]] + profile.dynamic.recent_topics)[:10]
                await self._profile_mgr.save(profile)
            except Exception as e:
                logger.debug("画像动态更新失败 (可忽略): %s", e)

        return result
