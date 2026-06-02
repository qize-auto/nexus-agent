"""
NexusAgent v4.0 — Checkpoint 持久化层

设计参考:
- LangGraph Checkpointer: https://ai.plainenglish.io/the-complete-guide-to-langchain-langgraph-2025-updates-and-production-ready-ai-frameworks-58bdb49a34b6
  "Save and resume workflows at any point without writing custom database logic"
- Temporal Event History: https://temporal.io/blog/build-durable-ai-agents-pydantic-ai-and-temporal
  "Event sourcing applied to code execution"

支持后端:
    - MemoryCheckpointer: 内存（开发/测试）
    - SqliteCheckpointer: SQLite（单实例生产）
    - PostgresCheckpointer: PostgreSQL（多实例分布式）
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from nexusagent.execution.state_graph import Checkpoint

logger = logging.getLogger("nexus.execution.checkpoint")


class BaseCheckpointer(ABC):
    """Checkpoint 抽象基类"""

    @abstractmethod
    async def save(self, checkpoint: Checkpoint) -> None:
        """保存 checkpoint"""
        ...

    @abstractmethod
    async def load(self, thread_id: str) -> Optional[Checkpoint]:
        """加载指定 thread 的最新 checkpoint"""
        ...

    @abstractmethod
    async def list_checkpoints(self, thread_id: str) -> List[Checkpoint]:
        """列出指定 thread 的所有 checkpoint（按时间升序）"""
        ...

    @abstractmethod
    async def load_at_node(self, thread_id: str, node_name: str) -> Optional[Checkpoint]:
        """加载指定 thread 在指定节点执行后的 checkpoint"""
        ...

    @abstractmethod
    async def delete(self, thread_id: str) -> None:
        """删除指定 thread 的所有 checkpoint"""
        ...


class MemoryCheckpointer(BaseCheckpointer):
    """内存 Checkpoint — 适合开发和测试，进程重启后数据丢失"""

    def __init__(self):
        self._store: Dict[str, List[Checkpoint]] = {}

    async def save(self, checkpoint: Checkpoint) -> None:
        self._store.setdefault(checkpoint.thread_id, []).append(checkpoint)

    async def load(self, thread_id: str) -> Optional[Checkpoint]:
        checkpoints = self._store.get(thread_id, [])
        return checkpoints[-1] if checkpoints else None

    async def list_checkpoints(self, thread_id: str) -> List[Checkpoint]:
        return list(self._store.get(thread_id, []))

    async def load_at_node(self, thread_id: str, node_name: str) -> Optional[Checkpoint]:
        for cp in reversed(self._store.get(thread_id, [])):
            if cp.node_name == node_name:
                return cp
        return None

    async def delete(self, thread_id: str) -> None:
        self._store.pop(thread_id, None)


class SqliteCheckpointer(BaseCheckpointer):
    """
    SQLite Checkpoint — 单实例生产级持久化

    表结构:
        CREATE TABLE checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT NOT NULL,
            node_name TEXT NOT NULL,
            state_json TEXT NOT NULL,
            timestamp REAL NOT NULL,
            iteration INTEGER NOT NULL,
            metadata_json TEXT,
            tenant_id TEXT DEFAULT 'default'
        )
    """

    def __init__(self, db_path: str = "checkpoints.db"):
        self._db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                node_name TEXT NOT NULL,
                state_json TEXT NOT NULL,
                timestamp REAL NOT NULL,
                iteration INTEGER NOT NULL,
                metadata_json TEXT DEFAULT '{}',
                tenant_id TEXT DEFAULT 'default'
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_checkpoints_thread
            ON checkpoints(thread_id, timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_checkpoints_tenant
            ON checkpoints(tenant_id)
        """)
        conn.commit()
        conn.close()

    def _connect(self):
        return sqlite3.connect(self._db_path, check_same_thread=False)

    def _save_sync(self, checkpoint: Checkpoint) -> None:
        tenant_id = checkpoint.metadata.get("tenant_id", "default")
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO checkpoints
                   (thread_id, node_name, state_json, timestamp, iteration, metadata_json, tenant_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    checkpoint.thread_id,
                    checkpoint.node_name,
                    json.dumps(checkpoint.state, ensure_ascii=False, default=str),
                    checkpoint.timestamp,
                    checkpoint.iteration,
                    json.dumps(checkpoint.metadata, ensure_ascii=False),
                    tenant_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    async def save(self, checkpoint: Checkpoint) -> None:
        # 避免同步 SQLite 阻塞事件循环
        await asyncio.to_thread(self._save_sync, checkpoint)

    def _load_sync(self, thread_id: str) -> Optional[Checkpoint]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT thread_id, node_name, state_json, timestamp, iteration, metadata_json "
                "FROM checkpoints WHERE thread_id = ? ORDER BY timestamp DESC LIMIT 1",
                (thread_id,),
            )
            row = cursor.fetchone()
            if row:
                return Checkpoint(
                    thread_id=row[0],
                    node_name=row[1],
                    state=json.loads(row[2]),
                    timestamp=row[3],
                    iteration=row[4],
                    metadata=json.loads(row[5]) if row[5] else {},
                )
            return None
        finally:
            conn.close()

    async def load(self, thread_id: str) -> Optional[Checkpoint]:
        return await asyncio.to_thread(self._load_sync, thread_id)

    def _list_sync(self, thread_id: str) -> List[Checkpoint]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT thread_id, node_name, state_json, timestamp, iteration, metadata_json "
                "FROM checkpoints WHERE thread_id = ? ORDER BY timestamp ASC",
                (thread_id,),
            )
            return [
                Checkpoint(
                    thread_id=r[0], node_name=r[1], state=json.loads(r[2]),
                    timestamp=r[3], iteration=r[4],
                    metadata=json.loads(r[5]) if r[5] else {},
                )
                for r in cursor.fetchall()
            ]
        finally:
            conn.close()

    async def list_checkpoints(self, thread_id: str) -> List[Checkpoint]:
        return await asyncio.to_thread(self._list_sync, thread_id)

    def _load_at_node_sync(self, thread_id: str, node_name: str) -> Optional[Checkpoint]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT thread_id, node_name, state_json, timestamp, iteration, metadata_json "
                "FROM checkpoints WHERE thread_id = ? AND node_name = ? "
                "ORDER BY timestamp DESC LIMIT 1",
                (thread_id, node_name),
            )
            row = cursor.fetchone()
            if row:
                return Checkpoint(
                    thread_id=row[0], node_name=row[1], state=json.loads(row[2]),
                    timestamp=row[3], iteration=row[4],
                    metadata=json.loads(row[5]) if row[5] else {},
                )
            return None
        finally:
            conn.close()

    async def load_at_node(self, thread_id: str, node_name: str) -> Optional[Checkpoint]:
        return await asyncio.to_thread(self._load_at_node_sync, thread_id, node_name)

    def _delete_sync(self, thread_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
            conn.commit()
        finally:
            conn.close()

    async def delete(self, thread_id: str) -> None:
        await asyncio.to_thread(self._delete_sync, thread_id)
