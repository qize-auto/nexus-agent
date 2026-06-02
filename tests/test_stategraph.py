"""
NexusAgent v4.0 — StateGraph 执行引擎测试
覆盖: 节点执行、条件边、并行分支、Checkpoint、重放、Reducer
"""

import asyncio
import os
import pytest

from nexusagent.execution.state_graph import (
    END,
    CompiledGraph,
    RunConfig,
    StateGraph,
    StateGraphValidationError,
)
from nexusagent.execution.checkpoint import MemoryCheckpointer, SqliteCheckpointer


class TestStateGraphBuild:
    """图构建测试"""

    async def _noop(self, state):
        return state

    def test_add_node(self):
        g = StateGraph()
        g.add_node("a", self._noop)
        assert "a" in g._nodes

    def test_add_node_not_async_raises(self):
        g = StateGraph()
        with pytest.raises(StateGraphValidationError):
            g.add_node("a", lambda s: s)

    def test_add_edge(self):
        g = StateGraph()
        g.add_node("a", self._noop)
        g.add_node("b", self._noop)
        g.add_edge("a", "b")
        assert len(g._edges) == 1
        assert g._edges[0].source == "a"

    def test_compile_without_entry_point_raises(self):
        g = StateGraph()
        g.add_node("a", self._noop)
        with pytest.raises(StateGraphValidationError, match="entry_point"):
            g.compile()

    def test_compile_missing_node_raises(self):
        g = StateGraph()
        g.add_node("a", self._noop)
        g.set_entry_point("a")
        g.add_edge("a", "missing")
        with pytest.raises(StateGraphValidationError, match="missing"):
            g.compile()


class TestStateGraphInvoke:
    """图执行测试"""

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
    async def test_simple_execution(self, simple_graph):
        result = await simple_graph.ainvoke({"count": 3})
        assert result["count"] == 8  # (3+1)*2
        assert result["__iteration__"] == 2

    @pytest.mark.asyncio
    async def test_execution_history(self, simple_graph):
        result = await simple_graph.ainvoke({"count": 0})
        history = result["__history__"]
        assert len(history) == 2
        assert history[0]["node"] == "add"
        assert history[1]["node"] == "double"

    @pytest.mark.asyncio
    async def test_max_iterations(self):
        async def loop(state):
            return {"i": state.get("i", 0) + 1}

        g = StateGraph()
        g.add_node("loop", loop)
        g.set_entry_point("loop")
        g.add_edge("loop", "loop")  # 无限循环
        compiled = g.compile()

        config = RunConfig(max_iterations=5)
        result = await compiled.ainvoke({"i": 0}, config=config)
        assert result["__truncated__"] is True
        assert result["__iteration__"] == 5


class TestConditionalEdges:
    """条件边测试"""

    @pytest.mark.asyncio
    async def test_conditional_routing(self):
        async def start(state):
            return {"route": state.get("route", "b")}

        async def node_b(state):
            return {"path": "b"}

        async def node_c(state):
            return {"path": "c"}

        async def router(state):
            return state["route"]

        g = StateGraph()
        g.add_node("start", start)
        g.add_node("b", node_b)
        g.add_node("c", node_c)
        g.set_entry_point("start")
        g.add_conditional_edges("start", router, {"b": "b", "c": "c"})
        g.add_edge("b", END)
        g.add_edge("c", END)
        compiled = g.compile()

        result = await compiled.ainvoke({"route": "c"})
        assert result["path"] == "c"

        result = await compiled.ainvoke({"route": "b"})
        assert result["path"] == "b"


class TestReducer:
    """Reducer 状态合并测试"""

    @pytest.mark.asyncio
    async def test_list_reducer(self):
        async def append_msg(state):
            return {"messages": [{"role": "assistant", "content": "hi"}]}

        g = StateGraph()
        g.add_node("step1", append_msg)
        g.add_node("step2", append_msg)
        g.set_entry_point("step1")
        g.add_edge("step1", "step2")
        g.add_edge("step2", END)
        g.set_reducer("messages", lambda old, new: (old or []) + new)
        compiled = g.compile()

        result = await compiled.ainvoke({"messages": [{"role": "user", "content": "hello"}]})
        assert len(result["messages"]) == 3

    @pytest.mark.asyncio
    async def test_default_override(self):
        async def update(state):
            return {"value": 100}

        g = StateGraph()
        g.add_node("step1", update)
        g.set_entry_point("step1")
        g.add_edge("step1", END)
        compiled = g.compile()

        result = await compiled.ainvoke({"value": 1})
        assert result["value"] == 100


