"""
Tests for nexusagent.evolution.hitl — HITL Approver
"""

import time

import pytest

from nexusagent.evolution.hitl import HITLApprover
from nexusagent.evolution.config import EvolutionProposal, ProposalStatus


class TestHITLApprover:
    @pytest.fixture
    def approver(self):
        return HITLApprover()

    @pytest.fixture
    def sample_proposal(self):
        return EvolutionProposal(
            id="prop_001",
            dimension="prompt",
            description="测试建议",
            current_config={"a": 1},
            proposed_config={"a": 2},
            rationale="测试",
            confidence=0.8,
            created_at=time.time(),
        )

    def test_submit_high_confidence(self, approver, sample_proposal):
        action = approver.submit(sample_proposal)
        assert action == "pending"
        assert sample_proposal.status == ProposalStatus.PENDING
        assert len(approver.get_pending()) == 1

    def test_submit_auto_reject_low_confidence(self, approver):
        proposal = EvolutionProposal(
            id="prop_002",
            dimension="prompt",
            description="低置信度",
            current_config={},
            proposed_config={},
            rationale="测试",
            confidence=0.2,
            created_at=time.time(),
        )
        action = approver.submit(proposal)
        assert action == "auto_rejected"
        assert proposal.status == ProposalStatus.REJECTED

    def test_approve(self, approver, sample_proposal):
        approver.submit(sample_proposal)
        result = approver.approve(sample_proposal.id, "Alice", "看起来不错")
        assert result is True
        assert sample_proposal.status == ProposalStatus.APPROVED
        assert sample_proposal.approved_by == "Alice"
        assert len(approver.get_pending()) == 0

    def test_reject(self, approver, sample_proposal):
        approver.submit(sample_proposal)
        result = approver.reject(sample_proposal.id, "Bob", "有风险")
        assert result is True
        assert sample_proposal.status == ProposalStatus.REJECTED
        assert len(approver.get_pending()) == 0

    def test_approve_nonexistent(self, approver):
        result = approver.approve("nonexistent", "Alice")
        assert result is False

    def test_generate_report(self, approver, sample_proposal):
        report = approver.generate_report(sample_proposal)
        assert "进化建议审批报告" in report
        assert sample_proposal.id in report
        assert "当前配置" in report
        assert "建议配置" in report

    def test_get_record(self, approver, sample_proposal):
        approver.submit(sample_proposal)
        approver.approve(sample_proposal.id, "Alice")
        record = approver.get_record(sample_proposal.id)
        assert record is not None
        assert record.approved is True
        assert record.approver == "Alice"

    def test_save_report(self, approver, sample_proposal, tmp_path):
        path = approver.save_report(sample_proposal, str(tmp_path))
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert sample_proposal.id in content
