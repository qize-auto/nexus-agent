"""
NexusAgent v4.0+ — Memory Profile Adapter

画像驱动的记忆检索适配器。
- 画像注入检索 query
- 按项目维度组织记忆
- 重要性加权调整
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from nexusagent.common.profile_adapter import ProfileAdapter
from nexusagent.memory.user_profile import UserProfile

logger = logging.getLogger("nexus.memory.profile_adapter")


class MemoryProfileAdapter(ProfileAdapter):
    _adapter_name = "memory.hybrid"
    """
    HybridMemory / MemoryStore 的画像适配器

    驱动逻辑:
        - current_project → 检索时优先该项目记忆
        - tech_stack → 检索关键词增强
        - recent_topics → 检索上下文注入
    """

    def __init__(self, hybrid_memory: Any):
        self._hybrid = hybrid_memory

    def enhance_query(self, profile: UserProfile, query: str) -> str:
        """使用画像增强检索 query"""
        enhancements = []

        # 项目上下文
        if profile.dynamic.current_project:
            enhancements.append(f"project:{profile.dynamic.current_project}")

        # 技术栈关键词
        for tech in profile.static.tech_stack[:3]:
            if tech.lower() not in query.lower():
                enhancements.append(tech)

        # 近期话题
        for topic in profile.dynamic.recent_topics[:2]:
            if topic.lower() not in query.lower():
                enhancements.append(topic)

        if enhancements:
            enhanced = f"{query} ({' '.join(enhancements)})"
            logger.debug("MemoryAdapter query enhanced: '%s' → '%s'", query, enhanced)
            return enhanced
        return query

    def get_memory_types_priority(self, profile: UserProfile) -> List[str]:
        """根据画像返回记忆类型优先级"""
        # 默认优先级
        priority = ["episodic", "semantic", "procedural", "working"]

        # 如果用户有明确的项目上下文，提升 episodic 优先级
        if profile.dynamic.current_project:
            priority = ["episodic", "working", "semantic", "procedural"]

        return priority

    def adjust_importance_threshold(self, profile: UserProfile) -> float:
        """调整重要性阈值"""
        # 细节偏好高的用户 → 降低阈值（检索更多）
        detail = profile.behavioral.detail_preference
        return max(0.0, 0.3 - detail * 0.2)
