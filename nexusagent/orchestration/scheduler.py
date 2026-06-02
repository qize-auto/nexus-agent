"""
NexusAgent v3.3 — 编排层：Cron调度 + Heartbeat心跳
补全: ARC-011, ARC-012
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("nexus.orchestration.scheduler")


@dataclass
class CronJob:
    """定时任务定义"""
    name: str
    schedule: str           # cron表达式或 "30m"/"every 2h"
    handler: Callable[[], Any]
    last_run: float = 0.0
    run_count: int = 0
    error_count: int = 0
    enabled: bool = True

    def should_run(self, now: float) -> bool:
        """简单调度检查（支持 "30m"/"1h" 格式）"""
        if not self.enabled:
            return False
        if self.last_run == 0:
            return True
        interval_s = self._parse_interval()
        return (now - self.last_run) >= interval_s

    def _parse_interval(self) -> float:
        """解析调度间隔"""
        s = self.schedule.lower().replace(" ", "")
        if s.endswith("m"):
            return float(s[:-1]) * 60
        if s.endswith("h"):
            return float(s[:-1]) * 3600
        if s.endswith("s"):
            return float(s[:-1])
        return 3600  # 默认1小时


@dataclass
class HeartbeatStatus:
    """心跳状态"""
    component: str
    alive: bool = True
    last_beat: float = field(default_factory=time.time)
    latency_ms: float = 0.0
    error: Optional[str] = None


class CronScheduler:
    """
    Cron调度器 — ARC-011
    支持定时任务注册、执行、错误统计
    """

    def __init__(self):
        self._jobs: Dict[str, CronJob] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def register(self, name: str, schedule: str, handler: Callable) -> CronJob:
        """注册定时任务"""
        job = CronJob(name=name, schedule=schedule, handler=handler)
        self._jobs[name] = job
        logger.info("Cron注册: %s (间隔=%s)", name, schedule)
        return job

    async def start(self) -> None:
        """启动调度循环"""
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Cron调度器启动 (%d任务)", len(self._jobs))

    async def stop(self) -> None:
        """停止调度"""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Cron调度器停止")

    async def _loop(self) -> None:
        """主调度循环 — 每30秒检查一次"""
        while self._running:
            now = time.time()
            for job in self._jobs.values():
                if job.should_run(now):
                    try:
                        if asyncio.iscoroutinefunction(job.handler):
                            await job.handler()
                        else:
                            job.handler()
                        job.last_run = now
                        job.run_count += 1
                    except Exception as e:
                        job.error_count += 1
                        logger.error("Cron[%s] 失败: %s", job.name, e)
            await asyncio.sleep(30)

    def get_status(self) -> Dict[str, Any]:
        """获取调度状态"""
        return {
            name: {
                "run_count": j.run_count,
                "error_count": j.error_count,
                "last_run": j.last_run,
                "enabled": j.enabled,
            }
            for name, j in self._jobs.items()
        }


class HeartbeatMonitor:
    """
    心跳监控 — ARC-012
    定期检查各层组件健康状态
    """

    def __init__(self):
        self._components: Dict[str, HeartbeatStatus] = {}
        self._check_interval = 60  # 秒

    def register(self, name: str) -> HeartbeatStatus:
        """注册心跳组件"""
        status = HeartbeatStatus(component=name)
        self._components[name] = status
        return status

    async def check(self, name: str, check_fn: Callable[[], bool]) -> None:
        """
        执行心跳检查

        Args:
            name: 组件名称
            check_fn: 健康检查函数，返回True=健康
        """
        status = self._components.get(name)
        if not status:
            status = self.register(name)

        start = time.monotonic()
        try:
            alive = check_fn()
            status.alive = alive
            status.error = None
        except Exception as e:
            status.alive = False
            status.error = str(e)

        status.last_beat = time.time()
        status.latency_ms = (time.monotonic() - start) * 1000

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有组件心跳状态"""
        return {
            name: {
                "alive": s.alive,
                "last_beat": s.last_beat,
                "latency_ms": s.latency_ms,
                "error": s.error,
            }
            for name, s in self._components.items()
        }

    def is_all_healthy(self) -> bool:
        """检查全部组件是否健康"""
        return all(s.alive for s in self._components.values())
