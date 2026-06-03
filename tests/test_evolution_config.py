"""
Tests for nexusagent.evolution.config — Evolution Data Models
"""

import pytest

from nexusagent.evolution.config import (
    EvolutionProposal,
    ABTestResult,
    BenchmarkMetrics,
    ProposalStatus,
)


class TestProposalStatus:
    def test_enum_values(self):
        assert ProposalStatus.PENDING.value == "pending"
        assert ProposalStatus.APPROVED.value == "approved"
        assert ProposalStatus.REJECTED.value == "rejected"
        assert ProposalStatus.DEPLOYED.value == "deployed"
        assert ProposalStatus.ROLLED_BACK.value == "rolled_back"


class TestBenchmarkMetrics:
    def test_default_values(self):
        m = BenchmarkMetrics()
        assert m.avg_latency_ms == 0.0
        assert m.success_rate == 0.0
        assert m.avg_tokens_per_request == 0.0

    def test_to_dict(self):
        m = BenchmarkMetrics(success_rate=0.95, avg_latency_ms=500)
        d = m.to_dict()
        assert d["success_rate"] == 0.95
        assert d["avg_latency_ms"] == 500
        assert "custom" in d

    def test_from_dict(self):
        d = {"success_rate": 0.9, "avg_latency_ms": 1000, "custom": {"foo": 1.0}}
        m = BenchmarkMetrics.from_dict(dict(d))
        assert m.success_rate == 0.9
        assert m.avg_latency_ms == 1000
        assert m.custom == {"foo": 1.0}

    def test_from_dict_extra_fields_ignored(self):
        d = {"success_rate": 0.9, "unknown_field": 123}
        m = BenchmarkMetrics.from_dict(dict(d))
        assert m.success_rate == 0.9


class TestEvolutionProposal:
    def test_default_status(self):
        p = EvolutionProposal(
            id="test_001",
            dimension="prompt",
            description="测试",
            current_config={},
            proposed_config={},
            rationale="测试",
        )
        assert p.status == ProposalStatus.PENDING

    def test_to_dict_roundtrip(self):
        p = EvolutionProposal(
            id="test_002",
            dimension="tool_map",
            description="新增工具映射",
            current_config={"a": 1},
            proposed_config={"a": 2},
            rationale="需要替代方案",
            confidence=0.85,
            expected_impact={"success_rate": 0.05},
            status=ProposalStatus.APPROVED,
            created_at=1234567890.0,
            approved_by="Alice",
            approved_at=1234567900.0,
        )
        d = p.to_dict()
        assert d["status"] == "approved"
        assert d["confidence"] == 0.85
        assert d["approved_by"] == "Alice"

        p2 = EvolutionProposal.from_dict(dict(d))
        assert p2.status == ProposalStatus.APPROVED
        assert p2.confidence == 0.85


class TestABTestResult:
    def test_improvement_ratio(self):
        ctrl = BenchmarkMetrics(success_rate=0.8)
        treat = BenchmarkMetrics(success_rate=0.9)
        result = ABTestResult(
            test_id="t1",
            proposal_id="p1",
            control_metrics=ctrl,
            treatment_metrics=treat,
        )
        # (0.9 - 0.8) / 0.8 = 0.125
        assert result.improvement_ratio("success_rate") == pytest.approx(0.125)

    def test_improvement_ratio_zero_control(self):
        ctrl = BenchmarkMetrics(success_rate=0.0)
        treat = BenchmarkMetrics(success_rate=0.1)
        result = ABTestResult(
            test_id="t2",
            proposal_id="p2",
            control_metrics=ctrl,
            treatment_metrics=treat,
        )
        assert result.improvement_ratio("success_rate") == 0.0

    def test_to_dict_roundtrip(self):
        result = ABTestResult(
            test_id="t3",
            proposal_id="p3",
            control_metrics=BenchmarkMetrics(success_rate=0.8),
            treatment_metrics=BenchmarkMetrics(success_rate=0.85),
            sample_size=30,
            winner="treatment",
            p_value=0.03,
        )
        d = result.to_dict()
        r2 = ABTestResult.from_dict(dict(d))
        assert r2.winner == "treatment"
        assert r2.sample_size == 30
        assert r2.p_value == pytest.approx(0.03)
