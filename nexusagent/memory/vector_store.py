"""
NexusAgent v4.0+ — 向量存储 / RAG 基础层

基于 ChromaDB 的语义检索，支持:
  - 文档嵌入与存储
  - 相似度搜索
  - 会话隔离 (collection per session)

可选依赖: pip install chromadb

Usage:
    store = ChromaVectorStore()
    await store.add_document("这是要存储的文本", {"source": "upload.pdf"})
    results = await store.search("相关查询", top_k=3)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nexus.memory.vector")


@dataclass
class VectorSearchResult:
    """向量搜索结果"""
    text: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class ChromaVectorStore:
    """
    ChromaDB 向量存储封装

    配置:
        CHROMA_PERSIST_DIR — 持久化目录（默认 ./chroma_db）
    """

    def __init__(
        self,
        collection_name: str = "nexus_documents",
        persist_dir: Optional[str] = None,
    ):
        self._collection_name = collection_name
        self._persist_dir = persist_dir or os.environ.get("CHROMA_PERSIST_DIR", "./chroma_db")
        self._client: Optional[Any] = None
        self._collection: Optional[Any] = None

    def _ensure_client(self) -> bool:
        """延迟初始化 ChromaDB 客户端"""
        if self._client is not None:
            return True
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            logger.warning("chromadb 未安装，向量存储不可用。pip install chromadb")
            return False

        try:
            self._client = chromadb.PersistentClient(
                path=self._persist_dir,
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("ChromaDB 向量存储已初始化: %s", self._persist_dir)
            return True
        except Exception as e:
            logger.warning("ChromaDB 初始化失败: %s", e)
            return False

    async def add_document(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None,
    ) -> bool:
        """
        添加文档到向量存储

        Args:
            text: 文档文本内容
            metadata: 附加元数据（如 source, filename, session_id）
            doc_id: 可选文档 ID（不指定则自动生成）
        """
        if not self._ensure_client():
            return False
        if not text or not text.strip():
            return False

        meta = metadata or {}
        doc_id = doc_id or f"doc_{hash(text) & 0xFFFFFFFF}"

        try:
            self._collection.add(
                documents=[text],
                metadatas=[meta],
                ids=[doc_id],
            )
            logger.debug("文档已嵌入: %s (len=%d)", doc_id, len(text))
            return True
        except Exception as e:
            logger.warning("文档嵌入失败: %s", e)
            return False

    async def add_documents(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        """批量添加文档，返回成功数量"""
        if not self._ensure_client():
            return 0

        metas = metadatas or [{}] * len(texts)
        ids = [f"doc_{i}_{hash(t) & 0xFFFFFFFF}" for i, t in enumerate(texts)]

        try:
            self._collection.add(
                documents=texts,
                metadatas=metas,
                ids=ids,
            )
            logger.info("批量嵌入 %d 篇文档", len(texts))
            return len(texts)
        except Exception as e:
            logger.warning("批量嵌入失败: %s", e)
            return 0

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchResult]:
        """
        语义相似度搜索

        Args:
            query: 查询文本
            top_k: 返回结果数
            filter_metadata: 元数据过滤条件（如 {"session_id": "xxx"}）
        """
        if not self._ensure_client():
            return []
        if not query or not query.strip():
            return []

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=min(top_k, 50),
                where=filter_metadata,
            )
            output: List[VectorSearchResult] = []
            docs = results.get("documents", [[]])[0]
            distances = results.get("distances", [[]])[0]
            metas = results.get("metadatas", [[]])[0]

            for doc, dist, meta in zip(docs, distances, metas):
                # ChromaDB cosine 距离 → 相似度分数 (1 - distance)
                score = 1.0 - float(dist)
                output.append(VectorSearchResult(text=doc, score=score, metadata=meta or {}))
            return output
        except Exception as e:
            logger.warning("向量搜索失败: %s", e)
            return []

    async def delete(self, doc_id: str) -> bool:
        """删除指定文档"""
        if not self._ensure_client():
            return False
        try:
            self._collection.delete(ids=[doc_id])
            return True
        except Exception as e:
            logger.warning("删除文档失败: %s", e)
            return False

    async def count(self) -> int:
        """返回存储的文档总数"""
        if not self._ensure_client():
            return 0
        try:
            return self._collection.count()
        except Exception as e:
            logger.warning("获取文档数失败: %s", e)
            return 0

    def is_available(self) -> bool:
        """检查向量存储是否可用"""
        return self._ensure_client()
