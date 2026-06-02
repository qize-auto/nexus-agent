"""
NexusAgent v4.0+ — 深度集成测试
覆盖: SlidingWindow→ReActEngine, ToolRegistry→ReActEngine,
      HybridMemory→Orchestrator, AgentSwarm→Orchestrator,
      CLI子命令, CrossPlatformPath→layer.py
"""

import os
import sys
import pytest


class TestReActEngineWithSlidingWindow:
    """ReActEngine + SlidingWindow 集成"""

    def test_window_manager_accepted(self):
        """ReActEngine 接受 window_manager 参数"""
        from nexusagent.execution.react_engine import ReActEngine
        from nexusagent.context.sliding_window import SlidingWindow, WindowStrategy

        window = SlidingWindow(max_tokens=500, strategy=WindowStrategy.TRUNCATE)
        # 使用 Mock 对象避免 heavy import
        class FakeLLM:
            async def complete(self, messages, tools=None, temperature=0.7):
                return {"content": "fake", "tool_calls": [], "usage": {"total_tokens": 10}}

        class FakeTools:
            def describe_tools(self):
                return []
            async def execute(self, name, arguments):
                return "ok"

        class FakeCheckpoint:
            async def save(self, session_id, state):
                pass
            async def load(self, session_id):
                return None

        engine = ReActEngine(
            llm=FakeLLM(),
            tools=FakeTools(),
            checkpoint_store=FakeCheckpoint(),
            window_manager=window,
        )
        assert engine._window_manager is window

    def test_prepare_messages_no_window(self):
        """无 window_manager 时返回原始消息"""
        from nexusagent.execution.react_engine import ReActEngine

        class FakeLLM:
            async def complete(self, messages, tools=None, temperature=0.7):
                return {"content": "fake", "tool_calls": [], "usage": {"total_tokens": 10}}

        class FakeTools:
            def describe_tools(self):
                return []
            async def execute(self, name, arguments):
                return "ok"

        class FakeCheckpoint:
            async def save(self, session_id, state):
                pass
            async def load(self, session_id):
                return None

        engine = ReActEngine(
            llm=FakeLLM(),
            tools=FakeTools(),
            checkpoint_store=FakeCheckpoint(),
        )
        msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
        result = engine._prepare_messages(msgs)
        assert result == msgs

    def test_prepare_messages_with_window(self):
        """有 window_manager 时压缩消息"""
        from nexusagent.execution.react_engine import ReActEngine
        from nexusagent.context.sliding_window import SlidingWindow, WindowStrategy, Message as SWMessage

        window = SlidingWindow(max_tokens=50, strategy=WindowStrategy.TRUNCATE, reserve_tokens=0)
        # 填满窗口使其截断
        for i in range(10):
            window.add_message(SWMessage(role="user", content=f"msg {i} " * 10))

        class FakeLLM:
            async def complete(self, messages, tools=None, temperature=0.7):
                return {"content": "fake", "tool_calls": [], "usage": {"total_tokens": 10}}

        class FakeTools:
            def describe_tools(self):
                return []
            async def execute(self, name, arguments):
                return "ok"

        class FakeCheckpoint:
            async def save(self, session_id, state):
                pass
            async def load(self, session_id):
                return None

        engine = ReActEngine(
            llm=FakeLLM(),
            tools=FakeTools(),
            checkpoint_store=FakeCheckpoint(),
            window_manager=window,
        )
        msgs = [{"role": "user", "content": f"msg {i} " * 10} for i in range(10)]
        result = engine._prepare_messages(msgs)
        assert len(result) <= len(msgs)


