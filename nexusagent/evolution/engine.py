"""
NexusAgent v4.0+ — Evolution Engine 进化引擎

自我进化系统核心引擎：
    1. 收集基准数据（BenchmarkRunner）
    2. 各策略分析并生成进化建议
    3. HITL 审批
    4. A/B 测试验证
    5. 部署/回滚

Usage:
    from nexusagent.evolution.engine import EvolutionEngine
    from nexusagent.benchmark.runner import BenchmarkRunner
    from nexusagent.evolution.strategies import (
        PromptOptimizationStrategy,
        ToolMappingStrategy,
        BudgetTuningStrategy,
    )

    engine = EvolutionEngine(
        config_dir=Path.home() / ".nexusagent" / "evolution",
        benchmark_runner=BenchmarkRunner(),
    )
    engine.register_strategy(PromptOptimizationStrategy())
    engine.register_strategy(ToolMappingStrategy())
    engine.register_strategy(BudgetTuningStrategy())

    proposals = await engine.run_cycle()
    # 审批后部署
    await engine.deploy(proposals[0])
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from nexusagent.evolution.config import (
    EvolutionProposal,
    ABTestResult,
    BenchmarkMetrics,
    ProposalStatus,
)
from nexusagent.evolution.history import ConfigHistory
from nexusagent.evolution.hitl import HITLApprover
from nexusagent.evolution.ab_test import ABTestFramework
from nexusagent.evolution.strategies.base import EvolutionStrategy

logger = logging.getLogger("nexus.evolution.engine")


class EvolutionEngine:
    """
    进化引擎主类

    三档模式开关:
        off    — 完全手动，run_cycle() 直接返回空
        notify — 后台分析，生成建议后提交 HITL 等待审批（默认）
        auto   — 低置信度建议自动批准并部署，高置信度仍需 HITL

    协调进化周期中的所有步骤：
        数据收集 → 策略分析 → HITL 审批 → A/B 测试 → 部署/回滚
    """

    MODE_OFF = "off"
    MODE_NOTIFY = "notify"
    MODE_AUTO = "auto"

    def __init__(
        self,
        config_dir: str,
        benchmark_runner: Any,
        mode: str = MODE_NOTIFY,
        cooldown_seconds: float = 21600.0,  # 6 小时冷却期
        auto_deploy_threshold: float = 0.95,
    ):
        self._config_dir = Path(config_dir)
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._benchmark = benchmark_runner
        self._mode = mode
        self._cooldown = cooldown_seconds
        self._last_run_at: float = 0.0
        self._strategies: List[EvolutionStrategy] = []
        self._history = ConfigHistory(str(self._config_dir))
        self._hitl = HITLApprover()
        self._ab = ABTestFramework(benchmark_runner)
        self._auto_deploy_threshold = auto_deploy_threshold

        # 当前配置缓存
        self._current_configs: Dict[str, Dict[str, Any]] = {}

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        """切换运行模式"""
        if mode not in (self.MODE_OFF, self.MODE_NOTIFY, self.MODE_AUTO):
            raise ValueError(f"无效模式: {mode}，可选: off/notify/auto")
        old = self._mode
        self._mode = mode
        logger.info("EvolutionEngine 模式切换: %s → %s", old, mode)

    def can_run(self) -> bool:
        """检查是否满足运行条件（模式不是 off 且冷却期已过）"""
        if self._mode == self.MODE_OFF:
            return False
        if self._last_run_at == 0:
            return True
        return time.time() - self._last_run_at >= self._cooldown

    def time_until_next_run(self) -> float:
        """距离下次可运行的秒数（0 表示现在可以运行）"""
        if self._mode == self.MODE_OFF:
            return float("inf")
        if self._last_run_at == 0:
            return 0.0
        remaining = self._cooldown - (time.time() - self._last_run_at)
        return max(0.0, remaining)

    def register_strategy(self, strategy: EvolutionStrategy) -> None:
        """注册进化策略"""
        # 设置策略的配置目录
        strategy._config_dir = self._config_dir / "configs"
        self._strategies.append(strategy)
        logger.info("注册进化策略: %s (%s)", strategy.dimension, strategy.__class__.__name__)

    def list_strategies(self) -> List[Dict[str, str]]:
        """列出已注册的策略"""
        return [
            {"dimension": s.dimension, "class": s.__class__.__name__}
            for s in self._strategies
        ]

    async def run_cycle(self) -> List[EvolutionProposal]:
        """
        执行一次进化周期

        三档模式行为:
            off    — 直接返回空列表
            notify — 分析后提交 HITL 等待审批（默认）
            auto   — 低置信度建议自动批准并尝试部署

        Returns:
            进入待审批队列的进化建议列表（off 模式下为空）
        """
        # 模式检查
        if self._mode == self.MODE_OFF:
            logger.debug("EvolutionEngine 处于 off 模式，跳过进化周期")
            return []

        # 冷却期检查
        if not self.can_run():
            wait = self.time_until_next_run()
            logger.debug("EvolutionEngine 冷却中，还需 %.0f 秒", wait)
            return []

        self._last_run_at = time.time()
        logger.info("===== 进化周期开始 (mode=%s) =====", self._mode)
        start = time.time()

        # 1. 收集基准数据
        metrics = await self._collect_metrics()
        logger.info("基准数据收集完成: success_rate=%.2f latency=%.0fms",
                    metrics.success_rate, metrics.avg_latency_ms)

        # 2. 各策略分析
        all_proposals: List[EvolutionProposal] = []
        for strategy in self._strategies:
            try:
                current_cfg = self._load_dimension_config(strategy.dimension)
                proposals = strategy.analyze(metrics, current_cfg)
                for p in proposals:
                    # 过滤低置信度
                    if p.confidence >= 0.5:
                        all_proposals.append(p)
                        logger.info("策略 %s 生成建议: %s (confidence=%.2f)",
                                    strategy.dimension, p.id, p.confidence)
            except Exception as e:
                logger.warning("策略 %s 分析失败: %s", strategy.dimension, e)

        # 3. 提交 HITL / 自动模式处理
        pending: List[EvolutionProposal] = []
        for proposal in all_proposals:
            if self._mode == self.MODE_AUTO and proposal.confidence >= self._auto_deploy_threshold:
                # 全自动模式：极高置信度直接批准并部署
                proposal.status = ProposalStatus.APPROVED
                proposal.approved_by = "auto"
                proposal.approved_at = time.time()
                logger.info("自动模式批准高置信度建议: %s (confidence=%.2f)",
                            proposal.id, proposal.confidence)
                # 尝试自动部署（不阻塞，失败则回滚）
                try:
                    success = await self.deploy(proposal)
                    if not success:
                        logger.warning("自动部署失败已回滚: %s", proposal.id)
                except Exception as e:
                    logger.warning("自动部署异常: %s", e)
            else:
                # notify 模式或 auto 模式下不够高置信度的建议
                action = self._hitl.submit(proposal)
                if action == "pending":
                    pending.append(proposal)

        elapsed = time.time() - start
        logger.info(
            "===== 进化周期完成: %d 建议生成, %d 待审批, %.1fs =====",
            len(all_proposals), len(pending), elapsed,
        )
        return pending

    async def deploy(self, proposal: EvolutionProposal) -> bool:
        """
        部署已批准的进化建议

        流程:
            1. 找到对应的策略
            2. 执行 A/B 测试
            3. 如果 treatment 胜出，应用配置
            4. 保存到历史
        """
        if proposal.status != ProposalStatus.APPROVED:
            logger.error("部署失败: 建议 %s 未批准 (status=%s)", proposal.id, proposal.status.value)
            return False

        # 找到对应策略
        strategy = self._find_strategy(proposal.dimension)
        if strategy is None:
            logger.error("部署失败: 未找到维度 %s 的策略", proposal.dimension)
            return False

        # 保存当前配置
        current_cfg = self._load_dimension_config(proposal.dimension)
        self._history.save(
            dimension=proposal.dimension,
            config=current_cfg,
            description="部署前快照",
            proposal_id=proposal.id,
        )

        # A/B 测试
        proposal.status = ProposalStatus.TESTING
        test_result = await self._ab.run_test(
            proposal_id=proposal.id,
            control_config=current_cfg,
            treatment_config=proposal.proposed_config,
            min_samples=30,
        )
        proposal.ab_test_id = test_result.test_id

        # 评估结果
        if test_result.winner == "treatment":
            # 应用配置
            if strategy.apply(proposal):
                proposal.status = ProposalStatus.DEPLOYED
                proposal.deployed_at = time.time()
                # 保存新版本
                self._history.save(
                    dimension=proposal.dimension,
                    config=proposal.proposed_config,
                    description=f"部署: {proposal.description}",
                    proposal_id=proposal.id,
                )
                logger.info(
                    "配置已部署: %s (dimension=%s, improvement=%+.2f%%)",
                    proposal.id, proposal.dimension,
                    test_result.improvement_ratio("success_rate") * 100,
                )
                return True
            else:
                logger.error("配置应用失败: %s", proposal.id)
                return False
        else:
            logger.info(
                "A/B 测试未通过: %s (winner=%s p=%.4f)",
                proposal.id, test_result.winner, test_result.p_value,
            )
            # 回滚到之前保存的配置
            self._rollback_to_last(proposal.dimension)
            proposal.status = ProposalStatus.ROLLED_BACK
            proposal.rolled_back_at = time.time()
            return False

    def rollback(self, dimension: str, version_id: Optional[str] = None) -> bool:
        """
        回滚配置

        Args:
            dimension: 配置维度
            version_id: 指定版本（None 则回滚到上一个版本）
        """
        if version_id:
            result = self._history.rollback(dimension, version_id)
            if result:
                # 应用回滚后的配置
                strategy = self._find_strategy(dimension)
                if strategy:
                    strategy.save_config(result.config)
                logger.warning("配置已回滚: %s → %s", dimension, result.version_id)
                return True
            return False
        else:
            # 回滚到上一个版本
            versions = self._history.list(dimension, limit=2)
            if len(versions) >= 2:
                return self.rollback(dimension, versions[1].version_id)
            logger.warning("回滚失败: %s 历史版本不足", dimension)
            return False

    def get_status(self) -> Dict[str, Any]:
        """获取进化系统状态"""
        return {
            "mode": self._mode,
            "can_run": self.can_run(),
            "time_until_next_run_seconds": round(self.time_until_next_run(), 0),
            "strategies_registered": len(self._strategies),
            "strategies": self.list_strategies(),
            "pending_proposals": len(self._hitl.get_pending()),
            "config_history": self._history.get_stats(),
            "last_run_at": self._last_run_at,
        }

    def get_pending_proposals(self) -> List[EvolutionProposal]:
        """获取待审批建议"""
        return self._hitl.get_pending()

    def approve(self, proposal_id: str, approver: str, reason: str = "") -> bool:
        """批准建议"""
        return self._hitl.approve(proposal_id, approver, reason)

    def reject(self, proposal_id: str, approver: str, reason: str = "") -> bool:
        """拒绝建议"""
        return self._hitl.reject(proposal_id, approver, reason)

    def generate_report(self, proposal: EvolutionProposal) -> str:
        """生成审批报告"""
        return self._hitl.generate_report(proposal)

    # ── 内部方法 ──

    async def _collect_metrics(self) -> BenchmarkMetrics:
        """收集性能基准数据"""
        try:
            if hasattr(self._benchmark, "run_dry"):
                raw = await self._benchmark.run_dry()
                return BenchmarkMetrics(
                    avg_latency_ms=raw.get("avg_latency_ms", 0.0),
                    success_rate=raw.get("success_rate", 0.0),
                    avg_tokens_per_request=raw.get("avg_tokens_per_request", 0.0),
                    avg_tokens_per_second=raw.get("avg_tokens_per_second", 0.0),
                    avg_cost_usd=raw.get("avg_cost_usd", 0.0),
                    recovery_attempts=raw.get("recovery_attempts", 0),
                    recovery_success_rate=raw.get("recovery_success_rate", 0.0),
                )
        except Exception as e:
            logger.warning("基准数据收集失败: %s", e)

        # 降级：返回空指标
        return BenchmarkMetrics()

    def _load_dimension_config(self, dimension: str) -> Dict[str, Any]:
        """加载指定维度的当前配置"""
        if dimension in self._current_configs:
            return self._current_configs[dimension]

        filepath = self._config_dir / "configs" / f"{dimension}.yaml"
        if filepath.exists():
            try:
                import yaml
                with open(filepath, "r", encoding="utf-8") as f:
                    self._current_configs[dimension] = yaml.safe_load(f) or {}
                    return self._current_configs[dimension]
            except Exception as e:
                logger.debug("加载配置失败 %s: %s", filepath, e)

        # 返回默认空配置
        self._current_configs[dimension] = {}
        return {}

    def _find_strategy(self, dimension: str) -> Optional[EvolutionStrategy]:
        """根据维度查找策略"""
        for s in self._strategies:
            if s.dimension == dimension:
                return s
        return None

    def _rollback_to_last(self, dimension: str) -> bool:
        """回滚到上一个版本"""
        versions = self._history.list(dimension, limit=2)
        if len(versions) >= 2:
            last = versions[1]
            strategy = self._find_strategy(dimension)
            if strategy:
                strategy.save_config(last.config)
                logger.warning("自动回滚: %s → %s", dimension, last.version_id)
                return True
        return False
