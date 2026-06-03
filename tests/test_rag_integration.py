"""
Tests for nexusagent.tools.rag — RAG retrieval tool integration
"""

import os
import pytest

from nexusagent.tools.rag import RAGRetrieveTool, _chunk_text


class TestChunkText:
    def test_empty(self):
        assert _chunk_text("") == []

    def test_short_text(self):
        assert _chunk_text("hello world") == ["hello world"]

    def test_chunking(self):
        text = "a" * 2500
        chunks = _chunk_text(text, chunk_size=1000, overlap=200)
        # 2500 chars, step=800: 0-1000, 800-1800, 1600-2600 -> but 1600+1000=2600 > 2500 so last is 1600-2500 (900 chars)
        # Actually: start=0 (end=1000), start=800 (end=1800), start=1600 (end=2600 -> clamp to 2500)
        # So 3 chunks
        assert len(chunks) >= 3
        assert len(chunks[0]) == 1000
        assert len(chunks[-1]) <= 1000

    def test_overlap_consistency(self):
        text = "x" * 3000
        chunks = _chunk_text(text, chunk_size=1000, overlap=200)
        # 相邻片段应有重叠
        assert chunks[0][-200:] == chunks[1][:200]


class TestRAGRetrieveTool:
    def test_to_tool_spec(self):
        tool = RAGRetrieveTool()
        spec = tool.to_tool_spec()
        assert spec["name"] == "rag.retrieve"
        assert "ChromaDB" in spec["description"] or "语义" in spec["description"]
        assert "query" in spec["input_schema"]["properties"]
        assert "top_k" in spec["input_schema"]["properties"]

    @pytest.mark.asyncio
    async def test_retrieve_empty_query(self):
        tool = RAGRetrieveTool()
        result = await tool.retrieve("")
        assert "不能为空" in result

    @pytest.mark.asyncio
    async def test_retrieve_no_chromadb(self):
        tool = RAGRetrieveTool()
        result = await tool.retrieve("python asyncio")
        # 没有 ChromaDB 时应返回友好提示
        assert "知识库暂不可用" in result or "未在知识库中找到" in result

    @pytest.mark.asyncio
    async def test_invoke_interface(self):
        tool = RAGRetrieveTool()
        result = await tool.invoke("test query")
        assert isinstance(result, str)

    def test_chunk_text_reusable_for_upload(self):
        # 验证 _chunk_text 函数在上传端点中的行为
        doc = "第一节内容。" * 200 + "第二节内容。" * 200 + "第三节内容。" * 200
        chunks = _chunk_text(doc, chunk_size=500, overlap=100)
        assert len(chunks) >= 3
        # 验证所有片段总长度 >= 原文长度（因为重叠）
        total_len = sum(len(c) for c in chunks)
        assert total_len >= len(doc)
        # 验证第一个和最后一个片段包含原文首尾
        assert doc.startswith(chunks[0][:50])
        assert doc.endswith(chunks[-1][-50:])
