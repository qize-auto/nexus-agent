"""
NexusAgent v4.0+ — 模型健康监控

职责:
    1. 跟踪每个 LLM 后端的延迟、错误率、成本
    2. 为 ModelRouter 提供健康指标，支持动态加权路由
    3. 自动标记故障后端，触发降级
"""

from __future__ import annotations

import logging
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nexus.models.health")


@dataclass
class BackendHealth:
    """后端健康状态"""
    name: str
    total_requests: int = 0
    success_requests: int = 0
    error_requests: int = 0
    latencies_ms: List[float] = field(default_factory=list)
    last_error: Optional[str] = None
    last_success_time: float = 0.0
    last_error_time: float = 0.0
    avg_cost_per_1k: float = 0.0
    is_healthy: bool = True

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.error_requests / self.total_requests

    @property
    def p99_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_latencies = sorted(self.latencies_ms)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    @property
    def avg_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return statistics.mean(self.latencies_ms)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "total_requests": self.total_requests,
            "error_rate": round(self.error_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "p99_latency_ms": round(self.p99_latency_ms, 2),
            "is_healthy": self.is_healthy,
            "last_error": self.last_error,
        }


class HealthMonitor:
    """
    健康监控器

    Usage:
        monitor = HealthMonitor()
        monitor.record_request("deepseek-chat", latency_ms=150, success=True)
        monitor.record_request("deepseek-chat", latency_ms=2000, success=False, error="timeout")

        health = monitor.get_health("deepseek-chat")
        if not health.is_healthy:
            # 触发降级
            ...
    """

    def __init__(self, error_threshold: float = 0.3, latency_threshold_ms: float = 5000.0):
        self._backends: Dict[str, BackendHealth] = {}
        self._error_threshold = error_threshold
        self._latency_threshold_ms = latency_threshold_ms

    def record_request(
        self,
        backend_name: str,
        latency_ms: float,
        success: bool,
        error: Optional[str] = None,
        tokens_used: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """记录一次请求结果"""
        health = self._backends.setdefault(backend_name, BackendHealth(name=backend_name))
        health.total_requests += 1

        if success:
            health.success_requests += 1
            health.last_success_time = time.time()
            health.latencies_ms.append(latency_ms)
            # 保留最近 100 条延迟记录
            if len(health.latencies_ms) > 100:
                health.latencies_ms = health.latencies_ms[-100:]
        else:
            health.error_requests += 1
            health.last_error = error
            health.last_error_time = time.time()

        # 更新健康状态
        health.is_healthy = (
            health.error_rate < self._error_threshold
            and health.p99_latency_ms < self._latency_threshold_ms
        )

    def get_health(self, backend_name: str) -> BackendHealth:
        return self._backends.get(backend_name, BackendHealth(name=backend_name))

    def get_all_health(self) -> Dict[str, BackendHealth]:
        return dict(self._backends)

    def get_healthy_backends(self) -> List[str]:
        """返回健康的后端列表"""
        return [name for name, h in self._backends.items() if h.is_healthy]

    def get_best_backend(self, candidates: List[str]) -> Optional[str]:
        """从候选列表中选择最佳后端（最低 p99 延迟）"""
        healthy = [c for c in candidates if c in self._backends and self._backends[c].is_healthy]
        if not healthy:
            return candidates[0] if candidates else None
        return min(healthy, key=lambda c: self._backends[c].p99_latency_ms)

    def reset(self, backend_name: str) -> None:
        """重置指定后端的健康状态"""
        if backend_name in self._backends:
            self._backends[backend_name] = BackendHealth(name=backend_name)


# 全局监控器
_health_monitor = HealthMonitor()


def get_health_monitor() -> HealthMonitor:
    return _health_monitor
