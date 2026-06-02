"""
NexusAgent v4.0+ — MiroFish 融合层测试 [MIROFISH-INSPIRED]
覆盖: PersonaEngine, SocialGraph, SimulationClock, ActivityConfig, MiroFishScheduler
来源验证: GitHub 666ghj/MiroFish
"""

import pytest

from nexusagent.orchestration.mirofish import (
    PersonaEngine,
    AgentPersona,
    SocialGraph,
    EntityNode,
    RelationEdge,
    SimulationClock,
    AgentActivityConfig,
    MiroFishScheduler,
    MiroFishResult,
)


class TestPersonaEngine:
    """PersonaEngine 测试"""

    def test_generate_basic(self):
        engine = PersonaEngine()
        p = engine.generate("researcher", "张三", agent_id="r1")
        assert p.agent_id == "r1"
        assert p.name == "张三"
        assert p.role == "researcher"
        assert p.mbti in PersonaEngine._MBTI_TYPES
        assert 22 <= p.age <= 55
        assert p.proactivity > 0.5  # researcher 主动性高
        assert p.detail_orientation > 0.5  # researcher 细节导向高

    def test_generate_batch(self):
        engine = PersonaEngine()
        personas = engine.generate_batch([
            ("analyst", "李四"),
            ("writer", "王五"),
        ])
        assert len(personas) == 2
        assert personas[0].role == "analyst"
        assert personas[1].role == "writer"

    def test_role_styles(self):
        engine = PersonaEngine()
        creative = engine.generate("creative", "创意A")
        analyst = engine.generate("analyst", "分析B")
        assert creative.risk_tolerance > analyst.risk_tolerance
        assert analyst.detail_orientation > creative.detail_orientation

    def test_custom_traits(self):
        engine = PersonaEngine()
        p = engine.generate("researcher", "张三", custom_traits={"mbti": "INTJ", "age": 30})
        assert p.mbti == "INTJ"
        assert p.age == 30

    def test_to_dict(self):
        p = AgentPersona(agent_id="a1", name="Test", role="r1")
        d = p.to_dict()
        assert d["agent_id"] == "a1"
        assert d["name"] == "Test"


class TestSocialGraph:
    """SocialGraph 测试"""

    def test_add_entity_and_relation(self):
        g = SocialGraph()
        g.add_entity(EntityNode("e1", "市场部", "organization"))
        g.add_entity(EntityNode("e2", "产品部", "organization"))
        g.add_relation(RelationEdge("e1", "e2", "collaborates_with", 0.8))
        assert g.get_entity("e1").name == "市场部"
        assert len(g.get_relations("e1")) == 1

    def test_find_collaboration_path(self):
        g = SocialGraph()
        g.add_entity(EntityNode("a", "A"))
        g.add_entity(EntityNode("b", "B"))
        g.add_entity(EntityNode("c", "C"))
        g.add_relation(RelationEdge("a", "b", "collaborates_with", 0.5))
        g.add_relation(RelationEdge("b", "c", "collaborates_with", 0.5))
        path = g.find_collaboration_path("a", "c")
        assert path == ["a", "b", "c"]

    def test_no_path(self):
        g = SocialGraph()
        g.add_entity(EntityNode("a", "A"))
        g.add_entity(EntityNode("b", "B"))
        assert g.find_collaboration_path("a", "b") is None

    def test_suggest_collaborators(self):
        g = SocialGraph()
        g.add_entity(EntityNode("a", "A"))
        g.add_entity(EntityNode("b", "B"))
        g.add_entity(EntityNode("c", "C"))
        g.add_relation(RelationEdge("a", "b", "collaborates_with", 0.9))
        g.add_relation(RelationEdge("a", "c", "influences", 0.6))
        collaborators = g.suggest_collaborators("a")
        assert len(collaborators) == 2
        assert collaborators[0][0] == "b"  # 强度最高

    def test_stats(self):
        g = SocialGraph()
        g.add_entity(EntityNode("a", "A"))
        g.add_entity(EntityNode("b", "B"))
        g.add_relation(RelationEdge("a", "b", "collaborates_with", 0.5))
        stats = g.stats()
        assert stats["node_count"] == 2
        assert stats["edge_count"] == 1


