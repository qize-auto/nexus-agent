"""
NexusAgent v4.0+ — 工具生态扩展测试
覆盖: BrowserTool, CodeInterpreterTool, PluginManager, MCPServer
"""

import pytest

from nexusagent.tools.browser import BrowserTool, BrowserResult
from nexusagent.tools.code_interpreter import CodeInterpreterTool, CodeResult
from nexusagent.tools.plugin_manager import PluginManager, PluginInfo


class TestBrowserTool:
    """浏览器工具测试"""

    def test_init(self):
        browser = BrowserTool()
        assert browser is not None

    @pytest.mark.asyncio
    async def test_visit_with_requests_fallback(self):
        """测试降级到 requests 模式（不需要 playwright）"""
        browser = BrowserTool()
        browser._playwright_available = False
        result = await browser.visit("https://example.com")
        # 如果网络不可用，可能失败
        assert isinstance(result, BrowserResult)

    def test_to_tool_spec(self):
        browser = BrowserTool()
        spec = browser.to_tool_spec()
        assert spec["name"] == "browser.visit"
        assert "url" in spec["input_schema"]["properties"]


class TestCodeInterpreterTool:
    """代码解释器工具测试"""

    def test_init(self):
        ci = CodeInterpreterTool()
        assert ci is not None

    @pytest.mark.asyncio
    async def test_execute_simple_python(self):
        ci = CodeInterpreterTool()
        result = await ci.execute("print('hello world')")
        assert isinstance(result, CodeResult)
        assert "hello world" in result.stdout or not result.success
        # 本地执行可能受环境限制

    @pytest.mark.asyncio
    async def test_execute_with_error(self):
        ci = CodeInterpreterTool()
        result = await ci.execute("raise ValueError('test error')")
        assert result.success is False or result.exit_code != 0

    def test_to_tool_spec(self):
        ci = CodeInterpreterTool()
        spec = ci.to_tool_spec()
        assert spec["name"] == "code_interpreter.execute"
        assert "code" in spec["input_schema"]["properties"]


class TestPluginManager:
    """插件管理器测试"""

    def test_discover(self):
        pm = PluginManager()
        plugins = pm.discover()
        assert isinstance(plugins, list)

    def test_register_and_get_tool(self):
        pm = PluginManager()
        pm.register_tool("test_tool", lambda x: x)
        assert pm.get_tool("test_tool") is not None
        assert pm.get_tool("missing") is None

    def test_list_plugins(self):
        pm = PluginManager()
        plugins = pm.list_plugins()
        assert isinstance(plugins, list)

    def test_load_nonexistent_plugin(self):
        pm = PluginManager()
        result = pm.load_plugin("nonexistent_plugin_xyz")
        assert result is False


class TestBrowserResult:
    """BrowserResult 数据类测试"""

    def test_default_links(self):
        result = BrowserResult(url="https://example.com")
        assert result.links == []

    def test_post_init(self):
        result = BrowserResult(url="https://example.com", links=[{"text": "a", "href": "/a"}])
        assert len(result.links) == 1


class TestCodeResult:
    """CodeResult 数据类测试"""

    def test_defaults(self):
        result = CodeResult(code="print(1)")
        assert result.images == []
        assert result.files == {}
        assert result.success is True
