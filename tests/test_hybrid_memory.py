"""
NexusAgent v4.0+ — Hybrid Memory 混合记忆系统测试
覆盖: Memory Blocks、混合检索、记忆关联、自动清理
"""

import os
import pytest

from nexusagent.memory.hybrid import HybridMemory, MemoryBlock, RetrievalResult
from nexusagent.memory.store import MemoryEntry


@pytest.fixture
def hm(tmp_path):
    """创建临时 HybridMemory 实例"""
    db_path = tmp_path / "test_hybrid.db"
    memory = HybridMemory(db_path=str(db_path))
    yield memory
    # 关闭连接后清理
    try:
        memory._store.close()
    except Exception:
        pass
    try:
        os.remove(db_path)
    except (FileNotFoundError, PermissionError):
        pass


class TestHybridMemory:
    """HybridMemory 核心测试"""

    @pytest.mark.asyncio
    async def test_add_recall(self, hm):
        """添加回忆记忆"""
        entry = await hm.add_recall("用户喜欢 Python", session_id="s1", importance=0.8)
        assert isinstance(entry, MemoryEntry)
        assert entry.memory_type == "episodic"
        assert entry.content == "用户喜欢 Python"
        assert entry.importance == 0.8

    @pytest.mark.asyncio
    async def test_add_archival(self, hm):
        """添加档案记忆"""
        entry = await hm.add_archival("Python 是一种高级语言", tags=["programming"], importance=0.9)
        assert entry.memory_type == "semantic"

    @pytest.mark.asyncio
    async def test_retrieve_basic(self, hm):
        """基本检索"""
        await hm.add_recall("用户喜欢 Python", session_id="s1", importance=0.8)
        await hm.add_recall("用户讨厌 Java", session_id="s1", importance=0.3)
        results = await hm.retrieve("Python", top_k=5)
        assert len(results) >= 1
        assert isinstance(results[0], RetrievalResult)
        assert "Python" in results[0].entry.content

    @pytest.mark.asyncio
    async def test_retrieve_importance_filter(self, hm):
        """重要性过滤"""
        await hm.add_recall("高重要性内容", session_id="s1", importance=0.9)
        await hm.add_recall("低重要性内容", session_id="s1", importance=0.1)
        results = await hm.retrieve("内容", top_k=5, min_importance=0.5)
        assert len(results) == 1
        assert results[0].entry.content == "高重要性内容"

    @pytest.mark.asyncio
    async def test_memory_link(self, hm):
        """记忆关联"""
        e1 = await hm.add_recall("记忆 A", session_id="s1")
        e2 = await hm.add_recall("记忆 B", session_id="s1")
        assert e1.id is not None
        assert e2.id is not None

        ok = await hm.link_memories(e1.id, e2.id, relation="similar")
        assert ok is True

        related = await hm.get_related(e1.id)
        assert len(related) == 1
        assert related[0].content == "记忆 B"

    @pytest.mark.asyncio
    async def test_core_block(self, hm):
        """Core Memory Block"""
        hm.set_core_block("persona", "你是一个 helpful assistant", max_tokens=1000)
        blocks = hm.get_core_blocks()
        assert len(blocks) == 1
        assert blocks[0].name == "persona"
        assert blocks[0].memory_type == "core"
        assert blocks[0].mutable is False

    @pytest.mark.asyncio
    async def test_stats(self, hm):
        """统计信息"""
        await hm.add_recall("测试内容", session_id="s1", importance=0.7)
        stats = await hm.stats()
        assert stats["total"] >= 1
        assert "by_type" in stats
        assert "avg_importance" in stats

    @pytest.mark.asyncio
    async def test_cleanup(self, hm):
        """自动清理"""
        import time
        # 添加一条旧记忆
        entry = await hm.add_recall("旧记忆", session_id="s1", importance=0.05)
        # 手动修改 created_at 为很久以前
        def _update():
            conn = hm._store._conn
            conn.execute("UPDATE memories SET created_at = ? WHERE id = ?", (time.time() - 86400 * 30, entry.id))
            conn.commit()
        await hm._store._run_sync(_update)

        removed = await hm.cleanup(max_age_days=7, min_importance=0.1)
        assert removed >= 1

    @pytest.mark.asyncio
    async def test_empty_retrieve(self, hm):
        """空记忆检索"""
        results = await hm.retrieve("不存在的查询", top_k=5)
        assert results == []
