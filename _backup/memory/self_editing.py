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

    def __init__(self, store: MemoryStore):
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
