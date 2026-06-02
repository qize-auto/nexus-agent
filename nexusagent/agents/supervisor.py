"""
NexusAgent v4.0 — Supervisor Agent

负责:
1. 接收用户复杂任务
2. 分解为子任务
3. 动态路由给合适的 Worker
4. 聚合结果并解决冲突

设计参考:
- CrewAI Flow + Planning agent: https://crewai.com/open-source
- Amazon Bedrock Supervisor+Sub-agent: https://www.infoq.com/news/2025/01/aws-bedrock-multi-agent-ai/
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from nexusagent.agents.message_bus import AgentMessage, MessageBus
from nexusagent.agents.worker import WorkerAgent, WorkerResult

logger = logging.getLogger("nexus.agents.supervisor")


@dataclass
class SubTask:
    """子任务"""
    task_id: str
    description: str
    role: str = ""  # 所需角色类型
    assigned_worker: str = ""  # worker agent_id
    expected_output: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    priority: int = 1  # 1=高, 3=低


@dataclass
class CrewResult:
    """Crew 执行结果"""
    task_id: str
    status: str  # success | partial | error
    final_output: str = ""
    subtask_results: List[WorkerResult] = field(default_factory=list)
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class SupervisorAgent:
    """
    Supervisor Agent — 多Agent编排的核心

    两种工作模式:
        1. 串行流水线: task A -> task B -> task C
        2. 并行分派:   task A, B, C 同时执行，然后聚合
    """

    def __init__(
        self,
        agent_id: str = "supervisor",
        name: str = "Supervisor",
        decomposition_prompt: Optional[str] = None,
    ):
        self.agent_id = agent_id
        self.name = name
        self.decomposition_prompt = decomposition_prompt or (
            "你是一个任务调度专家。请将用户的复杂任务分解为多个独立的子任务，"
            "每个子任务应指定适合处理它的角色类型。返回JSON格式:"
            '{"subtasks":[{"description":"...","role":" researcher|analyst|writer|critic ","priority":1}]}'
        )
        self._bus: Optional[MessageBus] = None
        self._workers: Dict[str, WorkerAgent] = {}
        self._result_buffer: Dict[str, WorkerResult] = {}
        self._lock = asyncio.Lock()

    def register_workers(self, workers: List[WorkerAgent]) -> None:
        """注册 Worker"""
        for w in workers:
            self._workers[w.agent_id] = w
        logger.info("Supervisor 注册了 %d 个 Workers", len(workers))

    async def connect(self, bus: MessageBus) -> None:
        """连接到消息总线"""
        self._bus = bus
        await bus.register_agent(self.agent_id)
        await bus.subscribe("task.result", self._on_result)
        logger.info("Supervisor '%s' 已连接到消息总线", self.name)

    async def _on_result(self, msg: AgentMessage) -> None:
        """接收 Worker 返回的结果"""
        result = msg.payload.get("result")
        if isinstance(result, dict):
            # 从 dict 恢复 WorkerResult
            wr = WorkerResult(**result)
            async with self._lock:
                self._result_buffer[wr.task_id] = wr
            logger.info("Supervisor 收到结果: task_id=%s, status=%s", wr.task_id, wr.status)

    async def decompose_task(self, task: str) -> List[SubTask]:
        """
        将复杂任务分解为子任务

        当前实现: 基于规则的分词分解（生产环境可接入 LLM）
        """
        # 简化的规则分解 — 可替换为 LLM 调用
        subtasks: List[SubTask] = []
        task_id_base = f"crew_{int(time.time())}"

        # 启发式分解
        if "财报" in task or "分析" in task:
            subtasks.append(SubTask(
                task_id=f"{task_id_base}_01",
                description=f"收集并分析相关财务数据: {task}",
                expected_output="财务分析报告（收入、利润、现金流）",
                role="analyst",
            ))
        if "竞品" in task or "监测" in task or "竞争" in task:
            subtasks.append(SubTask(
                task_id=f"{task_id_base}_02",
                description=f"监测竞争对手动态和市场表现: {task}",
                expected_output="竞品监测摘要",
                role="researcher",
            ))
        if "PPT" in task or "报告" in task or "生成" in task:
            subtasks.append(SubTask(
                task_id=f"{task_id_base}_03",
                description=f"基于分析结果生成可视化报告/PPT: {task}",
                expected_output="完整报告文档",
                role="writer",
            ))

        # 默认：至少一个分析子任务
        if not subtasks:
            subtasks.append(SubTask(
                task_id=f"{task_id_base}_01",
                description=task,
                expected_output="任务执行结果",
                role="analyst",
            ))

        return subtasks

    def _match_worker(self, subtask: SubTask) -> Optional[WorkerAgent]:
        """根据角色匹配最合适的 Worker"""
        candidates: List[tuple] = []
        for w in self._workers.values():
            score = 0
            role_lower = subtask.role.lower()
            if role_lower in w.role.lower():
                score += 10
            if any(k in w.goal.lower() for k in role_lower.split()):
                score += 5
            if score > 0:
                candidates.append((score, w))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]

        # fallback: 返回第一个可用 Worker
        return next(iter(self._workers.values())) if self._workers else None

    async def execute(
        self,
        task: str,
        tenant_id: str = "default",
        mode: str = "parallel",  # parallel | sequential
        timeout: float = 120.0,
    ) -> CrewResult:
        """
        执行复杂任务

        Args:
            task: 用户原始任务
            tenant_id: 租户ID
            mode: parallel=并行分派, sequential=串行执行
            timeout: 总超时时间
        """
        start = time.time()
        crew_task_id = f"crew_{int(start)}_{tenant_id}"
        logger.info("[tenant=%s] Supervisor 开始执行任务: %s (mode=%s)", tenant_id, task, mode)

        # 1. 分解任务
        subtasks = await self.decompose_task(task)
        logger.info("任务已分解为 %d 个子任务", len(subtasks))

        # 2. 匹配 Worker
        for st in subtasks:
            w = self._match_worker(st)
            if w:
                st.assigned_worker = w.agent_id
            else:
                logger.error("无可用 Worker 匹配角色: %s", st.role)
                return CrewResult(
                    task_id=crew_task_id,
                    status="error",
                    final_output=f"错误: 无可用 Worker 匹配角色 '{st.role}'",
                    execution_time=time.time() - start,
                )

        # 3. 分派执行
        results: List[WorkerResult] = []

        if mode == "parallel":
            # 并行分派
            tasks = []
            for st in subtasks:
                tasks.append(asyncio.create_task(self._dispatch_subtask(st, tenant_id, crew_task_id)))
            done, pending = await asyncio.wait(tasks, timeout=timeout, return_when=asyncio.ALL_COMPLETED)
            for fut in done:
                try:
                    results.append(fut.result())
                except Exception as e:
                    logger.error("子任务异常: %s", e)
                    results.append(WorkerResult(
                        worker_id="", task_id="", status="error", error=str(e),
                    ))
            for fut in pending:
                fut.cancel()

        else:
            # 串行执行
            for st in subtasks:
                result = await asyncio.wait_for(
                    self._dispatch_subtask(st, tenant_id, crew_task_id),
                    timeout=timeout,
                )
                results.append(result)
                # 串行时可将前面结果作为上下文传给后面的子任务
                if result.status == "error":
                    logger.warning("子任务失败，停止后续执行: %s", st.task_id)
                    break

        # 4. 聚合结果
        success_count = sum(1 for r in results if r.status == "success")
        final_status = "success" if success_count == len(results) else ("partial" if success_count > 0 else "error")

        final_output = self._aggregate_results(task, results)

        elapsed = time.time() - start
        logger.info("[tenant=%s] 任务完成: status=%s, 子任务=%d, 耗时=%.2fs",
                    tenant_id, final_status, len(results), elapsed)

        return CrewResult(
            task_id=crew_task_id,
            status=final_status,
            final_output=final_output,
            subtask_results=results,
            execution_time=elapsed,
            metadata={"mode": mode, "tenant_id": tenant_id, "subtask_count": len(subtasks)},
        )

    async def _dispatch_subtask(
        self,
        subtask: SubTask,
        tenant_id: str,
        correlation_id: str,
    ) -> WorkerResult:
        """分派单个子任务给 Worker"""
        worker = self._workers.get(subtask.assigned_worker)
        if not worker:
            return WorkerResult(
                worker_id=subtask.assigned_worker,
                task_id=subtask.task_id,
                status="error",
                error=f"Worker '{subtask.assigned_worker}' 不存在",
            )

        if self._bus:
            # 通过消息总线发送
            await self._bus.send_direct(worker.agent_id, AgentMessage(
                topic="task.delegation",
                sender=self.agent_id,
                recipient=worker.agent_id,
                payload={
                    "action": "execute",
                    "task": subtask.description,
                    "task_id": subtask.task_id,
                    "tenant_id": tenant_id,
                    "context": subtask.context,
                },
                correlation_id=correlation_id,
                reply_to=self.agent_id,
            ))
            # 从 Supervisor 的队列直接读取结果
            queue = await self._bus.get_queue(self.agent_id)
            try:
                result_msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                result = result_msg.payload.get("result")
                if isinstance(result, WorkerResult):
                    return result
                if isinstance(result, dict):
                    return WorkerResult(**result)
                return WorkerResult(
                    worker_id=worker.agent_id,
                    task_id=subtask.task_id,
                    status="error",
                    error="结果格式错误",
                )
            except asyncio.TimeoutError:
                return WorkerResult(
                    worker_id=worker.agent_id,
                    task_id=subtask.task_id,
                    status="error",
                    error="等待结果超时",
                )
        else:
            # 直接调用（单进程模式）
            return await worker.execute(
                subtask.description,
                task_id=subtask.task_id,
                tenant_id=tenant_id,
                context=subtask.context,
            )

    def _aggregate_results(self, original_task: str, results: List[WorkerResult]) -> str:
        """聚合多个 Worker 的结果为最终输出"""
        parts = [f"# 任务执行报告\n\n原始任务: {original_task}\n"]
        for r in results:
            parts.append(f"\n## [{r.worker_id}] {r.status.upper()}\n")
            if r.status == "success":
                parts.append(r.output)
            else:
                parts.append(f"错误: {r.error}")
        return "\n".join(parts)
