"""
NexusAgent v4.0+ — 流式输出测试
覆盖: astream(), SSE endpoint, on_step callback
"""

import asyncio
import pytest

from nexusagent.execution.state_graph import (
    END,
    CompiledGraph,
    RunConfig,
    StateGraph,
    StreamEvent,
)


class TestAstream:
    """StateGraph.astream() 测试"""

    @pytest.fixture
    def simple_graph(self):
        async def add_one(state):
            return {"count": state.get("count", 0) + 1}

        async def double(state):
            return {"count": state["count"] * 2}

        g = StateGraph()
        g.add_node("add", add_one)
        g.add_node("double", double)
        g.set_entry_point("add")
        g.add_edge("add", "double")
        g.add_edge("double", END)
        return g.compile()

    @pytest.mark.asyncio
    async def test_astream_yields_events(self, simple_graph):
        events = []
        async for evt in simple_graph.astream({"count": 3}):
            events.append(evt)
            assert isinstance(evt, StreamEvent)

        # 应该有: node_start(add), node_end(add), node_start(double), node_end(double), complete
        assert len(events) == 5
        assert events[0].event_type == "node_start"
        assert events[0].node_name == "add"
        assert events[1].event_type == "node_end"
        assert events[1].node_name == "add"
        assert events[2].event_type == "node_start"
        assert events[2].node_name == "double"
        assert events[-1].event_type == "complete"

    @pytest.mark.asyncio
    async def test_astream_final_state(self, simple_graph):
        final_state = None
        async for evt in simple_graph.astream({"count": 3}):
            if evt.event_type == "complete":
                final_state = evt.data["final_state"]

        assert final_state is not None
        assert final_state["count"] == 8  # (3+1)*2

    @pytest.mark.asyncio
    async def test_astream_with_conditional(self):
        async def router(state):
            return state.get("route", "b")

        async def start_node(state):
            return state

        async def node_b(state):
            return {"path": "b"}

        async def node_c(state):
            return {"path": "c"}

        g = StateGraph()
        g.add_node("start", start_node)
        g.add_node("b", node_b)
        g.add_node("c", node_c)
        g.set_entry_point("start")
        g.add_conditional_edges("start", router, {"b": "b", "c": "c"})
        g.add_edge("b", END)
        g.add_edge("c", END)
        compiled = g.compile()

        events = []
        async for evt in compiled.astream({"route": "c"}):
            events.append(evt)

        node_names = [e.node_name for e in events if e.event_type in ("node_start", "node_end")]
        assert "c" in node_names

    @pytest.mark.asyncio
    async def test_astream_error_event(self):
        async def fail(state):
            raise ValueError("intentional failure")

        g = StateGraph()
        g.add_node("fail", fail)
        g.set_entry_point("fail")
        compiled = g.compile()

        events = []
        async for evt in compiled.astream({}):
            events.append(evt)

        error_events = [e for e in events if e.event_type == "error"]
        assert len(error_events) == 1
        assert "intentional failure" in error_events[0].data["error"]

    @pytest.mark.asyncio
    async def test_astream_with_on_step_callback(self, simple_graph):
        steps = []

        async def on_step(node_name, state, iteration):
            steps.append((node_name, iteration))

        config = RunConfig(on_step=on_step)
        events = []
        async for evt in simple_graph.astream({"count": 0}, config=config):
            events.append(evt)

        assert len(steps) == 2
        assert steps[0] == ("add", 1)
        assert steps[1] == ("double", 2)

    @pytest.mark.asyncio
    async def test_astream_thread_id(self, simple_graph):
        events = []
        async for evt in simple_graph.astream({"count": 0}, config=RunConfig(thread_id="my_thread")):
            events.append(evt)

        start_event = events[0]
        assert start_event.data["thread_id"] == "my_thread"
        complete_event = events[-1]
        assert complete_event.data["thread_id"] == "my_thread"

    @pytest.mark.asyncio
    async def test_ainvoke_with_on_step(self, simple_graph):
        steps = []

        async def on_step(node_name, state, iteration):
            steps.append((node_name, iteration))

        result = await simple_graph.ainvoke({"count": 0}, config=RunConfig(on_step=on_step))
        assert result["count"] == 2
        assert len(steps) == 2


class TestGenerationConfig:
    """节点级生成配置测试"""

    def test_node_spec_has_generation_config(self):
        async def noop(state):
            return state

        g = StateGraph()
        g.add_node("n", noop)
        spec = g._nodes["n"]
        assert spec.generation_config is None

    def test_run_config_has_generation_config(self):
        from nexusagent.execution.state_graph import GenerationConfig
        config = RunConfig(generation_config=GenerationConfig(temperature=0.2))
        assert config.generation_config.temperature == 0.2
