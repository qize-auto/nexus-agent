"""
NexusAgent v4.0+ — Orchestrator Profile Adapter

画像驱动的编排策略适配器。
- 工作流偏好 → 默认执行策略选择
- 历史任务相似度 → 推荐相似工作流
- 急躁指数 → 预算/超时调整
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from nexusagent.common.profile_adapter import ProfileAdapter
from nexusagent.memory.user_profile import UserProfile

logger = logging.getLogger("nexus.orchestration.profile_adapter")


class OrchestratorProfileAdapter(ProfileAdapter):
    _adapter_name = "orchestration.main"
    """
    Orchestrator 的画像适配器

    驱动逻辑:
        - 用户偏好并行 → 优先 Swarm 策略
        - 用户偏好详细 → 优先 MiroFish 策略 (协作预演)
        - 用户急躁 → 优先 ReAct (最快路径)
        - 历史 workflow_frequency → 推荐常用工作流
    """

    def __init__(self, orchestrator: Any):
        self._orchestrator = orchestrator

    def recommend_strategy(self, profile: UserProfile, message: str) -> str:
        """根据画像推荐执行策略"""
        patience = profile.behavioral.patience_index
        detail = profile.behavioral.detail_preference

        # 急躁用户 → ReAct (最快)
        if patience < 0.3:
            return "react"

        # 复杂协作偏好 → MiroFish
        if detail > 0.7 and any(kw in message for kw in ("跨部门", "协同", "报告", "分析")):
            return "mirofish"

        # 并行偏好 → Swarm
        if "parallel" in profile.static.work_habits or patience > 0.7:
            return "swarm"

        # 默认
        return "react"

    def apply_budget_adjustments(self, profile: UserProfile, budget: Any) -> None:
        """根据画像调整 ReActBudget"""
        if not budget:
            return
        # 急躁用户 → 减少迭代上限和超时
        if profile.behavioral.patience_index < 0.3:
            budget.max_iterations = max(5, budget.max_iterations - 5)
            budget.max_time_seconds = max(30.0, budget.max_time_seconds * 0.7)
            logger.debug("OrchestratorAdapter: 急躁用户预算缩减")

        # 耐心用户 → 增加迭代上限
        elif profile.behavioral.patience_index > 0.8:
            budget.max_iterations += 5
            budget.max_time_seconds *= 1.3
            logger.debug("OrchestratorAdapter: 耐心用户预算扩展")
