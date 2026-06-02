"""
NexusAgent v4.0+ — 执行轨迹收集与可观测性

设计参考:
- LangSmith Trace: https://docs.smith.langchain.com/tracing
  "Traces are the fundamental unit in LangSmith... each step is a Run"
- OpenTelemetry Span: https://opentelemetry.io/docs/concepts/signals/traces/
  "A span represents a unit of work or operation"

职责:
    1. 收集 StateGraph/ReActEngine 的执行轨迹
    2. 聚合延迟、token 消耗、审查拦截率等指标
    3. 为 Dashboard API 提供数据源
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from nexusagent.execution.state_graph import StateType

logger = logging.getLogger("nexus.observability.tracing")


@dataclass
class StepTrace:
    """单步执行轨迹"""
    node_name: str
    iteration: int
    start_time: float
    end_time: float = 0.0
    latency_ms: float = 0.0
    error: Optional[str] = None
    state_keys: List[str] = field(default_factory=list)


@dataclass
class ExecutionTrace:
    """完整执行轨迹"""
    thread_id: str
    tenant_id: str = "default"
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    total_latency_ms: float = 0.0
    steps: List[StepTrace] = field(default_factory=list)
    final_state_keys: List[str] = field(default_factory=list)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "thread_id": self.thread_id,
            "tenant_id": self.tenant_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_latency_ms": self.total_latency_ms,
            "step_count": len(self.steps),
            "steps": [
                {
                    "node_name": s.node_name,
                    "iteration": s.iteration,
                    "latency_ms": s.latency_ms,
                    "error": s.error,
                }
                for s in self.steps
            ],
            "error": self.error,
        }


class TraceCollector:
    """
    执行轨迹收集器 — 单例模式

    使用方式:
        collector = TraceCollector()
        trace = collector.start_trace(thread_id="t1", tenant_id="acme")

        # 在 StateGraph on_step 回调中使用
        async def on_step(node_name, state, iteration):
            collector.record_step(node_name, iteration)

        # 执行完成后
        collector.finish_trace(trace.thread_id)
    """

    def __init__(self):
        self._traces: Dict[str, ExecutionTrace] = {}
        self._current_step: Dict[str, StepTrace] = {}

    def start_trace(self, thread_id: str, tenant_id: str = "default", metadata: Optional[Dict[str, Any]] = None) -> ExecutionTrace:
        """开始收集一条执行轨迹"""
        trace = ExecutionTrace(
            thread_id=thread_id,
            tenant_id=tenant_id,
            start_time=time.time(),
            metadata=metadata or {},
        )
        self._traces[thread_id] = trace
        logger.debug("Trace 开始收集: thread_id=%s", thread_id)
        return trace

    def record_step_start(self, thread_id: str, node_name: str, iteration: int) -> None:
        """记录步骤开始"""
        step = StepTrace(
            node_name=node_name,
            iteration=iteration,
            start_time=time.time(),
        )
        self._current_step[thread_id] = step

    def record_step_end(self, thread_id: str, state: StateType, error: Optional[str] = None) -> None:
        """记录步骤结束"""
        step = self._current_step.pop(thread_id, None)
        if not step:
            return

        step.end_time = time.time()
        step.latency_ms = (step.end_time - step.start_time) * 1000
        step.error = error
        step.state_keys = [k for k in state.keys() if not k.startswith("__")]

        trace = self._traces.get(thread_id)
        if trace:
            trace.steps.append(step)

    def finish_trace(self, thread_id: str, final_state: Optional[StateType] = None, error: Optional[str] = None) -> Optional[ExecutionTrace]:
        """完成轨迹收集"""
        trace = self._traces.get(thread_id)
        if not trace:
            return None

        trace.end_time = time.time()
        trace.total_latency_ms = (trace.end_time - trace.start_time) * 1000
        trace.error = error
        if final_state:
            trace.final_state_keys = [k for k in final_state.keys() if not k.startswith("__")]

        logger.debug(
            "Trace 完成: thread_id=%s, steps=%d, latency=%.2fms",
            thread_id, len(trace.steps), trace.total_latency_ms,
        )
        return trace

    def get_trace(self, thread_id: str) -> Optional[ExecutionTrace]:
        """获取指定轨迹"""
        return self._traces.get(thread_id)

    def list_traces(self, limit: int = 100) -> List[ExecutionTrace]:
        """列出最近轨迹（按结束时间倒序）"""
        traces = sorted(
            self._traces.values(),
            key=lambda t: t.end_time or t.start_time,
            reverse=True,
        )
        return traces[:limit]

    def get_metrics(self) -> Dict[str, Any]:
        """聚合指标"""
        traces = list(self._traces.values())
        if not traces:
            return {}

        completed = [t for t in traces if t.end_time > 0]
        latencies = [t.total_latency_ms for t in completed]
        errors = [t for t in completed if t.error]
        step_counts = [len(t.steps) for t in completed]

        return {
            "total_traces": len(traces),
            "completed_traces": len(completed),
            "error_count": len(errors),
            "error_rate": len(errors) / len(completed) if completed else 0.0,
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
            "max_latency_ms": max(latencies) if latencies else 0.0,
            "avg_steps": sum(step_counts) / len(step_counts) if step_counts else 0.0,
        }

    def clear(self) -> None:
        """清空所有轨迹"""
        self._traces.clear()
        self._current_step.clear()


# 全局收集器实例
trace_collector = TraceCollector()


def build_on_step_callback(thread_id: str):
    """
    为 StateGraph RunConfig.on_step 构建回调函数

    Usage:
        config = RunConfig(
            thread_id="t1",
            on_step=build_on_step_callback("t1"),
        )
    """
    collector = trace_collector
    collector.start_trace(thread_id)

    async def on_step(node_name: str, state: StateType, iteration: int) -> None:
        # 结束上一步
        collector.record_step_end(thread_id, state)
        # 开始新一步
        collector.record_step_start(thread_id, node_name, iteration)

    return on_step
