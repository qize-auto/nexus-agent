"""
Phase 3 — 健康监控 + 模型路由集成测试
"""

import asyncio

import pytest

from nexusagent.models.health_monitor import HealthMonitor, BackendHealth
from nexusagent.models.router import ModelRouter


# ── HealthMonitor ─────────────────────────────────────────────────

def test_record_success():
    hm = HealthMonitor()
    hm.record_request("deepseek-chat", latency_ms=100, success=True, tokens_used=50)
    health = hm.get_health("deepseek-chat")
    assert health.total_requests == 1
    assert health.success_requests == 1
    assert health.error_requests == 0
    assert health.is_healthy is True


def test_record_failure():
    hm = HealthMonitor()
    hm.record_request("deepseek-chat", latency_ms=100, success=False, error="timeout")
    health = hm.get_health("deepseek-chat")
    assert health.total_requests == 1
    assert health.error_requests == 1
    assert health.last_error == "timeout"
    assert health.is_healthy is False  # 1/1 = 1.0 >= 0.3 threshold


def test_error_rate_threshold():
    hm = HealthMonitor(error_threshold=0.3)
    for _ in range(7):
        hm.record_request("deepseek-chat", latency_ms=100, success=False, error="err")
    for _ in range(3):
        hm.record_request("deepseek-chat", latency_ms=100, success=True)
    health = hm.get_health("deepseek-chat")
    assert health.error_rate == 0.7
    assert health.is_healthy is False


def test_latency_threshold():
    hm = HealthMonitor(latency_threshold_ms=500)
    hm.record_request("deepseek-chat", latency_ms=600, success=True)
    health = hm.get_health("deepseek-chat")
    assert health.p99_latency_ms == 600
    assert health.is_healthy is False


def test_get_healthy_backends():
    hm = HealthMonitor()
    hm.record_request("a", latency_ms=100, success=True)
    hm.record_request("b", latency_ms=100, success=False, error="err")
    healthy = hm.get_healthy_backends()
    assert "a" in healthy
    assert "b" not in healthy


def test_get_best_backend():
    hm = HealthMonitor()
    hm.record_request("a", latency_ms=200, success=True)
    hm.record_request("b", latency_ms=100, success=True)
    best = hm.get_best_backend(["a", "b"])
    assert best == "b"


def test_get_best_backend_no_data():
    hm = HealthMonitor()
    best = hm.get_best_backend(["a", "b"])
    assert best == "a"


def test_reset():
    hm = HealthMonitor()
    hm.record_request("a", latency_ms=100, success=True)
    hm.reset("a")
    health = hm.get_health("a")
    assert health.total_requests == 0


def test_to_dict():
    hm = HealthMonitor()
    hm.record_request("a", latency_ms=150, success=True)
    d = hm.get_health("a").to_dict()
    assert d["name"] == "a"
    assert d["total_requests"] == 1
    assert d["error_rate"] == 0.0
    assert d["is_healthy"] is True


def test_latency_properties():
    hm = HealthMonitor()
    for i in range(1, 101):
        hm.record_request("a", latency_ms=float(i), success=True)
    health = hm.get_health("a")
    assert health.avg_latency_ms == pytest.approx(50.5, 0.1)
    assert health.p99_latency_ms == 100.0


# ── ModelRouter + HealthMonitor integration ───────────────────────

def test_router_with_healthy_monitor():
    hm = HealthMonitor()
    hm.record_request("deepseek-chat", latency_ms=100, success=True)
    router = ModelRouter(health_monitor=hm)
    model = router.route("hello")
    assert model == "deepseek-chat"


def test_router_with_unhealthy_preferred():
    hm = HealthMonitor(error_threshold=0.3)
    for _ in range(10):
        hm.record_request("deepseek-chat", latency_ms=100, success=False, error="err")
    hm.record_request("deepseek-v4-pro", latency_ms=100, success=True)
    router = ModelRouter(health_monitor=hm)
    model = router.route("分析这个复杂问题")
    assert model == "deepseek-v4-pro"


def test_router_no_health_monitor():
    router = ModelRouter(health_monitor=None)
    model = router.route("hello")
    assert model == "deepseek-chat"


def test_router_pii_ignores_health():
    hm = HealthMonitor()
    hm.record_request("deepseek-chat", latency_ms=100, success=False, error="err")
    router = ModelRouter(health_monitor=hm)
    model = router.route("hello", has_pii=True)
    assert model == "local"


def test_router_long_content_ignores_health():
    hm = HealthMonitor()
    hm.record_request("deepseek-v4-pro", latency_ms=100, success=False, error="err")
    router = ModelRouter(health_monitor=hm)
    model = router.route("x" * 10001)
    assert model == "deepseek-v4-pro"


@pytest.mark.asyncio
async def test_complete_with_fallback_records_health():
    hm = HealthMonitor()
    router = ModelRouter(health_monitor=hm)

    class _FakeBackend:
        async def complete(self, messages, tools=None, temperature=0.7):
            return {"content": "ok", "usage": {"total_tokens": 50}}

    backends = {"deepseek-chat": _FakeBackend()}
    result = await router.complete_with_fallback(
        backends, [{"role": "user", "content": "hi"}]
    )
    assert result["content"] == "ok"
    health = hm.get_health("deepseek-chat")
    assert health.total_requests == 1
    assert health.success_requests == 1


@pytest.mark.asyncio
async def test_complete_with_fallback_records_failure():
    hm = HealthMonitor()
    router = ModelRouter(health_monitor=hm)

    class _FailBackend:
        async def complete(self, messages, tools=None, temperature=0.7):
            raise RuntimeError("boom")

    class _OkBackend:
        async def complete(self, messages, tools=None, temperature=0.7):
            return {"content": "fallback", "usage": {"total_tokens": 10}}

    backends = {
        "deepseek-chat": _FailBackend(),
        "deepseek-v4-pro": _OkBackend(),
    }
    result = await router.complete_with_fallback(
        backends, [{"role": "user", "content": "hi"}]
    )
    assert result["content"] == "fallback"
    assert result["_model_used"] == "deepseek-v4-pro"
    # 检查 health 记录
    health = hm.get_health("deepseek-chat")
    assert health.error_requests == 1
    assert health.last_error == "boom"


@pytest.mark.asyncio
async def test_complete_with_fallback_all_fail():
    hm = HealthMonitor()
    router = ModelRouter(health_monitor=hm)

    class _FailBackend:
        async def complete(self, messages, tools=None, temperature=0.7):
            raise RuntimeError("fail")

    backends = {"deepseek-chat": _FailBackend()}
    result = await router.complete_with_fallback(
        backends, [{"role": "user", "content": "hi"}]
    )
    assert "所有模型均不可用" in result["content"]
    assert result["_model_used"] == "none"
    health = hm.get_health("deepseek-chat")
    assert health.error_requests == 1
