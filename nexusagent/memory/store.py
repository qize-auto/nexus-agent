"""
NexusAgent v3.3 — 记忆层：SQLite主存储 + FTS5全文搜索
来源: 设计稿第7章记忆层
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nexus.memory")


@dataclass
class MemoryEntry:
    """记忆条目"""
    id: Optional[int] = None
    session_id: str = ""
    memory_type: str = "working"  # working | episodic | semantic | procedural
    content: str = ""
    embedding: Optional[List[float]] = None
    metadata_json: str = "{}"
    created_at: float = field(default_factory=time.time)
    ttl: Optional[int] = None       # 秒, None=永不过期
    importance: float = 0.5         # 0-1重要性评分

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "memory_type": self.memory_type,
            "content": self.content,
            "metadata": json.loads(self.metadata_json),
            "created_at": self.created_at,
            "importance": self.importance,
        }


class MemoryStore:
    """
    SQLite主存储 — 唯一事实来源(SSOT)
    设计稿第7章: SQLite + FTS5全文搜索 + sqlite-vec向量搜索
    """

    def __init__(self, db_path: str, encryption: Any = None, vector_dimension: int = 1536):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._encryption = encryption
        self._vector_dim = vector_dimension
        self._vec_available = False
        self._loop: Optional[Any] = None
        self._init_db()

    def _get_loop(self):
        """获取当前事件循环"""
        import asyncio
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            # 不在异步上下文中时，返回当前线程的事件循环
            return asyncio.get_event_loop()

    def _run_sync(self, fn):
        """在线程池中同步执行数据库操作"""
        loop = self._get_loop()
        return loop.run_in_executor(None, fn)

    def _init_db(self) -> None:
        """初始化数据库 — 设计稿7.5 四级存储模型建表SQL + sqlite-vec向量扩展"""
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

        # 加载 sqlite-vec 扩展（优雅降级）
        try:
            import sqlite_vec
            self._conn.enable_load_extension(True)
            sqlite_vec.load(self._conn)
            self._vec_available = True
            logger.info("sqlite-vec 扩展已加载")
        except Exception as e:
            self._vec_available = False
            logger.warning("sqlite-vec 扩展加载失败（向量搜索将不可用）: %s", e)

        # 主记忆表
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL DEFAULT 'default',
                session_id TEXT NOT NULL,
                memory_type TEXT NOT NULL DEFAULT 'working',
                content TEXT NOT NULL,
                embedding BLOB,
                metadata_json TEXT DEFAULT '{}',
                created_at REAL NOT NULL,
                ttl INTEGER,
                importance REAL DEFAULT 0.5
            )
        """)

        # FTS5全文搜索 — 设计稿7.5 P1中文分词
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                content,
                session_id,
                memory_type,
                tokenize='unicode61'
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS tenant_metadata (
                tenant_id TEXT PRIMARY KEY,
                display_name TEXT,
                created_at REAL NOT NULL,
                quota_json TEXT DEFAULT '{}'
            )
        """)

        # sqlite-vec 向量搜索表 — 设计稿7.5 P1向量索引
        if self._vec_available:
            try:
                self._conn.execute(f"""
                    CREATE VIRTUAL TABLE IF NOT EXISTS memories_vec USING vec0(
                        embedding float[{self._vector_dim}]
                    )
                """)
            except Exception as e:
                logger.warning("向量表创建失败: %s", e)
                self._vec_available = False

        # Checkpoint表 — 设计稿7.5 P1原子保存
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL DEFAULT 'default',
                state_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                iteration INTEGER DEFAULT 0,
                UNIQUE(session_id, tenant_id)
            )
        """)

        # 迁移: 为旧表添加 tenant_id 列
        self._ensure_column("memories", "tenant_id", "TEXT NOT NULL DEFAULT 'default'")
        self._ensure_column("checkpoints", "tenant_id", "TEXT NOT NULL DEFAULT 'default'")

        # 索引
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_session
            ON memories(session_id)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_type_created
            ON memories(memory_type, created_at)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_tenant
            ON memories(tenant_id)
        """)

        self._conn.commit()
        logger.info(
            "MemoryStore initialized at %s (encryption=%s, vec=%s)",
            self._db_path, self._encryption is not None, self._vec_available,
        )

    def _ensure_column(self, table: str, column: str, col_def: str) -> None:
        """确保表存在指定列（兼容旧数据库迁移）"""
        try:
            cursor = self._conn.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in cursor.fetchall()]
            if column not in columns:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
                logger.info("数据库迁移: %s.%s 已添加", table, column)
        except Exception as e:
            logger.warning("数据库迁移检查失败 %s.%s: %s", table, column, e)

    def _encrypt_field(self, text: str) -> str:
        """加密字段（如果加密引擎已配置）"""
        if self._encryption and text:
            return self._encryption.encrypt(text)
        return text

    def _decrypt_field(self, text: str) -> str:
        """解密字段（如果加密引擎已配置）

        安全准则: 解密失败必须抛出异常（Fail-Closed），
        禁止静默返回明文，防止攻击者通过破坏密文获得明文数据。
        """
        if self._encryption and text:
            return self._encryption.decrypt(text)
        return text

    async def save(self, entry: MemoryEntry, tenant_id: str = "default") -> int:
        """保存记忆条目（自动加密敏感字段 + 向量索引 + 租户隔离）"""
        encrypted_content = self._encrypt_field(entry.content)
        encrypted_metadata = self._encrypt_field(entry.metadata_json)

        def _save():
            cursor = self._conn.execute(
                """INSERT INTO memories
                   (tenant_id, session_id, memory_type, content, embedding,
                    metadata_json, created_at, ttl, importance)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    tenant_id, entry.session_id, entry.memory_type, encrypted_content,
                    entry.embedding, encrypted_metadata,
                    entry.created_at, entry.ttl, entry.importance,
                )
            )
            # 同步FTS5索引（使用明文以支持搜索）
            memory_id = cursor.lastrowid
            self._conn.execute(
                "INSERT INTO memories_fts(rowid, content, session_id, memory_type) "
                "VALUES (?, ?, ?, ?)",
                (memory_id, entry.content, entry.session_id, entry.memory_type),
            )
            # 同步向量索引
            if self._vec_available and entry.embedding:
                try:
                    import sqlite_vec
                    self._conn.execute(
                        "INSERT INTO memories_vec(rowid, embedding) VALUES (?, ?)",
                        (memory_id, sqlite_vec.serialize_float32(entry.embedding)),
                    )
                except Exception as e:
                    logger.warning("向量索引写入失败: %s", e)
            self._conn.commit()
            return memory_id

        return await self._run_sync(_save)

    async def search_fts(self, query: str, limit: int = 10, tenant_id: Optional[str] = None) -> List[MemoryEntry]:
        """FTS5全文搜索 — 设计稿7.5（支持租户隔离）"""
        def _search():
            try:
                sql = """SELECT m.id, m.session_id, m.memory_type, m.content,
                              m.metadata_json, m.created_at, m.importance
                       FROM memories_fts
                       JOIN memories m ON memories_fts.rowid = m.id
                       WHERE memories_fts MATCH ?"""
                params = [query]
                if tenant_id:
                    sql += " AND m.tenant_id = ?"
                    params.append(tenant_id)
                sql += " ORDER BY rank LIMIT ?"
                params.append(limit)
                cursor = self._conn.execute(sql, params)
                results = []
                for row in cursor.fetchall():
                    results.append(MemoryEntry(
                        id=row[0], session_id=row[1], memory_type=row[2],
                        content=self._decrypt_field(row[3]),
                        metadata_json=self._decrypt_field(row[4]),
                        created_at=row[5], importance=row[6],
                    ))
                return results
            except sqlite3.OperationalError as e:
                logger.warning("FTS5搜索语法错误: %s", e)
                return []

        return await self._run_sync(_search)

    async def get_by_session(
        self, session_id: str, memory_type: Optional[str] = None, tenant_id: Optional[str] = None
    ) -> List[MemoryEntry]:
        """获取会话记忆（支持租户隔离）"""
        def _get():
            query = "SELECT id, session_id, memory_type, content, metadata_json, created_at, importance FROM memories WHERE session_id = ?"
            params = [session_id]
            if tenant_id:
                query += " AND tenant_id = ?"
                params.append(tenant_id)
            if memory_type:
                query += " AND memory_type = ?"
                params.append(memory_type)
            query += " ORDER BY created_at DESC"

            cursor = self._conn.execute(query, params)
            return [
                MemoryEntry(
                    id=row[0], session_id=row[1], memory_type=row[2],
                    content=self._decrypt_field(row[3]),
                    metadata_json=self._decrypt_field(row[4]),
                    created_at=row[5], importance=row[6],
                )
                for row in cursor.fetchall()
            ]

        return await self._run_sync(_get)

    async def save_checkpoint(self, session_id: str, state: Dict[str, Any], iteration: int = 0, tenant_id: str = "default") -> None:
        """原子保存状态快照 — 设计稿7.5 P1（支持租户隔离）"""
        def _save():
            self._conn.execute(
                """INSERT OR REPLACE INTO checkpoints
                   (session_id, tenant_id, state_json, created_at, iteration)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, tenant_id, json.dumps(state), time.time(), iteration),
            )
            self._conn.commit()

        await self._run_sync(_save)

    async def load_checkpoint(self, session_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """加载状态快照（支持租户隔离）"""
        def _load():
            if tenant_id:
                cursor = self._conn.execute(
                    "SELECT state_json FROM checkpoints WHERE session_id = ? AND tenant_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                    (session_id, tenant_id),
                )
            else:
                cursor = self._conn.execute(
                    "SELECT state_json FROM checkpoints WHERE session_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                    (session_id,),
                )
            row = cursor.fetchone()
            return json.loads(row[0]) if row else None

        return await self._run_sync(_load)

    async def search_vector(self, embedding: List[float], limit: int = 10, tenant_id: Optional[str] = None) -> List[MemoryEntry]:
        """sqlite-vec 向量相似度搜索 — 设计稿7.5 P1（支持租户隔离）"""
        if not self._vec_available:
            logger.debug("sqlite-vec 不可用，跳过向量搜索")
            return []

        def _search():
            try:
                import sqlite_vec
                sql = """SELECT m.id, m.session_id, m.memory_type, m.content,
                              m.metadata_json, m.created_at, m.importance
                       FROM memories_vec v
                       JOIN memories m ON v.rowid = m.id
                       WHERE v.embedding MATCH ?"""
                params = [sqlite_vec.serialize_float32(embedding)]
                if tenant_id:
                    sql += " AND m.tenant_id = ?"
                    params.append(tenant_id)
                sql += " ORDER BY v.distance LIMIT ?"
                params.append(limit)
                cursor = self._conn.execute(sql, params)
                return [
                    MemoryEntry(
                        id=row[0], session_id=row[1], memory_type=row[2],
                        content=self._decrypt_field(row[3]),
                        metadata_json=self._decrypt_field(row[4]),
                        created_at=row[5], importance=row[6],
                    )
                    for row in cursor.fetchall()
                ]
            except Exception as e:
                logger.warning("向量搜索失败: %s", e)
                return []

        return await self._run_sync(_search)

    def _sync_cleanup_vec(self):
        """同步清理向量表中的孤儿记录"""
        if self._vec_available:
            try:
                self._conn.execute(
                    "DELETE FROM memories_vec WHERE rowid NOT IN (SELECT id FROM memories)",
                )
            except Exception as e:
                logger.debug("向量表清理异常（可忽略）: %s", e)

    async def delete_by_session(self, session_id: str, tenant_id: Optional[str] = None) -> int:
        """删除指定会话的所有记忆（含FTS5 + 向量同步，支持租户隔离）"""
        def _delete():
            if tenant_id:
                cursor = self._conn.execute(
                    "DELETE FROM memories WHERE session_id = ? AND tenant_id = ?",
                    (session_id, tenant_id),
                )
            else:
                cursor = self._conn.execute(
                    "DELETE FROM memories WHERE session_id = ?",
                    (session_id,),
                )
            deleted = cursor.rowcount
            self._conn.execute(
                "DELETE FROM memories_fts WHERE rowid NOT IN (SELECT id FROM memories)",
            )
            self._sync_cleanup_vec()
            self._conn.commit()
            return deleted

        return await self._run_sync(_delete)

    async def delete_by_user(self, user_id: str, tenant_id: Optional[str] = None) -> int:
        """删除包含指定用户标识的所有记忆（基于session_id匹配，支持租户隔离）"""
        def _delete():
            if tenant_id:
                cursor = self._conn.execute(
                    "DELETE FROM memories WHERE session_id LIKE ? AND tenant_id = ?",
                    (f"%{user_id}%", tenant_id),
                )
            else:
                cursor = self._conn.execute(
                    "DELETE FROM memories WHERE session_id LIKE ?",
                    (f"%{user_id}%",),
                )
            deleted = cursor.rowcount
            self._conn.execute(
                "DELETE FROM memories_fts WHERE rowid NOT IN (SELECT id FROM memories)",
            )
            self._sync_cleanup_vec()
            self._conn.commit()
            return deleted

        return await self._run_sync(_delete)

    async def get_by_user(self, user_id: str, tenant_id: Optional[str] = None) -> List[MemoryEntry]:
        """获取包含指定用户标识的所有记忆（基于session_id匹配，支持租户隔离）"""
        def _get():
            if tenant_id:
                cursor = self._conn.execute(
                    "SELECT id, session_id, memory_type, content, metadata_json, created_at, importance FROM memories WHERE session_id LIKE ? AND tenant_id = ? ORDER BY created_at DESC",
                    (f"%{user_id}%", tenant_id),
                )
            else:
                cursor = self._conn.execute(
                    "SELECT id, session_id, memory_type, content, metadata_json, created_at, importance FROM memories WHERE session_id LIKE ? ORDER BY created_at DESC",
                    (f"%{user_id}%",),
                )
            return [
                MemoryEntry(
                    id=row[0], session_id=row[1], memory_type=row[2],
                    content=self._decrypt_field(row[3]),
                    metadata_json=self._decrypt_field(row[4]),
                    created_at=row[5], importance=row[6],
                )
                for row in cursor.fetchall()
            ]

        return await self._run_sync(_get)

    # ── 租户元数据管理 ──
    async def get_or_create_tenant(self, tenant_id: str, display_name: Optional[str] = None, quota: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """获取或创建租户元数据"""
        def _upsert():
            cursor = self._conn.execute(
                "SELECT tenant_id, display_name, created_at, quota_json FROM tenant_metadata WHERE tenant_id = ?",
                (tenant_id,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "tenant_id": row[0],
                    "display_name": row[1],
                    "created_at": row[2],
                    "quota": json.loads(row[3]) if row[3] else {},
                }
            now = time.time()
            quota_json = json.dumps(quota) if quota else "{}"
            self._conn.execute(
                "INSERT INTO tenant_metadata (tenant_id, display_name, created_at, quota_json) VALUES (?, ?, ?, ?)",
                (tenant_id, display_name or tenant_id, now, quota_json),
            )
            self._conn.commit()
            return {
                "tenant_id": tenant_id,
                "display_name": display_name or tenant_id,
                "created_at": now,
                "quota": quota or {},
            }

        return await self._run_sync(_upsert)

    async def get_tenant_quota(self, tenant_id: str) -> Dict[str, Any]:
        """获取租户配额"""
        def _get():
            cursor = self._conn.execute(
                "SELECT quota_json FROM tenant_metadata WHERE tenant_id = ?",
                (tenant_id,),
            )
            row = cursor.fetchone()
            return json.loads(row[0]) if row and row[0] else {}

        return await self._run_sync(_get)

    async def get_by_tenant(self, tenant_id: str, memory_type: Optional[str] = None, limit: int = 100) -> List[MemoryEntry]:
        """获取指定租户的所有记忆"""
        def _get():
            query = "SELECT id, session_id, memory_type, content, metadata_json, created_at, importance FROM memories WHERE tenant_id = ?"
            params = [tenant_id]
            if memory_type:
                query += " AND memory_type = ?"
                params.append(memory_type)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            cursor = self._conn.execute(query, params)
            return [
                MemoryEntry(
                    id=row[0], session_id=row[1], memory_type=row[2],
                    content=self._decrypt_field(row[3]),
                    metadata_json=self._decrypt_field(row[4]),
                    created_at=row[5], importance=row[6],
                )
                for row in cursor.fetchall()
            ]

        return await self._run_sync(_get)

    async def cleanup_expired(self) -> int:
        """清理过期记忆 — 设计稿7.5 AutoCompact"""
        def _clean():
            now = time.time()
            cursor = self._conn.execute(
                "DELETE FROM memories WHERE ttl IS NOT NULL AND (created_at + ttl) < ?",
                (now,),
            )
            deleted = cursor.rowcount
            self._conn.execute(
                "DELETE FROM memories_fts WHERE rowid NOT IN (SELECT id FROM memories)",
            )
            self._sync_cleanup_vec()
            self._conn.commit()
            return deleted

        return await self._run_sync(_clean)

    async def compact(self) -> Dict[str, Any]:
        """VACUUM 压缩数据库，回收碎片空间"""
        def _compact():
            before = self._db_path.stat().st_size if self._db_path.exists() else 0
            self._conn.execute("VACUUM")
            after = self._db_path.stat().st_size if self._db_path.exists() else 0
            return {"before_bytes": before, "after_bytes": after, "freed_bytes": before - after}

        return await self._run_sync(_compact)

    def get_size(self) -> int:
        """返回数据库文件大小（字节）"""
        return self._db_path.stat().st_size if self._db_path.exists() else 0

    async def health_check(self) -> Dict[str, Any]:
        """数据库健康检查"""
        def _check():
            # 检查数据库完整性
            cursor = self._conn.execute("PRAGMA integrity_check")
            integrity = cursor.fetchone()[0]
            # 获取表统计
            cursor = self._conn.execute("SELECT COUNT(*) FROM memories")
            memory_count = cursor.fetchone()[0]
            cursor = self._conn.execute("SELECT COUNT(*) FROM checkpoints")
            checkpoint_count = cursor.fetchone()[0]
            return {
                "integrity": integrity,
                "memory_count": memory_count,
                "checkpoint_count": checkpoint_count,
                "db_size_bytes": self.get_size(),
                "vec_available": self._vec_available,
            }

        return await self._run_sync(_check)

    def close(self) -> None:
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None
