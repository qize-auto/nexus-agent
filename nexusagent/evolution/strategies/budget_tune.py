"""
NexusAgent v4.0+ — Budget Tuning Strategy

ReAct 预算参数调优策略：
    1. 分析历史任务的 token 使用和迭代次数分布
    2. 识别预算设置过于保守或激进的情况
    3. 建议调整 max_iterations, max_tokens, max_time_seconds
    4. 输出 YAML 配置文件

进化维度: budget
配置文件: evolution/configs/react_budget.yaml
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from nexusagent.evolution.config import EvolutionProposal, BenchmarkMetrics
from nexusagent.evolution.strategies.base import EvolutionStrategy

logger = logging.getLogger("nexus.evolution.strategy.budget")


class BudgetTuningStrategy(EvolutionStrategy):
    """
    ReAct 预算参数调优策略

    基于性能指标自动调整预算参数：
        - avg_tokens_per_request 接近 max_tokens → 需要提高上限
        - success_rate 高但 avg_latency_ms 低 → 可适当降低预算节省成本
        - recovery_attempts 高 → 可能需要增加 max_iterations
    """

    dimension = "budget"

    # 默认预算配置
    _DEFAULT_BUDGET = {
        "max_iterations": {"default": 25, "coding_task": 15, "research_task": 35},
        "max_tokens": {"default": 8000, "long_context": 16000},
        "max_time_seconds": {"default": 120.0, "quick_task": 30.0},
    }

    def analyze(
        self,
        metrics: BenchmarkMetrics,
        current_config: Dict[str, Any],
    ) -> List[EvolutionProposal]:
        """分析性能数据，生成预算调优建议"""
        proposals: List[EvolutionProposal] = []

        current_budget = current_config.get("react_budget", self._DEFAULT_BUDGET)
        proposed_budget = self._tune_budget(metrics, current_budget)

        if proposed_budget != current_budget:
            # 计算变化摘要
            changes = self._summarize_changes(current_budget, proposed_budget)
            proposal = self._create_proposal(
                description=f"ReAct 预算调优: {changes}",
                current={"react_budget": current_budget},
                proposed={"react_budget": proposed_budget},
                rationale=self._build_rationale(metrics, current_budget, proposed_budget),
                confidence=self._calculate_confidence(metrics),
                expected_impact={
                    "avg_cost_usd": -0.1 if self._should_reduce_budget(metrics) else 0.0,
                    "success_rate": 0.02 if self._should_increase_budget(metrics) else 0.0,
                },
            )
            proposals.append(proposal)
            logger.info("生成预算调优建议: %s", proposal.id)

        return proposals

    def apply(self, proposal: EvolutionProposal) -> bool:
        """应用预算配置变更"""
        proposed = proposal.proposed_config
        budget = proposed.get("react_budget")
        if not budget:
            return False

        if self._config_dir:
            return self._safe_yaml_write(
                self._config_dir / "react_budget.yaml",
                {"react_budget": budget},
            )
        return False

    def _tune_budget(self, metrics: BenchmarkMetrics, current: Dict[str, Any]) -> Dict[str, Any]:
        """根据指标调整预算"""
        proposed = self._deep_copy(current)

        # 1. Token 使用率接近上限 → 提高上限
        max_tokens = self._get_nested(proposed, "max_tokens", "default", default=8000)
        if max_tokens is not None and metrics.avg_tokens_per_request > max_tokens * 0.85:
            new_max = int(max_tokens * 1.25)
            self._set_nested(proposed, "max_tokens", "default", value=new_max)
            logger.debug("预算调优: max_tokens %d → %d", max_tokens, new_max)

        # 2. 延迟低且成功率高 → 可适当降低迭代次数
        max_iter = self._get_nested(proposed, "max_iterations", "default", default=25)
        if max_iter is not None and metrics.avg_latency_ms < 1000 and metrics.success_rate > 0.9 and max_iter > 15:
            new_iter = max(15, max_iter - 5)
            self._set_nested(proposed, "max_iterations", "default", value=new_iter)
            logger.debug("预算调优: max_iterations %d → %d", max_iter, new_iter)

        # 3. 恢复尝试多 → 增加迭代次数
        if max_iter is not None and metrics.recovery_attempts > 10 and max_iter < 40:
            new_iter = min(40, max_iter + 5)
            self._set_nested(proposed, "max_iterations", "default", value=new_iter)
            logger.debug("预算调优: max_iterations %d → %d (recovery)", max_iter, new_iter)

        # 4. 成本偏高 → 降低时间限制
        max_time = self._get_nested(proposed, "max_time_seconds", "default", default=120.0)
        if max_time is not None and metrics.avg_cost_usd > 0.005 and max_time > 60:
            new_time = max(60.0, max_time * 0.8)
            self._set_nested(proposed, "max_time_seconds", "default", value=round(new_time, 1))
            logger.debug("预算调优: max_time_seconds %.1f → %.1f", max_time, new_time)

        return proposed

    def _should_reduce_budget(self, metrics: BenchmarkMetrics) -> bool:
        """判断是否应该降低预算"""
        return metrics.avg_latency_ms < 1000 and metrics.success_rate > 0.9

    def _should_increase_budget(self, metrics: BenchmarkMetrics) -> bool:
        """判断是否应该增加预算"""
        return metrics.avg_tokens_per_request > 7000 or metrics.recovery_attempts > 10

    def _calculate_confidence(self, metrics: BenchmarkMetrics) -> float:
        """计算建议置信度"""
        confidence = 0.6
        if metrics.avg_tokens_per_request > 7500:
            confidence += 0.15
        if metrics.success_rate > 0.95:
            confidence += 0.1
        if metrics.recovery_attempts > 15:
            confidence += 0.1
        return min(confidence, 0.9)

    def _build_rationale(
        self,
        metrics: BenchmarkMetrics,
        current: Dict[str, Any],
        proposed: Dict[str, Any],
    ) -> str:
        """构建分析理由"""
        parts = ["基于当前性能指标的预算分析:"]
        parts.append(f"- 平均 Token 使用: {metrics.avg_tokens_per_request:.0f}")
        parts.append(f"- 成功率: {metrics.success_rate:.1%}")
        parts.append(f"- 平均延迟: {metrics.avg_latency_ms:.0f}ms")
        parts.append(f"- 恢复尝试: {metrics.recovery_attempts}")
        parts.append(f"- 平均成本: ${metrics.avg_cost_usd:.4f}")
        parts.append("")
        parts.append("建议调整:")

        changes = self._summarize_changes(current, proposed)
        parts.append(changes)
        return "\n".join(parts)

    def _summarize_changes(self, current: Dict[str, Any], proposed: Dict[str, Any]) -> str:
        """总结配置变化"""
        changes = []
        for key in ["max_iterations", "max_tokens", "max_time_seconds"]:
            curr_def = self._get_nested(current, key, "default", default=None)
            prop_def = self._get_nested(proposed, key, "default", default=None)
            if curr_def is not None and prop_def is not None and curr_def != prop_def:
                changes.append(f"{key}: {curr_def} → {prop_def}")
        return ", ".join(changes) if changes else "无变化"

    @staticmethod
    def _deep_copy(d: Dict[str, Any]) -> Dict[str, Any]:
        """深拷贝字典"""
        import copy
        return copy.deepcopy(d)

    @staticmethod
    def _get_nested(d: Dict[str, Any], *keys: str, default: Any = None) -> Any:
        """安全获取嵌套字典值"""
        current = d
        for key in keys:
            if not isinstance(current, dict):
                return default
            current = current.get(key, default)
            if current is None:
                return default
        return current

    @staticmethod
    def _set_nested(d: Dict[str, Any], *keys: str, value: Any) -> None:
        """安全设置嵌套字典值"""
        current = d
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value
