"""
NexusAgent v4.0+ — Evolution Config Data Models

进化系统的核心数据模型：
    - EvolutionProposal: 进化建议
    - ABTestResult: A/B 测试结果
    - ProposalStatus: 建议状态枚举
    - BenchmarkMetrics: 性能指标
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ProposalStatus(str, Enum):
    """进化建议状态"""
    PENDING = "pending"           # 待审批
    APPROVED = "approved"         # 已批准
    REJECTED = "rejected"         # 已拒绝
    TESTING = "testing"           # A/B 测试中
    DEPLOYED = "deployed"         # 已部署
    ROLLED_BACK = "rolled_back"   # 已回滚


@dataclass
class BenchmarkMetrics:
    """性能基准指标"""
    # 延迟指标
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0

    # 成功率
    success_rate: float = 0.0
    tool_success_rate: float = 0.0

    # Token 效率
    avg_tokens_per_request: float = 0.0
    avg_tokens_per_second: float = 0.0

    # 成本
    avg_cost_usd: float = 0.0
    total_cost_usd: float = 0.0

    # 质量
    completeness_score: float = 0.0
    anti_compression_score: float = 0.0

    # 错误恢复
    recovery_attempts: int = 0
    recovery_success_rate: float = 0.0

    # 自定义指标
    custom: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "avg_latency_ms": self.avg_latency_ms,
            "p50_latency_ms": self.p50_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "p99_latency_ms": self.p99_latency_ms,
            "success_rate": self.success_rate,
            "tool_success_rate": self.tool_success_rate,
            "avg_tokens_per_request": self.avg_tokens_per_request,
            "avg_tokens_per_second": self.avg_tokens_per_second,
            "avg_cost_usd": self.avg_cost_usd,
            "total_cost_usd": self.total_cost_usd,
            "completeness_score": self.completeness_score,
            "anti_compression_score": self.anti_compression_score,
            "recovery_attempts": self.recovery_attempts,
            "recovery_success_rate": self.recovery_success_rate,
            "custom": self.custom,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BenchmarkMetrics":
        custom = data.pop("custom", {})
        return cls(custom=custom, **{
            k: v for k, v in data.items()
            if k in {f.name for f in cls.__dataclass_fields__.values()}
        })


@dataclass
class EvolutionProposal:
    """
    进化建议

    由 EvolutionStrategy 生成，经 HITL 审批后进入 A/B 测试，
    测试通过则部署，否则回滚。
    """
    id: str                          # ULID
    dimension: str                   # prompt | tool_map | budget | routing
    description: str                 # 变更描述（人类可读）
    current_config: Dict[str, Any]   # 当前配置快照
    proposed_config: Dict[str, Any]  # 建议配置
    rationale: str                   # LLM 分析理由
    confidence: float = 0.5          # 0-1
    expected_impact: Dict[str, float] = field(default_factory=dict)  # 预期改进指标
    status: ProposalStatus = ProposalStatus.PENDING
    created_at: float = 0.0
    approved_by: Optional[str] = None
    approved_at: Optional[float] = None
    ab_test_id: Optional[str] = None
    deployed_at: Optional[float] = None
    rolled_back_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "dimension": self.dimension,
            "description": self.description,
            "current_config": self.current_config,
            "proposed_config": self.proposed_config,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "expected_impact": self.expected_impact,
            "status": self.status.value,
            "created_at": self.created_at,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "ab_test_id": self.ab_test_id,
            "deployed_at": self.deployed_at,
            "rolled_back_at": self.rolled_back_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvolutionProposal":
        status = ProposalStatus(data.pop("status", "pending"))
        return cls(status=status, **{
            k: v for k, v in data.items()
            if k in {f.name for f in cls.__dataclass_fields__.values()}
        })


@dataclass
class ABTestResult:
    """
    A/B 测试结果

    control: 旧配置（当前生效配置）
    treatment: 新配置（进化建议配置）
    """
    test_id: str
    proposal_id: str
    control_metrics: BenchmarkMetrics = field(default_factory=BenchmarkMetrics)
    treatment_metrics: BenchmarkMetrics = field(default_factory=BenchmarkMetrics)
    sample_size: int = 0
    duration_seconds: float = 0.0
    winner: str = "inconclusive"  # control | treatment | inconclusive
    p_value: float = 1.0
    started_at: float = 0.0
    ended_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "proposal_id": self.proposal_id,
            "control_metrics": self.control_metrics.to_dict(),
            "treatment_metrics": self.treatment_metrics.to_dict(),
            "sample_size": self.sample_size,
            "duration_seconds": self.duration_seconds,
            "winner": self.winner,
            "p_value": self.p_value,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ABTestResult":
        cm = data.pop("control_metrics", {})
        tm = data.pop("treatment_metrics", {})
        return cls(
            control_metrics=BenchmarkMetrics.from_dict(cm),
            treatment_metrics=BenchmarkMetrics.from_dict(tm),
            **{k: v for k, v in data.items() if k in {f.name for f in cls.__dataclass_fields__.values()}}
        )

    def improvement_ratio(self, metric: str = "success_rate") -> float:
        """计算 treatment 相对 control 的改进比例"""
        ctrl = getattr(self.control_metrics, metric, 0.0)
        treat = getattr(self.treatment_metrics, metric, 0.0)
        if ctrl == 0:
            return 0.0
        return (treat - ctrl) / ctrl
