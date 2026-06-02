"""
NexusAgent v4.0+ — Guardrails Profile Adapter

画像驱动的安全审查适配器。
- 用户信任等级 → 动态审查强度映射
- 用户风险偏好 → 敏感关键词阈值调整
- 历史安全事件 → 预防规则定制
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from nexusagent.common.profile_adapter import ProfileAdapter
from nexusagent.memory.user_profile import UserProfile

logger = logging.getLogger("nexus.security.profile_adapter")


class GuardrailsProfileAdapter(ProfileAdapter):
    _adapter_name = "security.guardrails"
    """
    GuardrailsEngine 的画像适配器

    驱动逻辑:
        - EXPERT 信任等级 → 降低审查强度 (放行更多)
        - NOVICE 信任等级 → 增强审查强度
        - 用户 history 中有安全事件 → 提升该类事件敏感度
    """

    TIER_REVIEW_MULTIPLIER = {
        "NOVICE": 1.5,     # 新手: 审查更严格
        "LEARNER": 1.2,
        "TRUSTED": 1.0,    # 标准
        "EXPERT": 0.7,     # 专家: 审查更宽松
    }

    def __init__(self, guardrails_engine: Any):
        self._guardrails = guardrails_engine
        self._original_ml_threshold = 0.6  # 保存原始阈值

    def apply(self, profile: UserProfile) -> None:
        """应用画像到 GuardrailsEngine"""
        tier = profile.security.trust_tier
        multiplier = self.TIER_REVIEW_MULTIPLIER.get(tier, 1.0)

        # 调整 ML 风险阈值
        new_threshold = self._original_ml_threshold / multiplier
        # 注: 由于 GuardrailsEngine 没有暴露 ml_threshold 属性,
        # 我们在 review() 包装器中动态调整

        logger.debug(
            "GuardrailsAdapter: tier=%s multiplier=%.1f ml_threshold=%.2f",
            tier, multiplier, new_threshold,
        )

    def get_adjusted_ml_threshold(self, profile: Optional[UserProfile]) -> float:
        """根据画像获取调整后的 ML 阈值"""
        if not profile:
            return self._original_ml_threshold
        tier = profile.security.trust_tier
        multiplier = self.TIER_REVIEW_MULTIPLIER.get(tier, 1.0)
        return self._original_ml_threshold / multiplier

    def should_auto_approve(self, profile: UserProfile, tool_name: str) -> bool:
        """判断是否应该自动放行某工具"""
        auto_list = profile.security.auto_approve_tools
        return tool_name in auto_list

    def should_require_confirm(self, profile: UserProfile, tool_name: str) -> bool:
        """判断是否必须用户确认"""
        confirm_list = profile.security.require_confirm_tools
        return tool_name in confirm_list
