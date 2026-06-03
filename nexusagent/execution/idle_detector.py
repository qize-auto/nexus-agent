"""
NexusAgent v4.0+ — Idle Detector 空闲检测器

职责:
    1. 追踪用户最后活动时间戳
    2. 检测空闲窗口（可配置阈值，默认 30 秒）
    3. 支持中断/取消后台任务（用户发送新消息时）
    4. 线程安全

Usage:
    detector = IdleDetector(idle_seconds=30)
    detector.mark_active()          # 用户发送消息时调用
    if detector.is_idle():          # 检查是否空闲
        asyncio.create_task(background_work())
    detector.cancel_background()    # 用户再次活跃时中断后台
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger("nexus.execution.idle")


class IdleDetector:
    """
    空闲检测器

    设计原则:
        - 轻量级: 只维护时间戳，不创建线程/定时器
        - 非阻塞: is_idle() 是同步 O(1) 查询
        - 可中断: cancel_background() 取消正在运行的后台任务
    """

    def __init__(self, idle_seconds: float = 30.0):
        self._idle_threshold = idle_seconds
        self._last_active = 0.0
        self._background_task: Optional[asyncio.Task] = None

    def mark_active(self) -> None:
        """标记用户活跃（处理新消息时调用）"""
        self._last_active = time.time()
        # 如果有正在运行的后台任务，尝试取消
        self._cancel_background()

    def is_idle(self) -> bool:
        """检查当前是否处于空闲状态"""
        if self._last_active == 0:
            return False  # 从未活跃过，不算空闲
        elapsed = time.time() - self._last_active
        return elapsed >= self._idle_threshold

    def idle_duration(self) -> float:
        """返回已空闲的秒数（未空闲时返回 0）"""
        if self._last_active == 0:
            return 0.0
        elapsed = time.time() - self._last_active
        return elapsed if elapsed >= self._idle_threshold else 0.0

    def set_background_task(self, task: asyncio.Task) -> None:
        """注册当前后台任务（用于后续取消）"""
        self._background_task = task

    def _cancel_background(self) -> bool:
        """取消正在运行的后台任务"""
        if self._background_task and not self._background_task.done():
            self._background_task.cancel()
            logger.debug("后台任务已取消（用户重新活跃）")
            return True
        self._background_task = None
        return False

    def get_status(self) -> dict:
        """返回当前状态"""
        return {
            "idle_threshold_seconds": self._idle_threshold,
            "last_active": self._last_active,
            "is_idle": self.is_idle(),
            "idle_duration_seconds": round(self.idle_duration(), 1),
            "has_background_task": (
                self._background_task is not None and not self._background_task.done()
            ),
        }
