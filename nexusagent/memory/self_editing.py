# 🧪 EXPERIMENTAL / 实验性模块
# 该模块尚未接入 NexusAgent 主执行流程（main.py / orchestrator）。
# 功能完整且在测试中被引用，但 API 可能不稳定。
# This module is not yet wired into the main NexusAgent execution flow.
# Fully functional in isolation with test coverage, but APIs may change.
"""
NexusAgent v4.0+ — 自编辑记忆

设计参考:
- Letta Memory Blocks: https://docs.letta.ai/memory
  "Agent can actively modify its own memory via tool calls"

职责:
    将记忆维护操作（update/delete/query）封装为 Agent 可调用的工具接口
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from nexusagent.memory.store import MemoryEntry, MemoryStore

logger = logging.getLogger("nexus.memory.self_editing")


class SelfEditingMemory:
    """
    自编辑记忆接口

    Usage:
        sem = SelfEditingMemory(store)
        await sem.update_memory(memory_id=1, new_content="更新后的内容")
        await sem.delete_memory(memory_id=1)
    """

    def __init__(self, store: Optional[MemoryStore] = None):
        self._store = store

    async def update_memory(
        self,
        memory_id: int,
        new_content: str,
        tenant_id: str = "default",
    ) -> bool:
        """更新指定记忆内容"""
        try:
            # 使用 SQL 直接更新
            def _update():
                conn = self._store._conn
                cursor = conn.execute(
                    "UPDATE memories SET content = ? WHERE id = ? AND tenant_id = ?",
                    (new_content, memory_id, tenant_id),
                )
                conn.commit()
                return cursor.rowcount > 0

            result = await self._store._run_sync(_update)
            if result:
                logger.info("记忆已更新: id=%d, tenant=%s", memory_id, tenant_id)
            return result
        except Exception as e:
            logger.error("记忆更新失败: %s", e)
            return False

    async def delete_memory(
        self,
        memory_id: int,
        tenant_id: str = "default",
    ) -> bool:
        """删除指定记忆"""
        try:
            def _delete():
                conn = self._store._conn
                cursor = conn.execute(
                    "DELETE FROM memories WHERE id = ? AND tenant_id = ?",
                    (memory_id, tenant_id),
                )
                conn.commit()
                return cursor.rowcount > 0

            result = await self._store._run_sync(_delete)
            if result:
                logger.info("记忆已删除: id=%d, tenant=%s", memory_id, tenant_id)
            return result
        except Exception as e:
            logger.error("记忆删除失败: %s", e)
            return False

    async def query_memories(
        self,
        query: str,
        tenant_id: str = "default",
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """查询记忆"""
        try:
            results = await self._store.search_fts(query, limit=limit, tenant_id=tenant_id)
            return [r.to_dict() for r in results]
        except Exception as e:
            logger.error("记忆查询失败: %s", e)
            return []

    async def invoke(self, memory_id: int = None, new_content: str = None, **kwargs) -> Any:
        """ToolRegistry 兼容调用入口 — 更新记忆"""
        if memory_id is None or new_content is None:
            return {"error": "Missing memory_id or new_content"}
        return await self.update_memory(memory_id, new_content)

    def to_tool_spec(self) -> Dict[str, Any]:
        """返回 ToolSpec 兼容描述"""
        return {
            "name": "memory.update",
            "description": "更新 Agent 记忆中的特定条目。用于纠正错误信息或更新用户偏好。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "memory_id": {"type": "integer", "description": "记忆条目ID"},
                    "new_content": {"type": "string", "description": "新内容"},
                },
                "required": ["memory_id", "new_content"],
            },
        }


class SelfEditingDelete:
    """记忆删除工具"""

    def __init__(self, store: Optional[Any] = None):
        self._store = store

    async def invoke(self, memory_id: int = None, **kwargs) -> Any:
        """ToolRegistry 兼容调用入口 — 删除记忆"""
        if memory_id is None:
            return {"error": "Missing memory_id"}
        if self._store is None:
            return {"error": "Store not available"}
        try:
            def _delete():
                conn = self._store._conn
                cursor = conn.execute(
                    "DELETE FROM memories WHERE id = ? AND tenant_id = ?",
                    (memory_id, "default"),
                )
                conn.commit()
                return cursor.rowcount > 0
            result = await self._store._run_sync(_delete)
            return {"success": result}
        except Exception as e:
            return {"error": str(e)}

    def to_tool_spec(self) -> Dict[str, Any]:
        return {
            "name": "memory.delete",
            "description": "删除 Agent 记忆中的特定条目。用于清理过时或错误的记忆。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "memory_id": {"type": "integer", "description": "记忆条目ID"},
                },
                "required": ["memory_id"],
            },
        }


class SelfEditingQuery:
    """记忆查询工具"""

    def __init__(self, store: Optional[Any] = None):
        self._store = store

    async def invoke(self, query: str = None, limit: int = 10, **kwargs) -> Any:
        """ToolRegistry 兼容调用入口 — 查询记忆"""
        if query is None:
            return {"error": "Missing query"}
        if self._store is None:
            return {"error": "Store not available"}
        try:
            results = await self._store.search_fts(query, limit=limit, tenant_id="default")
            return [r.to_dict() for r in results]
        except Exception as e:
            return {"error": str(e)}

    def to_tool_spec(self) -> Dict[str, Any]:
        return {
            "name": "memory.query",
            "description": "查询 Agent 记忆中的相关条目。用于检索历史信息或用户偏好。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "查询关键词"},
                    "limit": {"type": "integer", "description": "返回条数上限", "default": 10},
                },
                "required": ["query"],
            },
        }
