"""
NexusAgent v4.0+ — MiroFish Scheduler [MIROFISH-INSPIRED]

基于 MiroFish 的 SimulationManager + SimulationRunner 理念：
    1. 深度 Persona 生成（OasisProfileGenerator）
    2. 社会图谱构建（GraphBuilderService）
    3. 时间感知模拟（TimeSimulationConfig）
    4. 活动配置生成（AgentActivityConfig）
    5. 协作预演：Agent 在虚拟空间中进行轻量级预演，发现最优协作路径

与现有 AgentSwarm 的区别：
    - Swarm = 直接执行（Handoff / GroupChat / RoundRobin / LoadBalance）
    - MiroFish = 先预演模拟、后执行，通过模拟优化协作路径

v4.0+ 优化:
    - 通信层: 支持 DIRECT（默认）和 MESSAGEBUS 两种模式，通过 communication_mode 切换
    - 负载均衡: 三维惩罚模型（本轮惩罚 + 历史累积惩罚 + 并发上限）
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from nexusagent.agents.message_bus import AgentMessage, MessageBus, MiroFishTopics
from nexusagent.orchestration.mirofish.activity_config import AgentActivityConfig
from nexusagent.orchestration.mirofish.persona_engine import AgentPersona, PersonaEngine
from nexusagent.orchestration.mirofish.simulation_clock import SimulationClock
from nexusagent.orchestration.mirofish.social_graph import RelationEdge, SocialGraph

logger = logging.getLogger("nexus.mirofish.scheduler")


@dataclass
class TaskNode:
    """任务节点 — 在 FishPond 中的任务实体"""
    task_id: str
    description: str
    required_capabilities: List[str] = field(default_factory=list)
    value: float = 1.0  # 任务价值
    difficulty: float = 1.0  # 难度系数
    status: str = "pending"  # pending | bidding | assigned | completed
    assigned_agent: Optional[str] = None
    position: Tuple[float, float] = (0.0, 0.0)  # Pond 中的位置


@dataclass
class SimulationRound:
    """模拟轮次记录"""
    round_num: int
    actions: List[Dict[str, Any]] = field(default_factory=list)
    clock_state: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MiroFishResult:
    """MiroFish 调度结果"""
    task: str
    status: str  # success | partial | error
    output: str = ""
    agent_assignments: Dict[str, List[str]] = field(default_factory=dict)  # agent_id -> [task_ids]
    simulation_trace: List[SimulationRound] = field(default_factory=list)
    consensus_notes: List[Dict[str, Any]] = field(default_factory=list)
    execution_time: float = 0.0


class MiroFishScheduler:
    """
    MiroFish 调度器 — 群体智能协作预演引擎

    核心流程（5步，对应 MiroFish 工作流）：
        1. Graph Building:   构建社会图谱（Agent 关系网络）
        2. Environment Setup: 生成 Agent 深度人设 + 活动配置
        3. Simulation:        在虚拟时钟下运行多轮协作预演
        4. Consensus:         收集 Agent 共识便签
        5. Execution:         根据预演结果执行实际任务

    Usage:
        scheduler = MiroFishScheduler()
        scheduler.register_agents([
            ("researcher", "研究员A"),
            ("analyst", "分析师B"),
            ("writer", "写手C"),
        ])
        result = await scheduler.run("分析某公司财报并生成报告", max_rounds=5)
    """

    def __init__(
        self,
        bus: Optional[MessageBus] = None,
        communication_mode: str = "direct",  # "direct" | "messagebus"
    ):
        self._bus = bus or MessageBus()
        self._comm_mode = communication_mode
        self._persona_engine = PersonaEngine()
        self._social_graph = SocialGraph()
        self._clock = SimulationClock()

        # Agent 注册表
        self._agents: Dict[str, AgentPersona] = {}
        self._activity_configs: Dict[str, AgentActivityConfig] = {}
        self._handlers: Dict[str, Callable] = {}  # agent_id -> task handler

        # 模拟状态
        self._task_nodes: Dict[str, TaskNode] = {}
        self._simulation_trace: List[SimulationRound] = []
        self._consensus_board: List[Dict[str, Any]] = []  # MiroBoard 便签

        # ── v4.0+ 通信层扩展 ──
        self._bus_handlers_setup = False
        self._bid_responses: Dict[str, Dict[str, float]] = {}  # task_id -> {agent_id: score}
        self._execute_responses: Dict[str, str] = {}  # task_id -> result

        # ── v4.0+ 负载均衡扩展 ──
        self._agent_total_assignments: Dict[str, int] = {}  # agent_id -> 历史总分配数
        self._agent_last_round: Dict[str, int] = {}  # agent_id -> 最近一次被分配的轮次

    # ───────────────────────── 注册 ─────────────────────────

    def register_agent(
        self,
        agent_id: str,
        role: str,
        name: str,
        handler: Optional[Callable] = None,
        custom_traits: Optional[Dict[str, Any]] = None,
    ) -> AgentPersona:
        """注册 Agent 并生成深度人设"""
        persona = self._persona_engine.generate(role, name, agent_id, custom_traits)
        self._agents[agent_id] = persona

        # 自动生成活动配置
        self._activity_configs[agent_id] = AgentActivityConfig(
            agent_id=agent_id,
            activity_level=persona.proactivity,
            active_hours=list(range(9, 18)),
            influence_weight=persona.influence_weight,
            stance="neutral",
            decision_style="analytical" if persona.detail_orientation > 0.6 else "intuitive",
        )

        if handler:
            self._handlers[agent_id] = handler

        # 添加到社会图谱
        from nexusagent.orchestration.mirofish.social_graph import EntityNode
        self._social_graph.add_entity(EntityNode(
            entity_id=agent_id,
            name=name,
            entity_type="person",
            properties={"role": role, "mbti": persona.mbti},
        ))

        logger.info("MiroFish 注册 Agent: %s (%s, %s)", agent_id, name, role)
        return persona

    def register_agents(self, role_name_pairs: List[tuple]) -> List[AgentPersona]:
        """批量注册 Agent"""
        personas = []
        for i, (role, name) in enumerate(role_name_pairs):
            persona = self.register_agent(f"agent_{i}", role, name)
            personas.append(persona)

        # 自动建立协作关系（相邻角色之间）
        for i in range(len(role_name_pairs) - 1):
            self._social_graph.add_relation(RelationEdge(
                source_id=f"agent_{i}",
                target_id=f"agent_{i + 1}",
                relation_type="collaborates_with",
                strength=round(0.5 + 0.3 * (1 - abs(i - (i + 1)) / max(1, len(role_name_pairs) - 1)), 2),
            ))

        return personas

    def add_relation(self, source: str, target: str, relation_type: str = "collaborates_with", strength: float = 0.5) -> None:
        """手动添加 Agent 间关系"""
        self._social_graph.add_relation(RelationEdge(source, target, relation_type, strength))

    # ───────────────────────── 核心调度 ─────────────────────────

    async def run(
        self,
        task: str,
        max_rounds: int = 5,
        timeout: float = 120.0,
    ) -> MiroFishResult:
        """
        执行 MiroFish 协作调度

        流程：
            1. 任务分解 → 创建 TaskNode
            2. 多轮模拟：Agent 竞标 → 分配 → 执行 → 留下共识便签
            3. 收集结果 → 聚合输出
        """
        start = time.time()
        self._clock.reset()
        self._simulation_trace.clear()
        self._consensus_board.clear()
        self._task_nodes.clear()
        self._agent_total_assignments.clear()
        self._agent_last_round.clear()

        # 边界检查
        if not self._agents:
            logger.warning("MiroFish: 无可用 Agent，直接返回")
            return MiroFishResult(
                task=task, status="error",
                output="[MiroFish] 错误: 未注册任何 Agent，无法执行协作预演。"
            )

        # v4.0+: 如需 MessageBus 通信，懒加载 handler
        if self._comm_mode == "messagebus":
            await self._setup_bus_handlers()

        await self._publish_event(MiroFishTopics.SIM_START, {
            "task": task,
            "agents": list(self._agents.keys()),
            "max_rounds": max_rounds,
            "communication_mode": self._comm_mode,
        })

        # Step 1: 任务分解（简化版规则分解）
        subtasks = self._decompose_task(task)
        for st in subtasks:
            self._task_nodes[st.task_id] = st

        # Step 2: 多轮协作预演模拟
        for round_num in range(max_rounds):
            round_record = SimulationRound(round_num=round_num)
            self._clock.tick()

            # 2a: Agent 竞标（根据通信模式选择收集方式）
            if self._comm_mode == "messagebus":
                bids = await self._collect_bids_bus()
            else:
                bids = self._collect_bids_direct()
            await self._publish_event(MiroFishTopics.BID, {"round": round_num, "bids": {k: [(a, round(s, 3)) for a, s in v[:3]] for k, v in bids.items()}})

            # 2b: 任务分配（带负载均衡惩罚）
            assignments = self._assign_tasks(bids, round_num=round_num)
            if assignments:
                for agent_id, task_ids in assignments.items():
                    await self._publish_event(MiroFishTopics.AWARD, {"round": round_num, "agent_id": agent_id, "task_ids": task_ids})

            # 2c: Agent 执行并留下共识便签
            for agent_id, task_ids in assignments.items():
                for tid in task_ids:
                    await self._simulate_execution(agent_id, tid)
                    # 留下共识便签
                    note = await self._generate_consensus_note(agent_id, tid)
                    self._consensus_board.append(note)
                    round_record.actions.append({
                        "agent_id": agent_id,
                        "task_id": tid,
                        "action": "execute",
                        "note": note,
                    })

            round_record.clock_state = self._clock.stats()
            self._simulation_trace.append(round_record)

            # 检查是否全部完成
            if all(t.status == "completed" for t in self._task_nodes.values()):
                break

        # Step 3: 聚合输出
        output = self._aggregate_output(task)
        elapsed = time.time() - start

        await self._publish_event(MiroFishTopics.SIM_END, {
            "task": task,
            "status": "success",
            "agents": len(self._agents),
            "tasks": len(self._task_nodes),
            "completed": sum(1 for t in self._task_nodes.values() if t.status == "completed"),
            "elapsed": round(elapsed, 3),
        })

        return MiroFishResult(
            task=task,
            status="success",
            output=output,
            agent_assignments={
                agent_id: [tid for tid, t in self._task_nodes.items() if t.assigned_agent == agent_id]
                for agent_id in self._agents
            },
            simulation_trace=self._simulation_trace,
            consensus_notes=self._consensus_board,
            execution_time=elapsed,
        )

    def _decompose_task(self, task: str) -> List[TaskNode]:
        """任务分解（简化规则版）"""
        subtasks = []
        base_id = f"task_{int(time.time())}"

        # 启发式分解 — 对应 MiroFish 的 decompose_task
        if "分析" in task or "数据" in task:
            subtasks.append(TaskNode(
                task_id=f"{base_id}_01",
                description=f"数据收集与分析: {task}",
                required_capabilities=["analysis", "data_processing"],
                value=1.5,
            ))
        if "报告" in task or "生成" in task or "撰写" in task:
            subtasks.append(TaskNode(
                task_id=f"{base_id}_02",
                description=f"报告撰写与可视化: {task}",
                required_capabilities=["writing", "visualization"],
                value=1.2,
            ))
        if "调研" in task or "搜索" in task or "竞品" in task:
            subtasks.append(TaskNode(
                task_id=f"{base_id}_03",
                description=f"市场调研与竞品分析: {task}",
                required_capabilities=["research", "market_analysis"],
                value=1.0,
            ))
        if "审查" in task or "检查" in task or "验证" in task:
            subtasks.append(TaskNode(
                task_id=f"{base_id}_04",
                description=f"质量审查与验证: {task}",
                required_capabilities=["critic", "quality_assurance"],
                value=0.8,
            ))

        if not subtasks:
            subtasks.append(TaskNode(
                task_id=f"{base_id}_01",
                description=task,
                required_capabilities=["general"],
                value=1.0,
            ))

        return subtasks

    # ───────────────────────── 竞标（可插拔通信） ─────────────────────────

    def _collect_bids(self) -> Dict[str, List[Tuple[str, float]]]:
        """收集 Agent 投标 — 直接调用模式（默认，向后兼容）"""
        return self._collect_bids_direct()

    def _collect_bids_direct(self) -> Dict[str, List[Tuple[str, float]]]:
        """直接调用模式：内部计算投标评分"""
        bids: Dict[str, List[Tuple[str, float]]] = {}
        time_mult = self._clock.get_current_multiplier()

        for task_id, task_node in self._task_nodes.items():
            if task_node.status != "pending":
                continue

            bids[task_id] = []
            for agent_id, persona in self._agents.items():
                config = self._activity_configs[agent_id]
                capability_match = self._calculate_capability_match(
                    persona, task_node.required_capabilities
                )
                current_load = self._calculate_load(agent_id)
                score = config.calculate_bid_score(capability_match, current_load, time_mult)
                bids[task_id].append((agent_id, score))

            bids[task_id].sort(key=lambda x: x[1], reverse=True)

        return bids

    async def _collect_bids_bus(self) -> Dict[str, List[Tuple[str, float]]]:
        """MessageBus 模式：通过消息总线收集投标"""
        self._bid_responses.clear()

        for task_id, task_node in self._task_nodes.items():
            if task_node.status != "pending":
                continue
            await self._publish_event(MiroFishTopics.BID_REQUEST, {
                "task_id": task_id,
                "required_capabilities": task_node.required_capabilities,
                "description": task_node.description,
            })

        # 等待 Agent 响应（给予足够时间处理）
        await asyncio.sleep(0.3)

        bids: Dict[str, List[Tuple[str, float]]] = {}
        for task_id, responses in self._bid_responses.items():
            bids[task_id] = sorted(responses.items(), key=lambda x: x[1], reverse=True)
        return bids

    # ───────────────────────── 分配（负载均衡增强） ─────────────────────────

    def _assign_tasks(
        self,
        bids: Dict[str, List[Tuple[str, float]]],
        round_num: int = 0,
    ) -> Dict[str, List[str]]:
        """分配任务 — 三维惩罚模型（本轮 + 历史累积 + 并发上限）"""
        assignments: Dict[str, List[str]] = {}  # agent_id -> [task_ids]
        round_assigned: Dict[str, int] = {}  # agent_id -> 本轮已分配数

        # 预计算当前负载（用于并发上限检查）
        current_load = {aid: self._calculate_load(aid) for aid in self._agents}

        # 按任务价值降序处理，高价值任务先分配
        sorted_tasks = sorted(
            bids.items(),
            key=lambda x: self._task_nodes[x[0]].value if x[0] in self._task_nodes else 0,
            reverse=True,
        )

        for task_id, bid_list in sorted_tasks:
            if not bid_list:
                continue

            best_agent = None
            best_score = -1.0

            for agent_id, raw_score in bid_list:
                # ── 并发上限检查 ──
                max_concurrent = self._get_max_concurrent(agent_id)
                if current_load.get(agent_id, 0) >= max_concurrent:
                    continue

                # ── 本轮惩罚 ──
                round_penalty = round_assigned.get(agent_id, 0) * 0.15

                # ── 历史累积惩罚（指数衰减） ──
                cumulative = self._agent_total_assignments.get(agent_id, 0)
                rounds_since = round_num - self._agent_last_round.get(agent_id, round_num)
                decay = math.exp(-0.1 * rounds_since)
                cumulative_penalty = cumulative * 0.05 * decay

                adjusted_score = max(0.0, raw_score - round_penalty - cumulative_penalty)
                if adjusted_score > best_score:
                    best_score = adjusted_score
                    best_agent = agent_id

            if best_agent:
                self._task_nodes[task_id].status = "assigned"
                self._task_nodes[task_id].assigned_agent = best_agent
                assignments.setdefault(best_agent, []).append(task_id)
                round_assigned[best_agent] = round_assigned.get(best_agent, 0) + 1
                current_load[best_agent] = current_load.get(best_agent, 0) + 1

                # 更新历史分配记录
                self._agent_total_assignments[best_agent] = self._agent_total_assignments.get(best_agent, 0) + 1
                self._agent_last_round[best_agent] = round_num

                logger.debug("任务分配: %s -> %s (adjusted_score=%.2f)", task_id, best_agent, best_score)

        return assignments

    def _get_max_concurrent(self, agent_id: str) -> int:
        """计算 Agent 的并发任务上限"""
        config = self._activity_configs.get(agent_id)
        if config and hasattr(config, "tasks_per_hour"):
            return max(2, int(config.tasks_per_hour // 2))
        return 3  # 默认上限

    # ───────────────────────── 执行（可插拔通信） ─────────────────────────

    async def _simulate_execution(self, agent_id: str, task_id: str) -> str:
        """模拟 Agent 执行任务 — 根据通信模式分发"""
        if self._comm_mode == "messagebus":
            return await self._simulate_execution_bus(agent_id, task_id)
        return await self._simulate_execution_direct(agent_id, task_id)

    async def _simulate_execution_direct(self, agent_id: str, task_id: str) -> str:
        """直接调用模式：直接调用 handler"""
        handler = self._handlers.get(agent_id)
        task_node = self._task_nodes.get(task_id)
        if not task_node:
            return ""

        result_str = ""
        if handler:
            try:
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(task_node.description, self._agents[agent_id])
                else:
                    result = handler(task_node.description, self._agents[agent_id])
                result_str = str(result)
                task_node.status = "completed"
            except Exception as e:
                logger.warning("Agent %s 任务执行失败: %s", agent_id, e)
                result_str = f"[错误: {e}]"
        else:
            persona = self._agents[agent_id]
            result_str = f"[{persona.name}] 完成: {task_node.description[:40]}..."
            task_node.status = "completed"

        await self._publish_event(MiroFishTopics.RESULT, {
            "agent_id": agent_id,
            "task_id": task_id,
            "status": task_node.status,
            "result": result_str[:200],
        })
        return result_str

    async def _simulate_execution_bus(self, agent_id: str, task_id: str) -> str:
        """MessageBus 模式：通过消息总线请求执行并等待结果"""
        task_node = self._task_nodes.get(task_id)
        if not task_node:
            return ""

        self._execute_responses.pop(task_id, None)
        await self._publish_event(MiroFishTopics.EXECUTE_REQUEST, {
            "agent_id": agent_id,
            "task_id": task_id,
            "description": task_node.description,
        })

        # 等待响应（最多 2 秒）
        for _ in range(20):
            if task_id in self._execute_responses:
                break
            await asyncio.sleep(0.1)

        result_str = self._execute_responses.get(task_id, "")
        if result_str:
            task_node.status = "completed"
        else:
            result_str = f"[超时: {agent_id} 未响应]"
            task_node.status = "completed"  # 模拟完成，避免阻塞

        await self._publish_event(MiroFishTopics.RESULT, {
            "agent_id": agent_id,
            "task_id": task_id,
            "status": task_node.status,
            "result": result_str[:200],
        })
        return result_str

    async def _generate_consensus_note(self, agent_id: str, task_id: str) -> Dict[str, Any]:
        """生成共识便签（MiroBoard 风格）并发布 STICKY 事件"""
        persona = self._agents[agent_id]
        task_node = self._task_nodes.get(task_id)
        note = {
            "agent_id": agent_id,
            "agent_name": persona.name,
            "task_id": task_id,
            "content": f"{persona.name} 认为 '{task_node.description[:30]}...' 已完成。",
            "stance": self._activity_configs[agent_id].stance,
            "influence": persona.influence_weight,
            "timestamp": time.time(),
        }
        await self._publish_event(MiroFishTopics.STICKY, note)
        return note

    def _calculate_capability_match(self, persona: AgentPersona, required: List[str]) -> float:
        """计算能力匹配度"""
        if not required:
            return 0.5
        role_lower = persona.role.lower()
        matches = sum(1 for cap in required if cap.lower() in role_lower or role_lower in cap.lower())
        return min(1.0, matches / len(required) + 0.3)

    def _calculate_load(self, agent_id: str) -> float:
        """计算 Agent 当前负载"""
        assigned = sum(
            1 for t in self._task_nodes.values()
            if t.assigned_agent == agent_id and t.status != "completed"
        )
        config = self._activity_configs[agent_id]
        return min(1.0, assigned / max(1, config.tasks_per_hour))

    def _aggregate_output(self, original_task: str) -> str:
        """聚合所有 Agent 的输出"""
        parts = [f"# MiroFish 协作结果: {original_task}", ""]

        # 任务分配摘要
        parts.append("## 任务分配")
        for task_id, task_node in self._task_nodes.items():
            agent_name = self._agents[task_node.assigned_agent].name if task_node.assigned_agent else "未分配"
            parts.append(f"- [{task_node.status}] {task_node.description[:50]} → {agent_name}")

        # 共识便签
        parts.extend(["", "## 共识便签"])
        for note in self._consensus_board[-5:]:
            parts.append(f"- **{note['agent_name']}** ({note['stance']}): {note['content']}")

        # 社会图谱统计
        stats = self._social_graph.stats()
        parts.extend(["", "## 协作网络", f"- Agent 数量: {stats['node_count']}", f"- 关系边数: {stats['edge_count']}"])

        return "\n".join(parts)

    # ───────────────────────── MessageBus 通信层 ─────────────────────────

    async def _setup_bus_handlers(self) -> None:
        """懒加载：注册 MessageBus 事件处理器（仅在 messagebus 模式下调用）"""
        if self._bus_handlers_setup or self._comm_mode != "messagebus":
            return

        # Scheduler 订阅响应主题
        await self._bus.subscribe(MiroFishTopics.BID_RESPONSE, self._on_bid_response)
        await self._bus.subscribe(MiroFishTopics.EXECUTE_RESPONSE, self._on_execute_response)

        # 为每个已注册 Agent 注册请求处理器
        for agent_id in self._agents:
            await self._register_agent_bus_handlers(agent_id)

        self._bus_handlers_setup = True
        logger.debug("MiroFish MessageBus handler 已注册，Agent 数=%d", len(self._agents))

    def _on_bid_response(self, msg: AgentMessage) -> None:
        """处理投标响应"""
        task_id = msg.payload.get("task_id")
        agent_id = msg.payload.get("agent_id")
        score = msg.payload.get("score", 0.0)
        if task_id and agent_id is not None:
            self._bid_responses.setdefault(task_id, {})[agent_id] = score

    def _on_execute_response(self, msg: AgentMessage) -> None:
        """处理执行结果响应"""
        task_id = msg.payload.get("task_id")
        result = msg.payload.get("result", "")
        if task_id:
            self._execute_responses[task_id] = result

    async def _register_agent_bus_handlers(self, agent_id: str) -> None:
        """为指定 Agent 注册 MessageBus 请求处理器"""
        persona = self._agents[agent_id]
        config = self._activity_configs[agent_id]
        handler = self._handlers.get(agent_id)

        async def on_bid_request(msg: AgentMessage) -> None:
            payload = msg.payload
            task_id = payload.get("task_id")
            if not task_id:
                return
            required = payload.get("required_capabilities", [])
            capability_match = self._calculate_capability_match(persona, required)
            current_load = self._calculate_load(agent_id)
            time_mult = self._clock.get_current_multiplier()
            score = config.calculate_bid_score(capability_match, current_load, time_mult)
            await self._bus.publish(AgentMessage(
                topic=MiroFishTopics.BID_RESPONSE,
                sender=agent_id,
                payload={"task_id": task_id, "agent_id": agent_id, "score": score},
            ))

        async def on_execute_request(msg: AgentMessage) -> None:
            payload = msg.payload
            if payload.get("agent_id") != agent_id:
                return
            task_id = payload.get("task_id")
            if not task_id:
                return
            result = await self._simulate_execution_direct(agent_id, task_id)
            await self._bus.publish(AgentMessage(
                topic=MiroFishTopics.EXECUTE_RESPONSE,
                sender=agent_id,
                payload={"task_id": task_id, "result": result},
            ))

        await self._bus.subscribe(MiroFishTopics.BID_REQUEST, on_bid_request)
        await self._bus.subscribe(MiroFishTopics.EXECUTE_REQUEST, on_execute_request)

    # ───────────────────────── 事件发布 ─────────────────────────

    async def _publish_event(self, topic: str, payload: Dict[str, Any]) -> None:
        """通过 MessageBus 发布 MiroFish 内部事件（供外部订阅者监听进度）"""
        try:
            msg = AgentMessage(
                topic=topic,
                sender="mirofish.scheduler",
                payload=payload,
            )
            await self._bus.publish(msg)
        except Exception as e:
            logger.debug("MessageBus 事件发布失败（可忽略）: %s", e)

    # ───────────────────────── 统计 ─────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        return {
            "agents": len(self._agents),
            "tasks": len(self._task_nodes),
            "completed": sum(1 for t in self._task_nodes.values() if t.status == "completed"),
            "rounds": len(self._simulation_trace),
            "consensus_notes": len(self._consensus_board),
            "graph": self._social_graph.stats(),
        }
