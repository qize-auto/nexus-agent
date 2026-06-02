"""
NexusAgent v4.0+ — Database Tool (Placeholder / Basic)

提供基础 SQLite 查询能力。
P2 级别，基础实现，完整数据库支持可后续扩展。

安全模型:
- 仅支持 SQLite（本地文件）
- 路径受项目根目录限制
- 禁止 DDL 操作（DROP, ALTER 等）需 NEXUS_ALLOW_FILE_OPS=1
- DML 写操作（INSERT/UPDATE/DELETE）需 NEXUS_ALLOW_FILE_OPS=1
- SELECT 查询无需特殊权限
"""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional

from nexusagent.utils.cross_platform import CrossPlatformPath

logger = logging.getLogger("nexus.tools.database")


def _sanitize_path(path: str) -> Optional[str]:
    if not path:
        return None
    root = os.path.realpath(os.getcwd())
    cpp = CrossPlatformPath()
    if os.path.isabs(path):
        full = os.path.realpath(path)
    else:
        full = os.path.realpath(os.path.join(root, path))
    if not cpp.is_safe(full, root):
        return None
    return full


class DatabaseTool:
    """SQLite 数据库查询工具"""

    # 危险 DDL 关键字
    _DDL_KEYWORDS = {"drop", "alter", "create", "truncate"}

    async def invoke(
        self,
        db_path: str,
        query: str,
    ) -> str:
        safe = _sanitize_path(db_path)
        if safe is None:
            return f"[ERROR] 数据库路径不安全: {db_path}"

        query_stripped = query.strip().lower()
        is_ddl = any(query_stripped.startswith(kw) for kw in self._DDL_KEYWORDS)
        is_dml_write = any(query_stripped.startswith(kw) for kw in ("insert", "update", "delete"))

        if is_ddl and os.getenv("NEXUS_ALLOW_FILE_OPS", "0") != "1":
            return "[ERROR] DDL 操作已被禁用。设置 NEXUS_ALLOW_FILE_OPS=1 以启用。"
        if is_dml_write and os.getenv("NEXUS_ALLOW_FILE_OPS", "0") != "1":
            return "[ERROR] 数据写入操作已被禁用。设置 NEXUS_ALLOW_FILE_OPS=1 以启用。"

        conn = None
        try:
            conn = sqlite3.connect(safe)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query)

            if query_stripped.startswith("select") or query_stripped.startswith("with"):
                rows = cursor.fetchall()
                if not rows:
                    return "[OK] 查询返回 0 行"
                # 表格式输出
                headers = rows[0].keys()
                lines = []
                lines.append(" | ".join(headers))
                lines.append("-" * len(lines[0]))
                for row in rows[:100]:  # 限制 100 行
                    lines.append(" | ".join(str(row[h]) for h in headers))
                if len(rows) > 100:
                    lines.append(f"... ({len(rows) - 100} more rows)")
                return "\n".join(lines)
            else:
                conn.commit()
                affected = cursor.rowcount
                return f"[OK] 执行成功，影响 {affected} 行"
        except Exception as e:
            return f"[ERROR] 数据库操作失败: {e}"
        finally:
            if conn:
                conn.close()

    def to_tool_spec(self) -> Dict[str, Any]:
        return {
            "name": "database.query",
            "description": "对 SQLite 数据库执行 SQL 查询。支持 SELECT/INSERT/UPDATE/DELETE。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "SQLite 数据库文件路径"},
                    "query": {"type": "string", "description": "SQL 查询语句"},
                },
                "required": ["db_path", "query"],
            },
        }
