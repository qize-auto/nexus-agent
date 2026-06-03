"""
Tests for nexusagent.execution.error_recovery — Error Recovery Engine
"""

import pytest

from nexusagent.execution.error_recovery import (
    ErrorRecoveryEngine,
    RecoveryAction,
    _extract_domain_keyword,
    _expand_short_query,
    _looks_like_url,
    _guess_url_from_query,
)


class TestHelpers:
    def test_extract_domain_keyword(self):
        assert _extract_domain_keyword("https://python.org/doc") == "python"
        assert _extract_domain_keyword("https://www.github.com") == "github"
        assert _extract_domain_keyword("not-a-url") == "not-a-url"

    def test_looks_like_url(self):
        assert _looks_like_url("https://example.com")
        assert _looks_like_url("http://test.org")
        assert _looks_like_url("www.baidu.com")
        assert not _looks_like_url("python tutorial")
        assert not _looks_like_url("")

    def test_guess_url_from_query(self):
        assert _guess_url_from_query("https://test.com") == "https://test.com"
        assert _guess_url_from_query("www.example.com") == "https://www.example.com"
        assert _guess_url_from_query("test") == "https://test"

    def test_expand_short_query(self):
        assert "Python" in _expand_short_query("py")
        assert "JavaScript" in _expand_short_query("js")
        assert _expand_short_query("hello") == "hello tutorial"
        assert _expand_short_query("ai") == "artificial intelligence"


class TestErrorRecoveryEngine:
    def test_can_recover_known_tools(self):
        engine = ErrorRecoveryEngine()
        assert engine.can_recover("browser.visit", "timeout")
        assert engine.can_recover("file.read", "not found")
        assert engine.can_recover("search.web", "no results")
        assert engine.can_recover("rag.retrieve", "empty")
        assert not engine.can_recover("unknown.tool", "error")

    def test_recover_browser_visit_timeout(self):
        engine = ErrorRecoveryEngine()
        action = engine.recover(
            "browser.visit",
            "Connection timeout",
            {"url": "https://python.org/doc"},
        )
        assert action is not None
        assert action.tool_name == "search.web"
        assert "python" in action.arguments.get("query", "")

    def test_recover_file_read_not_found(self):
        engine = ErrorRecoveryEngine()
        action = engine.recover(
            "file.read",
            "File not found: /path/to/file.txt",
            {"path": "/path/to/file.txt"},
        )
        assert action is not None
        assert action.tool_name == "file.list"
        assert action.arguments["path"] == "/path/to"

    def test_recover_file_read_unsafe_path(self):
        engine = ErrorRecoveryEngine()
        action = engine.recover(
            "file.read",
            "路径不安全或超出项目范围",
            {"path": "../../etc/passwd"},
        )
        assert action is not None
        # 参数修正：保留 basename
        assert action.arguments["path"] == "passwd"

    def test_recover_search_web_no_results(self):
        engine = ErrorRecoveryEngine()
        action = engine.recover(
            "search.web",
            "No results found",
            {"query": "https://docs.python.org"},
        )
        assert action is not None
        assert action.tool_name == "browser.visit"

    def test_recover_search_web_normal_query_no_url(self):
        engine = ErrorRecoveryEngine()
        action = engine.recover(
            "search.web",
            "No results found",
            {"query": "python asyncio tutorial"},
        )
        # 查询词不像 URL，不触发 browser.visit
        assert action is None

    def test_recover_rag_retrieve_empty(self):
        engine = ErrorRecoveryEngine()
        action = engine.recover(
            "rag.retrieve",
            "No results in knowledge base",
            {"query": "asyncio best practices"},
        )
        assert action is not None
        assert action.tool_name == "search.web"
        assert "asyncio" in action.arguments.get("query", "")

    def test_recover_unknown_tool_returns_none(self):
        engine = ErrorRecoveryEngine()
        action = engine.recover(
            "unknown.tool",
            "some error",
            {"arg": "value"},
        )
        assert action is None

    def test_recovery_action_reason(self):
        engine = ErrorRecoveryEngine()
        action = engine.recover(
            "browser.visit",
            "timeout",
            {"url": "https://example.com"},
        )
        assert action is not None
        assert "降级" in action.reason or "browser.visit" in action.reason


class TestRecoveryAction:
    @pytest.mark.asyncio
    async def test_execute_with_mock_registry(self):
        class MockTool:
            async def invoke(self, **kwargs):
                return f"mock result for {kwargs}"

        class MockRegistry:
            def get(self, name):
                return MockTool()

        action = RecoveryAction(
            tool_name="search.web",
            arguments={"query": "test"},
            reason="test recovery",
        )
        result = await action.execute(MockRegistry())
        assert "recovered via search.web" in result
        assert "mock result" in result

    @pytest.mark.asyncio
    async def test_execute_missing_tool(self):
        class MockRegistry:
            def get(self, name):
                return None

        action = RecoveryAction(
            tool_name="missing.tool",
            arguments={},
            reason="test",
        )
        result = await action.execute(MockRegistry())
        assert "recovery failed" in result
        assert "未注册" in result
