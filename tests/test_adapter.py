"""
接入层测试: 限流器 + 幂等性 + 消息信封
覆盖: NFR-099, NFR-100, 设计稿第3章
"""

import pytest
import asyncio


class TestMemoryTokenBucket:
    """NFR-099: 内存级 Token Bucket 限流"""

    def test_acquire_within_capacity(self):
        """正常请求在容量内应通过"""
        from nexusagent.interface.adapter import MemoryTokenBucket
        bucket = MemoryTokenBucket(rate=10.0, capacity=5.0)

        async def _test():
            assert await bucket.acquire("user_1") is True
            assert await bucket.acquire("user_1") is True

        asyncio.run(_test())

    def test_acquire_exceeds_capacity(self):
        """超过容量应拒绝"""
        from nexusagent.interface.adapter import MemoryTokenBucket
        bucket = MemoryTokenBucket(rate=10.0, capacity=1.0)

        async def _test():
            assert await bucket.acquire("user_1") is True
            assert await bucket.acquire("user_1") is False

        asyncio.run(_test())

    def test_tokens_refill_over_time(self):
        """令牌应随时间补充"""
        from nexusagent.interface.adapter import MemoryTokenBucket
        bucket = MemoryTokenBucket(rate=100.0, capacity=1.0)

        async def _test():
            assert await bucket.acquire("user_1") is True
            assert await bucket.acquire("user_1") is False
            await asyncio.sleep(0.02)  # 补充 2 个令牌
            assert await bucket.acquire("user_1") is True

        asyncio.run(_test())

    def test_per_key_isolation(self):
        """不同 key 的令牌桶应隔离"""
        from nexusagent.interface.adapter import MemoryTokenBucket
        bucket = MemoryTokenBucket(rate=10.0, capacity=1.0)

        async def _test():
            assert await bucket.acquire("user_a") is True
            assert await bucket.acquire("user_b") is True
            assert await bucket.acquire("user_a") is False

        asyncio.run(_test())

    def test_get_remaining(self):
        """查询剩余令牌"""
        from nexusagent.interface.adapter import MemoryTokenBucket
        bucket = MemoryTokenBucket(rate=10.0, capacity=5.0)

        async def _test():
            remaining = await bucket.get_remaining("user_1")
            assert remaining > 0
            await bucket.acquire("user_1")
            remaining_after = await bucket.get_remaining("user_1")
            assert remaining_after < remaining

        asyncio.run(_test())


class TestRedisTokenBucket:
    """NFR-099: Redis 分布式限流 + 自动降级"""

    def test_fallback_when_redis_unavailable(self):
        """Redis 不可用时自动降级为内存限流"""
        from nexusagent.interface.adapter import RedisTokenBucket
        # 使用无效 Redis 地址触发降级
        bucket = RedisTokenBucket(redis_url="redis://invalid_host:9999/0", rate=10.0, capacity=5.0)

        async def _test():
            # 第一次 acquire 会尝试连接 Redis 并降级
            assert await bucket.acquire("user_1") is True
            assert await bucket.acquire("user_1") is True
            # 确认内部已创建 fallback
            assert bucket._fallback is not None

        asyncio.run(_test())

    def test_fallback_get_remaining(self):
        """降级后 get_remaining 仍可用"""
        from nexusagent.interface.adapter import RedisTokenBucket
        bucket = RedisTokenBucket(redis_url="redis://invalid_host:9999/0", rate=10.0, capacity=3.0)

        async def _test():
            remaining = await bucket.get_remaining("user_1")
            assert remaining > 0

        asyncio.run(_test())


class TestIdempotencyStore:
    """NFR-100: 幂等性存储"""

    def test_check_and_set_new_key(self):
        """新键应允许通过"""
        from nexusagent.interface.adapter import IdempotencyStore
        store = IdempotencyStore(ttl_seconds=300.0)

        async def _test():
            assert await store.check_and_set("req_123") is True

        asyncio.run(_test())

    def test_check_and_set_duplicate_key(self):
        """重复键应拒绝"""
        from nexusagent.interface.adapter import IdempotencyStore
        store = IdempotencyStore(ttl_seconds=300.0)

        async def _test():
            assert await store.check_and_set("req_456") is True
            assert await store.check_and_set("req_456") is False

        asyncio.run(_test())

    def test_ttl_expiration(self):
        """过期键应允许重新通过"""
        from nexusagent.interface.adapter import IdempotencyStore
        store = IdempotencyStore(ttl_seconds=0.01)

        async def _test():
            assert await store.check_and_set("req_789") is True
            await asyncio.sleep(0.02)
            assert await store.check_and_set("req_789") is True

        asyncio.run(_test())


class TestMessageEnvelope:
    """设计稿第3章: 统一消息模型"""

    def test_envelope_creation(self):
        """消息信封基础构造"""
        from nexusagent.interface.adapter import MessageEnvelope, ChannelType, MessageType, SecurityLevel
        envelope = MessageEnvelope(
            content="Hello",
            channel_type=ChannelType.WEB,
            message_type=MessageType.TEXT,
            security_level=SecurityLevel.PUBLIC,
        )
        assert envelope.content == "Hello"
        assert envelope.channel_type == ChannelType.WEB

    def test_envelope_expiration(self):
        """TTL 过期检测"""
        from nexusagent.interface.adapter import MessageEnvelope
        import time
        envelope = MessageEnvelope(ttl=1, timestamp=time.time() - 2)
        assert envelope.is_expired() is True

    def test_envelope_to_dict(self):
        """序列化为字典"""
        from nexusagent.interface.adapter import MessageEnvelope, ChannelType
        envelope = MessageEnvelope(content="test", channel_type=ChannelType.CLI)
        d = envelope.to_dict()
        assert d["content"] == "test"
        assert d["channel_type"] == "cli"
