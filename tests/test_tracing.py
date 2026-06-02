"""
NexusAgent v4.0+ — 可观测性测试
覆盖: TraceCollector, MetricsCollector, AutoTracer
"""

import asyncio
import pytest

from nexusagent.observability.tracing import (
    ExecutionTrace,
    StepTrace,
    TraceCollector,
    trace_collector,
    build_on_step_callback,
)
from nexusagent.observability.metrics import MetricsCollector, metrics_collector
from nexusagent.observability.auto_tracer import trace_span, get_current_span, SimpleSpan


class TestTraceCollector:
    """轨迹收集器测试"""

    @pytest.fixture(autouse=True)
    def reset_collector(self):
        trace_collector.clear()
        yield
        trace_collector.clear()

    @pytest.mark.asyncio
    async def test_start_and_finish_trace(self):
        trace = trace_collector.start_trace("t1", tenant_id="acme")
        assert trace.thread_id == "t1"
        assert trace.tenant_id == "acme"

        trace_collector.record_step_start("t1", "node_a", 1)
        await asyncio.sleep(0.01)
        trace_collector.record_step_end("t1", {"key": "value"})

        trace_collector.finish_trace("t1", final_state={"result": "ok"})

        finished = trace_collector.get_trace("t1")
        assert finished is not None
        assert finished.end_time > 0
        assert len(finished.steps) == 1
        assert finished.steps[0].node_name == "node_a"
        assert finished.steps[0].latency_ms > 0

    @pytest.mark.asyncio
    async def test_multiple_steps(self):
        trace_collector.start_trace("t2")
        for i in range(3):
            trace_collector.record_step_start("t2", f"node_{i}", i + 1)
            await asyncio.sleep(0.01)
            trace_collector.record_step_end("t2", {"i": i})

        trace_collector.finish_trace("t2")
        trace = trace_collector.get_trace("t2")
        assert len(trace.steps) == 3

    def test_list_traces(self):
        trace_collector.start_trace("t3")
        trace_collector.finish_trace("t3")
        trace_collector.start_trace("t4")
        trace_collector.finish_trace("t4")

        traces = trace_collector.list_traces(limit=10)
        assert len(traces) == 2

    def test_get_metrics(self):
        trace_collector.start_trace("t5")
        trace_collector.record_step_start("t5", "n", 1)
        trace_collector.record_step_end("t5", {})
        trace_collector.finish_trace("t5")

        metrics = trace_collector.get_metrics()
        assert metrics["total_traces"] == 1
        assert metrics["completed_traces"] == 1
        assert metrics["error_rate"] == 0.0
        assert metrics["avg_steps"] == 1.0

    def test_trace_to_dict(self):
        trace = ExecutionTrace(
            thread_id="t6",
            steps=[StepTrace(node_name="n", iteration=1, start_time=1.0, end_time=2.0, latency_ms=1000.0)],
        )
        d = trace.to_dict()
        assert d["thread_id"] == "t6"
        assert d["step_count"] == 1
        assert d["steps"][0]["latency_ms"] == 1000.0


class TestMetricsCollector:
    """指标收集器测试"""

    def test_record_request(self):
        m = MetricsCollector()
        m.record_request(latency_ms=150.0, success=True, session_id="s1")
        m.record_request(latency_ms=200.0, success=False, session_id="s2")

        snapshot = m.snapshot()
        assert snapshot.requests_total == 2
        assert snapshot.requests_success == 1
        assert snapshot.requests_error == 1
        assert snapshot.avg_latency_ms == 175.0
        assert snapshot.active_sessions == 2

    def test_security_interception(self):
        m = MetricsCollector()
        m.record_security_interception()
        m.record_security_interception()
        assert m.snapshot().security_interceptions == 2

    def test_token_usage(self):
        m = MetricsCollector()
        m.record_tokens(100)
        m.record_tokens(200)
        assert m.snapshot().token_usage_total == 300

    def test_empty_snapshot(self):
        m = MetricsCollector()
        s = m.snapshot()
        assert s.requests_total == 0
        assert s.avg_latency_ms == 0.0


class TestAutoTracer:
    """自动追踪装饰器测试"""

    @pytest.mark.asyncio
    async def test_trace_span_async(self):
        @trace_span("test.async_op")
        async def async_op():
            span = get_current_span()
            assert span is not None
            assert span.name == "test.async_op"
            span.set_attribute("key", "value")
            return "result"

        result = await async_op()
        assert result == "result"

    def test_trace_span_sync(self):
        @trace_span("test.sync_op")
        def sync_op():
            span = get_current_span()
            assert span is not None
            span.set_attribute("sync", True)
            return 42

        result = sync_op()
        assert result == 42

    @pytest.mark.asyncio
    async def test_trace_span_error(self):
        @trace_span("test.error_op")
        async def error_op():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await error_op()

    def test_simple_span_to_dict(self):
        span = SimpleSpan("root")
        span.set_attribute("a", 1)
        child = SimpleSpan("child", parent=span)
        child.set_attribute("b", 2)
        child.end()
        span.end()

        d = span.to_dict()
        assert d["name"] == "root"
        assert d["attributes"]["a"] == 1
        assert len(d["children"]) == 1
        assert d["children"][0]["name"] == "child"
        assert "duration_ms" in d

    @pytest.mark.asyncio
    async def test_nested_spans(self):
        @trace_span("outer")
        async def outer():
            @trace_span("inner")
            async def inner():
                return get_current_span().name
            return await inner()

        result = await outer()
        assert result == "inner"


class TestBuildOnStepCallback:
    """on_step 回调构建测试"""

    @pytest.fixture(autouse=True)
    def reset_collector(self):
        trace_collector.clear()
        yield
        trace_collector.clear()

    @pytest.mark.asyncio
    async def test_on_step_callback_records_steps(self):
        from nexusagent.execution.state_graph import StateGraph, END, RunConfig

        async def step1(state):
            return {"s": 1}

        async def step2(state):
            return {"s": 2}

        g = StateGraph()
        g.add_node("s1", step1)
        g.add_node("s2", step2)
        g.set_entry_point("s1")
        g.add_edge("s1", "s2")
        g.add_edge("s2", END)
        compiled = g.compile()

        callback = build_on_step_callback("thread_onstep")
        await compiled.ainvoke({}, config=RunConfig(thread_id="thread_onstep", on_step=callback))

        trace = trace_collector.get_trace("thread_onstep")
        assert trace is not None
        assert len(trace.steps) >= 1
