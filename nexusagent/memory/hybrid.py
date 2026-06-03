"""
NexusAgent v4.0+ — Hybrid Memory 混合记忆系统

设计参考:
- Letta Memory Blocks: https://docs.letta.ai/memory
  "core memory (persona + human) + archival memory + recall memory"
- Mastra Observational Memory: "Observer + Reflector compress old conversations"
- MemGPT: "Working context vs. External storage hierarchy"

职责:
    1. 统一管理四级记忆 (working / episodic / semantic / procedural)
    2. 混合检索: 向量相似度 + FTS 全文 + 时间衰减 + 重要性加权
    3. 记忆关联: 自动链接相关记忆，构建知识图谱
    4. 自动清理: TTL 过期 + 低重要性淘汰
    5. Memory Blocks: core (角色设定) / archival (长期档案) / recall (会话历史)

Usage:
    from nexusagent.memory.hybrid import HybridMemory
    hm = HybridMemory(db_path="memory.db")
    await hm.add_recall("用户喜欢 Python", session_id="s1")
    results = await hm.retrieve("Python 偏好", top_k=5)
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from nexusagent.memory.store import MemoryEntry, MemoryStore
from nexusagent.memory.compressor import MemoryCompressor
from nexusagent.cognition.systems import HybridSearch

logger = logging.getLogger("nexus.memory.hybrid")


@dataclass
class RetrievalResult:
    """检索结果"""
    entry: MemoryEntry
    score: float  # 综合得分 (0-1)
    matched_by: str  # vector | fts | temporal | importance


@dataclass
class MemoryBlock:
    """Letta 风格 Memory Block"""
    name: str
    content: str
    memory_type: str  # core | archival | recall
    max_tokens: int = 4000
    mutable: bool = True  # core 通常不可变


class HybridMemory:
    """
    Hybrid Memory — 混合记忆系统

    架构:
        ┌─────────────────────────────────────┐
        │  Core Block (角色设定 + 用户档案)    │  ← 高频访问，常驻上下文
        ├─────────────────────────────────────┤
        │  Recall Block (会话历史 / 工作记忆)  │  ← 近期 episodic，TTL 管理
        ├─────────────────────────────────────┤
        │  Archival Block (长期档案 / 语义)    │  ← 压缩后的 semantic + procedural
        └─────────────────────────────────────┘
    """

    def __init__(
        self,
        db_path: str = "nexus_memory.db",
        vector_dimension: int = 1536,
        encryption: Any = None,
        llm_backend: Any = None,
        compression_threshold: int = 20,
    ):
        self._store = MemoryStore(db_path, encryption=encryption, vector_dimension=vector_dimension)
        self._compressor = MemoryCompressor(self._store, threshold=compression_threshold, llm_backend=llm_backend)
        self._llm = llm_backend
        self._blocks: Dict[str, MemoryBlock] = {}
        self._hybrid_search = HybridSearch(self._store)
        self._ensure_links_table()
        # 设置默认 core block（角色设定）
        self.set_core_block("persona", "You are NexusAgent, a local-first AI assistant.")

    def _ensure_links_table(self) -> None:
        """确保 memory_links 表存在"""
        conn = self._store._conn
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                relation TEXT DEFAULT 'related',
                created_at REAL NOT NULL,
                UNIQUE(source_id, target_id, relation)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_links_source
            ON memory_links(source_id)
        """)
        conn.commit()

    # ───────────────────────── Memory Blocks ─────────────────────────

    def set_core_block(self, name: str, content: str, max_tokens: int = 4000) -> None:
        """设置核心记忆块（角色设定、用户画像）"""
        self._blocks[name] = MemoryBlock(
            name=name,
            content=content,
            memory_type="core",
            max_tokens=max_tokens,
            mutable=False,
        )
        logger.info("设置 Core Block: %s (%d tokens)", name, max_tokens)

    def update_core_block(self, name: str, content: str) -> bool:
        """更新核心记忆块（仅在 mutable=True 时允许）"""
        block = self._blocks.get(name)
        if not block or not block.mutable:
            return False
        block.content = content
        return True

    def get_core_blocks(self) -> List[MemoryBlock]:
        """获取所有核心记忆块"""
        return [b for b in self._blocks.values() if b.memory_type == "core"]

    # ───────────────────────── 写入 ─────────────────────────

    async def add_recall(
        self,
        content: str,
        session_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 0.5,
        ttl: Optional[int] = None,
    ) -> MemoryEntry:
        """添加回忆记忆 (episodic)"""
        entry = MemoryEntry(
            session_id=session_id,
            memory_type="episodic",
            content=content,
            metadata_json=json.dumps(metadata or {}),
            importance=importance,
            ttl=ttl,
        )
        entry.id = await self._store.save(entry)
        # 触发压缩检查
        if session_id:
            await self._compressor.check_and_compress(session_id)
        # 自动关联相似记忆（v4.0+ 知识图谱构建）
        try:
            similar = await self._store.search_fts(content, limit=3)
            for sim in similar:
                if sim.id and sim.id != entry.id:
                    await self.link_memories(entry.id, sim.id, relation="related")
        except Exception as e:
            logger.debug("自动记忆关联失败 (可忽略): %s", e)
        return entry

    async def add_archival(
        self,
        content: str,
        tags: Optional[List[str]] = None,
        importance: float = 0.7,
    ) -> MemoryEntry:
        """添加档案记忆 (semantic / procedural)"""
        meta = {"tags": tags or []}
        entry = MemoryEntry(
            memory_type="semantic",
            content=content,
            metadata_json=json.dumps(meta),
            importance=importance,
        )
        await self._store.save(entry)
        return entry

    # ───────────────────────── 混合检索 ─────────────────────────

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        memory_types: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        min_importance: float = 0.0,
    ) -> List[RetrievalResult]:
        """
        混合检索: 向量 + FTS + 时间衰减 + 重要性加权

        评分公式:
            score = 0.4 * vector_score + 0.3 * fts_score + 0.2 * temporal_score + 0.1 * importance
        """
        results: Dict[int, RetrievalResult] = {}

        # 1. 向量搜索
        vector_results = await self._vector_search(query, top_k * 2, memory_types, session_id)
        for entry, score in vector_results:
            if entry.id is not None:
                results[entry.id] = RetrievalResult(
                    entry=entry,
                    score=score * 0.4,
                    matched_by="vector",
                )

        # 2. FTS 全文搜索
        fts_results = await self._fts_search(query, top_k * 2, memory_types, session_id)
        for entry, score in fts_results:
            if entry.id is not None:
                if entry.id in results:
                    results[entry.id].score += score * 0.3
                    results[entry.id].matched_by += "|fts"
                else:
                    results[entry.id] = RetrievalResult(
                        entry=entry,
                        score=score * 0.3,
                        matched_by="fts",
                    )

        # 3. 时间衰减 + 重要性加权
        now = time.time()
        for rid, rr in list(results.items()):
            age_hours = (now - rr.entry.created_at) / 3600
            temporal_score = math.exp(-age_hours / 168)  # 7天半衰期
            importance_boost = rr.entry.importance * 0.1
            rr.score += temporal_score * 0.2 + importance_boost

            # 过滤
            if rr.entry.importance < min_importance:
                del results[rid]

        # 排序返回
        sorted_results = sorted(results.values(), key=lambda x: x.score, reverse=True)[:top_k]
        logger.debug("检索 '%s' 返回 %d 条结果", query, len(sorted_results))
        return sorted_results

    async def _vector_search(
        self,
        query: str,
        top_k: int,
        memory_types: Optional[List[str]],
        session_id: Optional[str],
    ) -> List[Tuple[MemoryEntry, float]]:
        """向量搜索 — 使用 HybridSearch 的 FTS5 搜索作为降级方案"""
        try:
            results = await self._hybrid_search.search(query, limit=top_k)
            # 转换为 MemoryEntry 元组
            entries = []
            for r in results:
                entry = MemoryEntry(
                    id=r.get("entry_id"),
                    session_id=r.get("session_id", ""),
                    memory_type="episodic",
                    content=r.get("content", ""),
                )
                entries.append((entry, r.get("score", 1.0)))
            return entries
        except Exception as e:
            logger.debug("向量搜索失败，降级: %s", e)
            return []

    async def _fts_search(
        self,
        query: str,
        top_k: int,
        memory_types: Optional[List[str]],
        session_id: Optional[str],
    ) -> List[Tuple[MemoryEntry, float]]:
        """FTS 全文搜索（带 LIKE 降级）"""
        try:
            results = await self._store.search_fts(
                query=query,
                limit=top_k,
            )
            if results:
                return [(e, 1.0) for e in results]
        except Exception as e:
            logger.debug("FTS 搜索失败: %s", e)

        # 降级: LIKE 模糊匹配（适用于 CJK 短词）
        try:
            def _like_search():
                conn = self._store._conn
                sql = "SELECT id, session_id, memory_type, content, metadata_json, created_at, importance FROM memories WHERE content LIKE ?"
                params = [f"%{query}%"]
                if session_id:
                    sql += " AND session_id = ?"
                    params.append(session_id)
                if memory_types:
                    sql += " AND memory_type IN ({})".format(",".join("?" * len(memory_types)))
                    params.extend(memory_types)
                sql += " ORDER BY created_at DESC LIMIT ?"
                params.append(top_k)
                cursor = conn.execute(sql, params)
                return [
                    MemoryEntry(
                        id=row[0], session_id=row[1], memory_type=row[2],
                        content=row[3], metadata_json=row[4],
                        created_at=row[5], importance=row[6],
                    )
                    for row in cursor.fetchall()
                ]

            results = await self._store._run_sync(_like_search)
            return [(e, 0.7) for e in results]
        except Exception as e:
            logger.debug("LIKE 降级搜索失败: %s", e)
            return []

    # ───────────────────────── 记忆关联 ─────────────────────────

    async def link_memories(self, source_id: int, target_id: int, relation: str = "related") -> bool:
        """建立记忆关联"""
        try:
            def _link():
                conn = self._store._conn
                conn.execute(
                    "INSERT OR REPLACE INTO memory_links (source_id, target_id, relation, created_at) VALUES (?, ?, ?, ?)",
                    (source_id, target_id, relation, time.time()),
                )
                conn.commit()

            await self._store._run_sync(_link)
            logger.debug("记忆关联: %d -> %d (%s)", source_id, target_id, relation)
            return True
        except Exception as e:
            logger.warning("记忆关联失败: %s", e)
            return False

    async def get_related(self, memory_id: int) -> List[MemoryEntry]:
        """获取关联记忆"""
        try:
            def _query():
                conn = self._store._conn
                cursor = conn.execute(
                    "SELECT target_id FROM memory_links WHERE source_id = ?",
                    (memory_id,),
                )
                ids = [r[0] for r in cursor.fetchall()]
                if not ids:
                    return []
                placeholders = ",".join("?" * len(ids))
                cursor = conn.execute(
                    f"SELECT id, session_id, memory_type, content, metadata_json, created_at, importance FROM memories WHERE id IN ({placeholders})",
                    ids,
                )
                return [
                    MemoryEntry(
                        id=row[0], session_id=row[1], memory_type=row[2],
                        content=row[3], metadata_json=row[4],
                        created_at=row[5], importance=row[6],
                    )
                    for row in cursor.fetchall()
                ]

            return await self._store._run_sync(_query)
        except Exception as e:
            logger.warning("获取关联记忆失败: %s", e)
            return []

    # ───────────────────────── 自动清理 ─────────────────────────

    async def cleanup(self, max_age_days: Optional[int] = None, min_importance: float = 0.1) -> int:
        """清理过期和低重要性记忆"""
        removed = 0
        try:
            def _cleanup():
                nonlocal removed
                conn = self._store._conn
                # TTL 过期
                cursor = conn.execute(
                    "DELETE FROM memories WHERE ttl IS NOT NULL AND created_at + ttl < ?",
                    (time.time(),),
                )
                removed += cursor.rowcount

                # 低重要性 + 旧记忆
                if max_age_days:
                    cutoff = time.time() - max_age_days * 86400
                    cursor = conn.execute(
                        "DELETE FROM memories WHERE created_at < ? AND importance < ? AND memory_type != 'core'",
                        (cutoff, min_importance),
                    )
                    removed += cursor.rowcount
                conn.commit()

            await self._store._run_sync(_cleanup)
            logger.info("清理记忆: 删除 %d 条", removed)
            return removed
        except Exception as e:
            logger.warning("清理记忆失败: %s", e)
            return 0

    # ───────────────────────── 统计 ─────────────────────────

    async def stats(self) -> Dict[str, Any]:
        """获取记忆统计"""
        def _stats():
            conn = self._store._conn
            cursor = conn.execute("SELECT memory_type, COUNT(*) FROM memories GROUP BY memory_type")
            type_counts = {r[0]: r[1] for r in cursor.fetchall()}
            cursor = conn.execute("SELECT COUNT(*) FROM memories")
            total = cursor.fetchone()[0]
            cursor = conn.execute("SELECT AVG(importance) FROM memories")
            avg_importance = cursor.fetchone()[0] or 0.0
            return {
                "total": total,
                "by_type": type_counts,
                "avg_importance": round(avg_importance, 3),
                "core_blocks": len(self._blocks),
            }

        return await self._store._run_sync(_stats)

    async def health_check(self) -> Dict[str, Any]:
        """记忆系统健康检查"""
        store_health = await self._store.health_check()
        stats = await self.stats()
        return {
            "status": "healthy" if store_health["integrity"] == "ok" else "degraded",
            "integrity": store_health["integrity"],
            "memory_count": stats["total"],
            "core_blocks": stats["core_blocks"],
            "db_size_bytes": store_health["db_size_bytes"],
            "vector_search_available": store_health["vec_available"],
        }

    async def close(self) -> None:
        """关闭资源"""
        self._store.close()
