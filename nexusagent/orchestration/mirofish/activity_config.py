"""
NexusAgent v4.0+ — Agent Activity Config [MIROFISH-INSPIRED]

基于 MiroFish 的 AgentActivityConfig 理念：
    - 每个 Agent 有独立的活跃度配置
    - 发言频率、响应速度、情感倾向、立场
    - 影响力权重决定发言被采纳概率

来源: MiroFish backend/app/services/simulation_config_generator.py
      AgentActivityConfig 数据结构

融合到任务协作：
    - 活跃度影响 Agent 的任务竞标意愿
    - 立场影响 Agent 的决策方向（支持/反对/中立/观察）
    - 影响力权重影响 Agent 发言在共识中的权重
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentActivityConfig:
    """Agent 活动配置 — 基于 MiroFish AgentActivityConfig"""

    agent_id: str

    # 活跃度 (0.0-1.0)
    activity_level: float = 0.5  # 整体活跃度

    # 任务频率（每小时预期处理任务数）
    tasks_per_hour: float = 2.0

    # 活跃时间段（24小时制，0-23）
    active_hours: List[int] = field(default_factory=lambda: list(range(9, 18)))

    # 响应速度（对任务的反应延迟，单位：秒）
    response_delay_min: int = 5
    response_delay_max: int = 60

    # 情感倾向 (-1.0到1.0，负面到正面)
    sentiment_bias: float = 0.0

    # 立场（对特定话题的态度）
    stance: str = "neutral"  # supportive, opposing, neutral, observer

    # 影响力权重（决定其发言被其他 Agent 采纳的概率）
    influence_weight: float = 1.0

    # 决策风格
    decision_style: str = "analytical"  # analytical | intuitive | conservative | aggressive

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "activity_level": self.activity_level,
            "tasks_per_hour": self.tasks_per_hour,
            "active_hours": self.active_hours,
            "response_delay_min": self.response_delay_min,
            "response_delay_max": self.response_delay_max,
            "sentiment_bias": self.sentiment_bias,
            "stance": self.stance,
            "influence_weight": self.influence_weight,
            "decision_style": self.decision_style,
        }

    def calculate_bid_score(
        self,
        capability_match: float,
        current_load: float,
        time_multiplier: float = 1.0,
    ) -> float:
        """
        计算投标评分

        评分 = 能力匹配 * 0.35 + (1 - 负载) * 0.25 + 活跃度 * 0.2 + 时段系数 * 0.2
        """
        load_factor = max(0.0, 1.0 - current_load)
        activity_factor = self.activity_level
        return (
            capability_match * 0.35
            + load_factor * 0.25
            + activity_factor * 0.2
            + time_multiplier * 0.2
        )

    def calculate_consensus_weight(self) -> float:
        """计算共识权重"""
        return self.influence_weight * (0.5 + self.activity_level * 0.5)
