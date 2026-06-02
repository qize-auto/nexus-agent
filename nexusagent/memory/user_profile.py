"""
NexusAgent v4.0+ — User Profile Manager

以用户画像为中枢的自主进化系统核心存储。
设计参考:
- Letta Memory Blocks: Core (persona + human) + Archival + Recall
- Claude Memory Files: 持久化用户偏好与上下文
- LangChain Memory: 可插拔记忆抽象

职责:
    1. 层次化用户画像存储 (静态/动态/行为/安全)
    2. SQLite 持久化 + AES-256-GCM 加密敏感字段
    3. 画像版本快照 (支持回滚与审计)
    4. GDPR 合规: 被遗忘权、数据可携带权
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nexus.memory.user_profile")


# ═══════════════════════════════════════════════════════════════
# 用户画像数据模型
# ═══════════════════════════════════════════════════════════════

@dataclass
class StaticTraits:
    """静态属性 — 变化缓慢的用户特征"""
    tech_stack: List[str] = field(default_factory=list)       # 技术栈偏好
    preferred_tools: List[str] = field(default_factory=list)  # 常用工具
    work_habits: Dict[str, Any] = field(default_factory=dict)  # 工作习惯
    communication_style: str = "neutral"  # formal | casual | technical | neutral
    timezone: str = "Asia/Shanghai"
    language_preference: str = "zh-CN"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StaticTraits":
        return cls(**d)


@dataclass
class DynamicTraits:
    """动态属性 — 随会话实时变化"""
    current_project: str = ""           # 当前项目上下文
    recent_topics: List[str] = field(default_factory=list)  # 近期关注话题
    mood_trend: str = "neutral"         # 情绪倾向趋势
    last_activity: float = 0.0          # 最后活跃时间
    active_sessions: int = 0            # 当前活跃会话数

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DynamicTraits":
        return cls(**d)


@dataclass
class BehavioralTraits:
    """行为模式 — 从交互历史中提炼"""
    error_patterns: List[Dict[str, Any]] = field(default_factory=list)  # 常见错误模式
    feedback_history: List[Dict[str, Any]] = field(default_factory=list)  # 反馈历史
    workflow_frequency: Dict[str, int] = field(default_factory=dict)  # 工作流使用频率
    patience_index: float = 0.5         # 耐心指数 (0-1, 高=有耐心)
    detail_preference: float = 0.5      # 细节偏好 (0-1, 高=喜欢详细)
    temperature_preference: float = 0.7  # LLM temperature 偏好
    max_tokens_preference: int = 8000   # 期望最大token数
    timeout_preference: float = 120.0   # 期望超时秒数

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BehavioralTraits":
        return cls(**d)


@dataclass
class SecurityTraits:
    """安全与信任属性"""
    trust_score: float = 10.0           # 信任积分 (EMA)
    trust_tier: str = "NOVICE"          # NOVICE | LEARNER | TRUSTED | EXPERT
    permission_boundaries: List[str] = field(default_factory=list)  # 权限边界
    data_privacy_level: str = "standard"  # minimal | standard | strict
    pii_consent: bool = False           # 是否同意收集PII
    auto_approve_tools: List[str] = field(default_factory=list)  # 自动放行工具
    require_confirm_tools: List[str] = field(default_factory=list)  # 需确认工具

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SecurityTraits":
        return cls(**d)


@dataclass
class UserProfile:
    """
    完整用户画像 — 层次化结构

    版本控制:
        - version: 画像版本号，每次重大更新+1
        - updated_at: 最后更新时间戳
        - changelog: 变更日志列表
    """
    user_id: str
    version: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    static: StaticTraits = field(default_factory=StaticTraits)
    dynamic: DynamicTraits = field(default_factory=DynamicTraits)
    behavioral: BehavioralTraits = field(default_factory=BehavioralTraits)
    security: SecurityTraits = field(default_factory=SecurityTraits)

    # 变更日志 (支持审计与回滚)
    changelog: List[Dict[str, Any]] = field(default_factory=list)

    # 待验证画像条目 (梦境引擎处理前)
    pending_traits: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "static": self.static.to_dict(),
            "dynamic": self.dynamic.to_dict(),
            "behavioral": self.behavioral.to_dict(),
            "security": self.security.to_dict(),
            "changelog": self.changelog,
            "pending_traits": self.pending_traits,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "UserProfile":
        return cls(
            user_id=d["user_id"],
            version=d.get("version", 1),
            created_at=d.get("created_at", time.time()),
            updated_at=d.get("updated_at", time.time()),
            static=StaticTraits.from_dict(d.get("static", {})),
            dynamic=DynamicTraits.from_dict(d.get("dynamic", {})),
            behavioral=BehavioralTraits.from_dict(d.get("behavioral", {})),
            security=SecurityTraits.from_dict(d.get("security", {})),
            changelog=d.get("changelog", []),
            pending_traits=d.get("pending_traits", []),
        )

    def snapshot(self) -> Dict[str, Any]:
        """生成版本快照"""
        snap = self.to_dict()
        snap["snapshot_at"] = time.time()
        return snap


# ═══════════════════════════════════════════════════════════════
# UserProfileManager — 画像存储与管理
# ═══════════════════════════════════════════════════════════════

class UserProfileManager:
    """
    用户画像管理器

    存储: SQLite (与 MemoryStore 共享数据库文件，独立表)
    加密: 复用 MemoryEncryption 对敏感字段加密
    """

    def __init__(self, db_path: str = "nexus_memory.db", encryption: Any = None):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._encryption = encryption
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        """初始化画像表"""
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

        # 主画像表
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                version INTEGER NOT NULL DEFAULT 1,
                profile_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)

        # 版本快照表 (支持回滚)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS user_profile_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                snapshot_json TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)

        # 待处理画像条目队列
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS user_pending_traits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                trait_category TEXT NOT NULL,
                trait_key TEXT NOT NULL,
                trait_value TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.5,
                extracted_at REAL NOT NULL,
                source TEXT DEFAULT ""
            )
        """)

        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_pending_traits_user
            ON user_pending_traits(user_id)
        """)

        self._conn.commit()
        logger.info("UserProfileManager initialized at %s", self._db_path)

    def _encrypt_field(self, text: str) -> str:
        if self._encryption and text:
            return self._encryption.encrypt(text)
        return text

    def _decrypt_field(self, text: str) -> str:
        if self._encryption and text:
            return self._encryption.decrypt(text)
        return text

    # ── CRUD ──

    async def load(self, user_id: str) -> Optional[UserProfile]:
        """加载用户画像"""
        def _load():
            cursor = self._conn.execute(
                "SELECT profile_json FROM user_profiles WHERE user_id = ?",
                (user_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            decrypted = self._decrypt_field(row[0])
            return UserProfile.from_dict(json.loads(decrypted))

        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _load)

    async def save(self, profile: UserProfile) -> None:
        """保存用户画像（自动创建快照）"""
        # 先保存快照
        await self._create_snapshot(profile)

        profile.updated_at = time.time()
        profile_json = json.dumps(profile.to_dict(), ensure_ascii=False)
        encrypted = self._encrypt_field(profile_json)

        def _save():
            self._conn.execute(
                """INSERT OR REPLACE INTO user_profiles
                   (user_id, version, profile_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (profile.user_id, profile.version, encrypted,
                 profile.created_at, profile.updated_at),
            )
            self._conn.commit()

        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _save)
        logger.debug("UserProfile saved: %s v%d", profile.user_id, profile.version)

    async def create(self, user_id: str) -> UserProfile:
        """创建新用户画像"""
        profile = UserProfile(user_id=user_id)
        await self.save(profile)
        logger.info("UserProfile created: %s", user_id)
        return profile

    async def get_or_create(self, user_id: str) -> UserProfile:
        """获取或创建用户画像"""
        profile = await self.load(user_id)
        if profile is None:
            profile = await self.create(user_id)
        return profile

    # ── 版本控制 ──

    async def _create_snapshot(self, profile: UserProfile) -> None:
        """创建版本快照"""
        snapshot = profile.snapshot()
        snapshot_json = json.dumps(snapshot, ensure_ascii=False)
        encrypted = self._encrypt_field(snapshot_json)

        def _save():
            self._conn.execute(
                """INSERT INTO user_profile_snapshots
                   (user_id, version, snapshot_json, created_at)
                   VALUES (?, ?, ?, ?)""",
                (profile.user_id, profile.version, encrypted, time.time()),
            )
            # 保留最近 20 个快照
            self._conn.execute(
                """DELETE FROM user_profile_snapshots WHERE id IN (
                    SELECT id FROM user_profile_snapshots
                    WHERE user_id = ?
                    ORDER BY created_at DESC LIMIT -1 OFFSET 20
                )""",
                (profile.user_id,),
            )
            self._conn.commit()

        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _save)

    async def get_history(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取画像版本历史"""
        def _query():
            cursor = self._conn.execute(
                """SELECT version, snapshot_json, created_at
                   FROM user_profile_snapshots
                   WHERE user_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (user_id, limit),
            )
            results = []
            for row in cursor.fetchall():
                decrypted = self._decrypt_field(row[1])
                results.append({
                    "version": row[0],
                    "snapshot": json.loads(decrypted),
                    "created_at": row[2],
                })
            return results

        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _query)

    async def rollback(self, user_id: str, target_version: int) -> Optional[UserProfile]:
        """回滚到指定版本"""
        def _query():
            cursor = self._conn.execute(
                """SELECT snapshot_json FROM user_profile_snapshots
                   WHERE user_id = ? AND version = ?
                   ORDER BY created_at DESC LIMIT 1""",
                (user_id, target_version),
            )
            row = cursor.fetchone()
            if not row:
                return None
            decrypted = self._decrypt_field(row[0])
            return json.loads(decrypted)

        import asyncio
        loop = asyncio.get_event_loop()
        snapshot_data = await loop.run_in_executor(None, _query)
        if not snapshot_data:
            logger.warning("Rollback failed: version %d not found for %s", target_version, user_id)
            return None

        profile = UserProfile.from_dict(snapshot_data)
        profile.version += 1  # 回滚后版本+1
        profile.changelog.append({
            "action": "rollback",
            "from_version": target_version,
            "to_version": profile.version,
            "timestamp": time.time(),
        })
        await self.save(profile)
        logger.info("UserProfile rolled back: %s → v%d", user_id, profile.version)
        return profile

    # ── Pending Traits ──

    async def add_pending_trait(
        self,
        user_id: str,
        category: str,
        key: str,
        value: Any,
        confidence: float = 0.5,
        source: str = "",
    ) -> None:
        """添加待验证画像条目"""
        def _save():
            self._conn.execute(
                """INSERT INTO user_pending_traits
                   (user_id, trait_category, trait_key, trait_value, confidence, extracted_at, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, category, key, json.dumps(value, ensure_ascii=False),
                 confidence, time.time(), source),
            )
            self._conn.commit()

        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _save)

    async def get_pending_traits(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户的待验证条目"""
        def _query():
            cursor = self._conn.execute(
                """SELECT trait_category, trait_key, trait_value, confidence, extracted_at, source
                   FROM user_pending_traits WHERE user_id = ? ORDER BY extracted_at DESC""",
                (user_id,),
            )
            return [
                {
                    "category": row[0],
                    "key": row[1],
                    "value": json.loads(row[2]),
                    "confidence": row[3],
                    "extracted_at": row[4],
                    "source": row[5],
                }
                for row in cursor.fetchall()
            ]

        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _query)

    async def clear_pending_traits(self, user_id: str) -> int:
        """清空用户的待验证条目，返回删除数"""
        def _delete():
            cursor = self._conn.execute(
                "DELETE FROM user_pending_traits WHERE user_id = ?",
                (user_id,),
            )
            self._conn.commit()
            return cursor.rowcount

        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _delete)

    # ── GDPR 合规 ──

    async def delete_profile(self, user_id: str) -> bool:
        """完全删除用户画像 (被遗忘权)"""
        def _delete():
            self._conn.execute("DELETE FROM user_profiles WHERE user_id = ?", (user_id,))
            self._conn.execute("DELETE FROM user_profile_snapshots WHERE user_id = ?", (user_id,))
            self._conn.execute("DELETE FROM user_pending_traits WHERE user_id = ?", (user_id,))
            self._conn.commit()

        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _delete)
        logger.info("UserProfile deleted (GDPR): %s", user_id)
        return True

    async def export_profile(self, user_id: str) -> Dict[str, Any]:
        """导出用户画像 (数据可携带权)"""
        profile = await self.load(user_id)
        if not profile:
            return {"error": "Profile not found"}
        return {
            "export_metadata": {
                "user_id": user_id,
                "exported_at": time.time(),
                "format_version": "1.0",
                "legal_basis": "GDPR_Article_20",
            },
            "profile": profile.to_dict(),
            "snapshots": await self.get_history(user_id, limit=100),
        }

    # ── 便捷更新接口 ──

    async def update_trait(
        self,
        user_id: str,
        category: str,
        key: str,
        value: Any,
        source: str = "explicit",
    ) -> UserProfile:
        """更新画像属性 (自动创建 changelog 条目)"""
        profile = await self.get_or_create(user_id)

        old_value = None
        target = None
        if category == "static":
            target = profile.static
        elif category == "dynamic":
            target = profile.dynamic
        elif category == "behavioral":
            target = profile.behavioral
        elif category == "security":
            target = profile.security

        if target and hasattr(target, key):
            old_value = getattr(target, key)
            setattr(target, key, value)

        profile.version += 1
        profile.changelog.append({
            "action": "update",
            "category": category,
            "key": key,
            "old_value": old_value,
            "new_value": value,
            "source": source,
            "timestamp": time.time(),
        })

        await self.save(profile)
        return profile

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
