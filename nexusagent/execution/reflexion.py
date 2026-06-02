"""
NexusAgent v4.0+ — 自我反思节点 (Reflexion)

设计参考:
- Reflexion: Self-Reflective Agents: https://arxiv.org/abs/2303.11366
  "Agents reflect on task feedback signals and maintain their own reflective text"
- MetaGPT AFlow (ICLR 2025): https://arxiv.org/abs/2405.04232
  "Experience learning automatically optimizes workflows"

职责:
    在节点执行失败后，分析错误原因，生成反思报告，决定重试策略或降级路径
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from nexusagent.execution.state_graph import END, StateGraph, StateType

logger = logging.getLogger("nexus.execution.reflexion")


@dataclass
class ReflectionReport:
    """反思报告"""
    error_node: str
    error_message: str
    root_cause: str
    suggested_fix: str
    should_retry: bool
    retry_strategy: str = ""  # retry_same | retry_alternative | abort
    confidence: float = 0.5


class ReflexionNode:
    """
    自我反思节点

    Usage:
        # 在 StateGraph 中使用
        graph.add_node("reflexion", reflexion_node.func)
        graph.add_conditional_edges("reflexion", route_after_reflexion, {
            "retry": "original_node",
            "abort": END,
        })
    """

    def __init__(self, llm_backend: Optional[Any] = None):
        self._llm = llm_backend

    async def reflect(
        self,
        error_node: str,
        error: Exception,
        state: StateType,
        history: List[Dict[str, Any]],
    ) -> ReflectionReport:
        """
        生成反思报告

        Args:
            error_node: 失败的节点名
            error: 异常对象
            state: 当前状态
            history: 执行历史

        Returns:
            ReflectionReport
        """
        error_msg = str(error)
        error_type = type(error).__name__

        # 基于规则的分析（不依赖 LLM）
        root_cause, strategy = self._rule_based_analysis(error_type, error_msg)

        # 如果有 LLM，生成更深入的反思
        if self._llm:
            try:
                llm_reflection = await self._llm_reflect(error_node, error_msg, state, history)
                if llm_reflection:
                    return llm_reflection
            except Exception as e:
                logger.warning("LLM 反思失败: %s", e)

        return ReflectionReport(
            error_node=error_node,
            error_message=error_msg,
            root_cause=root_cause,
            suggested_fix="基于规则生成的修复建议",
            should_retry=strategy != "abort",
            retry_strategy=strategy,
            confidence=0.6,
        )

    def _rule_based_analysis(self, error_type: str, error_msg: str) -> tuple:
        """基于错误类型的规则分析"""
        error_lower = error_msg.lower()

        # 网络/超时 → 重试
        if any(kw in error_type.lower() for kw in ("timeout", "connection", "network")):
            return "网络连接不稳定或后端响应超时", "retry_same"

        # 权限/配额 → 切换后端
        if any(kw in error_lower for kw in ("rate limit", "quota", "forbidden", "unauthorized")):
            return "API 配额耗尽或权限不足", "retry_alternative"

        # 格式/验证 → 修复输入
        if any(kw in error_type.lower() for kw in ("validation", "parse", "json", "value")):
            return "输入格式错误或数据验证失败", "retry_same"
        if any(kw in error_lower for kw in ("json", "parse", "invalid format")):
            return "输入格式错误或数据验证失败", "retry_same"

        # 未知/严重 → 中止
        if any(kw in error_type.lower() for kw in ("fatal", "crash", "memory")):
            return "严重系统错误", "abort"

        return f"{error_type}: {error_msg[:100]}", "retry_same"

    async def _llm_reflect(
        self,
        error_node: str,
        error_msg: str,
        state: StateType,
        history: List[Dict[str, Any]],
    ) -> Optional[ReflectionReport]:
        """使用 LLM 生成深度反思"""
        history_text = "\n".join(
            f"- {h.get('node', '?')} (iter={h.get('iteration', '?')})"
            for h in history[-5:]
        )

        prompt = f"""你是一个错误分析专家。请分析以下 Agent 执行失败的原因，并给出修复建议。

失败节点: {error_node}
错误信息: {error_msg}

执行历史:
{history_text}

请用 JSON 格式回复:
{{"root_cause": "...", "suggested_fix": "...", "should_retry": true/false, "retry_strategy": "retry_same|retry_alternative|abort", "confidence": 0.0-1.0}}
"""

        response = await self._llm.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        content = response.get("content", "")

        # 尝试解析 JSON
        import json
        import re
        json_match = re.search(r"\{[^}]+\}", content)
        if json_match:
            data = json.loads(json_match.group())
            return ReflectionReport(
                error_node=error_node,
                error_message=error_msg,
                root_cause=data.get("root_cause", "未知"),
                suggested_fix=data.get("suggested_fix", ""),
                should_retry=data.get("should_retry", True),
                retry_strategy=data.get("retry_strategy", "retry_same"),
                confidence=data.get("confidence", 0.5),
            )
        return None

    async def __call__(self, state: StateType) -> StateType:
        """作为 StateGraph 节点调用"""
        error_info = state.get("__error__", {})
        error_node = error_info.get("node", "unknown")
        error_msg = error_info.get("error", "unknown")
        history = state.get("__history__", [])

        # 构造一个模拟异常（实际使用时应传入真实异常）
        class _FakeError(Exception):
            pass
        fake_error = _FakeError(error_msg)

        report = await self.reflect(error_node, fake_error, state, history)

        return {
            "__reflection__": {
                "error_node": report.error_node,
                "root_cause": report.root_cause,
                "should_retry": report.should_retry,
                "retry_strategy": report.retry_strategy,
            },
        }
