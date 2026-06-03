"""
NexusAgent v4.0+ — Prompt Optimization Strategy

系统提示词优化策略：
    1. 分析高频失败场景（成功率低、完整性差）
    2. 识别提示词中的模糊或缺失指令
    3. 生成改进后的提示词建议
    4. 输出 YAML 配置文件

进化维度: prompt
配置文件: evolution/configs/prompt.yaml
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from nexusagent.evolution.config import EvolutionProposal, BenchmarkMetrics
from nexusagent.evolution.strategies.base import EvolutionStrategy

logger = logging.getLogger("nexus.evolution.strategy.prompt")


class PromptOptimizationStrategy(EvolutionStrategy):
    """
    系统提示词优化策略

    基于性能指标自动识别提示词改进机会：
        - success_rate < 0.8 → 提示词可能需要更清晰的指令
        - completeness_score < 0.7 → 可能需要添加完整性检查要求
        - anti_compression_score < 0.7 → 可能需要强调详细回答
    """

    dimension = "prompt"

    # 提示词优化规则库
    _OPTIMIZATION_RULES = {
        "low_success": {
            "condition": lambda m: m.success_rate < 0.8,
            "additions": [
                "\n在执行任务前，请先确认你理解了用户的真实意图。",
                "\n如果指令不明确，请主动提出澄清问题。",
            ],
            "rationale": "成功率低于 80%，提示词可能需要更清晰的指令和意图确认机制",
        },
        "low_completeness": {
            "condition": lambda m: m.completeness_score < 0.7,
            "additions": [
                "\n回答完成后，请自我检查是否覆盖了用户问题的所有方面。",
                "\n如果答案不完整，请补充遗漏的内容。",
            ],
            "rationale": "完整性得分低于 70%，需要添加自我检查要求",
        },
        "low_anti_compression": {
            "condition": lambda m: m.anti_compression_score < 0.7,
            "additions": [
                "\n请提供详细的回答，不要省略中间步骤或推理过程。",
                "\n即使问题看似简单，也请给出充分的解释和背景信息。",
            ],
            "rationale": "防偷懒得分低于 70%，提示词需要强调详细回答",
        },
        "high_latency": {
            "condition": lambda m: m.avg_latency_ms > 3000,
            "additions": [
                "\n在回答复杂问题时，先给出简要结论，再逐步展开详细解释。",
            ],
            "rationale": "平均延迟超过 3 秒，建议采用先结论后详述的结构",
        },
    }

    def __init__(self, config_dir: Optional[str] = None):
        super().__init__(config_dir)
        self._template_dir = Path(__file__).parent.parent / "templates"

    def analyze(
        self,
        metrics: BenchmarkMetrics,
        current_config: Dict[str, Any],
    ) -> List[EvolutionProposal]:
        """分析性能数据，生成提示词优化建议"""
        proposals: List[EvolutionProposal] = []

        current_prompt = current_config.get("system_prompt", "")
        if not current_prompt:
            # 尝试从模板加载默认提示词
            current_prompt = self._load_default_prompt()

        additions: List[str] = []
        triggered_rules: List[str] = []

        for rule_name, rule in self._OPTIMIZATION_RULES.items():
            if rule["condition"](metrics):
                additions.extend(rule["additions"])
                triggered_rules.append(rule_name)

        if not additions:
            logger.debug("提示词优化: 未触发任何规则")
            return proposals

        # 构建新提示词
        new_prompt = current_prompt + "\n".join(additions)

        # 计算预期改进
        expected_impact = self._estimate_impact(metrics, triggered_rules)

        # 置信度基于触发的规则数量和严重程度
        confidence = min(0.5 + len(triggered_rules) * 0.1, 0.9)

        proposal = self._create_proposal(
            description=f"系统提示词优化: 触发 {len(triggered_rules)} 条规则 ({', '.join(triggered_rules)})",
            current={"system_prompt": current_prompt},
            proposed={"system_prompt": new_prompt},
            rationale=self._build_rationale(metrics, triggered_rules),
            confidence=confidence,
            expected_impact=expected_impact,
        )
        proposals.append(proposal)
        logger.info("生成提示词优化建议: %s (rules=%s)", proposal.id, triggered_rules)
        return proposals

    def apply(self, proposal: EvolutionProposal) -> bool:
        """应用提示词配置变更"""
        proposed = proposal.proposed_config
        prompt = proposed.get("system_prompt", "")
        if not prompt:
            return False

        if self._config_dir:
            return self._safe_yaml_write(
                self._config_dir / "prompt.yaml",
                {"system_prompt": prompt},
            )
        return False

    def _load_default_prompt(self) -> str:
        """加载默认提示词模板"""
        filepath = self._template_dir / "system_default.yaml"
        data = self._safe_yaml_read(filepath)
        return data.get("system_prompt", "You are NexusAgent, a local-first AI assistant.")

    def _build_rationale(self, metrics: BenchmarkMetrics, triggered_rules: List[str]) -> str:
        """构建分析理由"""
        parts = ["基于当前性能指标分析:"]
        parts.append(f"- 成功率: {metrics.success_rate:.1%}")
        parts.append(f"- 完整性: {metrics.completeness_score:.1%}")
        parts.append(f"- 防偷懒: {metrics.anti_compression_score:.1%}")
        parts.append(f"- 平均延迟: {metrics.avg_latency_ms:.0f}ms")
        parts.append("")
        parts.append(f"触发的优化规则: {', '.join(triggered_rules)}")
        parts.append("建议添加相应的提示词指令以改善上述指标。")
        return "\n".join(parts)

    def _estimate_impact(self, metrics: BenchmarkMetrics, triggered_rules: List[str]) -> Dict[str, float]:
        """估算预期改进"""
        impact: Dict[str, float] = {}
        if "low_success" in triggered_rules:
            impact["success_rate"] = min(0.1, (0.8 - metrics.success_rate) * 0.5)
        if "low_completeness" in triggered_rules:
            impact["completeness_score"] = min(0.15, (0.7 - metrics.completeness_score) * 0.5)
        if "low_anti_compression" in triggered_rules:
            impact["anti_compression_score"] = min(0.15, (0.7 - metrics.anti_compression_score) * 0.5)
        if "high_latency" in triggered_rules:
            impact["avg_latency_ms"] = -0.1  # 预期延迟降低 10%
        return impact