class TestCheckpoint:
    """Checkpoint 持久化测试"""

    @pytest.fixture
    def memory_cp(self):
        return MemoryCheckpointer()

    @pytest.mark.asyncio
    async def test_memory_checkpoint_save_load(self, memory_cp):
        from nexusagent.execution.state_graph import Checkpoint

        cp = Checkpoint(
            thread_id="t1", node_name="a",
            state={"x": 1}, timestamp=1.0, iteration=1,
        )
        await memory_cp.save(cp)
        loaded = await memory_cp.load("t1")
        assert loaded is not None
        assert loaded.node_name == "a"
        assert loaded.state["x"] == 1

    @pytest.mark.asyncio
    async def test_checkpoint_integration(self, memory_cp):
        async def step1(state):
            return {"step": 1}

        async def step2(state):
            return {"step": 2}

        g = StateGraph()
        g.add_node("s1", step1)
        g.add_node("s2", step2)
        g.set_entry_point("s1")
        g.add_edge("s1", "s2")
        g.add_edge("s2", END)
        compiled = g.compile()

        config = RunConfig(thread_id="chk_test", checkpointer=memory_cp)
        result = await compiled.ainvoke({}, config=config)
        assert result["step"] == 2

        # 验证 checkpoint 被保存
        checkpoints = await memory_cp.list_checkpoints("chk_test")
        assert len(checkpoints) >= 2  # pre + post for each node

    @pytest.mark.asyncio
    async def test_sqlite_checkpoint(self, tmp_path):
        db = str(tmp_path / "cp.db")
        cp = SqliteCheckpointer(db)
        from nexusagent.execution.state_graph import Checkpoint

        await cp.save(Checkpoint(
            thread_id="t2", node_name="b",
            state={"y": 2}, timestamp=2.0, iteration=1,
            metadata={"tenant_id": "acme"},
        ))
        loaded = await cp.load("t2")
        assert loaded.state["y"] == 2
        assert loaded.metadata["tenant_id"] == "acme"

    @pytest.mark.asyncio
    async def test_load_at_node(self, memory_cp):
        from nexusagent.execution.state_graph import Checkpoint

        await memory_cp.save(Checkpoint(
            thread_id="t3", node_name="node_a",
            state={"s": 1}, timestamp=1.0, iteration=1,
        ))
        await memory_cp.save(Checkpoint(
            thread_id="t3", node_name="node_b",
            state={"s": 2}, timestamp=2.0, iteration=2,
        ))
        loaded = await memory_cp.load_at_node("t3", "node_a")
        assert loaded.state["s"] == 1


class TestReplay:
    """重放测试"""

    @pytest.mark.asyncio
    async def test_areplay_from_checkpoint(self):
        async def step1(state):
            return {"count": state.get("count", 0) + 1}

        async def step2(state):
            return {"count": state["count"] * 2}

        g = StateGraph()
        g.add_node("s1", step1)
        g.add_node("s2", step2)
        g.set_entry_point("s1")
        g.add_edge("s1", "s2")
        g.add_edge("s2", END)
        compiled = g.compile()

        cp = MemoryCheckpointer()
        config = RunConfig(thread_id="replay_t", checkpointer=cp)
        await compiled.ainvoke({"count": 0}, config=config)

        # 重放: 从 s1 开始，count 应该变成 2 (0+1)*2
        result = await compiled.areplay("replay_t", from_node="s1", checkpointer=cp)
        assert result["count"] == 2
        assert result["__replayed_from__"] == "s1"

    @pytest.mark.asyncio
    async def test_areplay_without_checkpointer_raises(self):
        async def noop(state):
            return state

        g = StateGraph()
        g.add_node("s", noop)
        g.set_entry_point("s")
        compiled = g.compile()

        with pytest.raises(Exception, match="checkpointer"):
            await compiled.areplay("t", checkpointer=None)


class TestMermaidExport:
    """可视化导出测试"""

    def test_to_mermaid(self):
        async def noop(state):
            return state

        g = StateGraph()
        g.add_node("a", noop)
        g.add_node("b", noop)
        g.set_entry_point("a")
        g.add_edge("a", "b")
        g.add_edge("b", END)
        compiled = g.compile()

        mermaid = compiled.to_mermaid()
        assert "graph TD" in mermaid
        assert "a --> b" in mermaid
        assert "START" in mermaid


class TestTenantIsolationInGraph:
    """租户隔离在图执行中的测试"""

    @pytest.mark.asyncio
    async def test_tenant_id_in_checkpoint_metadata(self):
        async def noop(state):
            return {"data": "ok"}

        g = StateGraph()
        g.add_node("n", noop)
        g.set_entry_point("n")
        g.add_edge("n", END)
        compiled = g.compile()

        cp = MemoryCheckpointer()
        config = RunConfig(thread_id="tenant_t", tenant_id="corp_a", checkpointer=cp)
        await compiled.ainvoke({}, config=config)

        checkpoints = await cp.list_checkpoints("tenant_t")
        assert all(c.metadata.get("tenant_id") == "corp_a" for c in checkpoints)
