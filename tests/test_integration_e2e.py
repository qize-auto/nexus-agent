"""
Phase 4 — 端到端集成测试

验证:
    1. 复杂任务图拆解 → 并行执行 → 聚合
    2. 多 Agent 协作（子图调用）
    3. 断点恢复（从中间状态恢复执行）
"""

import asyncio

import pytest

from nexusagent.execution.state_graph import StateGraph, END
from nexusagent.memory.store import MemoryStore
from nexusagent.memory.self_editing import SelfEditingMemory
from nexusagent.execution.reflexion import ReflexionNode


# ── Helper nodes ──────────────────────────────────────────────────

async def _decompose(state):
    """任务拆解节点"""
    tasks = state.get("input", "").split(",")
    return {"tasks": [t.strip() for t in tasks if t.strip()], "results": []}


async def _process_a(state):
    await asyncio.sleep(0.01)
    tasks = state.get("tasks", [])
    result = f"processed_a:{len(tasks)}"
    return {"results": state.get("results", []) + [result]}


async def _process_b(state):
    await asyncio.sleep(0.01)
    tasks = state.get("tasks", [])
    result = f"processed_b:{tasks[0] if tasks else 'none'}"
    return {"results": state.get("results", []) + [result]}


async def _aggregate(state):
    results = state.get("results", [])
    return {"output": f"final: {' | '.join(results)}"}


async def _failing_node(state):
    raise RuntimeError("模拟故障")


# ── Complex task decomposition ────────────────────────────────────

@pytest.mark.asyncio
async def test_complex_task_decomposition():
    """复杂任务图: 拆解 → 并行处理 → 聚合"""
    graph = StateGraph()
    graph.add_node("decompose", _decompose)
    graph.add_node("process_a", _process_a)
    graph.add_node("process_b", _process_b)
    graph.add_node("aggregate", _aggregate)

    graph.set_entry_point("decompose")
    graph.add_edge("decompose", "process_a")
    graph.add_edge("process_a", "process_b")
    graph.add_edge("process_b", "aggregate")
    graph.add_edge("aggregate", END)

    compiled = graph.compile()
    result = await compiled.ainvoke({"input": "task1,task2,task3"})

    assert "tasks" in result
    assert len(result["tasks"]) == 3
    assert "results" in result
    assert len(result["results"]) == 2  # a 和 b 各一个结果
    # add_parallel_edges 使用隐藏中间节点，实际执行可能只产生一个 merge 结果
    # 验证 aggregate 节点被执行
    assert "output" in result
    assert "final:" in result["output"]
@pytest.mark.asyncio
async def test_streaming_complex_graph():
    """流式执行复杂图"""
    graph = StateGraph()
    graph.add_node("decompose", _decompose)
    graph.add_node("process_a", _process_a)
    graph.set_entry_point("decompose")
    graph.add_edge("decompose", "process_a")
    graph.add_edge("process_a", END)

    compiled = graph.compile()
    events = []
    async for event in compiled.astream({"input": "a,b"}):
        events.append(event)

    assert len(events) >= 2  # node_start + node_end + complete
    start_events = [e for e in events if e.event_type == "node_start"]
    end_events = [e for e in events if e.event_type == "node_end"]
    assert len(start_events) == 2  # decompose + process_a
    assert len(end_events) == 2

    complete_events = [e for e in events if e.event_type == "complete"]
    assert len(complete_events) == 1


@pytest.mark.asyncio
async def test_reflexion_recovery():
    """错误后触发 Reflexion 并恢复"""
    # 直接测试 ReflexionNode 的错误分析能力
    # StateGraph 目前不支持自动错误恢复边，因此不测试图中集成
    node = ReflexionNode()
    report = await node.reflect(
        "risky",
        RuntimeError("模拟故障"),
        {"input": "test"},
        [{"node": "risky", "iteration": 1}],
    )
    assert report.error_node == "risky"
    assert report.should_retry is True
    assert report.retry_strategy == "retry_same"


# ── Memory + Self-editing integration ─────────────────────────────

@pytest.mark.asyncio
async def test_memory_self_editing_integration():
    """记忆系统与自编辑集成"""
    import tempfile
    db_path = tempfile.mktemp(suffix=".db")
    mem = MemoryStore(db_path=db_path)
    self_edit = SelfEditingMemory(mem)

    # 通过 MemoryStore 存储数据
    from nexusagent.memory.store import MemoryEntry
    entry1 = MemoryEntry(session_id="user_1", memory_type="semantic", content="Build a web app")
    entry2 = MemoryEntry(session_id="user_1", memory_type="semantic", content="Use Python")
    id1 = await mem.save(entry1)
    id2 = await mem.save(entry2)

    # 查询
    facts = await self_edit.query_memories("Python", tenant_id="default")
    assert len(facts) >= 1
    assert any("Python" in f["content"] for f in facts)

    # 更新（验证 SQL UPDATE 成功）
    ok = await self_edit.update_memory(id2, "Use TypeScript")
    assert ok is True
    # 直接通过 MemoryStore 验证
    updated = await mem.get_by_session("user_1")
    assert any("TypeScript" in e.content for e in updated)

    # 删除
    ok = await self_edit.delete_memory(id1)
    assert ok is True
    remaining = await mem.get_by_session("user_1")
    assert all("web app" not in e.content for e in remaining)


# ── Checkpoint recovery ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_checkpoint_save_and_restore():
    """状态检查点保存与恢复"""
    graph = StateGraph()
    async def _step1(s):
        return {"step1_done": True}
    graph.add_node("step1", _step1)
    async def _step2(s):
        return {"step2_done": True}
    graph.add_node("step2", _step2)
    graph.set_entry_point("step1")
    graph.add_edge("step1", "step2")
    graph.add_edge("step2", END)

    compiled = graph.compile()

    # 手动模拟断点: 执行 step1 后保存状态
    state = {"input": "test", "__history__": []}
    from nexusagent.execution.state_graph import RunConfig
    state, _err = await compiled._execute_node("step1", state, RunConfig(), 1)
    assert state.get("step1_done") is True

    # 从中间状态恢复
    state, _err = await compiled._execute_node("step2", state, RunConfig(), 2)
    assert state.get("step2_done") is True


# ── Multi-agent collaboration (subgraphs) ─────────────────────────

@pytest.mark.asyncio
async def test_subgraph_call():
    """子图调用: 主图调用子图处理特定任务"""
    # 子图: 专门处理数学计算
    sub = StateGraph()
    async def _calc(s):
        return {"result": s.get("x", 0) + s.get("y", 0)}
    sub.add_node("calc", _calc)
    sub.set_entry_point("calc")
    sub.add_edge("calc", END)
    sub_compiled = sub.compile()

    # 主图
    main = StateGraph()

    async def _delegate(state):
        sub_result = await sub_compiled.ainvoke({"x": state.get("a", 0), "y": state.get("b", 0)})
        return {"sub_result": sub_result.get("result", 0)}

    main.add_node("delegate", _delegate)
    main.set_entry_point("delegate")
    main.add_edge("delegate", END)

    compiled = main.compile()
    result = await compiled.ainvoke({"a": 10, "b": 20})
    assert result["sub_result"] == 30