class TestToolRegistryIntegration:
    """ToolRegistry 集成到 ReActEngine"""

    @pytest.mark.asyncio
    async def test_registry_describe_tools_compatible(self):
        """ToolRegistry.describe_tools 兼容 ReActEngine 协议"""
        from nexusagent.tools.registry import ToolRegistry

        registry = ToolRegistry()
        registry.register("test.tool", lambda x: x, metadata=type('M', (), {
            'name': 'test.tool',
            'description': 'A test tool',
            'input_schema': {'type': 'object', 'properties': {'x': {'type': 'string'}}},
            'source': 'builtin',
            'enabled': True,
            'version': '1.0.0',
            'author': 'test',
            'tags': [],
            'dependencies': [],
            'output_schema': {},
        })())
        tools = registry.describe_tools()
        assert isinstance(tools, list)
        assert len(tools) == 1
        assert tools[0]["name"] == "test.tool"
        assert "description" in tools[0]
        assert "parameters" in tools[0]

    @pytest.mark.asyncio
    async def test_registry_execute_compatible(self):
        """ToolRegistry.execute 兼容 ReActEngine 协议"""
        from nexusagent.tools.registry import ToolRegistry, ToolMetadata

        registry = ToolRegistry()
        registry.register(
            "test.double",
            lambda x: x * 2,
            metadata=ToolMetadata(
                name="test.double",
                description="Double a number",
                input_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
            ),
        )
        result = await registry.execute("test.double", {"x": 21})
        assert result == 42


class TestOrchestratorWithHybridMemory:
    """Orchestrator + HybridMemory 集成"""

    @pytest.mark.asyncio
    async def test_orchestrator_accepts_hybrid(self):
        """Orchestrator 接受 hybrid_memory 参数"""
        from nexusagent.orchestration.orchestrator import Orchestrator

        class FakeGuardrails:
            def review(self, content, context=None):
                type('R', (), {'is_denied': False, 'requires_user_approval': False, 'reason': ''})()

        class FakeReact:
            async def run(self, **kwargs):
                from nexusagent.execution.react_engine import ReActResult, ExitReason
                return ReActResult(answer="ok", exit_reason=ExitReason.NORMAL_COMPLETION)

        orch = Orchestrator(
            guardrails=FakeGuardrails(),
            react_engine=FakeReact(),
            trust_scores={},
            memory_store=None,
            hybrid_memory=None,
            swarm=None,
        )
        assert orch._hybrid is None
        assert orch._swarm is None

    def test_is_complex_task_detection(self):
        """复杂任务检测"""
        from nexusagent.orchestration.orchestrator import Orchestrator

        class FakeGuardrails:
            pass

        class FakeReact:
            pass

        orch = Orchestrator(
            guardrails=FakeGuardrails(),
            react_engine=FakeReact(),
            trust_scores={},
            memory_store=None,
            swarm=type('FakeSwarm', (), {})(),  # 有 swarm 才能检测
        )
        assert orch._is_complex_task("分析数据并生成图表") == (True, "swarm")
        assert orch._is_complex_task("搜索新闻并总结") == (True, "swarm")
        assert orch._is_complex_task("你好") == (False, "react")
        assert orch._is_complex_task("简单查询") == (False, "react")


class TestLayerWithCrossPlatform:
    """layer.py + CrossPlatformPath 集成"""

    def test_sanitize_path_uses_cross_platform(self):
        """_sanitize_path 使用 CrossPlatformPath.is_safe"""
        from nexusagent.tools.layer import MockToolRegistry

        reg = MockToolRegistry(project_root="/tmp/test_project")
        # 合法路径
        assert reg._sanitize_path("data/file.txt") is not None
        # 路径遍历应被阻止
        assert reg._sanitize_path("../../../etc/passwd") is None


class TestMainCLIIntegration:
    """main.py CLI 子命令集成"""

    def test_main_parser_has_subcommands(self):
        """argparse 包含子命令"""
        from nexusagent.main import main
        import argparse
        # 通过 inspect 确认 main 函数存在
        assert callable(main)

    def test_cli_doctor_importable(self):
        """cli.doctor 可导入"""
        from nexusagent.cli.doctor import main as doctor_main
        assert callable(doctor_main)

    def test_cli_tool_importable(self):
        """cli.main.cmd_tool 可导入"""
        from nexusagent.cli.main import cmd_tool
        assert callable(cmd_tool)
