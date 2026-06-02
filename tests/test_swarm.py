"""
NexusAgent v4.0+ — Agent Swarm 测试
覆盖: 注册/注销、Handoff、GroupChat、RoundRobin、LoadBalance
"""

import pytest

from nexusagent.agents.swarm import AgentSwarm, SwarmAgent, SwarmResult


class TestAgentSwarm:
    """AgentSwarm 核心测试"""

    def test_register_and_list(self):
        """注册和列出 Agent"""
        swarm = AgentSwarm()
        swarm.register(SwarmAgent("a1", "Agent1", role="researcher"))
        swarm.register(SwarmAgent("a2", "Agent2", role="writer"))
        assert len(swarm.list_agents()) == 2
        assert swarm.get_agent("a1").role == "researcher"

    def test_unregister(self):
        """注销 Agent"""
        swarm = AgentSwarm()
        swarm.register(SwarmAgent("a1", "Agent1"))
        assert swarm.unregister("a1") is True
        assert swarm.get_agent("a1") is None
        assert swarm.unregister("a1") is False

    def test_select_by_role(self):
        """按角色选择"""
        swarm = AgentSwarm()
        swarm.register(SwarmAgent("r1", "R1", role="researcher"))
        swarm.register(SwarmAgent("r2", "R2", role="researcher"))
        selected = swarm._select_by_role("researcher")
        assert selected is not None
        assert selected.role == "researcher"

    def test_select_by_load(self):
        """负载均衡选择"""
        swarm = AgentSwarm()
        swarm.register(SwarmAgent("a1", "A1"), handler=lambda ctx, agent: "ok")
        swarm.register(SwarmAgent("a2", "A2"), handler=lambda ctx, agent: "ok")
        selected = swarm._select_by_load()
        assert selected is not None

    @pytest.mark.asyncio
    async def test_run_handoff(self):
        """Handoff 策略"""
        swarm = AgentSwarm()
        calls = []

        async def researcher(ctx, agent):
            calls.append((agent.agent_id, ctx))
            return "研究结果 [HANDOFF: writer]"

        async def writer(ctx, agent):
            calls.append((agent.agent_id, ctx))
            return "撰写完成 [DONE]"

        swarm.register(SwarmAgent("researcher", "研究员", role="researcher"), researcher)
        swarm.register(SwarmAgent("writer", "写手", role="writer"), writer)

        result = await swarm.run("研究并撰写报告", strategy="handoff")
        assert isinstance(result, SwarmResult)
        assert result.status == "success"
        assert "研究结果" in result.output
        assert "撰写完成" in result.output
        assert len(result.agent_trace) == 2

    @pytest.mark.asyncio
    async def test_run_groupchat(self):
        """GroupChat 策略"""
        swarm = AgentSwarm()

        async def agent_a(ctx, agent):
            return "A 的观点: 需要更多数据。"

        async def agent_b(ctx, agent):
            return "B 的观点: 结论完成。"

        swarm.register(SwarmAgent("a", "AgentA"), agent_a)
        swarm.register(SwarmAgent("b", "AgentB"), agent_b)

        result = await swarm.run("讨论问题", strategy="groupchat", max_turns=3)
        assert result.status == "success"
        assert "A 的观点" in result.output
        assert "B 的观点" in result.output

    @pytest.mark.asyncio
    async def test_run_round_robin(self):
        """轮询策略"""
        swarm = AgentSwarm()

        def agent1(ctx, agent):
            return "step1"

        def agent2(ctx, agent):
            return "step2"

        swarm.register(SwarmAgent("a1", "A1"), agent1)
        swarm.register(SwarmAgent("a2", "A2"), agent2)

        result = await swarm.run("任务", strategy="round_robin", max_turns=4)
        assert result.status == "success"
        lines = result.output.split("\n")
        assert len(lines) == 4

    @pytest.mark.asyncio
    async def test_run_load_balance(self):
        """负载均衡策略"""
        swarm = AgentSwarm()

        def handler(ctx, agent):
            return f"handled by {agent.name}"

        swarm.register(SwarmAgent("a1", "A1"), handler)
        swarm.register(SwarmAgent("a2", "A2"), handler)

        result = await swarm.run("任务", strategy="load_balance", max_turns=2)
        assert result.status == "success"
        assert len(result.agent_trace) == 2

    def test_parse_handoff(self):
        """解析 Handoff 指令"""
        swarm = AgentSwarm()
        assert swarm._parse_handoff("结果 [HANDOFF: writer]") == "writer"
        assert swarm._parse_handoff("结果 [移交: analyst]") == "analyst"
        assert swarm._parse_handoff("结果 [DONE]") == "__DONE__"
        assert swarm._parse_handoff("普通结果") == ""

    def test_get_stats(self):
        """统计信息"""
        swarm = AgentSwarm()
        swarm.register(SwarmAgent("a1", "A1"))
        stats = swarm.get_stats()
        assert stats["total_agents"] == 1
        assert stats["enabled_agents"] == 1

    @pytest.mark.asyncio
    async def test_empty_swarm(self):
        """空 Swarm 处理"""
        swarm = AgentSwarm()
        result = await swarm.run("任务", strategy="handoff")
        assert result.status in ("error", "partial")

    @pytest.mark.asyncio
    async def test_handler_error(self):
        """Handler 异常处理"""
        swarm = AgentSwarm()

        def bad_handler(ctx, agent):
            raise ValueError("模拟错误")

        swarm.register(SwarmAgent("bad", "BadAgent"), bad_handler)
        result = await swarm.run("任务", strategy="round_robin", max_turns=1)
        assert result.status == "success"  # 单条错误不影响整体
        assert "错误" in result.output
