"""
Tests for nexusagent.evolution.engine — Evolution Engine
"""

import tempfile
from pathlib import Path

import pytest

from nexusagent.evolution.engine import EvolutionEngine
from nexusagent.evolution.config import EvolutionProposal, ProposalStatus, BenchmarkMetrics
from nexusagent.evolution.strategies.prompt_opt import PromptOptimizationStrategy
from nexusagent.evolution.strategies.tool_map import ToolMappingStrategy


class MockBenchmarkRunner:
    """模拟 BenchmarkRunner"""

    def __init__(self, metrics=None):
        self._metrics = metrics or {
            "avg_latency_ms": 500,
            "success_rate": 0.7,  # 低成功率，触发优化
            "avg_tokens_per_request": 2000,
            "avg_tokens_per_second": 100,
            "avg_cost_usd": 0.002,
            "recovery_attempts": 10,
            "recovery_success_rate": 0.3,
        }

    async def run_dry(self):
        return dict(self._metrics)


class TestEvolutionEngine:
    @pytest.fixture
    def engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield EvolutionEngine(
                config_dir=tmp,
                benchmark_runner=MockBenchmarkRunner(),
            )

    @pytest.mark.asyncio
    async def test_run_cycle_generates_proposals(self, engine):
        engine.register_strategy(PromptOptimizationStrategy())
        engine.register_strategy(ToolMappingStrategy())

        proposals = await engine.run_cycle()
        assert isinstance(proposals, list)
        # 低成功率和低恢复率应该触发建议
        assert len(proposals) >= 1

    @pytest.mark.asyncio
    async def test_run_cycle_no_strategies(self, engine):
        proposals = await engine.run_cycle()
        assert proposals == []

    def test_register_strategy(self, engine):
        from nexusagent.evolution.strategies.base import EvolutionStrategy

        class DummyStrategy(EvolutionStrategy):
            dimension = "test"

            def analyze(self, metrics, current_config):
                return []

            def apply(self, proposal):
                return True

        engine.register_strategy(DummyStrategy())
        assert len(engine.list_strategies()) == 1
        assert engine.list_strategies()[0]["dimension"] == "test"

    def test_get_status(self, engine):
        engine.register_strategy(PromptOptimizationStrategy())
        status = engine.get_status()
        assert "strategies_registered" in status
        assert status["strategies_registered"] == 1
        assert "pending_proposals" in status

    def test_approve_reject(self, engine):
        proposal = EvolutionProposal(
            id="prop_test",
            dimension="prompt",
            description="测试",
            current_config={},
            proposed_config={},
            rationale="测试",
            confidence=0.8,
            status=ProposalStatus.PENDING,
            created_at=0,
        )
        engine._hitl.submit(proposal)
        assert len(engine.get_pending_proposals()) == 1

        engine.approve(proposal.id, "Alice", "批准")
        assert proposal.status == ProposalStatus.APPROVED
        assert len(engine.get_pending_proposals()) == 0

        # 测试拒绝
        proposal2 = EvolutionProposal(
            id="prop_test2",
            dimension="prompt",
            description="测试2",
            current_config={},
            proposed_config={},
            rationale="测试",
            confidence=0.8,
            status=ProposalStatus.PENDING,
            created_at=0,
        )
        engine._hitl.submit(proposal2)
        engine.reject(proposal2.id, "Bob", "拒绝")
        assert proposal2.status == ProposalStatus.REJECTED

    @pytest.mark.asyncio
    async def test_deploy_unapproved_fails(self, engine):
        proposal = EvolutionProposal(
            id="prop_unapproved",
            dimension="prompt",
            description="测试",
            current_config={},
            proposed_config={"system_prompt": "new"},
            rationale="测试",
            status=ProposalStatus.PENDING,
        )
        result = await engine.deploy(proposal)
        assert result is False

    @pytest.mark.asyncio
    async def test_deploy_no_strategy_fails(self, engine):
        proposal = EvolutionProposal(
            id="prop_no_strategy",
            dimension="nonexistent",
            description="测试",
            current_config={},
            proposed_config={},
            rationale="测试",
            status=ProposalStatus.APPROVED,
        )
        result = await engine.deploy(proposal)
        assert result is False

    def test_generate_report(self, engine):
        proposal = EvolutionProposal(
            id="prop_report",
            dimension="prompt",
            description="测试报告",
            current_config={"a": 1},
            proposed_config={"a": 2},
            rationale="测试",
            confidence=0.8,
        )
        report = engine.generate_report(proposal)
        assert proposal.id in report
        assert "当前配置" in report
        assert "建议配置" in report

    def test_rollback(self, engine):
        # 先保存一个版本
        engine._history.save("prompt", {"v": 1}, "版本1")
        engine._history.save("prompt", {"v": 2}, "版本2")

        result = engine.rollback("prompt")
        assert result is True

        current = engine._history.get_current("prompt")
        assert current is not None
        assert current.config == {"v": 1}

    def test_rollback_nonexistent_dimension(self, engine):
        result = engine.rollback("nonexistent")
        assert result is False

    def test_rollback_specific_version(self, engine):
        v1 = engine._history.save("prompt", {"v": 1}, "版本1")
        engine._history.save("prompt", {"v": 2}, "版本2")
        engine._history.save("prompt", {"v": 3}, "版本3")

        result = engine.rollback("prompt", v1.version_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, engine):
        """测试完整生命周期: 生成 → 审批 → 部署"""
        engine.register_strategy(PromptOptimizationStrategy())

        # 1. 运行进化周期
        proposals = await engine.run_cycle()
        assert len(proposals) > 0

        # 2. 审批
        proposal = proposals[0]
        engine.approve(proposal.id, "test_user")
        assert proposal.status == ProposalStatus.APPROVED

        # 3. 部署（A/B 测试可能会 inconclusive）
        # 由于 MockBenchmarkRunner 返回固定数据，treatment 和 control 指标相同
        # 所以 winner 应该是 inconclusive，部署会失败并回滚
        result = await engine.deploy(proposal)
        # 结果取决于 A/B 测试，但不应该抛异常
        assert proposal.status in (ProposalStatus.DEPLOYED, ProposalStatus.ROLLED_BACK)


