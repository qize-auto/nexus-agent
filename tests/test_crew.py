"""
NexusAgent v4.0 — 多Agent编排测试
覆盖: MessageBus、WorkerAgent、SupervisorAgent、AgentCrew
"""

import asyncio
import pytest

from nexusagent.agents.message_bus import AgentMessage, MessageBus
from nexusagent.agents.worker import WorkerAgent, WorkerResult
from nexusagent.agents.supervisor import SupervisorAgent, CrewResult, SubTask
from nexusagent.agents.crew import AgentCrew
from nexusagent.execution.state_graph import END, StateGraph


class TestMessageBus:
    """消息总线测试"""

    @pytest.mark.asyncio
    async def test_publish_subscribe(self):
        bus = MessageBus()
        received = []

        async def handler(msg):
            received.append(msg.payload["data"])

        await bus.subscribe("test.topic", handler)
        await bus.publish(AgentMessage(topic="test.topic", payload={"data": "hello"}))
        await asyncio.sleep(0.1)
        assert received == ["hello"]

    @pytest.mark.asyncio
    async def test_direct_send(self):
        bus = MessageBus()
        queue = await bus.register_agent("agent_1")

        await bus.send_direct("agent_1", AgentMessage(
            topic="direct", sender="boss", payload={"cmd": "do_it"},
        ))
        msg = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert msg.payload["cmd"] == "do_it"

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self):
        bus = MessageBus()
        counts = [0, 0]

        async def h1(msg):
            counts[0] += 1

        async def h2(msg):
            counts[1] += 1

        await bus.subscribe("multi", h1)
        await bus.subscribe("multi", h2)
        await bus.publish(AgentMessage(topic="multi"))
        await asyncio.sleep(0.1)
        assert counts == [1, 1]

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        bus = MessageBus()
        received = []

        async def handler(msg):
            received.append(1)

        await bus.subscribe("x", handler)
        await bus.unsubscribe("x", handler)
        await bus.publish(AgentMessage(topic="x"))
        await asyncio.sleep(0.1)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_drain(self):
        bus = MessageBus()
        queue = await bus.register_agent("a")
        await bus.send_direct("a", AgentMessage(topic="t"))
        await bus.drain()
        assert queue.empty()


class TestWorkerAgent:
    """Worker Agent 测试"""

    @pytest.mark.asyncio
    async def test_basic_execute(self):
        w = WorkerAgent("w1", "分析师", "analyst", "分析数据")
        result = await w.execute("分析某公司财报", task_id="t1")
        assert result.status == "success"
        assert result.worker_id == "w1"
        assert "分析" in result.output

    @pytest.mark.asyncio
    async def test_execute_with_graph(self):
        async def double_it(state):
            return {"value": state["value"] * 2}

        g = StateGraph()
        g.add_node("calc", double_it)
        g.set_entry_point("calc")
        g.add_edge("calc", END)

        w = WorkerAgent("w_graph", "计算器", "calculator", "计算", graph=g.compile())
        result = await w.execute("计算", task_id="t2", context={"value": 5})
        assert result.status == "success"
        assert result.state["value"] == 10

    @pytest.mark.asyncio
    async def test_message_loop(self):
        bus = MessageBus()
        w = WorkerAgent("w_loop", "助手", "assistant", "帮助")
        await w.connect(bus)

        # 发送执行请求
        await bus.send_direct("w_loop", AgentMessage(
            topic="task.delegation",
            sender="supervisor",
            payload={"action": "execute", "task": "测试任务", "task_id": "loop_t1"},
            reply_to="supervisor",
        ))

        # 等待 Worker 处理并发送结果
        await asyncio.sleep(0.3)
        await w.disconnect()

    @pytest.mark.asyncio
    async def test_tenant_in_payload(self):
        w = WorkerAgent("w_tenant", "租户助手", "assistant", "帮助")
        result = await w.execute("任务", task_id="t3", tenant_id="tenant_x")
        assert result.status == "success"


