"""
Tests for memory health check and startup validation
"""

import os
import tempfile

import pytest

from nexusagent.memory.store import MemoryStore
from nexusagent.memory.hybrid import HybridMemory


class TestMemoryStoreHealth:
    @pytest.mark.asyncio
    async def test_health_check(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            store = MemoryStore(db_path=db_path)
            health = await store.health_check()
            assert health["integrity"] == "ok"
            assert health["memory_count"] == 0
            assert health["checkpoint_count"] == 0
            assert health["db_size_bytes"] > 0
            store.close()

    @pytest.mark.asyncio
    async def test_compact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            store = MemoryStore(db_path=db_path)
            # 先写入一些数据
            from nexusagent.memory.store import MemoryEntry
            entry = MemoryEntry(session_id="s1", content="test content")
            await store.save(entry)
            result = await store.compact()
            assert "before_bytes" in result
            assert "after_bytes" in result
            store.close()

    def test_get_size(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            store = MemoryStore(db_path=db_path)
            size = store.get_size()
            assert size > 0
            store.close()


class TestHybridMemoryHealth:
    @pytest.mark.asyncio
    async def test_hybrid_health_check(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "hybrid.db")
            hm = HybridMemory(db_path=db_path)
            health = await hm.health_check()
            assert health["status"] in ("healthy", "degraded")
            assert "integrity" in health
            assert "memory_count" in health
            await hm.close()
