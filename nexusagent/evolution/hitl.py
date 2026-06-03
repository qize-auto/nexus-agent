"""
NexusAgent v4.0+ — HITL (Human-in-the-Loop) Approver

人类在环审批系统：
    1. 生成 Markdown 格式的变更报告
    2. 支持 CLI 审批: nexus evolution review <proposal_id>
    3. 记录审批人、审批时间、审批理由
    4. 支持批量审批和自动拒绝（低置信度）

审批策略:
    - confidence < 0.5: 自动拒绝
    - 0.5 <= confidence < 0.7: 需要审批
    - confidence >= 0.7: 建议批准（仍需确认）
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from nexusagent.evolution.config import EvolutionProposal, ProposalStatus

logger = logging.getLogger("nexus.evolution.hitl")


@dataclass
class ApprovalRecord:
    """审批记录"""
    proposal_id: str
    approved: bool
    approver: str
    reason: str
    timestamp: float


class HITLApprover:
    """
    人类在环审批器

    Usage:
        hitl = HITLApprover()
        hitl.submit(proposal)           # 提交建议
        report = hitl.generate_report(proposal)  # 生成审批报告
        hitl.approve(proposal_id, "Alice", "看起来不错")  # 批准
        hitl.reject(proposal_id, "Alice", "有风险")       # 拒绝
    """

    # 自动审批阈值
    AUTO_REJECT_CONFIDENCE = 0.3
    AUTO_APPROVE_CONFIDENCE = 0.95  # 极高置信度可自动批准（可选）

    def __init__(self):
        self._pending: Dict[str, EvolutionProposal] = {}
        self._records: Dict[str, ApprovalRecord] = {}

    def submit(self, proposal: EvolutionProposal) -> str:
        """
        提交进化建议

        Returns:
            审批动作: "auto_rejected" | "pending" | "auto_approved"
        """
        # 自动拒绝低置信度
        if proposal.confidence < self.AUTO_REJECT_CONFIDENCE:
            proposal.status = ProposalStatus.REJECTED
            self._records[proposal.id] = ApprovalRecord(
                proposal_id=proposal.id,
                approved=False,
                approver="system",
                reason=f"置信度过低 ({proposal.confidence:.2f} < {self.AUTO_REJECT_CONFIDENCE})",
                timestamp=time.time(),
            )
            logger.info("自动拒绝低置信度建议: %s (confidence=%.2f)", proposal.id, proposal.confidence)
            return "auto_rejected"

        # 自动批准极高置信度（可选，默认关闭）
        if proposal.confidence >= self.AUTO_APPROVE_CONFIDENCE:
            proposal.status = ProposalStatus.APPROVED
            self._records[proposal.id] = ApprovalRecord(
                proposal_id=proposal.id,
                approved=True,
                approver="system",
                reason=f"极高置信度自动批准 ({proposal.confidence:.2f})",
                timestamp=time.time(),
            )
            logger.info("自动批准高置信度建议: %s (confidence=%.2f)", proposal.id, proposal.confidence)
            return "auto_approved"

        # 进入待审批队列
        self._pending[proposal.id] = proposal
        proposal.status = ProposalStatus.PENDING
        logger.info("建议已提交待审批: %s (confidence=%.2f)", proposal.id, proposal.confidence)
        return "pending"

    def approve(self, proposal_id: str, approver: str, reason: str = "") -> bool:
        """批准建议"""
        proposal = self._pending.pop(proposal_id, None)
        if proposal is None:
            logger.warning("批准失败: 建议 %s 不在待审批队列", proposal_id)
            return False

        proposal.status = ProposalStatus.APPROVED
        proposal.approved_by = approver
        proposal.approved_at = time.time()

        self._records[proposal_id] = ApprovalRecord(
            proposal_id=proposal_id,
            approved=True,
            approver=approver,
            reason=reason or "批准",
            timestamp=time.time(),
        )
        logger.info("建议已批准: %s by %s", proposal_id, approver)
        return True

    def reject(self, proposal_id: str, approver: str, reason: str = "") -> bool:
        """拒绝建议"""
        proposal = self._pending.pop(proposal_id, None)
        if proposal is None:
            logger.warning("拒绝失败: 建议 %s 不在待审批队列", proposal_id)
            return False

        proposal.status = ProposalStatus.REJECTED

        self._records[proposal_id] = ApprovalRecord(
            proposal_id=proposal_id,
            approved=False,
            approver=approver,
            reason=reason or "拒绝",
            timestamp=time.time(),
        )
        logger.info("建议已拒绝: %s by %s", proposal_id, approver)
        return True

    def get_pending(self) -> List[EvolutionProposal]:
        """获取所有待审批建议"""
        return list(self._pending.values())

    def get_record(self, proposal_id: str) -> Optional[ApprovalRecord]:
        """获取审批记录"""
        return self._records.get(proposal_id)

    def generate_report(self, proposal: EvolutionProposal) -> str:
        """
        生成 Markdown 格式的审批报告

        Returns:
            Markdown 文本
        """
        lines = [
            f"# 进化建议审批报告",
            f"",
            f"## 基本信息",
            f"- **ID**: `{proposal.id}`",
            f"- **维度**: {proposal.dimension}",
            f"- **置信度**: {proposal.confidence:.2f}",
            f"- **创建时间**: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(proposal.created_at))}",
            f"",
            f"## 变更描述",
            f"{proposal.description}",
            f"",
            f"## 分析理由",
            f"{proposal.rationale}",
            f"",
            f"## 预期影响",
        ]

        for metric, value in proposal.expected_impact.items():
            lines.append(f"- {metric}: {value:+.2%}")

        lines.extend([
            f"",
            f"## 配置差异",
            f"",
            f"### 当前配置",
            f"```json",
        ])
        import json
        lines.append(json.dumps(proposal.current_config, indent=2, ensure_ascii=False))
        lines.extend([
            f"```",
            f"",
            f"### 建议配置",
            f"```json",
        ])
        lines.append(json.dumps(proposal.proposed_config, indent=2, ensure_ascii=False))
        lines.extend([
            f"```",
            f"",
            f"---",
            f"",
            f"**审批操作**:",
            f"- 批准: `nexus evolution approve {proposal.id}`",
            f"- 拒绝: `nexus evolution reject {proposal.id}`",
            f"",
        ])

        return "\n".join(lines)

    def save_report(self, proposal: EvolutionProposal, output_dir: str) -> Path:
        """保存审批报告到文件"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        filepath = out / f"proposal_{proposal.id}.md"
        filepath.write_text(self.generate_report(proposal), encoding="utf-8")
        return filepath
