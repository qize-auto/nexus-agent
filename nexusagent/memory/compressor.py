"""
NexusAgent v4.0+ — 记忆压缩器

设计参考:
- Mastra Observational Memory: https://mastra.ai/docs/memory
  "Observer + Reflector compress old conversations into structured observations"

策略:
    触发式压缩：当会话消息数超过阈值时，触发 LLM 总结为语义摘要
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from nexusagent.memory.store import MemoryEntry, MemoryStore

logger = logging.getLogger("nexus.memory.compressor")


@dataclass
class CompressionResult:
    """压缩结果"""
    original_count: int
    summary: str
    success: bool


class MemoryCompressor:
    """
    记忆压缩器

    Usage:
        compressor = MemoryCompressor(store, threshold=20)
        await compressor.check_and_compress(session_id="s1")
    """

    def __init__(
        self,
        store: MemoryStore,
        threshold: int = 20,
        llm_backend: Optional[Any] = None,
    ):
        self._store = store
        self._threshold = threshold
        self._llm = llm_backend
        self._compressing: set = set()

    async def check_and_compress(self, session_id: str, tenant_id: str = "default") -> Optional[CompressionResult]:
        """
        检查并压缩会话记忆

        Returns:
            CompressionResult if compression happened, None otherwise
        """
        if session_id in self._compressing:
            return None

        try:
            entries = await self._store.get_by_session(session_id, tenant_id=tenant_id)
            if len(entries) < self._threshold:
                return None

            self._compressing.add(session_id)

            # 提取内容
            contents = [e.content for e in entries[:self._threshold]]
            summary = await self._generate_summary(contents)

            # 保存摘要到 semantic 记忆
            summary_entry = MemoryEntry(
                session_id=session_id,
                memory_type="semantic",
                content=f"[会话摘要] {summary}",
                metadata_json='{"compressed_from": "episodic", "original_count": ' + str(len(entries)) + '}',
            )
            await self._store.save(summary_entry, tenant_id=tenant_id)

            # 删除原始 episodic 条目（可选：保留最近 5 条）
            # 这里选择保留最近 5 条，删除其余
            to_delete = entries[self._threshold:]
            for entry in to_delete:
                if entry.id:
                    # 当前 MemoryStore 没有按 ID 删除的方法，需要添加
                    pass

            return CompressionResult(
                original_count=len(entries),
                summary=summary,
                success=True,
            )

        except Exception as e:
            logger.error("记忆压缩失败: %s", e)
            return CompressionResult(original_count=0, summary="", success=False)
        finally:
            self._compressing.discard(session_id)

    async def _generate_summary(self, contents: List[str]) -> str:
        """生成摘要"""
        if self._llm:
            try:
                prompt = (
                    "请将以下对话记录总结为一段简洁的摘要，保留关键信息、用户偏好和重要结论。\n\n"
                    + "\n---\n".join(contents[:15])
                    + "\n\n摘要:"
                )
                response = await self._llm.complete(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                )
                return response.get("content", "")[:500]
            except Exception as e:
                logger.warning("LLM 摘要生成失败: %s", e)

        # 降级：简单拼接
        return "; ".join(contents[:5])[:500]
