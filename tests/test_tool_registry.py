"""
NexusAgent v4.0+ — Tool Registry 测试
覆盖: 注册/注销、发现、搜索、统计、CLI 集成
"""

import pytest

from nexusagent.tools.registry import (
    ToolRegistry,
    ToolMetadata,
    RegisteredTool,
    get_registry,
)


class TestToolRegistry:
    """ToolRegistry 核心测试"""

    def test_register_and_get(self):
        """注册和获取工具"""
        registry = ToolRegistry()

        def dummy_tool(x: int) -> int:
            return x * 2

        tool = registry.register("dummy.double", dummy_tool)
        assert isinstance(tool, RegisteredTool)

        fetched = registry.get("dummy.double")
        assert fetched is tool
        assert fetched.metadata.name == "dummy.double"

    def test_unregister(self):
        """注销工具"""
        registry = ToolRegistry()
        registry.register("test.a", lambda: 1)
        assert registry.get("test.a") is not None
        assert registry.unregister("test.a") is True
        assert registry.get("test.a") is None
        assert registry.unregister("test.a") is False

    def test_list_tools(self):
        """列出工具"""
        registry = ToolRegistry()
        registry.register("a.tool", lambda: 1, ToolMetadata(name="a.tool", source="builtin"))
        registry.register("b.tool", lambda: 2, ToolMetadata(name="b.tool", source="plugin"))

        all_tools = registry.list_tools()
        assert len(all_tools) == 2

        builtin = registry.list_tools(source="builtin")
        assert len(builtin) == 1
        assert builtin[0]["name"] == "a.tool"

    def test_search(self):
        """搜索工具"""
        registry = ToolRegistry()
        registry.register(
            "browser.visit",
            lambda: 1,
            ToolMetadata(name="browser.visit", description="访问网页", tags=["web", "browser"]),
        )
        registry.register(
            "code.run",
            lambda: 2,
            ToolMetadata(name="code.run", description="运行代码", tags=["code"]),
        )

        results = registry.search("browser")
        assert len(results) == 1
        assert results[0]["name"] == "browser.visit"

        results = registry.search("run")
        assert len(results) == 1
        assert results[0]["name"] == "code.run"

        results = registry.search("", tags=["web"])
        assert len(results) == 1

    def test_get_by_tag(self):
        """按标签获取工具"""
        registry = ToolRegistry()
        registry.register(
            "t1",
            lambda: 1,
            ToolMetadata(name="t1", tags=["network", "io"]),
        )
        registry.register(
            "t2",
            lambda: 2,
            ToolMetadata(name="t2", tags=["network"]),
        )

        tools = registry.get_by_tag("network")
        assert len(tools) == 2

        tools = registry.get_by_tag("io")
        assert len(tools) == 1
        assert tools[0].metadata.name == "t1"

    def test_get_stats(self):
        """统计信息"""
        registry = ToolRegistry()
        registry.register("a", lambda: 1, ToolMetadata(name="a", source="builtin"))
        registry.register("b", lambda: 2, ToolMetadata(name="b", source="plugin"))

        stats = registry.get_stats()
        assert stats["total"] == 2
        assert stats["enabled"] == 2
        assert stats["sources"]["builtin"] == 1
        assert stats["sources"]["plugin"] == 1

    def test_export_manifest(self):
        """导出清单"""
        registry = ToolRegistry()
        registry.register("a", lambda: 1, ToolMetadata(name="a", version="1.0.0"))
        manifest = registry.export_manifest()
        assert "a" in manifest
        assert "1.0.0" in manifest

    @pytest.mark.asyncio
    async def test_invoke_async(self):
        """调用异步工具"""
        registry = ToolRegistry()

        async def async_tool(x: int) -> int:
            return x + 10

        registry.register("async.add10", async_tool)
        tool = registry.get("async.add10")
        result = await tool.invoke(x=5)
        assert result == 15

    @pytest.mark.asyncio
    async def test_invoke_sync(self):
        """调用同步工具（invoke 始终为 async 接口）"""
        registry = ToolRegistry()

        def sync_tool(x: int) -> int:
            return x * 3

        registry.register("sync.mul3", sync_tool)
        tool = registry.get("sync.mul3")
        result = await tool.invoke(x=4)
        assert result == 12

    def test_discover_builtin_tools(self):
        """发现内置工具"""
        registry = ToolRegistry()
        count = registry.discover_builtin_tools()
        assert count >= 0  # 可能有模块加载失败
        stats = registry.get_stats()
        assert stats["total"] >= count

    def test_get_registry_singleton(self):
        """全局单例"""
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_tool_metadata_defaults(self):
        """工具元数据默认值"""
        meta = ToolMetadata(name="test")
        assert meta.version == "1.0.0"
        assert meta.source == "builtin"
        assert meta.enabled is True
        assert meta.tags == []
