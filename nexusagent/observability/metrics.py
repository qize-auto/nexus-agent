"""
NexusAgent v4.0+ — 聚合指标收集器

为 Dashboard API 提供结构化指标数据。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class MetricsSnapshot:
    """指标快照"""
    timestamp: float
    requests_total: int = 0
    requests_success: int = 0
    requests_error: int = 0
    avg_latency_ms: float = 0.0
    active_sessions: int = 0
    security_interceptions: int = 0
    token_usage_total: int = 0


class MetricsCollector:
    """轻量级内存指标收集器"""

    def __init__(self):
        self._requests: List[Dict[str, Any]] = []
        self._security_events: int = 0
        self._token_usage: int = 0
        self._sessions: set = set()

    def record_request(self, latency_ms: float, success: bool, session_id: str = "") -> None:
        self._requests.append({
            "timestamp": time.time(),
            "latency_ms": latency_ms,
            "success": success,
        })
        if session_id:
            self._sessions.add(session_id)
        # 保留最近 1000 条
        if len(self._requests) > 1000:
            self._requests = self._requests[-1000:]

    def record_security_interception(self) -> None:
        self._security_events += 1

    def record_tokens(self, tokens: int) -> None:
        self._token_usage += tokens

    def snapshot(self) -> MetricsSnapshot:
        recent = [r for r in self._requests if time.time() - r["timestamp"] < 3600]
        latencies = [r["latency_ms"] for r in recent]
        successes = sum(1 for r in recent if r["success"])
        errors = len(recent) - successes

        return MetricsSnapshot(
            timestamp=time.time(),
            requests_total=len(recent),
            requests_success=successes,
            requests_error=errors,
            avg_latency_ms=sum(latencies) / len(latencies) if latencies else 0.0,
            active_sessions=len(self._sessions),
            security_interceptions=self._security_events,
            token_usage_total=self._token_usage,
        )


metrics_collector = MetricsCollector()
