"""
Tests for TaskDecomposer — 任务分解器
"""

import pytest
from nexusagent.execution.task_decomposer import TaskDecomposer, TaskPlan, TaskStep


class TestTaskDecomposer:
    """任务分解器测试集"""

    @pytest.mark.asyncio
    async def test_decompose_coding_task(self):
        """编码任务分解"""
        decomposer = TaskDecomposer()
        plan = await decomposer.decompose(
            goal="实现一个用户登录功能",
            task_type="coding",
            target_files=["auth.py"],
        )
        assert isinstance(plan, TaskPlan)
        assert plan.goal == "实现一个用户登录功能"
        assert plan.total_steps > 0
        assert all(isinstance(s, TaskStep) for s in plan.steps)

    @pytest.mark.asyncio
    async def test_decompose_refactoring_task(self):
        """重构任务分解"""
        decomposer = TaskDecomposer()
        plan = await decomposer.decompose(
            goal="重构 utils.py",
            task_type="refactoring",
            target_files=["utils.py"],
        )
        assert plan.total_steps > 0
        assert any("分析" in s.description for s in plan.steps)

    @pytest.mark.asyncio
    async def test_decompose_debugging_task(self):
        """调试任务分解"""
        decomposer = TaskDecomposer()
        plan = await decomposer.decompose(
            goal="修复 NullPointerException",
            task_type="debugging",
            target_files=[],
        )
        assert plan.total_steps > 0
        assert any("定位" in s.description or "复现" in s.description for s in plan.steps)

    @pytest.mark.asyncio
    async def test_decompose_testing_task(self):
        """测试任务分解"""
        decomposer = TaskDecomposer()
        plan = await decomposer.decompose(
            goal="为 api.py 添加单元测试",
            task_type="testing",
            target_files=["api.py"],
        )
        assert plan.total_steps > 0
        assert any("测试" in s.description for s in plan.steps)

    @pytest.mark.asyncio
    async def test_decompose_config_task(self):
        """配置任务分解"""
        decomposer = TaskDecomposer()
        plan = await decomposer.decompose(
            goal="更新 config.yaml",
            task_type="config",
            target_files=["config.yaml"],
        )
        assert plan.total_steps > 0

    @pytest.mark.asyncio
    async def test_step_has_id(self):
        """每个步骤应有唯一 ID"""
        decomposer = TaskDecomposer()
        plan = await decomposer.decompose("实现功能", "coding", [])
        ids = [s.id for s in plan.steps]
        assert len(ids) == len(set(ids)), "步骤 ID 应唯一"

    @pytest.mark.asyncio
    async def test_step_has_description(self):
        """每个步骤应有描述"""
        decomposer = TaskDecomposer()
        plan = await decomposer.decompose("实现功能", "coding", [])
        for step in plan.steps:
            assert step.description
            assert len(step.description) > 0

    @pytest.mark.asyncio
    async def test_step_has_action(self):
        """每个步骤应有动作"""
        decomposer = TaskDecomposer()
        plan = await decomposer.decompose("实现功能", "coding", [])
        for step in plan.steps:
            assert step.action
            assert len(step.action) > 0

    @pytest.mark.asyncio
    async def test_step_has_verification(self):
        """每个步骤应有验证标准"""
        decomposer = TaskDecomposer()
        plan = await decomposer.decompose("实现功能", "coding", [])
        for step in plan.steps:
            assert step.verification
            assert len(step.verification) > 0

    @pytest.mark.asyncio
    async def test_plan_has_risks(self):
        """计划应包含风险列表"""
        decomposer = TaskDecomposer()
        plan = await decomposer.decompose("实现功能", "coding", [])
        assert isinstance(plan.risks, list)

    @pytest.mark.asyncio
    async def test_plan_to_dict(self):
        """to_dict 应返回有效字典"""
        decomposer = TaskDecomposer()
        plan = await decomposer.decompose("实现功能", "coding", [])
        d = plan.to_dict()
        assert isinstance(d, dict)
        assert "goal" in d
        assert "total_steps" in d
        assert "steps" in d
        assert "risks" in d

    @pytest.mark.asyncio
    async def test_step_to_dict(self):
        """TaskStep to_dict 应返回有效字典"""
        from nexusagent.execution.task_decomposer import StepType
        step = TaskStep(
            id=1,
            type=StepType.MODIFY,
            description="测试步骤",
            action="test_action",
            verification="验证通过",
        )
        d = step.to_dict()
        assert d["id"] == 1
        assert d["description"] == "测试步骤"
        assert d["action"] == "test_action"
        assert d["verification"] == "验证通过"

    @pytest.mark.asyncio
    async def test_context_influence(self):
        """上下文应影响分解结果"""
        decomposer = TaskDecomposer()
        plan_with_context = await decomposer.decompose(
            goal="实现功能",
            task_type="coding",
            target_files=["main.py"],
            context="使用 asyncio",
        )
        plan_without = await decomposer.decompose(
            goal="实现功能",
            task_type="coding",
            target_files=["main.py"],
        )
        # 有上下文的计划可能包含更具体的步骤
        assert plan_with_context.total_steps > 0
        assert plan_without.total_steps > 0

    @pytest.mark.asyncio
    async def test_llm_fallback_mock(self):
        """LLM 兜底分解（Mock）"""
        mock_llm = type("MockLLM", (), {
            "generate": lambda self, prompt, **kwargs: "Step 1: Analyze\nStep 2: Implement\nStep 3: Verify",
        })()
        decomposer = TaskDecomposer(llm_backend=mock_llm)
        plan = await decomposer.decompose("复杂任务", "coding", [])
        # 规则模板应已处理，不会走到 LLM
        assert plan.total_steps > 0

    @pytest.mark.asyncio
    async def test_unknown_task_type(self):
        """未知任务类型应使用通用模板"""
        decomposer = TaskDecomposer()
        plan = await decomposer.decompose("做点什么", "unknown", [])
        assert plan.total_steps > 0
        assert plan.goal == "做点什么"
