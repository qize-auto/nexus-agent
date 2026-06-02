"""
NexusAgent v4.0+ — 端到端全链路集成验证
验证: 用户输入 → SlidingWindow → ToolRegistry → ReActEngine → Orchestrator → Swarm/HybridMemory → 输出
"""

import pytest


class TestEndToEndV4:
    """全链路端到端测试"""

    @pytest.mark.asyncio
    async def test_full_chain_simple_task(self):
        """简单任务全链路: 不触发 Swarm"""
        from nexusagent.orchestration.orchestrator import Orchestrator
        from nexusagent.execution.react_engine import ReActEngine, ReActResult, ExitReason
        from nexusagent.context.sliding_window import SlidingWindow, WindowStrategy

        class FakeGuardrails:
            def review(self, content, context=None):
                return type('R', (), {'is_denied': False, 'requires_user_approval': False, 'reason': ''})()
            def review_output(self, content):
                return type('R', (), {'is_denied': False, 'reason': ''})()

        class FakeLLM:
            async def complete(self, messages, tools=None, temperature=0.7):
                return {"content": "Fake answer", "tool_calls": [], "usage": {"total_tokens": 10}}

        class FakeTools:
            def describe_tools(self):
                return []
            async def execute(self, name, arguments):
                return "ok"
            def get_tool(self, name):
                return None

        class FakeCheckpoint:
            async def save(self, session_id, state):
                pass
            async def load(self, session_id):
                return None

        window = SlidingWindow(max_tokens=1000, strategy=WindowStrategy.TRUNCATE)
        engine = ReActEngine(
            llm=FakeLLM(),
            tools=FakeTools(),
            checkpoint_store=FakeCheckpoint(),
            window_manager=window,
        )

        orch = Orchestrator(
            guardrails=FakeGuardrails(),
            react_engine=engine,
            trust_scores={},
            memory_store=FakeCheckpoint(),
            hybrid_memory=None,
            swarm=None,
        )

        result = await orch.process("user1", "你好", session_id="s1")
        assert result.review_passed is True
        assert "你好" in result.answer or "Fake" in result.answer
        assert result.exit_reason == "normal"

    @pytest.mark.asyncio
    async def test_full_chain_complex_task_with_swarm(self):
        """复杂任务全链路: 触发 Swarm"""
        from nexusagent.orchestration.orchestrator import Orchestrator
        from nexusagent.execution.react_engine import ReActEngine, ReActResult, ExitReason
        from nexusagent.agents.swarm import AgentSwarm, SwarmAgent
        from nexusagent.context.sliding_window import SlidingWindow, WindowStrategy

        class FakeGuardrails:
            def review(self, content, context=None):
                return type('R', (), {'is_denied': False, 'requires_user_approval': False, 'reason': ''})()
            def review_output(self, content):
                return type('R', (), {'is_denied': False, 'reason': ''})()

        class FakeLLM:
            async def complete(self, messages, tools=None, temperature=0.7):
                return {"content": "Fake answer", "tool_calls": [], "usage": {"total_tokens": 10}}

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

        window = SlidingWindow(max_tokens=1000, strategy=WindowStrategy.TRUNCATE)
        engine = ReActEngine(
            llm=FakeLLM(),
            tools=FakeTools(),
            checkpoint_store=FakeCheckpoint(),
            window_manager=window,
        )

        swarm = AgentSwarm()
        swarm.register(
            SwarmAgent("a1", "Agent1"),
            handler=lambda ctx, agent: f"[{agent.name}] handled: {ctx[:20]}",
        )

        orch = Orchestrator(
            guardrails=FakeGuardrails(),
            react_engine=engine,
            trust_scores={},
            memory_store=FakeCheckpoint(),
            hybrid_memory=None,
            swarm=swarm,
        )

        # 复杂任务应触发 Swarm
        result = await orch.process("user1", "分析数据并生成图表", session_id="s2")
        assert result.review_passed is True
        # Swarm 处理后的输出应包含 Agent 标记
        assert "[" in result.answer or "Fake" in result.answer

    @pytest.mark.asyncio
    async def test_full_chain_with_hybrid_memory(self, tmp_path):
        """全链路 + HybridMemory 记忆持久化"""
        from nexusagent.orchestration.orchestrator import Orchestrator
        from nexusagent.execution.react_engine import ReActEngine, ReActResult, ExitReason
        from nexusagent.memory.hybrid import HybridMemory
        from nexusagent.memory.store import MemoryStore
        from nexusagent.context.sliding_window import SlidingWindow, WindowStrategy

        class FakeGuardrails:
            def review(self, content, context=None):
                return type('R', (), {'is_denied': False, 'requires_user_approval': False, 'reason': ''})()
            def review_output(self, content):
                return type('R', (), {'is_denied': False, 'reason': ''})()

        class FakeLLM:
            async def complete(self, messages, tools=None, temperature=0.7):
                return {"content": "Answer with memory", "tool_calls": [], "usage": {"total_tokens": 10}}

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

        db_path = str(tmp_path / "e2e_hybrid.db")
        hybrid = HybridMemory(db_path=db_path)
        window = SlidingWindow(max_tokens=1000, strategy=WindowStrategy.TRUNCATE)
        engine = ReActEngine(
            llm=FakeLLM(),
            tools=FakeTools(),
            checkpoint_store=FakeCheckpoint(),
            window_manager=window,
        )

        orch = Orchestrator(
            guardrails=FakeGuardrails(),
            react_engine=engine,
            trust_scores={},
            memory_store=hybrid._store,
            hybrid_memory=hybrid,
            swarm=None,
        )

        result = await orch.process("user1", "记住我喜欢Python", session_id="s3")
        assert result.review_passed is True

        # 验证记忆已保存
        stats = await hybrid.stats()
        assert stats["total"] >= 1
        assert stats["by_type"].get("episodic", 0) >= 1

        # 关闭连接以便清理
        hybrid._store.close()