class TestSimulationClock:
    """SimulationClock 测试"""

    def test_tick(self):
        clock = SimulationClock()
        assert clock._simulated_hour == 9
        clock.tick()
        assert clock._simulated_hour == 10

    def test_get_current_multiplier(self):
        clock = SimulationClock()
        # 9点属于 work 时段，multiplier = 0.7
        assert clock.get_current_multiplier() == 0.7

    def test_is_agent_active(self):
        clock = SimulationClock()
        assert clock.is_agent_active([9, 10, 11]) is True
        assert clock.is_agent_active([20, 21]) is False  # 当前 9 点

    def test_calculate_response_delay(self):
        clock = SimulationClock()
        delay = clock.calculate_response_delay(5, 60, activity_level=0.5)
        assert 1 <= delay <= 120

    def test_get_bid_willingness(self):
        clock = SimulationClock()
        w = clock.get_bid_willingness(activity_level=0.5)
        assert 0 <= w <= 1.0

    def test_reset(self):
        clock = SimulationClock()
        clock.tick()
        clock.tick()
        clock.reset()
        assert clock._simulated_hour == 9
        assert clock._round_count == 0


class TestAgentActivityConfig:
    """AgentActivityConfig 测试"""

    def test_calculate_bid_score(self):
        config = AgentActivityConfig(agent_id="a1", activity_level=0.8)
        score = config.calculate_bid_score(capability_match=0.9, current_load=0.2, time_multiplier=1.0)
        assert 0 <= score <= 1.0
        # 高能力匹配 + 低负载 + 高活跃度 = 高分
        assert score > 0.5

    def test_high_load_reduces_score(self):
        config = AgentActivityConfig(agent_id="a1", activity_level=0.8)
        low_load = config.calculate_bid_score(0.9, 0.1, 1.0)
        high_load = config.calculate_bid_score(0.9, 0.9, 1.0)
        assert low_load > high_load

    def test_calculate_consensus_weight(self):
        config = AgentActivityConfig(agent_id="a1", influence_weight=2.0, activity_level=1.0)
        w = config.calculate_consensus_weight()
        assert w == 2.0 * (0.5 + 1.0 * 0.5)  # 2.0