class TestSupervisorAgent:
    """Supervisor Agent 测试"""

    @pytest.mark.asyncio
    async def test_decompose_task(self):
        s = SupervisorAgent()
        subtasks = await s.decompose_task("分析财报并监测竞品")
        assert len(subtasks) >= 1
        roles = [st.role for st in subtasks]
        assert "analyst" in roles

    @pytest.mark.asyncio
    async def test_match_worker(self):
        s = SupervisorAgent()
        w1 = WorkerAgent("w1", "分析师", "analyst", "财务分析")
        w2 = WorkerAgent("w2", "研究员", "researcher", "市场研究")
        s.register_workers([w1, w2])

        st = SubTask(task_id="t1", description="分析", role="analyst")
        matched = s._match_worker(st)
        assert matched is not None
        assert matched.agent_id == "w1"

    @pytest.mark.asyncio
    async def test_execute_parallel(self):
        s = SupervisorAgent()
        w1 = WorkerAgent("w1", "分析师", "analyst", "财务分析")
        w2 = WorkerAgent("w2", "研究员", "researcher", "市场研究")
        s.register_workers([w1, w2])

        result = await s.execute("分析财报并监测竞品", mode="parallel", timeout=5.0)
        assert isinstance(result, CrewResult)
        assert result.status in ("success", "partial", "error")
        assert len(result.subtask_results) >= 1
        assert "分析" in result.final_output or "错误" in result.final_output

    @pytest.mark.asyncio
    async def test_execute_sequential(self):
        s = SupervisorAgent()
        w = WorkerAgent("w_seq", "通用助手", "general", "通用任务")
        s.register_workers([w])

        result = await s.execute("简单任务", mode="sequential", timeout=5.0)
        assert isinstance(result, CrewResult)

    @pytest.mark.asyncio
    async def test_tenant_in_execution(self):
        s = SupervisorAgent()
        w = WorkerAgent("w_t", "助手", "assistant", "帮助")
        s.register_workers([w])

        result = await s.execute("任务", tenant_id="tenant_abc", mode="sequential", timeout=5.0)
        assert result.metadata.get("tenant_id") == "tenant_abc"


class TestAgentCrew:
    """AgentCrew 集成测试"""

    @pytest.mark.asyncio
    async def test_crew_lifecycle(self):
        crew = AgentCrew()
        w1 = WorkerAgent("w1", "分析师", "analyst", "财务分析")
        w2 = WorkerAgent("w2", "研究员", "researcher", "市场研究")
        crew.add_workers([w1, w2])

        await crew.initialize()
        assert crew._initialized is True
        await crew.shutdown()

    @pytest.mark.asyncio
    async def test_crew_execute(self):
        crew = AgentCrew()
        w1 = WorkerAgent("w1", "分析师", "analyst", "财务分析")
        crew.add_workers([w1])

        result = await crew.execute("分析某公司", tenant_id="t1", mode="sequential", timeout=5.0)
        assert isinstance(result, CrewResult)
        assert result.status in ("success", "partial")

    @pytest.mark.asyncio
    async def test_crew_parallel_mode(self):
        crew = AgentCrew()
        w1 = WorkerAgent("w1", "分析师", "analyst", "财务分析")
        w2 = WorkerAgent("w2", "研究员", "researcher", "市场研究")
        crew.add_workers([w1, w2])

        result = await crew.execute("分析财报并监测竞品", mode="parallel", timeout=5.0)
        assert isinstance(result, CrewResult)
        assert len(result.subtask_results) >= 1


class TestSupervisorWorkerIntegration:
    """Supervisor + Worker 集成测试（通过消息总线）"""

    @pytest.mark.asyncio
    async def test_full_pipeline_via_bus(self):
        bus = MessageBus()
        supervisor = SupervisorAgent()
        w1 = WorkerAgent("w_bus", "分析师", "analyst", "财务分析")

        supervisor.register_workers([w1])
        await supervisor.connect(bus)
        await w1.connect(bus)

        # 直接分派（通过 bus）
        result = await supervisor.execute("分析某公司", mode="parallel", timeout=5.0)
        assert result.status in ("success", "partial")

        await w1.disconnect()

    @pytest.mark.asyncio
    async def test_worker_ping_pong(self):
        bus = MessageBus()
        w = WorkerAgent("w_ping", "助手", "assistant", "帮助")
        await w.connect(bus)

        # 注册测试接收者
        await bus.register_agent("test")

        # 发送 ping
        await bus.send_direct("w_ping", AgentMessage(
            sender="test", payload={"action": "ping"}, reply_to="test",
        ))

        # 接收 pong
        queue = await bus.get_queue("test")
        msg = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert msg.payload.get("status") == "alive"

        await w.disconnect()
