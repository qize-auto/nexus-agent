"""
NexusAgent v4.0+ — ReAct Profile Adapter

画像驱动的执行引擎适配器。
- 温度偏好 → LLM temperature
- 耐心指数 → 预算/迭代/超时
- 细节偏好 → 系统提示词调整
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from nexusagent.memory.user_profile import UserProfile

logger = logging.getLogger("nexus.execution.profile_adapter")


class ReActProfileAdapter:
    """
    ReActEngine 的画像适配器

    驱动逻辑:
        - temperature_preference → LLM temperature 参数
        - patience_index → max_iterations / max_time_seconds
        - detail_preference → 系统提示词追加详细度要求
    """

    def __init__(self, react_engine: Any):
        self._react = react_engine

    def apply(self, profile: UserProfile) -> Dict[str, Any]:
        """应用画像到 ReActEngine，返回调整参数"""
        adjustments = {
            "temperature": profile.behavioral.temperature_preference,
            "max_iterations": self._compute_iterations(profile),
            "max_time_seconds": profile.behavioral.timeout_preference,
            "system_prompt_suffix": self._build_prompt_suffix(profile),
        }
        logger.debug("ReActAdapter adjustments: %s", adjustments)
        return adjustments

    def _compute_iterations(self, profile: UserProfile) -> int:
        """根据耐心指数计算迭代上限"""
        base = 25
        patience = profile.behavioral.patience_index
        if patience < 0.3:
            return max(5, int(base * 0.5))   # 急躁: 减少迭代
        elif patience > 0.8:
            return int(base * 1.5)            # 耐心: 增加迭代
        return base

    def _build_prompt_suffix(self, profile: UserProfile) -> str:
        """构建系统提示词后缀"""
        parts = []
        if profile.behavioral.detail_preference > 0.7:
            parts.append("请提供详细、全面的回答，包含必要的背景信息和推理过程。")
        elif profile.behavioral.detail_preference < 0.3:
            parts.append("请简洁回答，直接给出结论和关键步骤，避免冗长解释。")

        if profile.static.language_preference == "zh-CN":
            parts.append("使用中文回复。")
        elif profile.static.language_preference == "en":
            parts.append("Reply in English.")

        tech = profile.static.tech_stack
        if tech:
            parts.append(f"用户技术栈偏好: {', '.join(tech[:5])}。")

        return "\n".join(parts)
