"""
Tests for StrictExecutionWorkflow — 严谨执行工作流
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from nexusagent.execution.strict_mode import StrictExecutionWorkflow
from nexusagent.execution.intent_analyzer import IntentAnalysis


class TestStrictExecutionWorkflow:
    """严谨执行工作流测试集"""

    @pytest.fixture
    def mock_llm(self):
        """Mock LLM 后端"""
        return MagicMock()

    @pytest.fixture
    def mock_tools(self):
        """Mock 工具注册表"""
        return MagicMock()

    @pytest.fixture
    def mock_deliberation(self):
        """Mock 研讨引擎"""
        d = AsyncMock()
        d.deliberate = AsyncMock(return_value=MagicMock(
            consensus="建议使用异步方案",
            confidence=0.9,
        ))
        return d

    @pytest.fixture
    def mock_reflexion(self):
        """Mock 反思节点"""
        r = AsyncMock()
        r.reflect = AsyncMock(return_value=MagicMock(
            root_cause="网络超时",
            retry_strategy="retry_same",
        ))
        return r

    @pytest.fixture
    def workflow(self, mock_llm, mock_tools, mock_deliberation, mock_reflexion):
        """构建工作流实例"""
        return StrictExecutionWorkflow(
            llm_backend=mock_llm,
            tool_registry=mock_tools,
            deliberation=mock_deliberation,
            reflexion=mock_reflexion,
            max_clarify_rounds=2,
            max_retry_attempts=2,
        )

    @pytest.mark.asyncio
    async def test_run_task_request(self, workflow):
        """任务请求应走严谨模式并生成报告"""
        result = await workflow.run("帮我写一个Python函数", session_id="test1")
        assert isinstance(result, dict)
        assert result["mode"] == "strict"
        assert "report" in result
        assert result.get("success") is not None

    @pytest.mark.asyncio
    async def test_run_chat_request(self, workflow):
        """聊天请求应回退到对话模式"""
        result = await workflow.run("你好", session_id="test2")
        assert result["mode"] == "chat"

    @pytest.mark.asyncio
    async def test_run_weather_request(self, workflow):
        """天气询问应回退到对话模式"""
        result = await workflow.run("今天天气怎么样？", session_id="test3")
        assert result["mode"] == "chat"

    @pytest.mark.asyncio
    async def test_run_returns_report(self, workflow):
        """任务请求应返回 Markdown 报告"""
        result = await workflow.run("实现一个用户登录功能", session_id="test4")
        if result["mode"] == "strict":
            assert isinstance(result["report"], str)
            assert len(result["report"]) > 0

    @pytest.mark.asyncio
    async def test_run_with_empty_message(self, workflow):
        """空消息处理"""
        result = await workflow.run("", session_id="test5")
        assert result["mode"] == "chat"

    @pytest.mark.asyncio
    async def test_run_elapsed_time(self, workflow):
        """应记录执行耗时"""
        result = await workflow.run("帮我写代码", session_id="test6")
        if result["mode"] == "strict":
            assert "elapsed_seconds" in result
            assert result["elapsed_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_run_execution_records(self, workflow):
        """应包含执行记录"""
        result = await workflow.run("实现功能", session_id="test7")
        if result["mode"] == "strict":
            assert "execution_records" in result
            assert isinstance(result["execution_records"], list)

    @pytest.mark.asyncio
    async def test_run_multiple_times(self, workflow):
        """多次运行应独立"""
        r1 = await workflow.run("任务A", session_id="test8")
        r2 = await workflow.run("任务B", session_id="test9")
        assert r1["mode"] == "strict"
        assert r2["mode"] == "strict"

    @pytest.mark.asyncio
    async def test_graph_compiles(self, workflow):
        """StateGraph 应成功编译"""
        assert workflow._graph is not None

    @pytest.mark.asyncio
    async def test_route_after_intent_chat(self, workflow):
        """意图分析后路由: 聊天 → END"""
        state = {"intent": IntentAnalysis(is_task=False, task_type="unknown", confidence=0.1)}
        route = await workflow._route_after_intent(state)
        assert route == "chat"
        assert state["should_chat"] is True

    @pytest.mark.asyncio
    async def test_route_after_intent_task_clear(self, workflow):
        """意图分析后路由: 明确任务 → 分解"""
        state = {"intent": IntentAnalysis(is_task=True, task_type="coding", confidence=0.95, ambiguity_score=0.1)}
        route = await workflow._route_after_intent(state)
        assert route == "decompose"

    @pytest.mark.asyncio
    async def test_route_after_intent_task_unclear(self, workflow):
        """意图分析后路由: 模糊任务 → 澄清"""
        state = {"intent": IntentAnalysis(is_task=True, task_type="coding", confidence=0.6, ambiguity_score=0.8)}
        route = await workflow._route_after_intent(state)
        assert route == "clarify"

    @pytest.mark.asyncio
    async def test_route_after_answer_continue(self, workflow):
        """澄清后路由: 还需澄清 → 继续问"""
        from nexusagent.execution.clarifier import ClarificationSession
        session = ClarificationSession(
            "s1", "msg",
            IntentAnalysis(is_task=True, task_type="coding", confidence=0.6, ambiguity_score=0.5, missing_info=["目标文件路径"])
        )
        session.is_complete = False
        session.max_rounds = 3
        state = {"clarification_session": session}
        route = await workflow._route_after_answer(state)
        assert route == "more"

    @pytest.mark.asyncio
    async def test_route_after_answer_done(self, workflow):
        """澄清后路由: 已明确 → 分解"""
        from nexusagent.execution.clarifier import ClarificationSession
        session = ClarificationSession(
            "s1", "msg",
            IntentAnalysis(is_task=True, task_type="coding", confidence=0.95, ambiguity_score=0.1)
        )
        session.rounds.append(("q", "a"))
        state = {"clarification_session": session}
        route = await workflow._route_after_answer(state)
        assert route == "decompose"

    @pytest.mark.asyncio
    async def test_route_after_verify_pass_next(self, workflow):
        """验证后路由: 通过且有下一步 → next"""
        from nexusagent.execution.task_decomposer import TaskPlan, TaskStep, StepType
        from nexusagent.execution.verifier import VerificationResult, VerificationStatus
        plan = TaskPlan(goal="g", steps=[
            TaskStep(1, StepType.MODIFY, "s1", "a1", "v1"),
            TaskStep(2, StepType.MODIFY, "s2", "a2", "v2"),
        ])
        state = {
            "plan": plan,
            "current_step_idx": 0,
            "last_verification": VerificationResult(step_id=1, status=VerificationStatus.PASSED, method="auto", details="ok"),
        }
        route = await workflow._route_after_verify(state)
        assert route == "next"
        assert state["current_step_idx"] == 1

    @pytest.mark.asyncio
    async def test_route_after_verify_pass_deliver(self, workflow):
        """验证后路由: 通过且最后一步 → deliver"""
        from nexusagent.execution.task_decomposer import TaskPlan, TaskStep, StepType
        from nexusagent.execution.verifier import VerificationResult, VerificationStatus
        plan = TaskPlan(goal="g", steps=[TaskStep(1, StepType.MODIFY, "s1", "a1", "v1")])
        state = {
            "plan": plan,
            "current_step_idx": 0,
            "last_verification": VerificationResult(step_id=1, status=VerificationStatus.PASSED, method="auto", details="ok"),
        }
        route = await workflow._route_after_verify(state)
        assert route == "deliver"

    @pytest.mark.asyncio
    async def test_route_after_verify_fail(self, workflow):
        """验证后路由: 失败 → reflect"""
        from nexusagent.execution.task_decomposer import TaskPlan, TaskStep, StepType
        from nexusagent.execution.verifier import VerificationResult, VerificationStatus
        plan = TaskPlan(goal="g", steps=[TaskStep(1, StepType.MODIFY, "s1", "a1", "v1")])
        state = {
            "plan": plan,
            "current_step_idx": 0,
            "last_verification": VerificationResult(step_id=1, status=VerificationStatus.FAILED, method="auto", details="error"),
        }
        route = await workflow._route_after_verify(state)
        assert route == "reflect"

    @pytest.mark.asyncio
    async def test_route_after_reflect_retry(self, workflow):
        """反思后路由: 默认重试"""
        state = {"retry_count": 1, "should_abort": False}
        route = await workflow._route_after_reflect(state)
        assert route == "retry"

    @pytest.mark.asyncio
    async def test_route_after_reflect_abort(self, workflow):
        """反思后路由: 放弃 → abort"""
        state = {"retry_count": 1, "should_abort": True}
        route = await workflow._route_after_reflect(state)
        assert route == "abort"

    @pytest.mark.asyncio
    async def test_route_after_reflect_revise(self, workflow):
        """反思后路由: 修改计划"""
        mock_report = MagicMock()
        mock_report.retry_strategy = "retry_alternative"
        state = {"retry_count": 1, "should_abort": False, "reflection_report": mock_report}
        route = await workflow._route_after_reflect(state)
        assert route == "revise"

    @pytest.mark.asyncio
    async def test_node_intent_analysis(self, workflow):
        """意图分析节点"""
        state = {"user_message": "帮我写代码"}
        result = await workflow._node_intent_analysis(state)
        assert "intent" in result
        assert result["intent"].is_task is True

    @pytest.mark.asyncio
    async def test_node_task_decompose(self, workflow):
        """任务分解节点"""
        state = {
            "user_message": "实现功能",
            "intent": IntentAnalysis(is_task=True, task_type="coding", confidence=0.9),
        }
        result = await workflow._node_task_decompose(state)
        assert "plan" in result
        assert result["plan"].total_steps > 0

    @pytest.mark.asyncio
    async def test_node_deliver(self, workflow):
        """交付节点"""
        from nexusagent.execution.task_decomposer import TaskPlan, TaskStep, StepType
        plan = TaskPlan(goal="g", steps=[TaskStep(1, StepType.MODIFY, "s1", "a1", "v1")])
        state = {"plan": plan, "execution_records": [], "user_message": "msg"}
        result = await workflow._node_deliver(state)
        assert "report" in result
        assert isinstance(result["report"], str)
        assert len(result["report"]) > 0

    @pytest.mark.asyncio
    async def test_run_without_deliberation(self, mock_llm, mock_tools, mock_reflexion):
        """无研讨引擎时应正常工作"""
        wf = StrictExecutionWorkflow(
            llm_backend=mock_llm,
            tool_registry=mock_tools,
            deliberation=None,
            reflexion=mock_reflexion,
        )
        result = await wf.run("帮我写代码", session_id="test10")
        assert result["mode"] in ("strict", "chat")

    @pytest.mark.asyncio
    async def test_run_without_reflexion(self, mock_llm, mock_tools, mock_deliberation):
        """无反思节点时应正常工作"""
        wf = StrictExecutionWorkflow(
            llm_backend=mock_llm,
            tool_registry=mock_tools,
            deliberation=mock_deliberation,
            reflexion=None,
        )
        result = await wf.run("帮我写代码", session_id="test11")
        assert result["mode"] in ("strict", "chat")
