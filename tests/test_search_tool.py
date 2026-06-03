"""
Tests for nexusagent.tools.search — SearXNG search tool
"""

import pytest

from nexusagent.tools.search import SearXNGTool, SearchResult, SearchResultItem


class TestSearchResult:
    def test_to_markdown_with_results(self):
        result = SearchResult(
            query="python",
            items=[
                SearchResultItem(title="Python.org", url="https://python.org", content="Python is a programming language.", engine="google", score=1.0),
                SearchResultItem(title="PyPI", url="https://pypi.org", content="Python Package Index", engine="bing", score=0.9),
            ],
            total=2,
        )
        md = result.to_markdown()
        assert "Python.org" in md
        assert "https://python.org" in md
        assert "PyPI" in md
        assert "Python is a programming language" in md

    def test_to_markdown_empty(self):
        result = SearchResult(query="xyz123notfound", items=[], total=0)
        md = result.to_markdown()
        assert "No results found" in md
        assert "xyz123notfound" in md

    def test_to_markdown_error(self):
        result = SearchResult(query="test", error="connection refused")
        md = result.to_markdown()
        assert "connection refused" in md

    def test_to_dict(self):
        result = SearchResult(
            query="test",
            items=[SearchResultItem(title="T", url="http://t", content="c", engine="e", score=1.0)],
            total=1,
        )
        d = result.to_dict()
        assert d["query"] == "test"
        assert d["total"] == 1
        assert len(d["items"]) == 1
        assert d["items"][0]["title"] == "T"


class TestSearXNGTool:
    def test_init_default_host(self):
        tool = SearXNGTool()
        assert tool._host == "http://localhost:8081"

    def test_init_custom_host(self):
        tool = SearXNGTool(host="http://searxng:8080")
        assert tool._host == "http://searxng:8080"

    def test_to_tool_spec(self):
        tool = SearXNGTool()
        spec = tool.to_tool_spec()
        assert spec["name"] == "search.web"
        assert "SearXNG" in spec["description"]
        assert "query" in spec["input_schema"]["properties"]
        assert "categories" in spec["input_schema"]["properties"]

    @pytest.mark.asyncio
    async def test_search_empty_query(self):
        tool = SearXNGTool()
        result = await tool.search("")
        assert result.error is not None
        assert "cannot be empty" in result.error

    @pytest.mark.asyncio
    async def test_invoke_returns_markdown(self):
        tool = SearXNGTool(host="http://invalid-host:9999")
        result = await tool.invoke("python")
        # 由于 host 无效，应该返回错误信息
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_search_unavailable_host(self):
        tool = SearXNGTool(host="http://localhost:59999")
        result = await tool.search("test query")
        assert result.error is not None
        assert "Cannot connect" in result.error or "Failed" in result.error or "Connection" in result.error