class TestMiroFishScheduler:
    """MiroFishScheduler 集成测试"""

    @pytest.mark.asyncio
    async def test_run_no_agents(self):
        """无 Agent 边界检查"""
        scheduler = MiroFishScheduler()
        result = await scheduler.run("测试任务", max_rounds=3)
        assert result.status == "error"
        assert "未注册任何 Agent" in result.output

    def test_register_agent(self):
        scheduler = MiroFishScheduler()
        p = scheduler.register_agent("a1", "researcher", "张三")
        assert p.agent_id == "a1"
        assert "a1" in scheduler._agents
        assert "a1" in scheduler._activity_configs
        assert scheduler._social_graph.get_entity("a1") is not None

    def test_register_agents_batch(self):
        scheduler = MiroFishScheduler()
        personas = scheduler.register_agents([
            ("researcher", "张三"),
            ("analyst", "李四"),
            ("writer", "王五"),
        ])
        assert len(personas) == 3
        # 检查自动建立的关系
        stats = scheduler._social_graph.stats()
        assert stats["edge_count"] >= 2  # 相邻 Agent 之间有边

    @pytest.mark.asyncio
    async def test_run_simple_task(self):
        scheduler = MiroFishScheduler()
        scheduler.register_agents([
            ("researcher", "张三"),
            ("analyst", "李四"),
        ])
        result = await scheduler.run("你好", max_rounds=3)
        assert isinstance(result, MiroFishResult)
        assert result.status == "success"
        assert "MiroFish" in result.output

    @pytest.mark.asyncio
    async def test_run_complex_task(self):
        scheduler = MiroFishScheduler()
        scheduler.register_agents([
            ("researcher", "张三"),
            ("analyst", "李四"),
            ("writer", "王五"),
        ])
        result = await scheduler.run("分析数据并生成报告", max_rounds=5)
        assert result.status == "success"
        assert len(result.agent_assignments) > 0
        assert len(result.simulation_trace) > 0
        assert len(result.consensus_notes) > 0

    @pytest.mark.asyncio
    async def test_run_with_handler(self):
        scheduler = MiroFishScheduler()
        calls = []

        def handler(task, persona):
            calls.append((persona.agent_id, task[:20]))
            return f"[{persona.name}] done"

        scheduler.register_agent("a1", "researcher", "张三", handler=handler)
        scheduler.register_agent("a2", "writer", "李四", handler=handler)
        result = await scheduler.run("测试任务", max_rounds=3)
        assert result.status == "success"
        assert len(calls) > 0

    def test_get_stats(self):
        scheduler = MiroFishScheduler()
        scheduler.register_agents([
            ("researcher", "张三"),
            ("analyst", "李四"),
        ])
        stats = scheduler.get_stats()
        assert stats["agents"] == 2
        assert stats["tasks"] == 0
        assert stats["rounds"] == 0

    def test_decompose_task(self):
        scheduler = MiroFishScheduler()
        subtasks = scheduler._decompose_task("分析数据并生成报告")
        assert len(subtasks) >= 2  # 分析 + 报告
        descs = [s.description for s in subtasks]
        assert any("分析" in d for d in descs)
        assert any("报告" in d for d in descs)

    def test_load_balancing_penalty(self):
        """负载均衡惩罚：高负载 Agent 不应拿走所有任务"""
        scheduler = MiroFishScheduler()
        # 注册两个能力相近的 Agent
        scheduler.register_agent("a1", "researcher", "张三")
        scheduler.register_agent("a2", "researcher", "李四")

        # 手动构造 3 个待分配任务
        from nexusagent.orchestration.mirofish.scheduler import TaskNode
        scheduler._task_nodes["t1"] = TaskNode("t1", "任务1", required_capabilities=["research"], value=1.5)
        scheduler._task_nodes["t2"] = TaskNode("t2", "任务2", required_capabilities=["research"], value=1.2)
        scheduler._task_nodes["t3"] = TaskNode("t3", "任务3", required_capabilities=["research"], value=1.0)

        # 收集投标并分配
        bids = scheduler._collect_bids()
        assignments = scheduler._assign_tasks(bids)

        # 统计每个 Agent 分配到的任务数
        counts = {agent_id: len(tids) for agent_id, tids in assignments.items()}
        total = sum(counts.values())
        assert total == 3
        # 由于负载均衡惩罚，不应出现某个 Agent 分配到全部 3 个任务的情况
        assert max(counts.values()) <= 2, f"负载不均衡: {counts}"

    @pytest.mark.asyncio
    async def test_messagebus_events(self):
        """MessageBus 事件发布验证"""
        from nexusagent.agents.message_bus import MiroFishTopics

        received = []

        async def handler(msg):
            received.append(msg.topic)

        scheduler = MiroFishScheduler()
        await scheduler._bus.subscribe(MiroFishTopics.AWARD, handler)
        await scheduler._bus.subscribe(MiroFishTopics.RESULT, handler)

        scheduler.register_agent("a1", "researcher", "张三", handler=lambda t, p: "done")
        result = await scheduler.run("分析数据", max_rounds=3)
        assert result.status == "success"
        # 至少收到了 AWARD 和 RESULT 事件
        assert MiroFishTopics.AWARD in received
        assert MiroFishTopics.RESULT in received
