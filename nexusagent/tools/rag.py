"""
NexusAgent v4.0+ — RAG 检索工具

基于 ChromaVectorStore 的语义检索，让 ReAct 引擎能查询用户上传的文档。

Usage:
    tool = RAGRetrieveTool()
    result = await tool.retrieve("asyncio 并发编程")
    print(result)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from nexusagent.memory.vector_store import ChromaVectorStore, VectorSearchResult

logger = logging.getLogger("nexus.tools.rag")


class RAGRetrieveTool:
    """
    RAG 检索工具 — 查询已上传文档的语义内容

    配置:
        CHROMA_PERSIST_DIR — ChromaDB 持久化目录
    """

    def __init__(self, store: Optional[ChromaVectorStore] = None):
        self._store = store

    def _get_store(self) -> Optional[ChromaVectorStore]:
        if self._store is None:
            try:
                self._store = ChromaVectorStore()
            except Exception as e:
                logger.warning("ChromaVectorStore 初始化失败: %s", e)
        return self._store

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        session_id: str = "",
    ) -> str:
        """
        语义检索已上传的文档内容

        Args:
            query: 查询问题
            top_k: 返回结果数 (1-10)
            session_id: 可选会话过滤
        """
        store = self._get_store()
        if store is None:
            return (
                "[RAG] 知识库暂不可用。"
                "可能原因: chromadb 未安装 或 尚未上传任何文档。"
            )

        if not query or not query.strip():
            return "[RAG] 查询内容不能为空。"

        filter_meta = {"session_id": session_id} if session_id else None
        try:
            results = await store.search(
                query=query.strip(),
                top_k=min(top_k, 10),
                filter_metadata=filter_meta,
            )
        except Exception as e:
            logger.warning("RAG 检索失败: %s", e)
            return f"[RAG] 检索出错: {e}"

        if not results:
            return (
                f"未在知识库中找到与「{query}」相关的内容。"
                "提示: 请先上传文档（PDF/DOCX/TXT 等），再提问。"
            )

        lines = [f"## RAG 检索结果: {query}", ""]
        for i, r in enumerate(results, 1):
            source = r.metadata.get("filename", r.metadata.get("source", "未知来源"))
            score_pct = round(r.score * 100, 1)
            lines.append(f"### {i}. {source} (相关度: {score_pct}%)")
            # 截断过长的文本
            snippet = r.text.replace("\n", " ")[:800]
            lines.append(snippet)
            lines.append("")

        return "\n".join(lines)

    # ── ToolSpec 兼容 ──

    async def invoke(self, query: str, top_k: int = 5, session_id: str = "") -> str:
        """供 ToolRegistry 调用的统一接口"""
        return await self.retrieve(query, top_k, session_id)

    def to_tool_spec(self) -> Dict[str, Any]:
        return {
            "name": "rag.retrieve",
            "description": (
                "检索用户已上传文档的内容。"
                "当用户的问题涉及已上传的 PDF、Word、PPT 等文件时使用此工具。"
                "支持语义相似度搜索，无需精确关键词匹配。"
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "查询问题，如'这份文档讲了什么'",
                    },
                    "top_k": {
                        "type": "integer",
                        "default": 5,
                        "description": "返回结果数 (1-10)",
                    },
                    "session_id": {
                        "type": "string",
                        "default": "",
                        "description": "可选会话 ID 过滤",
                    },
                },
                "required": ["query"],
            },
        }


def _chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """
    将长文本切分为重叠的片段

    Args:
        text: 原始文本
        chunk_size: 每片最大字符数
        overlap: 相邻片段的重叠字符数
    """
    if not text:
        return []
    chunks: List[str] = []
    step = chunk_size - overlap
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        if end >= len(text):
            break
        start += step
    return chunks
