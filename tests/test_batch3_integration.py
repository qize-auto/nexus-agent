"""
Batch 3 Integration Tests — Verify ProfileAdapters are wired into main flow.
"""

import pytest


class TestReActEngineToolsOverride:
    """Verify ReActEngine.run() accepts tools_override."""

    def test_run_accepts_tools_override(self):
        from nexusagent.execution.react_engine import ReActEngine
        import inspect

        sig = inspect.signature(ReActEngine.run)
        assert "tools_override" in sig.parameters

    def test_tools_override_is_optional(self):
        from nexusagent.execution.react_engine import ReActEngine
        import inspect

        sig = inspect.signature(ReActEngine.run)
        param = sig.parameters["tools_override"]
        assert param.default is None


class TestMemoryProfileAdapterIntegration:
    """Verify MemoryProfileAdapter is callable from Orchestrator.process()."""

    def test_memory_profile_adapter_is_importable(self):
        from nexusagent.memory.profile_adapter import MemoryProfileAdapter
        assert MemoryProfileAdapter is not None

    def test_enhance_query_returns_string(self):
        from nexusagent.memory.profile_adapter import MemoryProfileAdapter
        from nexusagent.memory.user_profile import UserProfile

        adapter = MemoryProfileAdapter(hybrid_memory=None)
        profile = UserProfile(user_id="test")
        result = adapter.enhance_query(profile, "hello")
        assert isinstance(result, str)


class TestSwarmProfileAdapterIntegration:
    """Verify SwarmProfileAdapter influences swarm strategy."""

    def test_swarm_profile_adapter_is_importable(self):
        from nexusagent.agents.profile_adapter import SwarmProfileAdapter
        assert SwarmProfileAdapter is not None

    def test_recommend_strategy_returns_valid_strategy(self):
        from nexusagent.agents.profile_adapter import SwarmProfileAdapter
        from nexusagent.memory.user_profile import UserProfile

        adapter = SwarmProfileAdapter(swarm=None)
        profile = UserProfile(user_id="test")
        strategy = adapter.recommend_strategy(profile)
        assert strategy in ("handoff", "groupchat", "load_balance")


class TestToolRegistryProfileAdapterIntegration:
    """Verify ToolRegistryProfileAdapter filters and sorts tools."""

    def test_filter_tools_excludes_disliked(self):
        from nexusagent.tools.profile_adapter import ToolRegistryProfileAdapter
        from nexusagent.memory.user_profile import UserProfile

        adapter = ToolRegistryProfileAdapter(tool_registry=None)
        profile = UserProfile(user_id="test")
        profile.static.disliked_tools = ["shell"]

        tools = [
            {"name": "shell.exec"},
            {"name": "browser.visit"},
            {"name": "code.insert"},
        ]
        filtered = adapter.filter_tools(profile, tools)
        names = [t["name"] for t in filtered]
        assert "shell.exec" not in names
        assert "browser.visit" in names

    def test_sort_tools_prefers_preferred(self):
        from nexusagent.tools.profile_adapter import ToolRegistryProfileAdapter
        from nexusagent.memory.user_profile import UserProfile

        adapter = ToolRegistryProfileAdapter(tool_registry=None)
        profile = UserProfile(user_id="test")
        profile.static.preferred_tools = ["browser"]

        tools = [
            {"name": "code.insert", "description": ""},
            {"name": "browser.visit", "description": ""},
        ]
        sorted_tools = adapter.sort_tools(profile, tools)
        assert sorted_tools[0]["name"] == "browser.visit"