class TestEvolutionEngineModes:
    """EvolutionEngine 三档模式测试"""

    @pytest.fixture
    def engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield EvolutionEngine(
                config_dir=tmp,
                benchmark_runner=MockBenchmarkRunner(),
            )

    def test_default_mode_is_notify(self, engine):
        assert engine.mode == "notify"

    def test_set_mode_valid(self, engine):
        engine.set_mode("off")
        assert engine.mode == "off"
        engine.set_mode("auto")
        assert engine.mode == "auto"
        engine.set_mode("notify")
        assert engine.mode == "notify"

    def test_set_mode_invalid(self, engine):
        with pytest.raises(ValueError):
            engine.set_mode("invalid")

    @pytest.mark.asyncio
    async def test_off_mode_returns_empty(self, engine):
        engine.register_strategy(PromptOptimizationStrategy())
        engine.set_mode("off")
        proposals = await engine.run_cycle()
        assert proposals == []

    @pytest.mark.asyncio
    async def test_off_mode_cannot_run(self, engine):
        engine.set_mode("off")
        assert engine.can_run() is False
        assert engine.time_until_next_run() == float("inf")

    def test_cooldown_blocks_run(self, engine):
        engine.set_mode("notify")
        engine._last_run_at = 9999999999.0  # 未来时间，冷却期肯定没过
        assert engine.can_run() is False
        assert engine.time_until_next_run() > 0

    def test_can_run_after_cooldown(self, engine):
        engine.set_mode("notify")
        engine._last_run_at = 0  # 从未运行
        assert engine.can_run() is True
        assert engine.time_until_next_run() == 0.0

    @pytest.mark.asyncio
    async def test_auto_mode_auto_approves_high_confidence(self, engine):
        """auto 模式下极高置信度建议应自动批准"""
        from nexusagent.evolution.strategies.base import EvolutionStrategy

        class HighConfidenceStrategy(EvolutionStrategy):
            dimension = "test_auto"

            def analyze(self, metrics, current_config):
                return [
                    EvolutionProposal(
                        id="auto_prop_001",
                        dimension="test_auto",
                        description="高置信度测试",
                        current_config={},
                        proposed_config={"x": 1},
                        rationale="测试",
                        confidence=0.98,  # 超过 auto_deploy_threshold (0.95)
                    )
                ]

            def apply(self, proposal):
                return True

        engine.register_strategy(HighConfidenceStrategy())
        engine.set_mode("auto")
        proposals = await engine.run_cycle()
        # auto 模式下高置信度建议会被自动处理，不会进入 pending
        assert len(proposals) == 0

    @pytest.mark.asyncio
    async def test_auto_mode_low_confidence_goes_pending(self, engine):
        """auto 模式下不够高置信度的建议仍需审批"""
        from nexusagent.evolution.strategies.base import EvolutionStrategy

        class MidConfidenceStrategy(EvolutionStrategy):
            dimension = "test_auto2"

            def analyze(self, metrics, current_config):
                return [
                    EvolutionProposal(
                        id="auto_prop_002",
                        dimension="test_auto2",
                        description="中置信度测试",
                        current_config={},
                        proposed_config={"x": 1},
                        rationale="测试",
                        confidence=0.8,  # 低于 auto_deploy_threshold (0.95)
                    )
                ]

            def apply(self, proposal):
                return True

        engine.register_strategy(MidConfidenceStrategy())
        engine.set_mode("auto")
        proposals = await engine.run_cycle()
        assert len(proposals) == 1
        assert proposals[0].status == ProposalStatus.PENDING

    def test_status_includes_mode(self, engine):
        engine.set_mode("auto")
        status = engine.get_status()
        assert status["mode"] == "auto"
        assert "can_run" in status
        assert "time_until_next_run_seconds" in status
        assert "last_run_at" in status
