"""
NexusAgent v4.0 — AgentCrew 编排器

将 Supervisor + Workers 封装为易用的 Crew 接口。
设计参考 CrewAI Crew/Flow 抽象。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from nexusagent.agents.message_bus import MessageBus
from nexusagent.agents.supervisor import CrewResult, SupervisorAgent
from nexusagent.agents.worker import WorkerAgent

logger = logging.getLogger("nexus.agents.crew")


class AgentCrew:
    """
    AgentCrew — 多Agent团队编排器

    Usage:
        crew = AgentCrew()
        crew.add_workers([
            WorkerAgent("analyst", "财务分析师", "analyst", "分析财务数据"),
            WorkerAgent("researcher", "市场研究员", "researcher", "监测市场动态"),
        ])
        result = await crew.execute("分析某公司财报并监测竞品", tenant_id="t1")
    """

    def __init__(self, supervisor: Optional[SupervisorAgent] = None):
        self.supervisor = supervisor or SupervisorAgent()
        self.workers: List[WorkerAgent] = []
        self._bus = MessageBus()
        self._initialized = False

    def add_workers(self, workers: List[WorkerAgent]) -> AgentCrew:
        """添加 Worker"""
        self.workers.extend(workers)
        self.supervisor.register_workers(workers)
        return self

    async def initialize(self) -> None:
        """初始化消息总线连接"""
        if self._initialized:
            return
        await self.supervisor.connect(self._bus)
        for w in self.workers:
            await w.connect(self._bus)
        self._initialized = True
        logger.info("AgentCrew 初始化完成: %d workers", len(self.workers))

    async def shutdown(self) -> None:
        """优雅关闭"""
        for w in self.workers:
            await w.disconnect()
        self._initialized = False

    async def execute(
        self,
        task: str,
        tenant_id: str = "default",
        mode: str = "parallel",
        timeout: float = 120.0,
    ) -> CrewResult:
        """执行复杂任务"""
        if not self._initialized:
            await self.initialize()
        return await self.supervisor.execute(
            task=task, tenant_id=tenant_id, mode=mode, timeout=timeout,
        )
