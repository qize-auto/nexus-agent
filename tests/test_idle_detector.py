"""
Tests for nexusagent.execution.idle_detector — Idle Detector
"""

import asyncio

import pytest

from nexusagent.execution.idle_detector import IdleDetector


class TestIdleDetector:
    def test_mark_active(self):
        d = IdleDetector(idle_seconds=1.0)
        assert d._last_active == 0
        d.mark_active()
        assert d._last_active > 0
        assert d.is_idle() is False

    def test_is_idle_threshold(self):
        d = IdleDetector(idle_seconds=0.1)
        d.mark_active()
        assert d.is_idle() is False
        # 等待超过阈值
        import time
        time.sleep(0.15)
        assert d.is_idle() is True

    def test_idle_duration(self):
        d = IdleDetector(idle_seconds=0.1)
        assert d.idle_duration() == 0.0  # 从未活跃
        d.mark_active()
        assert d.idle_duration() == 0.0  # 未超过阈值
        import time
        time.sleep(0.15)
        assert d.idle_duration() > 0.1

    def test_never_active_not_idle(self):
        d = IdleDetector(idle_seconds=1.0)
        assert d.is_idle() is False

    @pytest.mark.asyncio
    async def test_cancel_background(self):
        d = IdleDetector(idle_seconds=1.0)
        d.mark_active()

        async def bg():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(bg())
        d.set_background_task(task)
        assert d.get_status()["has_background_task"] is True

        # 用户再次活跃，应取消后台任务
        d.mark_active()
        # 给事件循环一点时间处理取消
        await asyncio.sleep(0.05)
        assert task.cancelled() is True
        assert d.get_status()["has_background_task"] is False

    def test_get_status(self):
        d = IdleDetector(idle_seconds=30.0)
        d.mark_active()
        s = d.get_status()
        assert s["idle_threshold_seconds"] == 30.0
        assert s["is_idle"] is False
        assert s["idle_duration_seconds"] == 0.0
        assert s["has_background_task"] is False
        assert "last_active" in s
