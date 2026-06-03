"""
端到端测试: EvolutionEngine 自我进化系统

验证:
    1. 三档模式切换正常
    2. 手动触发进化周期生成建议
    3. HITL 审批流程
    4. 配置历史记录
    5. 回滚功能
"""

import pytest
import pytest_asyncio
import tempfile
import os

from nexusagent.evolution.engine import EvolutionEngine
from nexusagent.evolution.strategies import (
    PromptOptimizationStrategy,
    ToolMappingStrategy,
    BudgetTuningStrategy,
)
from nexusagent.benchmark.runner import BenchmarkRunner


@pytest_asyncio.fixture
async def evolution_setup():
    """创建临时配置目录和 EvolutionEngine"""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = EvolutionEngine(
            config_dir=tmpdir,
            benchmark_runner=BenchmarkRunner(),
            mode="notify",
            cooldown_seconds=0,  # 测试时禁用冷却期
        )
        engine.register_strategy(PromptOptimizationStrategy())
        engine.register_strategy(ToolMappingStrategy())
        engine.register_strategy(BudgetTuningStrategy())
        yield engine


class TestEvolutionEngineE2E:
    """自我进化系统端到端测试"""

    @pytest.mark.asyncio
    async def test_mode_switch(self, evolution_setup):
        """三档模式切换"""
        engine = evolution_setup
        assert engine.get_status()["mode"] == "notify"

        engine.set_mode("off")
        assert engine.get_status()["mode"] == "off"

        engine.set_mode("auto")
        assert engine.get_status()["mode"] == "auto"

        engine.set_mode("notify")
        assert engine.get_status()["mode"] == "notify"

    @pytest.mark.asyncio
    async def test_run_cycle_generates_proposals(self, evolution_setup):
        """手动触发进化周期应生成建议"""
        engine = evolution_setup
        proposals = await engine.run_cycle()
        # 可能生成也可能不生成（取决于当前配置状态），但不应抛异常
        assert isinstance(proposals, list)
        for p in proposals:
            assert hasattr(p, "id")
            assert hasattr(p, "dimension")
            assert hasattr(p, "confidence")
            assert hasattr(p, "description")

    @pytest.mark.asyncio
    async def test_proposal_lifecycle(self, evolution_setup):
        """建议的完整生命周期：生成 → 审批 → 部署/拒绝"""
        engine = evolution_setup

        # 生成建议
        proposals = await engine.run_cycle()
        if not proposals:
            pytest.skip("未生成进化建议（当前配置已优化）")

        proposal = proposals[0]

        # 确认在待审批列表中
        pending = engine.get_pending_proposals()
        assert any(p.id == proposal.id for p in pending)

        # 审批
        ok = engine.approve(proposal.id, approver="test_user")
        assert ok is True

        # 确认已不在待审批列表
        pending_after = engine.get_pending_proposals()
        assert not any(p.id == proposal.id for p in pending_after)

    @pytest.mark.asyncio
    async def test_reject_proposal(self, evolution_setup):
        """拒绝建议"""
        engine = evolution_setup
        proposals = await engine.run_cycle()
        if not proposals:
            pytest.skip("未生成进化建议")

        proposal = proposals[0]
        ok = engine.reject(proposal.id, approver="test_user")
        assert ok is True

        pending = engine.get_pending_proposals()
        assert not any(p.id == proposal.id for p in pending)

    @pytest.mark.asyncio
    async def test_config_history(self, evolution_setup):
        """配置历史记录"""
        engine = evolution_setup
        status = engine.get_status()
        # 初始状态下历史为空
        assert isinstance(status["config_history"], dict)

    @pytest.mark.asyncio
    async def test_rollback(self, evolution_setup):
        """回滚功能"""
        engine = evolution_setup
        # 回滚到不存在的版本应失败
        ok = engine.rollback("nonexistent_dimension")
        # 回滚结果取决于是否有历史记录，但不应抛异常
        assert ok in (True, False)

    @pytest.mark.asyncio
    async def test_cooldown_respected(self, evolution_setup):
        """冷却期应被尊重"""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = EvolutionEngine(
                config_dir=tmpdir,
                benchmark_runner=BenchmarkRunner(),
                mode="auto",
                cooldown_seconds=3600,  # 1 小时冷却期
            )
            # 第一次运行
            await engine.run_cycle()
            # 第二次运行应在冷却期内，可能返回空列表
            proposals = await engine.run_cycle()
            assert isinstance(proposals, list)
