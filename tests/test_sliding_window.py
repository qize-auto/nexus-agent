"""
NexusAgent v4.0+ — Sliding Window 智能上下文管理测试
覆盖: Token 计数、TRUNCATE、SUMMARIZE、SEMANTIC、fit_context
"""

import pytest

from nexusagent.context.sliding_window import (
    SlidingWindow,
    Message,
    WindowStrategy,
    SummaryEntry,
)


class TestSlidingWindow:
    """SlidingWindow 核心测试"""

    def test_add_message_and_count(self):
        """添加消息和 Token 计数"""
        window = SlidingWindow(max_tokens=1000, reserve_tokens=0)
        msg = Message(role="user", content="Hello world")
        window.add_message(msg)
        assert len(window.get_messages()) == 1
        assert window.token_count() > 0

    def test_truncate_strategy(self):
        """截断策略"""
        window = SlidingWindow(max_tokens=50, strategy=WindowStrategy.TRUNCATE, reserve_tokens=0)
        for i in range(10):
            window.add_message(Message(role="user", content=f"消息 {i} " * 5))
        # 应该被截断到只剩少量消息
        assert len(window.get_messages()) < 10
        assert window.available_tokens() >= 0

    def test_max_messages_limit(self):
        """最大消息数限制"""
        window = SlidingWindow(max_tokens=10000, max_messages=3, reserve_tokens=0)
        for i in range(5):
            window.add_message(Message(role="user", content=f"m{i}"))
        assert len(window.get_messages()) == 3

    def test_summarize_strategy(self):
        """总结策略"""
        def mock_summarizer(msgs):
            return "摘要: " + ", ".join(m.content[:5] for m in msgs)

        window = SlidingWindow(
            max_tokens=300,
            strategy=WindowStrategy.SUMMARIZE,
            summarizer=mock_summarizer,
            reserve_tokens=0,
        )
        # 添加 5 条短消息，单条约 20 tokens，总计约 100 tokens
        for i in range(5):
            window.add_message(Message(role="user", content=f"消息{i} " * 5))

        # 手动触发压缩（消息数 > 3 才会总结）
        window.compress()
        # 应该有摘要
        assert len(window._summaries) >= 1
        context = window.get_context()
        assert any("[历史摘要]" in m["content"] for m in context)

    def test_semantic_strategy(self):
        """语义策略"""
        window = SlidingWindow(
            max_tokens=80,
            strategy=WindowStrategy.SEMANTIC,
            reserve_tokens=0,
        )
        window.add_message(Message(role="system", content="系统指令", importance=1.0))
        window.add_message(Message(role="user", content="不重要的问题", importance=0.1))
        window.add_message(Message(role="assistant", content="回答", importance=0.5))
        window.add_message(Message(role="user", content="关键问题", importance=0.9))
        window.add_message(Message(role="assistant", content="关键回答", importance=0.9))

        window.compress()
        msgs = window.get_messages()
        # system 消息和最近的高重要性消息应该保留
        roles = [m.role for m in msgs]
        assert "system" in roles

    def test_clear(self):
        """清空窗口"""
        window = SlidingWindow()
        window.add_message(Message(role="user", content="test"))
        window.clear()
        assert len(window.get_messages()) == 0
        assert window.token_count() == 0

    def test_get_context_format(self):
        """上下文格式"""
        window = SlidingWindow()
        window.add_message(Message(role="system", content="sys"))
        window.add_message(Message(role="user", content="hello"))
        ctx = window.get_context()
        assert len(ctx) == 2
        assert ctx[0]["role"] == "system"
        assert ctx[1]["role"] == "user"

    def test_fit_context(self):
        """静态适配方法"""
        window = SlidingWindow(max_tokens=50, reserve_tokens=0)
        msgs = [Message(role="user", content=f"msg{i}" * 10) for i in range(10)]
        fitted = window.fit_context(msgs)
        assert len(fitted) < len(msgs)
        total = sum(m.estimate_tokens() for m in fitted)
        assert total <= 50

    def test_stats(self):
        """统计信息"""
        window = SlidingWindow(max_tokens=1000, reserve_tokens=0)
        window.add_message(Message(role="user", content="test"))
        stats = window.stats()
        assert stats["messages"] == 1
        assert stats["max_tokens"] == 1000
        assert stats["strategy"] == "truncate"

    def test_message_token_estimate(self):
        """Token 估算"""
        m1 = Message(role="user", content="hello world")
        assert m1.estimate_tokens() > 0
        m2 = Message(role="user", content="你好世界")
        assert m2.estimate_tokens() == 4  # 4 个中文字符

    def test_available_tokens(self):
        """可用 Token 计算"""
        window = SlidingWindow(max_tokens=100, reserve_tokens=20)
        assert window.available_tokens() == 80
        window.add_message(Message(role="user", content="test content here"))
        assert window.available_tokens() < 80

    def test_summarize_without_handler(self):
        """无总结器时降级为截断"""
        window = SlidingWindow(
            max_tokens=50,
            strategy=WindowStrategy.SUMMARIZE,
            reserve_tokens=0,
        )
        for i in range(5):
            window.add_message(Message(role="user", content=f"long message content {i} " * 5))
        # 应该成功降级，不会崩溃
        assert len(window.get_messages()) <= 5
