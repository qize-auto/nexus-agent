"""
NexusAgent v4.0+ — Simulation Clock [MIROFISH-INSPIRED]

基于 MiroFish 的 TimeSimulationConfig 理念：
    - 模拟时间流速：每轮代表 N 分钟
    - 活跃时段：Agent 有各自的活跃时间（如 9:00-18:00）
    - 响应延迟：Agent 对消息的反应有延迟（5-60 分钟）
    - 高峰/低谷时段：不同时段活跃度不同

来源: MiroFish backend/app/services/simulation_config_generator.py
      TimeSimulationConfig + CHINA_TIMEZONE_CONFIG

融合到任务协作：
    - Agent 在非活跃时段降低任务竞标意愿
    - 响应延迟影响异步协作的效率评估
    - 高峰时段 Agent 更主动参与讨论
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TimeSlot:
    """时间槽"""
    hour: int  # 0-23
    activity_multiplier: float = 1.0  # 活跃度系数
    label: str = "normal"  # dead | morning | work | peak | night


class SimulationClock:
    """
    模拟时钟 — 为 Agent 协作引入时间感知

    Usage:
        clock = SimulationClock()
        # 检查 Agent 是否活跃
        if clock.is_agent_active(agent_active_hours=[9, 10, 11, 14, 15]):
            ...
        # 计算响应延迟
        delay = clock.calculate_response_delay(base_delay=10)
    """

    # 默认时段配置（基于 MiroFish 的 CHINA_TIMEZONE_CONFIG）
    DEFAULT_SLOTS: Dict[int, TimeSlot] = {
        0: TimeSlot(0, 0.05, "dead"),
        1: TimeSlot(1, 0.05, "dead"),
        2: TimeSlot(2, 0.05, "dead"),
        3: TimeSlot(3, 0.05, "dead"),
        4: TimeSlot(4, 0.05, "dead"),
        5: TimeSlot(5, 0.05, "dead"),
        6: TimeSlot(6, 0.4, "morning"),
        7: TimeSlot(7, 0.4, "morning"),
        8: TimeSlot(8, 0.4, "morning"),
        9: TimeSlot(9, 0.7, "work"),
        10: TimeSlot(10, 0.7, "work"),
        11: TimeSlot(11, 0.7, "work"),
        12: TimeSlot(12, 0.7, "work"),
        13: TimeSlot(13, 0.7, "work"),
        14: TimeSlot(14, 0.7, "work"),
        15: TimeSlot(15, 0.7, "work"),
        16: TimeSlot(16, 0.7, "work"),
        17: TimeSlot(17, 0.7, "work"),
        18: TimeSlot(18, 0.7, "work"),
        19: TimeSlot(19, 1.5, "peak"),
        20: TimeSlot(20, 1.5, "peak"),
        21: TimeSlot(21, 1.5, "peak"),
        22: TimeSlot(22, 1.5, "peak"),
        23: TimeSlot(23, 0.5, "night"),
    }

    def __init__(self, time_slots: Optional[Dict[int, TimeSlot]] = None):
        self._slots = time_slots or dict(self.DEFAULT_SLOTS)
        self._simulated_hour = 9  # 默认从早上 9 点开始
        self._minutes_per_round = 60
        self._round_count = 0

    def tick(self) -> int:
        """推进一轮时间"""
        self._round_count += 1
        self._simulated_hour = (9 + self._round_count * self._minutes_per_round // 60) % 24
        return self._simulated_hour

    def get_current_multiplier(self) -> float:
        """获取当前时段的活跃度系数"""
        slot = self._slots.get(self._simulated_hour, TimeSlot(self._simulated_hour, 1.0, "normal"))
        return slot.activity_multiplier

    def is_agent_active(self, active_hours: List[int]) -> bool:
        """Agent 在当前时段是否活跃"""
        return self._simulated_hour in active_hours

    def calculate_response_delay(
        self,
        delay_min: int = 5,
        delay_max: int = 60,
        activity_level: float = 0.5,
    ) -> int:
        """
        计算响应延迟（秒）

        延迟 = base_delay / (activity_multiplier * activity_level)
        活跃度越高，延迟越低
        """
        import random
        base_delay = random.randint(delay_min, delay_max)
        multiplier = self.get_current_multiplier()
        effective_activity = max(0.1, multiplier * activity_level)
        delay = int(base_delay / effective_activity)
        return max(1, min(delay, delay_max * 2))

    def get_bid_willingness(self, activity_level: float) -> float:
        """
        计算 Agent 的投标意愿

        意愿 = activity_level * time_multiplier * random_factor
        """
        import random
        multiplier = self.get_current_multiplier()
        base = activity_level * multiplier
        noise = random.uniform(0.8, 1.2)
        return min(1.0, base * noise)

    def reset(self) -> None:
        """重置时钟"""
        self._simulated_hour = 9
        self._round_count = 0

    def stats(self) -> Dict[str, Any]:
        return {
            "simulated_hour": self._simulated_hour,
            "round_count": self._round_count,
            "current_multiplier": self.get_current_multiplier(),
        }
