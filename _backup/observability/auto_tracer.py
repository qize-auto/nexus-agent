"""
NexusAgent v4.0+ — 自动 OpenTelemetry 追踪装饰器

设计参考:
- PydanticAI Logfire: https://docs.pydantic.dev/logfire/
  "Zero-config OpenTelemetry instrumentation for Python"

使用方式:
    @trace_span("agent.execute")
    async def execute(self, ...):
        ...
"""

from __future__ import annotations

import functools
import inspect
import logging
import time
from typing import Any, Callable, Optional

logger = logging.getLogger("nexus.observability.auto_tracer")


class SimpleSpan:
    """轻量 Span 实现（无需外部 OTel SDK 依赖）"""

    def __init__(self, name: str, parent: Optional["SimpleSpan"] = None):
        self.name = name
        self.parent = parent
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.attributes: dict = {}
        self.children: list = []
        self._active = True

        if parent:
            parent.children.append(self)

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def end(self) -> None:
        self.end_time = time.time()
        self._active = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": (self.end_time - self.start_time) * 1000 if self.end_time else None,
            "attributes": self.attributes,
            "children": [c.to_dict() for c in self.children],
        }


# 当前活跃 Span 栈（thread-local 简化版）
_current_span: Optional[SimpleSpan] = None


def get_current_span() -> Optional[SimpleSpan]:
    return _current_span


def trace_span(name: str):
    """
    自动追踪装饰器

    为 async/sync 函数自动创建 Span，记录执行时间和属性。

    Usage:
        @trace_span("llm.complete")
        async def complete(self, messages):
            span = get_current_span()
            span.set_attribute("model", self._model)
            ...
    """
    def decorator(func: Callable) -> Callable:
        is_async = inspect.iscoroutinefunction(func)

        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                global _current_span
                parent = _current_span
                span = SimpleSpan(name=name, parent=parent)
                _current_span = span

                try:
                    result = await func(*args, **kwargs)
                    span.set_attribute("status", "ok")
                    return result
                except Exception as e:
                    span.set_attribute("status", "error")
                    span.set_attribute("error", str(e))
                    raise
                finally:
                    span.end()
                    _current_span = parent

            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                global _current_span
                parent = _current_span
                span = SimpleSpan(name=name, parent=parent)
                _current_span = span

                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("status", "ok")
                    return result
                except Exception as e:
                    span.set_attribute("status", "error")
                    span.set_attribute("error", str(e))
                    raise
                finally:
                    span.end()
                    _current_span = parent

            return sync_wrapper

    return decorator
