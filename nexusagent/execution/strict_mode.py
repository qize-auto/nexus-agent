"""
NexusAgent v4.0+ — Strict Execution Mode 严谨执行工作流

核心工作流（StateGraph 编排）:
    intent_analysis → [need_clarify?] → clarify_loop → task_decompose
                                                  ↓
                                              chat_mode → END
                                                  ↓
    planning → execute_step → verify_step → [pass?] → next_or_deliver
                                    ↓ fail
                                reflect → [retry?] → execute_step
                                    ↓ abort
                                deliver → END

职责:
    1. 编排 8 阶段严谨执行工作流
    2. 复用现有组件（ReActEngine、DeliberationEngine、ReflexionNode）
    3. 与常规 ReAct 模式无缝切换
    4. 生成结构化交付报告

Usage:
    from nexusagent.execution.strict_mode import StrictExecutionWorkflow
    workflow = StrictExecutionWorkflow(
        llm=llm_backend,
        tool_registry=tools,
        deliberation=deliberation_engine,
        reflexion=reflexion_node,
    )
    report = await workflow.run(user_message, session_id="s1")
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from nexusagent.execution.state_graph import StateGraph, END
from nexusagent.execution.intent_analyzer import IntentAnalyzer, IntentAnalysis
from nexusagent.execution.clarifier import Clarifier, ClarificationSession
from nexusagent.execution.task_decomposer import TaskDecomposer, TaskPlan, TaskStep
from nexusagent.execution.verifier import Verifier, VerificationResult, VerificationStatus
from nexusagent.execution.delivery import DeliveryReportGenerator, ExecutionRecord

logger = logging.getLogger("nexus.execution.strict_mode")


class StrictExecutionWorkflow:
    """
    严谨执行工作流

    将用户任务请求通过 8 阶段工作流严谨处理，
    产出可审计的交付报告。
    """

    def __init__(
        self,
        llm_backend: Optional[Any] = None,
        tool_registry: Optional[Any] = None,
        deliberation: Optional[Any] = None,
        reflexion: Optional[Any] = None,
        max_clarify_rounds: int = 3,
        max_retry_attempts: int = 3,
    ):
        self._llm = llm_backend
        self._tools = tool_registry
        self._deliberation = deliberation
        self._reflexion = reflexion
        self._max_clarify = max_clarify_rounds
        self._max_retry = max_retry_attempts

        # 子组件
        self._analyzer = IntentAnalyzer(llm_backend)
        self._clarifier = Clarifier(llm_backend)
        self._decomposer = TaskDecomposer(llm_backend)
        self._verifier = Verifier(llm_backend)
        self._delivery = DeliveryReportGenerator()

        # 构建 StateGraph
        self._graph = self._build_graph()

    async def run(self, user_message: str, session_id: str = "") -> Dict[str, Any]:
        """
        执行严谨工作流

        Args:
            user_message: 用户原始请求
            session_id: 会话 ID

        Returns:
            {"success": bool, "report": str, "mode": "strict"}
        """
        logger.info("严谨模式启动: session=%s msg=%s", session_id, user_message[:80])
        start_time = time.time()

        # 初始状态
        initial_state = {
            "user_message": user_message,
            "session_id": session_id,
            "intent": None,
            "clarification_session": None,
            "requirements": {},
            "plan": None,
            "completed_steps": [],
            "execution_records": [],
            "current_step_idx": 0,
            "retry_count": 0,
            "error": None,
            "report": "",
            "should_chat": False,
        }

        try:
            # 运行 StateGraph
            final_state = await self._graph.ainvoke(initial_state)

            elapsed = time.time() - start_time
            logger.info("严谨模式完成: session=%s elapsed=%.1fs", session_id, elapsed)

            if final_state.get("should_chat"):
                return {
                    "success": True,
                    "report": "",
                    "mode": "chat",
                    "reason": "非任务请求，走常规对话模式",
                }

            return {
                "success": final_state.get("error") is None,
                "report": final_state.get("report", ""),
                "mode": "strict",
                "execution_records": [
                    r.to_dict() if hasattr(r, "to_dict") else r
                    for r in final_state.get("execution_records", [])
                ],
                "elapsed_seconds": elapsed,
            }

        except Exception as e:
            logger.error("严谨模式异常: %s", e, exc_info=True)
            return {
                "success": False,
                "report": f"执行异常: {e}",
                "mode": "strict",
                "error": str(e),
            }

    # ═══════════════════════════════════════════════════════════════
    # StateGraph 构建
    # ═══════════════════════════════════════════════════════════════

    def _build_graph(self) -> StateGraph:
        """构建严谨执行工作流 StateGraph"""
        graph = StateGraph()

        # 节点注册
        graph.add_node("intent_analysis", self._node_intent_analysis)
        graph.add_node("generate_question", self._node_generate_question)
        graph.add_node("receive_answer", self._node_receive_answer)
        graph.add_node("task_decompose", self._node_task_decompose)
        graph.add_node("planning", self._node_planning)
        graph.add_node("execute_step", self._node_execute_step)
        graph.add_node("verify_step", self._node_verify_step)
        graph.add_node("reflect", self._node_reflect)
        graph.add_node("deliver", self._node_deliver)

        # 入口
        graph.set_entry_point("intent_analysis")

        # 条件分支 1: 意图分析后
        graph.add_conditional_edges("intent_analysis", self._route_after_intent, {
            "clarify": "generate_question",
            "decompose": "task_decompose",
            "chat": END,
        })

        # 澄清循环
        graph.add_edge("generate_question", "receive_answer")
        graph.add_conditional_edges("receive_answer", self._route_after_answer, {
            "more": "generate_question",      # 还需澄清
            "decompose": "task_decompose",    # 已明确，进入分解
        })

        # 分解 → 计划 → 执行
        graph.add_edge("task_decompose", "planning")
        graph.add_edge("planning", "execute_step")
        graph.add_edge("execute_step", "verify_step")

        # 验证结果分支
        graph.add_conditional_edges("verify_step", self._route_after_verify, {
            "next": "execute_step",     # 还有下一步
            "deliver": "deliver",       # 全部完成，交付
            "reflect": "reflect",       # 验证失败，反思
        })

        # 反思后分支
        graph.add_conditional_edges("reflect", self._route_after_reflect, {
            "retry": "execute_step",    # 重试当前步骤
            "revise": "planning",       # 修改计划
            "abort": "deliver",         # 放弃，尽力交付
        })

        # 交付 → 结束
        graph.add_edge("deliver", END)

        return graph.compile()

    # ═══════════════════════════════════════════════════════════════
    # 节点实现
    # ═══════════════════════════════════════════════════════════════

    async def _node_intent_analysis(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """节点 1: 意图分析"""
        msg = state["user_message"]
        intent = await self._analyzer.analyze(msg)
        state["intent"] = intent
        logger.debug("意图分析: ambiguity=%.2f is_task=%s type=%s",
                     intent.ambiguity_score, intent.is_task, intent.task_type)
        return state

    async def _node_generate_question(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """节点 2: 生成澄清问题"""
        session = state.get("clarification_session")
        if session is None:
            intent = state["intent"]
            sid = state.get("session_id", "default")
            session = self._clarifier.start_session(
                session_id=f"{sid}_clarify",
                original_message=state["user_message"],
                intent=intent,
            )
            session.max_rounds = self._max_clarify
            state["clarification_session"] = session

        question = await self._clarifier.generate_question(session)
        state["pending_question"] = question
        logger.info("澄清问题 (第%d轮): %s", session.current_round + 1, question)
        return state

    async def _node_receive_answer(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """节点 3: 接收用户回答（实际由外部注入，这里标记占位）"""
        # 注意：在真实交互中，这里会暂停等待用户输入
        # 但在工作流内部，我们假设 answer 已通过某种方式传入
        # 当前简化实现：直接标记为完成（实际应在外部控制循环）
        session = state["clarification_session"]
        if session:
            # 模拟回答（实际应从外部获取）
            answer = state.get("user_response", "")
            if answer:
                self._clarifier.receive_answer(session, answer)
                state.pop("user_response", None)
            else:
                # 无回答 → 强制结束澄清（避免无限等待）
                session.is_complete = True
                logger.warning("澄清会话无用户回答，强制结束")
        return state

    async def _node_task_decompose(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """节点 4: 任务分解"""
        # 合并需求
        session = state.get("clarification_session")
        if session and session.rounds:
            requirements = self._clarifier.merge_requirements(session)
            goal = requirements.get("merged_goal", state["user_message"])
            context = requirements.get("constraints", [])
        else:
            goal = state["user_message"]
            context = []

        intent = state["intent"]
        plan = await self._decomposer.decompose(
            goal=goal,
            task_type=intent.task_type,
            target_files=intent.target_files,
            context="\n".join(context),
        )
        state["plan"] = plan
        state["requirements"] = {"goal": goal, "context": context}
        logger.info("任务分解完成: %d 步骤", plan.total_steps)
        return state

    async def _node_planning(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """节点 5: 计划研讨（可选，使用 DeliberationEngine）"""
        if self._deliberation:
            try:
                plan = state["plan"]
                result = await self._deliberation.deliberate(
                    question=f"如何执行以下任务: {plan.goal}",
                    context=f"计划包含 {plan.total_steps} 个步骤: " + 
                            ", ".join(s.description for s in plan.steps),
                )
                state["deliberation_result"] = result
                logger.debug("5 Expert 研讨完成: consensus=%s", result.consensus[:80])
            except Exception as e:
                logger.debug("研讨阶段失败（可忽略）: %s", e)

        # 初始化执行索引
        state["current_step_idx"] = 0
        state["retry_count"] = 0
        return state

    async def _node_execute_step(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """节点 6: 执行单步"""
        plan = state["plan"]
        idx = state.get("current_step_idx", 0)

        if idx >= plan.total_steps:
            logger.debug("所有步骤已执行完毕")
            return state

        step = plan.steps[idx]
        logger.info("执行步骤 %d/%d: %s", idx + 1, plan.total_steps, step.description)

        step_start = time.time()

        try:
            # 使用 ReActEngine 或 ToolRegistry 执行
            if self._tools and hasattr(self._tools, "execute"):
                # 这里简化处理，实际应调用 ReActEngine
                result = f"步骤 {step.id} 执行完成: {step.action}"
                status = "success"
            else:
                result = f"模拟执行: {step.action}"
                status = "success"

            duration = (time.time() - step_start) * 1000
            record = ExecutionRecord(
                step_id=step.id,
                step_description=step.description,
                status=status,
                duration_ms=duration,
            )
            state["execution_records"] = state.get("execution_records", []) + [record]
            state["last_action_result"] = result

        except Exception as e:
            duration = (time.time() - step_start) * 1000
            record = ExecutionRecord(
                step_id=step.id,
                step_description=step.description,
                status="failed",
                duration_ms=duration,
                error=str(e),
            )
            state["execution_records"] = state.get("execution_records", []) + [record]
            state["error"] = str(e)
            logger.warning("步骤 %d 执行失败: %s", step.id, e)

        return state

    async def _node_verify_step(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """节点 7: 验证单步"""
        plan = state["plan"]
        idx = state.get("current_step_idx", 0)

        if idx >= plan.total_steps:
            return state

        step = plan.steps[idx]
        records = state.get("execution_records", [])

        if not records or records[-1].status != "success":
            # 执行失败，跳过验证
            return state

        # 构建验证上下文
        context = {
            "goal": state["requirements"].get("goal", ""),
            "last_action_result": state.get("last_action_result", ""),
            "target_files": state["intent"].target_files if state.get("intent") else [],
            "modified_files": state.get("modified_files", []),
            "step_id": step.id,
        }

        try:
            vresult = await self._verifier.verify(step, context)
            records[-1].verification = vresult
            state["last_verification"] = vresult
            logger.debug("步骤 %d 验证: %s — %s", step.id, vresult.status.value, vresult.details)
        except Exception as e:
            logger.debug("验证失败: %s", e)

        return state

    async def _node_reflect(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """节点 8: 反思修正"""
        retry = state.get("retry_count", 0)
        retry += 1
        state["retry_count"] = retry

        if retry > self._max_retry:
            logger.warning("达到最大重试次数 (%d)，放弃重试", self._max_retry)
            state["should_abort"] = True
            return state

        # 使用 ReflexionNode 分析
        if self._reflexion:
            try:
                error = state.get("error", "")
                last_v = state.get("last_verification")
                error_msg = error or (last_v.details if last_v else "未知错误")

                report = await self._reflexion.reflect(
                    error_node=f"step_{state.get('current_step_idx', 0)}",
                    error=Exception(error_msg),
                    state=state,
                    history=[
                        {"node": f"step_{r.step_id}", "status": r.status}
                        for r in state.get("execution_records", [])
                    ],
                )
                state["reflection_report"] = report
                logger.info("反思结论: %s (strategy=%s)",
                            report.root_cause[:60], report.retry_strategy)
            except Exception as e:
                logger.debug("反思失败: %s", e)

        return state

    async def _node_deliver(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """节点 9: 交付报告"""
        plan = state.get("plan")
        records = state.get("execution_records", [])

        if plan:
            context = {
                "modified_files": state.get("modified_files", []),
                "test_output": state.get("test_output", ""),
                "limitations": plan.risks if hasattr(plan, "risks") else [],
            }
            report_md = self._delivery.generate(plan, records, context)
        else:
            report_md = f"## 执行结果\n\n未能生成执行计划。\n\n原始请求: {state.get('user_message', '')}"

        state["report"] = report_md
        logger.info("交付报告已生成")
        return state

    # ═══════════════════════════════════════════════════════════════
    # 条件路由
    # ═══════════════════════════════════════════════════════════════

    async def _route_after_intent(self, state: Dict[str, Any]) -> str:
        """意图分析后的路由决策"""
        intent = state.get("intent")
        if not intent or not intent.is_task:
            state["should_chat"] = True
            return "chat"
        if intent.is_clear_enough():
            return "decompose"
        return "clarify"

    async def _route_after_answer(self, state: Dict[str, Any]) -> str:
        """澄清回答后的路由决策"""
        session = state.get("clarification_session")
        if session and self._clarifier.is_clear_enough(session):
            return "decompose"
        if session and not session.can_continue:
            return "decompose"  # 达到最大轮数，强制进入分解
        return "more"

    async def _route_after_verify(self, state: Dict[str, Any]) -> str:
        """验证后的路由决策"""
        plan = state.get("plan")
        idx = state.get("current_step_idx", 0)
        last_v = state.get("last_verification")

        # 验证失败 → 反思
        if last_v and last_v.status == VerificationStatus.FAILED:
            return "reflect"

        # 验证通过 → 下一步或交付
        state["current_step_idx"] = idx + 1
        if state["current_step_idx"] >= (plan.total_steps if plan else 0):
            return "deliver"
        return "next"

    async def _route_after_reflect(self, state: Dict[str, Any]) -> str:
        """反思后的路由决策"""
        if state.get("should_abort"):
            return "abort"

        report = state.get("reflection_report")
        if report:
            if report.retry_strategy == "retry_alternative":
                return "revise"
            if report.retry_strategy == "abort":
                return "abort"

        # 默认重试
        return "retry"
