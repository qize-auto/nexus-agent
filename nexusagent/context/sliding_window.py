"""
NexusAgent v4.0+ — Sliding Window 智能上下文管理

设计参考:
- Anthropic Context Caching: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
  "Cache frequently used context to reduce latency and cost"
- OpenAI Token Management: "Truncate, summarize, or filter to fit context limit"
- LangChain ConversationBufferWindowMemory: "Keep last K interactions"

职责:
    1. 管理对话上下文窗口，确保不超过 LLM 的 token 限制
    2. 支持多种压缩策略: 截断 / 总结 / 语义重要性
    3. Token 计数（近似）
    4. 与 LLM 调用集成：自动在调用前压缩上下文

Usage:
    from nexusagent.context.sliding_window import SlidingWindow, Message, WindowStrategy
    window = SlidingWindow(max_tokens=4000, strategy=WindowStrategy.SUMMARIZE)
    window.add_message(Message(role="user", content="你好"))
    context = window.get_context()
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("nexus.context.sliding_window")


class WindowStrategy(str, Enum):
    """上下文压缩策略"""
    TRUNCATE = "truncate"      # 简单截断，保留最近 N 条
    SUMMARIZE = "summarize"    # 自动总结旧消息
    SEMANTIC = "semantic"      # 基于语义重要性保留


@dataclass
class Message:
    """上下文消息"""
    role: str  # system | user | assistant | tool
    content: str
    tokens: Optional[int] = None  # 预计算的 token 数
    importance: float = 0.5       # 0-1 重要性评分
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def estimate_tokens(self) -> int:
        """近似 token 计数"""
        if self.tokens is not None:
            return self.tokens
        text = self.content
        # 简单启发式：中文字符 ≈ 1 token，英文单词 ≈ 1.3 tokens
        # 标点符号和空格单独计算
        import re
        cn_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        en_words = len(re.findall(r"[a-zA-Z]+", text))
        others = len(text) - cn_chars - sum(len(w) for w in re.findall(r"[a-zA-Z]+", text))
        # others 中包含标点、数字、空格等，近似 0.5 token/字符
        total = cn_chars + int(en_words * 1.3) + int(others * 0.5)
        self.tokens = max(1, total)
        return self.tokens


@dataclass
class SummaryEntry:
    """摘要条目"""
    original_range: tuple  # (start_index, end_index)
    summary: str
    tokens: int


class SlidingWindow:
    """
    Sliding Window — 智能上下文管理

    Args:
        max_tokens: 窗口最大 token 数
        strategy: 压缩策略
        max_messages: 最大消息数（可选）
        reserve_tokens: 为回复预留的 token 数
        summarizer: 总结函数（SUMMARIZE 策略必需）
    """

    def __init__(
        self,
        max_tokens: int = 4000,
        strategy: WindowStrategy = WindowStrategy.TRUNCATE,
        max_messages: Optional[int] = None,
        reserve_tokens: int = 1000,
        summarizer: Optional[Callable[[List[Message]], str]] = None,
    ):
        self.max_tokens = max_tokens
        self.strategy = strategy
        self.max_messages = max_messages
        self.reserve_tokens = reserve_tokens
        self._summarizer = summarizer
        self._messages: List[Message] = []
        self._summaries: List[SummaryEntry] = []
        self._total_tokens: int = 0

    # ───────────────────────── 基本操作 ─────────────────────────

    def add_message(self, message: Message) -> None:
        """添加消息到窗口"""
        self._messages.append(message)
        self._total_tokens += message.estimate_tokens()
        self._maybe_compress()

    def add_messages(self, messages: List[Message]) -> None:
        """批量添加消息"""
        for msg in messages:
            self.add_message(msg)

    def get_context(self) -> List[Dict[str, str]]:
        """获取当前上下文（OpenAI 消息格式）"""
        result = []
        # 先添加摘要
        for summary in self._summaries:
            result.append({"role": "system", "content": f"[历史摘要] {summary.summary}"})
        # 再添加原始消息
        for msg in self._messages:
            result.append({"role": msg.role, "content": msg.content})
        return result

    def get_messages(self) -> List[Message]:
        """获取原始消息列表"""
        return list(self._messages)

    def clear(self) -> None:
        """清空窗口"""
        self._messages.clear()
        self._summaries.clear()
        self._total_tokens = 0

    def token_count(self) -> int:
        """当前总 token 数（含摘要）"""
        summary_tokens = sum(s.tokens for s in self._summaries)
        return self._total_tokens + summary_tokens

    def available_tokens(self) -> int:
        """剩余可用 token 数"""
        return self.max_tokens - self.reserve_tokens - self.token_count()

    # ───────────────────────── 压缩逻辑 ─────────────────────────

    def _maybe_compress(self) -> None:
        """检查是否需要压缩"""
        if self.available_tokens() < 0:
            self.compress()
        if self.max_messages and len(self._messages) > self.max_messages:
            self.compress()

    def compress(self) -> None:
        """手动触发压缩"""
        if self.strategy == WindowStrategy.TRUNCATE:
            self._compress_truncate()
        elif self.strategy == WindowStrategy.SUMMARIZE:
            self._compress_summarize()
        elif self.strategy == WindowStrategy.SEMANTIC:
            self._compress_semantic()

    def _compress_truncate(self) -> None:
        """截断策略: 移除最旧的消息直到满足限制"""
        while self._messages and self.available_tokens() < 0:
            removed = self._messages.pop(0)
            self._total_tokens -= removed.estimate_tokens()
            logger.debug("截断消息: %s (%d tokens)", removed.role, removed.estimate_tokens())

        if self.max_messages and len(self._messages) > self.max_messages:
            overflow = len(self._messages) - self.max_messages
            for _ in range(overflow):
                removed = self._messages.pop(0)
                self._total_tokens -= removed.estimate_tokens()

    def _compress_summarize(self) -> None:
        """总结策略: 将旧消息总结为摘要"""
        if not self._summarizer:
            # 没有总结器，降级为截断
            self._compress_truncate()
            return

        # 保留最近 3 条消息，总结其余
        keep_count = 3
        if len(self._messages) <= keep_count:
            self._compress_truncate()
            return

        to_summarize = self._messages[:-keep_count]
        self._messages = self._messages[-keep_count:]
        self._total_tokens = sum(m.estimate_tokens() for m in self._messages)

        try:
            summary_text = self._summarizer(to_summarize)
            summary_msg = Message(role="system", content=f"[历史摘要] {summary_text}")
            summary_tokens = summary_msg.estimate_tokens()
            self._summaries.append(SummaryEntry(
                original_range=(0, len(to_summarize)),
                summary=summary_text,
                tokens=summary_tokens,
            ))
            logger.debug("生成摘要: %d tokens", summary_tokens)
        except Exception as e:
            logger.warning("总结失败，降级为截断: %s", e)

        # 如果摘要太多，合并旧摘要
        if len(self._summaries) > 3:
            combined = "; ".join(s.summary for s in self._summaries[:-1])
            self._summaries = self._summaries[-1:]
            self._summaries.insert(0, SummaryEntry(
                original_range=(0, 0),
                summary=combined,
                tokens=Message(role="system", content=combined).estimate_tokens(),
            ))

    def _compress_semantic(self) -> None:
        """语义策略: 基于重要性评分保留高重要性消息"""
        if not self._messages:
            return

        # 保留 system 消息和最近的用户-助手交互
        # 按重要性排序，保留高分消息
        indexed = list(enumerate(self._messages))
        # 最近 2 条必须保留
        must_keep = set(range(max(0, len(self._messages) - 2), len(self._messages)))
        # system 消息通常重要
        for i, msg in indexed:
            if msg.role == "system":
                must_keep.add(i)

        # 其余按重要性排序，保留直到 token 限制
        others = [(i, msg) for i, msg in indexed if i not in must_keep]
        others.sort(key=lambda x: x[1].importance, reverse=True)

        keep_indices = set(must_keep)
        current_tokens = sum(self._messages[i].estimate_tokens() for i in keep_indices)

        for i, msg in others:
            msg_tokens = msg.estimate_tokens()
            if current_tokens + msg_tokens <= self.max_tokens - self.reserve_tokens:
                keep_indices.add(i)
                current_tokens += msg_tokens

        # 重建消息列表（保持原始顺序）
        new_messages = [self._messages[i] for i in sorted(keep_indices)]
        self._messages = new_messages
        self._total_tokens = sum(m.estimate_tokens() for m in new_messages)
        logger.debug("语义压缩后: %d 条消息, %d tokens", len(new_messages), self._total_tokens)

    # ───────────────────────── 工具方法 ─────────────────────────

    def fit_context(
        self,
        messages: List[Message],
        max_tokens: Optional[int] = None,
    ) -> List[Message]:
        """静态方法：将消息列表适配到指定 token 限制"""
        limit = max_tokens or self.max_tokens
        total = 0
        result = []
        # 从后向前遍历，保留最近的消息
        for msg in reversed(messages):
            tokens = msg.estimate_tokens()
            if total + tokens > limit - self.reserve_tokens:
                break
            result.append(msg)
            total += tokens
        return list(reversed(result))

    def stats(self) -> Dict[str, Any]:
        """获取窗口统计"""
        return {
            "messages": len(self._messages),
            "summaries": len(self._summaries),
            "total_tokens": self.token_count(),
            "available_tokens": self.available_tokens(),
            "max_tokens": self.max_tokens,
            "strategy": self.strategy.value,
        }
