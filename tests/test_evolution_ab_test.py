"""
Tests for nexusagent.evolution.ab_test — A/B Test Framework
"""

import pytest

from nexusagent.evolution.ab_test import ABTestFramework
from nexusagent.evolution.config import BenchmarkMetrics


class MockBenchmarkRunner:
    """模拟 BenchmarkRunner"""

    def __init__(self, success_rate=0.9, latency_ms=500):
        self._success_rate = success_rate
        self._latency_ms = latency_ms

    async def run_dry(self):
        return {
            "avg_latency_ms": self._latency_ms,
            "success_rate": self._success_rate,
            "avg_tokens_per_request": 2000,
            "avg_tokens_per_second": 100,
            "avg_cost_usd": 0.002,
            "recovery_attempts": 2,
            "recovery_success_rate": 0.8,
        }


class TestABTestFramework:
    @pytest.fixture
    def ab(self):
        return ABTestFramework(MockBenchmarkRunner())

    @pytest.mark.asyncio
    async def test_run_test_basic(self, ab):
        result = await ab.run_test(
            proposal_id="p1",
            control_config={"a": 1},
            treatment_config={"a": 2},
            min_samples=10,
            max_duration_seconds=30,
        )
        assert result.test_id
        assert result.proposal_id == "p1"
        assert result.sample_size >= 10
        assert result.winner in ("control", "treatment", "inconclusive")
        assert 0 <= result.p_value <= 1

    @pytest.mark.asyncio
    async def test_run_test_timeout(self, ab):
        result = await ab.run_test(
            proposal_id="p1",
            control_config={"a": 1},
            treatment_config={"a": 2},
            min_samples=1000,  # 很大的样本量
            max_duration_seconds=0.1,  # 很短的超时
        )
        assert result.winner == "inconclusive"  # 样本不足

    def test_compute_metrics(self, ab):
        from nexusagent.evolution.ab_test import _Sample
        samples = [
            _Sample(latency_ms=100, success=True, tokens_used=1000, cost_usd=0.001),
            _Sample(latency_ms=200, success=True, tokens_used=2000, cost_usd=0.002),
            _Sample(latency_ms=300, success=False, tokens_used=3000, cost_usd=0.003),
        ]
        metrics = ab._compute_metrics(samples)
        assert metrics.avg_latency_ms == 200.0
        assert metrics.success_rate == pytest.approx(2 / 3)
        assert metrics.avg_tokens_per_request == 2000.0

    def test_t_test(self, ab):
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        b = [10.0, 11.0, 12.0, 13.0, 14.0]
        p = ab._t_test(a, b)
        assert p < 0.05  # 显著差异

    def test_t_test_identical(self, ab):
        a = [1.0, 1.0, 1.0]
        b = [1.0, 1.0, 1.0]
        p = ab._t_test(a, b)
        assert p == 1.0  # 无差异

    def test_t_test_insufficient_samples(self, ab):
        p = ab._t_test([1.0], [2.0])
        assert p == 1.0

    def test_determine_winner_treatment_wins(self, ab):
        ctrl = BenchmarkMetrics(success_rate=0.8, avg_latency_ms=1000, avg_cost_usd=0.005)
        treat = BenchmarkMetrics(success_rate=0.9, avg_latency_ms=800, avg_cost_usd=0.004)
        winner = ab._determine_winner(ctrl, treat, p_value=0.01, sample_size=30, min_samples=10)
        assert winner == "treatment"

    def test_determine_winner_inconclusive(self, ab):
        ctrl = BenchmarkMetrics(success_rate=0.8)
        treat = BenchmarkMetrics(success_rate=0.81)
        winner = ab._determine_winner(ctrl, treat, p_value=0.01, sample_size=30, min_samples=10)
        assert winner == "inconclusive"

    def test_determine_winner_insufficient_samples(self, ab):
        ctrl = BenchmarkMetrics()
        treat = BenchmarkMetrics(success_rate=1.0)
        winner = ab._determine_winner(ctrl, treat, p_value=0.01, sample_size=5, min_samples=30)
        assert winner == "inconclusive"
