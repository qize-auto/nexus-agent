"""
NexusAgent v4.0+ — Tool Registry Profile Adapter

画像驱动的工具适配器。
- 禁用工具过滤
- 偏好工具排序置顶
- 技能水平 → 工具描述详细度
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from nexusagent.common.profile_adapter import ProfileAdapter
from nexusagent.memory.user_profile import UserProfile

logger = logging.getLogger("nexus.tools.profile_adapter")


class ToolRegistryProfileAdapter(ProfileAdapter):
    _adapter_name = "tools.registry"
    """
    ToolRegistry 的画像适配器

    驱动逻辑:
        - disliked_tools → 过滤/降权
        - preferred_tools → 排序置顶
        - tech_stack → 相关工具高亮
        - detail_preference → 描述详细度调整
    """

    def __init__(self, tool_registry: Any):
        self._registry = tool_registry

    def filter_tools(self, profile: UserProfile, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """根据画像过滤工具列表"""
        disliked = set(t.lower() for t in getattr(profile.static, "disliked_tools", []))
        filtered = []
        for tool in tools:
            name = tool.get("name", "").lower()
            # 检查是否被禁用
            if any(d in name for d in disliked):
                logger.debug("Tool filtered by profile: %s", name)
                continue
            filtered.append(tool)
        return filtered

    def sort_tools(self, profile: UserProfile, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """根据画像排序工具列表（偏好置顶）"""
        preferred = set(t.lower() for t in profile.static.preferred_tools)
        tech = set(t.lower() for t in profile.static.tech_stack)

        def score(tool: Dict[str, Any]) -> float:
            name = tool.get("name", "").lower()
            desc = tool.get("description", "").lower()
            s = 0.0
            if any(p in name or p in desc for p in preferred):
                s += 10.0
            if any(t in name or t in desc for t in tech):
                s += 5.0
            return s

        return sorted(tools, key=score, reverse=True)

    def adjust_description(self, profile: UserProfile, tool_desc: str) -> str:
        """根据用户技能水平调整工具描述"""
        detail = profile.behavioral.detail_preference
        if detail > 0.7:
            # 高细节偏好：保留完整描述
            return tool_desc
        elif detail < 0.3:
            # 低细节偏好：只保留第一行
            return tool_desc.split("\n")[0]
        return tool_desc
