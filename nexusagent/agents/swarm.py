"""
NexusAgent v4.0+ — Agent Swarm 多智能体编排

设计参考:
- OpenAI Swarm: https://github.com/openai/swarm
  "Handoffs + Routine: lightweight multi-agent orchestration"
- AutoGen GroupChat: https://microsoft.github.io/autogen/docs/Use-Cases/agent_chat
  "Multi-agent conversation with speaker selection"
- CrewAI Flow: https://crewai.com/open-source
  "Event-driven agent coordination"

职责:
    1. Handoff 移交: Agent 动态将任务移交给更合适的 Agent
    2. GroupChat 群聊: 多 Agent 协作讨论，自动选择下一个发言者
    3. 动态扩展: 运行时注册/注销 Agent
    4. 负载均衡: 基于队列深度和响应时间动态路由

Usage:
    from nexusagent.agents.swarm import AgentSwarm, SwarmAgent
    swarm = AgentSwarm()
    swarm.register(SwarmAgent("researcher", "研究员"))
    swarm.register(SwarmAgent("writer", "写手"))
    result = await swarm.run("研究并撰写一份报告", strategy="handoff")
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from nexusagent.agents.message_bus import AgentMessage, MessageBus

logger = logging.getLogger("nexus.agents.swarm")


@dataclass
class SwarmAgent:
    """Swarm 中的 Agent 定义"""
    agent_id: str
    name: str
    role: str = "generalist"
    instructions: str = ""
    tools: List[str] = field(default_factory=list)
    # 运行时指标
    pending_tasks: int = 0
    total_tasks: int = 0
    avg_response_time: float = 0.0
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "pending_tasks": self.pending_tasks,
            "total_tasks": self.total_tasks,
            "avg_response_time": round(self.avg_response_time, 2),
            "enabled": self.enabled,
        }


@dataclass
class SwarmResult:
    """Swarm 执行结果"""
    task: str
    strategy: str
    status: str  # success | partial | error
    output: str = ""
    agent_trace: List[Dict[str, Any]] = field(default_factory=list)
    execution_time: float = 0.0


class AgentSwarm:
    """
    Agent Swarm — 多智能体编排引擎

    支持两种策略:
        handoff: OpenAI Swarm 风格，一个 Agent 处理完移交下一个
        groupchat: AutoGen 风格，多 Agent 群聊讨论
        round_robin: 轮询，每个 Agent 依次处理
        load_balance: 负载均衡，选择最空闲的 Agent
    """

    def __init__(self, bus: Optional[MessageBus] = None):
        self._bus = bus or MessageBus()
        self._agents: Dict[str, SwarmAgent] = {}
        self._handlers: Dict[str, Callable] = {}  # agent_id -> handler
        self._history: List[Dict[str, Any]] = []

    # ───────────────────────── 注册管理 ─────────────────────────

    def register(self, agent: SwarmAgent, handler: Optional[Callable] = None) -> None:
        """注册 Agent"""
        self._agents[agent.agent_id] = agent
        if handler:
            self._handlers[agent.agent_id] = handler
        logger.info("注册 Agent: %s (%s)", agent.name, agent.agent_id)

    def unregister(self, agent_id: str) -> bool:
        """注销 Agent"""
        if agent_id not in self._agents:
            return False
        del self._agents[agent_id]
        self._handlers.pop(agent_id, None)
        logger.info("注销 Agent: %s", agent_id)
        return True

    def get_agent(self, agent_id: str) -> Optional[SwarmAgent]:
        return self._agents.get(agent_id)

    def list_agents(self, enabled_only: bool = True) -> List[SwarmAgent]:
        """列出所有 Agent"""
        agents = list(self._agents.values())
        if enabled_only:
            agents = [a for a in agents if a.enabled]
        return agents

    def set_handler(self, agent_id: str, handler: Callable) -> None:
        """设置 Agent 处理函数"""
        self._handlers[agent_id] = handler

    # ───────────────────────── 路由策略 ─────────────────────────

    def _select_by_role(self, role: str) -> Optional[SwarmAgent]:
        """按角色选择 Agent"""
        candidates = [a for a in self._agents.values() if a.role == role and a.enabled]
        if not candidates:
            return None
        # 选择 pending 最少的
        return min(candidates, key=lambda a: a.pending_tasks)

    def _select_by_load(self) -> Optional[SwarmAgent]:
        """负载均衡: 选择最空闲的 Agent"""
        candidates = [a for a in self._agents.values() if a.enabled]
        if not candidates:
            return None
        # 综合评分: pending_tasks + avg_response_time
        return min(candidates, key=lambda a: a.pending_tasks + a.avg_response_time)

    def _select_next_speaker(self, context: str) -> Optional[SwarmAgent]:
        """GroupChat: 选择下一个发言者"""
        candidates = [a for a in self._agents.values() if a.enabled]
        if not candidates:
            return None
        # 简单策略: 轮询 + 角色匹配
        # 优先选择没有发过言的，然后选择与上下文最相关的角色
        for a in candidates:
            if a.agent_id not in {h.get("agent_id") for h in self._history[-len(candidates):]}:
                return a
        return candidates[0]

    # ───────────────────────── 执行策略 ─────────────────────────

    async def run(
        self,
        task: str,
        strategy: str = "handoff",
        initial_agent: Optional[str] = None,
        max_turns: int = 10,
        timeout: float = 120.0,
    ) -> SwarmResult:
        """
        执行 Swarm 任务

        Args:
            task: 用户任务描述
            strategy: handoff | groupchat | round_robin | load_balance
            initial_agent: 初始 Agent ID
            max_turns: 最大轮数
            timeout: 超时秒数
        """
        start = time.time()
        self._history.clear()

        try:
            if strategy == "handoff":
                return await self._run_handoff(task, initial_agent, max_turns, timeout)
            elif strategy == "groupchat":
                return await self._run_groupchat(task, initial_agent, max_turns, timeout)
            elif strategy == "round_robin":
                return await self._run_round_robin(task, max_turns, timeout)
            elif strategy == "load_balance":
                return await self._run_load_balance(task, max_turns, timeout)
            else:
                return SwarmResult(task=task, strategy=strategy, status="error", output=f"未知策略: {strategy}")
        except asyncio.TimeoutError:
            return SwarmResult(
                task=task, strategy=strategy, status="partial",
                output="执行超时", execution_time=time.time() - start,
            )
        except Exception as e:
            logger.error("Swarm 执行失败: %s", e)
            return SwarmResult(
                task=task, strategy=strategy, status="error",
                output=str(e), execution_time=time.time() - start,
            )

    async def _run_handoff(
        self, task: str, initial_agent: Optional[str], max_turns: int, timeout: float
    ) -> SwarmResult:
        """Handoff 策略: Agent 处理完可以移交下一个"""
        if not self._agents:
            return SwarmResult(task=task, strategy="handoff", status="error", output="没有可用的 Agent")

        current_id = initial_agent
        if not current_id:
            current_id = list(self._agents.keys())[0]

        context = task
        output_parts = []
        turn_start = time.time()

        for turn in range(max_turns):
            agent = self._agents.get(current_id)
            if not agent or not agent.enabled:
                break

            agent.pending_tasks += 1
            turn_start = time.time()
            result = await self._invoke_agent(agent, context, timeout)
            agent.pending_tasks -= 1
            agent.total_tasks += 1
            elapsed = time.time() - turn_start
            agent.avg_response_time = (agent.avg_response_time * (agent.total_tasks - 1) + elapsed) / agent.total_tasks

            self._history.append({
                "turn": turn,
                "agent_id": agent.agent_id,
                "agent_name": agent.name,
                "input": context,
                "output": result,
                "elapsed": round(elapsed, 2),
            })
            output_parts.append(f"[{agent.name}] {result}")

            # 解析 handoff 指令
            next_id = self._parse_handoff(result)
            if next_id == "__DONE__" or not next_id:
                break
            if next_id in self._agents:
                current_id = next_id
                context = f"前序结果: {result}\n原始任务: {task}"
            else:
                # 按角色匹配
                role_agent = self._select_by_role(next_id)
                if role_agent:
                    current_id = role_agent.agent_id
                    context = f"前序结果: {result}\n原始任务: {task}"
                else:
                    break

        return SwarmResult(
            task=task,
            strategy="handoff",
            status="success",
            output="\n".join(output_parts),
            agent_trace=self._history.copy(),
            execution_time=time.time() - turn_start,
        )

    async def _run_groupchat(
        self, task: str, initial_agent: Optional[str], max_turns: int, timeout: float
    ) -> SwarmResult:
        """GroupChat 策略: 多 Agent 群聊讨论"""
        context = f"系统: 请协作完成以下任务\n任务: {task}"
        output_parts = []
        turn_start = time.time()

        for turn in range(max_turns):
            agent = self._select_next_speaker(context)
            if not agent:
                break

            agent.pending_tasks += 1
            turn_start = time.time()
            result = await self._invoke_agent(agent, context, timeout)
            agent.pending_tasks -= 1
            agent.total_tasks += 1
            elapsed = time.time() - turn_start
            agent.avg_response_time = (agent.avg_response_time * (agent.total_tasks - 1) + elapsed) / agent.total_tasks

            self._history.append({
                "turn": turn,
                "agent_id": agent.agent_id,
                "agent_name": agent.name,
                "input": context[-200:],
                "output": result,
                "elapsed": round(elapsed, 2),
            })
            output_parts.append(f"{agent.name}: {result}")

            # 终止条件: 某个 Agent 说 "完成" 或 "done"
            if any(kw in result.lower() for kw in ("完成", "done", "结论")):
                break

            context = f"{context}\n{agent.name}: {result}"

        return SwarmResult(
            task=task,
            strategy="groupchat",
            status="success",
            output="\n".join(output_parts),
            agent_trace=self._history.copy(),
            execution_time=time.time() - turn_start,
        )

    async def _run_round_robin(self, task: str, max_turns: int, timeout: float) -> SwarmResult:
        """轮询策略"""
        agents = [a for a in self._agents.values() if a.enabled]
        if not agents:
            return SwarmResult(task=task, strategy="round_robin", status="error", output="没有可用的 Agent")

        context = task
        output_parts = []

        for turn in range(max_turns):
            agent = agents[turn % len(agents)]
            result = await self._invoke_agent(agent, context)
            output_parts.append(f"[{agent.name}] {result}")
            self._history.append({"turn": turn, "agent_id": agent.agent_id, "output": result})
            context = result

        return SwarmResult(
            task=task,
            strategy="round_robin",
            status="success",
            output="\n".join(output_parts),
            agent_trace=self._history.copy(),
        )

    async def _run_load_balance(self, task: str, max_turns: int, timeout: float) -> SwarmResult:
        """负载均衡策略"""
        output_parts = []

        for turn in range(max_turns):
            agent = self._select_by_load()
            if not agent:
                break
            result = await self._invoke_agent(agent, task)
            output_parts.append(f"[{agent.name}] {result}")
            self._history.append({"turn": turn, "agent_id": agent.agent_id, "output": result})

        return SwarmResult(
            task=task,
            strategy="load_balance",
            status="success",
            output="\n".join(output_parts),
            agent_trace=self._history.copy(),
        )

    async def _invoke_agent(self, agent: SwarmAgent, context: str, timeout: float = 120.0) -> str:
        """调用 Agent 处理函数（带超时保护）"""
        handler = self._handlers.get(agent.agent_id)
        if not handler:
            return f"[Agent {agent.name} 未配置处理函数]"
        try:
            if asyncio.iscoroutinefunction(handler):
                return await asyncio.wait_for(handler(context, agent), timeout=timeout)
            return await asyncio.wait_for(asyncio.to_thread(handler, context, agent), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Agent %s 调用超时 (%.1fs)", agent.agent_id, timeout)
            return f"[错误: 执行超时 ({timeout}s)]"
        except Exception as e:
            logger.warning("Agent %s 调用失败: %s", agent.agent_id, e)
            return f"[错误: {e}]"

    def _parse_handoff(self, output: str) -> str:
        """解析 Handoff 指令"""
        # 支持格式: [HANDOFF: agent_id] 或 [移交: agent_id] 或 [DONE]
        import re
        m = re.search(r"\[HANDOFF:\s*(\w+)\]", output, re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(r"\[移交[:：]\s*(\w+)\]", output)
        if m:
            return m.group(1)
        if re.search(r"\[DONE\]|\[完成\]", output, re.IGNORECASE):
            return "__DONE__"
        return ""

    # ───────────────────────── 统计 ─────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """获取 Swarm 统计"""
        return {
            "total_agents": len(self._agents),
            "enabled_agents": sum(1 for a in self._agents.values() if a.enabled),
            "agents": [a.to_dict() for a in self._agents.values()],
            "history_length": len(self._history),
        }
