"""
NexusAgent v4.0 — Specialist Worker Agent

每个 Worker 是一个具备特定角色的 Agent，内部由 StateGraph 驱动执行。
设计参考 CrewAI 角色抽象 + AutoGen Actor 模型。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from nexusagent.agents.message_bus import AgentMessage, MessageBus
from nexusagent.execution.state_graph import END, CompiledGraph, RunConfig, StateGraph

logger = logging.getLogger("nexus.agents.worker")


@dataclass
class WorkerResult:
    """Worker 执行结果"""
    worker_id: str
    task_id: str
    status: str  # success | error | timeout
    output: str = ""
    state: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    execution_time: float = 0.0


class WorkerAgent:
    """
    Specialist Worker Agent

    Attributes:
        agent_id: 唯一标识
        name: 显示名称
        role: 角色描述 (如 "财务分析师")
        goal: 目标描述
        tools: 可用工具列表
        graph: 内部 StateGraph（每个 Worker 是一个子图）
    """

    def __init__(
        self,
        agent_id: str,
        name: str,
        role: str,
        goal: str,
        tools: Optional[List[Any]] = None,
        graph: Optional[CompiledGraph] = None,
    ):
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.goal = goal
        self.tools = tools or []
        self.graph = graph
        self._bus: Optional[MessageBus] = None
        self._queue: Optional[asyncio.Queue] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def connect(self, bus: MessageBus) -> None:
        """连接到消息总线"""
        self._bus = bus
        self._queue = await bus.register_agent(self.agent_id)
        self._running = True
        self._task = asyncio.create_task(self._message_loop())
        logger.info("Worker '%s' (%s) 已连接到消息总线", self.name, self.agent_id)

    async def disconnect(self) -> None:
        """断开连接"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Worker '%s' 已断开", self.name)

    async def _message_loop(self) -> None:
        """消息接收循环"""
        while self._running and self._queue:
            try:
                msg = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._handle_message(msg)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Worker '%s' 消息处理错误: %s", self.name, e)

    async def _handle_message(self, msg: AgentMessage) -> None:
        """处理接收到的消息"""
        action = msg.payload.get("action")
        if action == "execute":
            task = msg.payload.get("task", "")
            task_id = msg.payload.get("task_id", "")
            tenant_id = msg.payload.get("tenant_id", "default")
            result = await self.execute(task, task_id=task_id, tenant_id=tenant_id)
            # 发送结果回 Supervisor
            if msg.reply_to and self._bus:
                await self._bus.send_direct(msg.reply_to, AgentMessage(
                    topic="task.result",
                    sender=self.agent_id,
                    recipient=msg.sender,
                    payload={
                        "action": "result",
                        "task_id": task_id,
                        "result": result,
                    },
                    correlation_id=msg.correlation_id,
                ))
        elif action == "ping":
            if msg.reply_to and self._bus:
                await self._bus.send_direct(msg.reply_to, AgentMessage(
                    topic="worker.pong",
                    sender=self.agent_id,
                    payload={"status": "alive", "role": self.role},
                ))

    async def execute(
        self,
        task: str,
        task_id: str = "",
        tenant_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
    ) -> WorkerResult:
        """
        执行任务

        如果 Worker 配置了 graph，则在 graph 中执行；
        否则执行默认的 ReAct 循环。
        """
        import time as tm
        start = tm.time()
        task_id = task_id or f"task_{tm.time()}"

        try:
            if self.graph:
                initial_state = {
                    "task": task,
                    "task_id": task_id,
                    "tenant_id": tenant_id,
                    "messages": [{"role": "user", "content": task}],
                    **(context or {}),
                }
                config = RunConfig(thread_id=task_id, tenant_id=tenant_id)
                final_state = await self.graph.ainvoke(initial_state, config=config)
                output = final_state.get("output", str(final_state.get("messages", [])[-1:]))
                return WorkerResult(
                    worker_id=self.agent_id,
                    task_id=task_id,
                    status="success",
                    output=str(output),
                    state=final_state,
                    execution_time=tm.time() - start,
                )
            else:
                # 默认：直接返回处理结果（子类可覆盖）
                output = f"[{self.name}] 处理任务: {task[:50]}..."
                return WorkerResult(
                    worker_id=self.agent_id,
                    task_id=task_id,
                    status="success",
                    output=output,
                    execution_time=tm.time() - start,
                )
        except Exception as e:
            logger.error("Worker '%s' 任务执行失败: %s", self.name, e)
            return WorkerResult(
                worker_id=self.agent_id,
                task_id=task_id,
                status="error",
                error=str(e),
                execution_time=tm.time() - start,
            )
