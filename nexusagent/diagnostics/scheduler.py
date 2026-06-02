"""
NexusAgent Diagnostic Scheduler — 定时后台巡检 + 告警推送

Usage:
    from nexusagent.diagnostics.scheduler import DiagnosticScheduler
    scheduler = DiagnosticScheduler(interval_seconds=300)
    scheduler.on_alert = lambda alert: print(alert)
    asyncio.create_task(scheduler.run())
    # ... later
    await scheduler.stop()
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("nexus.diagnostics.scheduler")


@dataclass
class Alert:
    """告警事件"""
    level: str          # critical | error | warning | info
    title: str
    message: str
    source: str         # health | connectivity | modules | ux | system
    timestamp: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: f"alert_{time.time():.6f}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "type": "alert",
            "level": self.level,
            "title": self.title,
            "message": self.message,
            "source": self.source,
            "timestamp": self.timestamp,
            "id": self.id,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class AlertRuleEngine:
    """告警规则引擎 — 基于诊断数据判断是否需要告警"""

    def __init__(
        self,
        dedup_seconds: float = 600.0,
        latency_warning_ms: float = 5000.0,
        latency_critical_ms: float = 10000.0,
        error_rate_warning: float = 5.0,
        error_rate_critical: float = 10.0,
    ):
        self._dedup_seconds = dedup_seconds
        self._latency_warning_ms = latency_warning_ms
        self._latency_critical_ms = latency_critical_ms
        self._error_rate_warning = error_rate_warning
        self._error_rate_critical = error_rate_critical
        self._recent_alerts: Dict[str, float] = {}  # alert_key -> last_sent_time

    def evaluate(self, health: Dict, connectivity: Dict, modules: Dict) -> List[Alert]:
        alerts: List[Alert] = []

        # Rule 1: Overall health not ok
        if not health.get("overall_healthy", True):
            alerts.append(Alert(
                level="critical",
                title="System Unhealthy",
                message="One or more backends reported unhealthy status.",
                source="health",
            ))

        # Rule 2: Connectivity probe failed
        probes = connectivity.get("probes", {})
        for name, info in probes.items():
            if info.get("status") != "ok":
                alerts.append(Alert(
                    level="error",
                    title=f"Probe Failed: {name}",
                    message=info.get("error", "Connection probe failed."),
                    source="connectivity",
                ))

        # Rule 3: Module import/health failed
        for m in modules.get("modules", []):
            if m.get("status") != "ok":
                alerts.append(Alert(
                    level="warning",
                    title=f"Module Unhealthy: {m.get('name', 'Unknown')}",
                    message=m.get("error", "Module failed import or deep health check."),
                    source="modules",
                ))

        # Rule 4: High error rate
        metrics = health.get("metrics", {})
        error_rate = (metrics.get("requests_error", 0) / max(metrics.get("requests_total", 1), 1)) * 100
        if error_rate >= self._error_rate_critical:
            alerts.append(Alert(
                level="critical",
                title="Critical Error Rate",
                message=f"Error rate is {error_rate:.1f}% in the last hour (threshold: {self._error_rate_critical:.0f}%).",
                source="health",
            ))
        elif error_rate >= self._error_rate_warning:
            alerts.append(Alert(
                level="warning",
                title="Elevated Error Rate",
                message=f"Error rate is {error_rate:.1f}% in the last hour (threshold: {self._error_rate_warning:.0f}%).",
                source="health",
            ))

        # Rule 5: High latency
        avg_latency = metrics.get("avg_latency_ms", 0)
        if avg_latency >= self._latency_critical_ms:
            alerts.append(Alert(
                level="critical",
                title="Critical Latency",
                message=f"Average latency is {avg_latency:.0f}ms (threshold: {self._latency_critical_ms:.0f}ms).",
                source="health",
            ))
        elif avg_latency >= self._latency_warning_ms:
            alerts.append(Alert(
                level="warning",
                title="High Latency",
                message=f"Average latency is {avg_latency:.0f}ms (threshold: {self._latency_warning_ms:.0f}ms).",
                source="health",
            ))

        # Deduplication
        now = time.time()
        deduped = []
        for a in alerts:
            key = f"{a.source}:{a.title}"
            last = self._recent_alerts.get(key, 0)
            if now - last > self._dedup_seconds:
                self._recent_alerts[key] = now
                deduped.append(a)
            # Cleanup old entries
            for k in list(self._recent_alerts.keys()):
                if now - self._recent_alerts[k] > self._dedup_seconds * 2:
                    del self._recent_alerts[k]

        return deduped


class DiagnosticScheduler:
    """诊断调度器 — 定时运行诊断收集并推送告警"""

    def __init__(
        self,
        interval_seconds: float = 300.0,
        on_alert: Optional[Callable[[Alert], Any]] = None,
        run_once: bool = False,
        store: Any = None,
    ):
        self._interval = max(10.0, interval_seconds)
        self._on_alert = on_alert
        self._run_once = run_once
        self._store = store
        self._task: Optional[asyncio.Task] = None
        self._stopped = asyncio.Event()
        self._engine = AlertRuleEngine()

    async def run(self) -> None:
        """主循环"""
        logger.info("DiagnosticScheduler 启动，间隔 %.0fs", self._interval)
        while not self._stopped.is_set():
            try:
                await self._tick()
            except Exception as e:
                logger.warning("DiagnosticScheduler tick 失败: %s", e)
            if self._run_once:
                break
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass
        logger.info("DiagnosticScheduler 停止")

    async def _tick(self) -> None:
        """单次巡检"""
        from nexusagent.diagnostics import collect_health, collect_connectivity, collect_modules

        health = await collect_health()
        connectivity = await collect_connectivity()
        modules = await collect_modules()

        alerts = self._engine.evaluate(health, connectivity, modules)
        if alerts:
            if self._on_alert:
                for alert in alerts:
                    try:
                        self._on_alert(alert)
                    except Exception as e:
                        logger.warning("告警回调失败: %s", e)
            # Persist alerts
            if self._store:
                try:
                    import asyncio
                    for alert in alerts:
                        await asyncio.to_thread(self._store.save_alert, alert)
                except Exception as e:
                    logger.warning("告警持久化失败: %s", e)

        # Persist snapshots for history trending
        if self._store:
            try:
                import asyncio
                await asyncio.to_thread(self._store.save_snapshot, "health", health, len(alerts))
                await asyncio.to_thread(self._store.save_snapshot, "connectivity", connectivity, 0)
                await asyncio.to_thread(self._store.save_snapshot, "modules", modules, 0)
                await asyncio.to_thread(self._store.cleanup, 30)
                await asyncio.to_thread(self._store.cleanup_alerts, 90)
            except Exception as e:
                logger.warning("诊断快照持久化失败: %s", e)

    async def stop(self) -> None:
        """停止调度器"""
        self._stopped.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def start_in_background(self) -> None:
        """在后台启动调度器（ convenience 方法）"""
        self._task = asyncio.create_task(self.run())
