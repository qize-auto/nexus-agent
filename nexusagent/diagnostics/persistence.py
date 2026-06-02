"""
NexusAgent Diagnostic Persistence — 诊断快照持久化与历史趋势查询

Usage:
    from nexusagent.diagnostics.persistence import DiagnosticStore
    store = DiagnosticStore()
    store.save_snapshot("health", {"overall_healthy": True}, alert_count=0)
    points = store.get_history("health", hours=24)
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nexus.diagnostics.persistence")


class DiagnosticStore:
    """诊断快照存储 — SQLite WAL 模式，与 MemoryStore 共享数据库文件"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = str(Path.home() / ".nexusagent" / "nexus_memory.db")
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库表"""
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS diagnostics_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                category TEXT NOT NULL,
                data_json TEXT NOT NULL,
                alert_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_diagnostics_snapshots_category_time
            ON diagnostics_snapshots(category, timestamp)
            """
        )

        # Alerts 表 — 告警历史
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS diagnostics_alerts (
                id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                level TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                source TEXT NOT NULL,
                acknowledged INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_diagnostics_alerts_time
            ON diagnostics_alerts(timestamp)
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_diagnostics_alerts_level
            ON diagnostics_alerts(level)
            """
        )
        self._conn.commit()
        logger.info("DiagnosticStore 初始化完成: %s", self._db_path)

    def save_snapshot(self, category: str, data: Dict[str, Any], alert_count: int = 0) -> None:
        """保存诊断快照"""
        if self._conn is None:
            return
        try:
            self._conn.execute(
                """
                INSERT INTO diagnostics_snapshots (timestamp, category, data_json, alert_count)
                VALUES (?, ?, ?, ?)
                """,
                (time.time(), category, json.dumps(data, ensure_ascii=False), alert_count),
            )
            self._conn.commit()
        except (sqlite3.ProgrammingError, sqlite3.OperationalError):
            # Connection closed while thread operating — ignore gracefully
            pass
        except Exception as e:
            logger.warning("诊断快照保存失败: %s", e)

    def get_history(self, category: str, hours: float = 24.0) -> List[Dict[str, Any]]:
        """按类别和时间范围查询历史快照"""
        if self._conn is None:
            return []
        since = time.time() - (hours * 3600)
        try:
            cur = self._conn.execute(
                """
                SELECT timestamp, data_json, alert_count
                FROM diagnostics_snapshots
                WHERE category = ? AND timestamp > ?
                ORDER BY timestamp ASC
                """,
                (category, since),
            )
            rows = []
            for ts, data_json, alert_count in cur.fetchall():
                try:
                    data = json.loads(data_json)
                except Exception:
                    data = {}
                rows.append({
                    "timestamp": ts,
                    "data": data,
                    "alert_count": alert_count,
                })
            return rows
        except Exception as e:
            logger.warning("历史查询失败: %s", e)
            return []

    def cleanup(self, keep_days: int = 30) -> None:
        """清理过期快照"""
        if self._conn is None:
            return
        cutoff = time.time() - (keep_days * 86400)
        try:
            cur = self._conn.execute(
                "DELETE FROM diagnostics_snapshots WHERE timestamp < ?",
                (cutoff,),
            )
            self._conn.commit()
            if cur.rowcount > 0:
                logger.info("清理了 %d 条过期诊断快照", cur.rowcount)
        except (sqlite3.ProgrammingError, sqlite3.OperationalError):
            pass
        except Exception as e:
            logger.warning("诊断快照清理失败: %s", e)

    def save_alert(self, alert: Any) -> None:
        """保存告警记录"""
        if self._conn is None:
            return
        try:
            self._conn.execute(
                """
                INSERT INTO diagnostics_alerts (id, timestamp, level, title, message, source, acknowledged)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (alert.id, alert.timestamp, alert.level, alert.title, alert.message, alert.source),
            )
            self._conn.commit()
        except (sqlite3.ProgrammingError, sqlite3.OperationalError):
            pass
        except Exception as e:
            logger.warning("告警保存失败: %s", e)

    def get_alerts(
        self,
        level_filter: str = "",
        hours: float = 24.0,
        limit: int = 50,
        acknowledged: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """查询告警历史"""
        if self._conn is None:
            return []
        since = time.time() - (hours * 3600)
        sql = """
            SELECT id, timestamp, level, title, message, source, acknowledged
            FROM diagnostics_alerts
            WHERE timestamp > ?
        """
        params: List[Any] = [since]
        if level_filter:
            sql += " AND level = ?"
            params.append(level_filter)
        if acknowledged is not None:
            sql += " AND acknowledged = ?"
            params.append(1 if acknowledged else 0)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        try:
            cur = self._conn.execute(sql, params)
            rows = []
            for row in cur.fetchall():
                rows.append({
                    "id": row[0],
                    "timestamp": row[1],
                    "level": row[2],
                    "title": row[3],
                    "message": row[4],
                    "source": row[5],
                    "acknowledged": bool(row[6]),
                })
            return rows
        except Exception as e:
            logger.warning("告警查询失败: %s", e)
            return []

    def acknowledge_alert(self, alert_id: str) -> bool:
        """标记告警为已读"""
        if self._conn is None:
            return False
        try:
            cur = self._conn.execute(
                "UPDATE diagnostics_alerts SET acknowledged = 1 WHERE id = ?",
                (alert_id,),
            )
            self._conn.commit()
            return cur.rowcount > 0
        except (sqlite3.ProgrammingError, sqlite3.OperationalError):
            return False
        except Exception as e:
            logger.warning("告警标记失败: %s", e)
            return False

    def count_unacknowledged_alerts(self, hours: float = 24.0) -> int:
        """统计未读告警数量"""
        if self._conn is None:
            return 0
        since = time.time() - (hours * 3600)
        try:
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM diagnostics_alerts WHERE timestamp > ? AND acknowledged = 0",
                (since,),
            )
            row = cur.fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    def cleanup_alerts(self, keep_days: int = 90) -> None:
        """清理过期告警"""
        if self._conn is None:
            return
        cutoff = time.time() - (keep_days * 86400)
        try:
            cur = self._conn.execute(
                "DELETE FROM diagnostics_alerts WHERE timestamp < ?",
                (cutoff,),
            )
            self._conn.commit()
            if cur.rowcount > 0:
                logger.info("清理了 %d 条过期告警", cur.rowcount)
        except (sqlite3.ProgrammingError, sqlite3.OperationalError):
            pass
        except Exception as e:
            logger.warning("告警清理失败: %s", e)

    def close(self) -> None:
        """关闭连接"""
        if self._conn:
            self._conn.close()
            self._conn = None
