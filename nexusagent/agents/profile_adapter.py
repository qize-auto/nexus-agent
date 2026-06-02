"""
NexusAgent v4.0+ — Swarm Profile Adapter

画像驱动的多智能体编排适配器。
- Specialist 偏好匹配
- 角色优先级排序
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from nexusagent.common.profile_adapter import ProfileAdapter
from nexusagent.memory.user_profile import UserProfile

logger = logging.getLogger("nexus.agents.profile_adapter")


class SwarmProfileAdapter(ProfileAdapter):
    _adapter_name = "agents.swarm"
    """
    AgentSwarm 的画像适配器

    驱动逻辑:
        - tech_stack → 选择对应 specialist
        - preferred_tools → 优先有相关工具的 Agent
        - work_habits → 选择 handoff vs groupchat 策略
    """

    def __init__(self, swarm: Any):
        self._swarm = swarm

    def recommend_specialists(self, profile: UserProfile, task: str) -> List[str]:
        """推荐最适合的 specialist 角色列表"""
        recommendations = []
        tech = set(t.lower() for t in profile.static.tech_stack)

        # 基于技术栈映射到 specialist 角色
        tech_role_map = {
            "python": ["coder", "data_analyst"],
            "javascript": ["frontend", "fullstack"],
            "java": ["backend", "enterprise"],
            "sql": ["dba", "data_analyst"],
            "docker": ["devops", "sre"],
            "kubernetes": ["devops", "sre"],
            "cloud": ["cloud_architect", "devops"],
        }

        for t, roles in tech_role_map.items():
            if t in tech:
                recommendations.extend(roles)

        # 去重
        seen = set()
        unique = []
        for r in recommendations:
            if r not in seen:
                seen.add(r)
                unique.append(r)

        logger.debug("SwarmAdapter recommendations for %s: %s", profile.user_id, unique)
        return unique

    def recommend_strategy(self, profile: UserProfile) -> str:
        """推荐 Swarm 执行策略"""
        habits = profile.static.work_habits
        if habits.get("prefer_parallel", False):
            return "groupchat"
        if habits.get("prefer_sequential", False):
            return "handoff"
        if profile.behavioral.patience_index < 0.3:
            return "load_balance"  # 急躁用户：负载均衡最快
        return "handoff"
