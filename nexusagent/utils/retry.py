"""
NexusAgent v3.3 — 指数退避重试工具
补全: NFR-082
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
import time
from typing import Any, Callable, Optional, Type, TypeVar, Union

logger = logging.getLogger("nexus.utils.retry")

T = TypeVar("T")


def exponential_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 30.0,
    jitter: bool = True,
    retryable_exceptions: tuple = (Exception,),
):
    """
    指数退避重试装饰器
    公式: delay = min(base_delay * backoff_factor^attempt + jitter, max_delay)

    Args:
        max_retries: 最大重试次数（不含首次尝试）
        base_delay: 基础延迟秒数
        backoff_factor: 退避因子
        max_delay: 最大延迟上限
        jitter: 是否添加随机抖动
        retryable_exceptions: 可重试的异常类型
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_error = e
                    if attempt < max_retries:
                        delay = base_delay * (backoff_factor ** attempt)
                        if jitter:
                            delay *= 0.5 + random.random()
                        delay = min(delay, max_delay)
                        logger.debug(
                            "重试 %s: 尝试%d/%d, 等待%.1fs: %s",
                            func.__name__, attempt + 1, max_retries, delay, e,
                        )
                        await asyncio.sleep(delay)
            raise last_error  # type: ignore

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_error = e
                    if attempt < max_retries:
                        delay = base_delay * (backoff_factor ** attempt)
                        if jitter:
                            delay *= 0.5 + random.random()
                        delay = min(delay, max_delay)
                        logger.debug(
                            "重试 %s: 尝试%d/%d, 等待%.1fs: %s",
                            func.__name__, attempt + 1, max_retries, delay, e,
                        )
                        time.sleep(delay)
            raise last_error  # type: ignore

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


async def retry_async(
    coro_factory: Callable[[], Any],
    max_retries: int = 3,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 30.0,
    jitter: bool = True,
    retryable_exceptions: tuple = (Exception,),
    max_total_timeout: Optional[float] = None,
) -> Any:
    """
    异步指数退避重试（函数式接口）

    用法:
        result = await retry_async(lambda: api_call(), max_retries=3)

    Notes:
        - 默认 retryable_exceptions=(Exception,) 不捕获 KeyboardInterrupt/SystemExit
        - max_total_timeout 限制整体重试耗时，超时抛 asyncio.TimeoutError
    """
    last_error = None
    start = time.monotonic()
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except retryable_exceptions as e:
            last_error = e
            if attempt < max_retries:
                delay = base_delay * (backoff_factor ** attempt)
                if jitter:
                    delay *= 0.5 + random.random()
                delay = min(delay, max_delay)
                # 检查总超时
                if max_total_timeout is not None:
                    elapsed = time.monotonic() - start
                    if elapsed + delay > max_total_timeout:
                        raise asyncio.TimeoutError(
                            f"重试总耗时超过 {max_total_timeout}s (已用 {elapsed:.1f}s)"
                        ) from e
                logger.debug(
                    "重试 %s: 尝试%d/%d, 等待%.1fs: %s",
                    coro_factory.__name__ if hasattr(coro_factory, "__name__") else "coro",
                    attempt + 1, max_retries, delay, e,
                )
                await asyncio.sleep(delay)
    raise last_error  # type: ignore
