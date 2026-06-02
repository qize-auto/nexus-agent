"""
NexusAgent v0.1.0 — 模型路由层
来源: 设计稿第10章模型策略与成本控制
实现: 三层路由(隐私→能力→上下文) + 多级Fallback链

Compatible wrappers 兼容包装器:
    DeepSeekLLMBackend -> UnifiedLLMBackend(provider="deepseek")
    MoonshotLLMBackend -> UnifiedLLMBackend(provider="moonshot")
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

from nexusagent.models.unified_backend import (
    UnifiedLLMBackend,
    ProviderRegistry,
    provider_registry,
)

logger = logging.getLogger("nexus.models")


def _get_health_monitor() -> Any:
    """懒加载 HealthMonitor — 避免循环导入"""
    try:
        from nexusagent.models.health_monitor import HealthMonitor
        return HealthMonitor
    except ImportError:
        return None


# ═══════════════════════════════════════════════════════════════
# 兼容包装器 (Backward Compatible Wrappers)
# 保留旧类名，底层调用 UnifiedLLMBackend
# ═══════════════════════════════════════════════════════════════

class DeepSeekLLMBackend(UnifiedLLMBackend):
    """
    DeepSeek API 后端 — 兼容旧接口。
    底层实际调用 UnifiedLLMBackend(provider="deepseek").
    """

    def __init__(self, api_key: str = "", model: str = "deepseek-chat"):
        super().__init__(
            provider="deepseek",
            model=model,
            api_key=api_key or os.getenv("DEEPSEEK_API_KEY", ""),
        )


class MoonshotLLMBackend(UnifiedLLMBackend):
    """
    Moonshot (Kimi) API 后端 — 兼容旧接口。
    底层实际调用 UnifiedLLMBackend(provider="moonshot").
    """

    def __init__(self, api_key: str = "", model: str = "moonshot-v1-8k"):
        super().__init__(
            provider="moonshot",
            model=model,
            api_key=api_key or os.getenv("MOONSHOT_API_KEY", ""),
        )


class MockLLMBackend:
    """
    [最佳实践补全] 模拟LLM后端 — 用于开发和测试
    """

    async def complete(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """模拟LLM响应"""
        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = m.get("content", "")
                break

        return {
            "content": f"[MockLLM] Received: {last_user_msg[:100]}...",
            "tool_calls": [],
            "usage": {"total_tokens": 100, "prompt_tokens": 50, "completion_tokens": 50},
            "_model_used": "mock",
            "_provider": "mock",
        }

    async def close(self) -> None:
        pass


# ═══════════════════════════════════════════════════════════════
# ModelRouter — 三层路由
# ═══════════════════════════════════════════════════════════════

class ModelRouter:
    """
    三层模型路由 — 设计稿第10章
    隐私层 → 能力层 → 上下文层

    支持所有已注册的 Provider，自动构建 Fallback 链。
    """

    _DEFAULT_FALLBACK_CHAIN = [
        "deepseek-chat",
        "deepseek-v4-pro",
        "openai/gpt-4o-mini",
        "local",
    ]

    def __init__(self, health_monitor=None):
        self._health_monitor = health_monitor
        self._fallback_chain: List[str] = list(self._DEFAULT_FALLBACK_CHAIN)

    def set_fallback_chain(self, chain: List[str]) -> None:
        """显式设置 Fallback 链（模型标识列表）"""
        self._fallback_chain = list(chain)

    def _get_healthy_chain(self) -> List[str]:
        """获取健康的后端列表，优先返回健康度高的后端"""
        if not self._health_monitor or not self._fallback_chain:
            return self._fallback_chain

        healthy = []
        for name in self._fallback_chain:
            health = self._health_monitor.get_health(name)
            if health.total_requests == 0:
                healthy.append((name, 0.5))
            elif health.is_healthy:
                score = max(0.0, 1.0 - health.error_rate)
                healthy.append((name, score))

        healthy.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in healthy]

    def route(self, content: str, has_pii: bool = False) -> str:
        """
        路由决策 — 设计稿第10章三层路由

        Args:
            content: 用户消息内容
            has_pii: 是否包含PII数据

        Returns:
            str: 选中的模型标识 (格式 "provider/model")
        """
        # 层1: 隐私检查
        if has_pii:
            return "local"

        # 层2: 能力检查 — 基于内容复杂度
        if len(content) > 10000:
            # 长上下文直接返回对应模型，健康检查在 fallback 层处理
            return "deepseek-v4-pro"

        if self._is_complex_query(content):
            candidate = "deepseek-v4-pro"
        else:
            candidate = "deepseek-chat"

        # 层3: 健康检查 — 如果首选不健康，降级到下一个健康后端
        if self._health_monitor:
            for name in self._get_healthy_chain():
                if name == candidate or name == "deepseek-v4-pro":
                    return name
            if self._fallback_chain:
                return self._fallback_chain[0]

        return candidate

    def _is_complex_query(self, content: str) -> bool:
        """判断是否为复杂查询"""
        complex_indicators = [
            "分析", "推理", "为什么", "如何设计",
            "代码", "算法", "架构", "优化",
            "比较", "评估", "重构", "调试",
            "analyze", "reasoning", "why", "how to design",
            "code", "algorithm", "architecture", "optimize",
            "compare", "evaluate", "refactor", "debug",
        ]
        return any(ind in content for ind in complex_indicators)

    def get_fallback(self, current_model: str) -> Optional[str]:
        """获取下一个Fallback模型"""
        try:
            idx = self._fallback_chain.index(current_model)
            if idx + 1 < len(self._fallback_chain):
                return self._fallback_chain[idx + 1]
        except ValueError:
            logger.debug("模型 %s 不在Fallback链中", current_model)
        return None

    async def complete_with_fallback(
        self,
        llm_backends: Dict[str, Any],
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """
        带Fallback链的LLM调用 — 自动降级
        """
        import time

        chain = self._get_healthy_chain()
        current = chain[0] if chain else (self._fallback_chain[0] if self._fallback_chain else None)

        if not current:
            return {
                "content": "[NexusAgent] No LLM backend configured.",
                "tool_calls": [],
                "usage": {"total_tokens": 0},
                "_model_used": "none",
            }

        tried = []
        while current:
            backend = llm_backends.get(current)
            if not backend:
                tried.append(f"{current}: backend not configured")
                current = self.get_fallback(current)
                continue

            start = time.time()
            try:
                response = await backend.complete(messages, tools, temperature)
                latency_ms = (time.time() - start) * 1000

                if self._health_monitor:
                    self._health_monitor.record_request(
                        backend_name=current,
                        latency_ms=latency_ms,
                        success=True,
                        tokens_used=response.get("usage", {}).get("total_tokens", 0),
                    )

                response["_model_used"] = current
                if tried:
                    response["_fallback_tried"] = tried
                return response
            except Exception as e:
                if isinstance(e, asyncio.CancelledError):
                    raise
                latency_ms = (time.time() - start) * 1000
                logger.warning("模型 %s 调用失败: %s", current, e)
                tried.append(f"{current}: {e}")

                if self._health_monitor:
                    self._health_monitor.record_request(
                        backend_name=current,
                        latency_ms=latency_ms,
                        success=False,
                        error=str(e),
                    )

                current = self.get_fallback(current)

        return {
            "content": f"[NexusAgent] 所有模型均不可用。已尝试: {', '.join(tried)}",
            "tool_calls": [],
            "usage": {"total_tokens": 0},
            "_model_used": "none",
            "_fallback_tried": tried,
        }
