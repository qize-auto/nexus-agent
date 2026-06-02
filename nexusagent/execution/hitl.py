"""
NexusAgent v4.0+ — Human-in-the-Loop 中断节点

设计参考:
- LangGraph interrupt: https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/
  "interrupt_before / interrupt_after — pause execution for human input"

职责:
    在 StateGraph 执行中暂停，等待人类确认后继续
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger("nexus.execution.hitl")


@dataclass
class HITLRequest:
    """人机协作请求"""
    thread_id: str
    node_name: str
    question: str
    context: Dict[str, Any]
    timeout_seconds: float = 300.0


@dataclass
class HITLResponse:
    """人机协作响应"""
    approved: bool
    feedback: str = ""
    modified_state: Optional[Dict[str, Any]] = None


class HITLManager:
    """
    HITL 管理器

    Usage:
        manager = HITLManager()

        # 在节点中请求确认
        async def risky_node(state):
            req = HITLRequest(thread_id="t1", node_name="deploy", question="确认部署到生产环境？")
            resp = await manager.request_approval(req)
            if not resp.approved:
                return {"__hitl_denied__": True, "reason": resp.feedback}
            return {"deploy_result": "success"}
    """

    def __init__(self):
        self._pending: Dict[str, asyncio.Future] = {}
        self._responses: Dict[str, HITLResponse] = {}

    async def request_approval(self, request: HITLRequest) -> HITLResponse:
        """请求人类批准，阻塞直到响应或超时"""
        key = f"{request.thread_id}:{request.node_name}"
        # 安全修复: 使用 get_running_loop() 替代 get_event_loop()
        # 避免在子线程或事件循环已变更时获取到已关闭的 loop
        future = asyncio.get_running_loop().create_future()
        self._pending[key] = future

        # 安全准则: 避免在日志中记录可能包含敏感信息的 question
        logger.info("HITL 请求: %s (timeout=%.0fs)", key, request.timeout_seconds)

        try:
            response = await asyncio.wait_for(future, timeout=request.timeout_seconds)
            # 成功响应后清理，防止 _responses 无限增长
            self._responses.pop(key, None)
            return response
        except asyncio.TimeoutError:
            logger.warning("HITL 请求超时: %s", key)
            return HITLResponse(approved=False, feedback="等待超时，操作已取消")
        finally:
            self._pending.pop(key, None)

    def submit_response(self, thread_id: str, node_name: str, response: HITLResponse) -> bool:
        """外部系统提交人类响应"""
        key = f"{thread_id}:{node_name}"
        future = self._pending.get(key)
        if future and not future.done():
            future.set_result(response)
            # 成功提交后记录响应（用于审计），但限制容量
            self._responses[key] = response
            # 防止 _responses 无限增长，仅保留最近 100 条
            if len(self._responses) > 100:
                oldest = next(iter(self._responses))
                self._responses.pop(oldest, None)
            return True
        logger.warning("HITL 响应提交失败，请求不存在或已超时: %s", key)
        return False

    def get_pending_requests(self) -> Dict[str, HITLRequest]:
        """获取所有待处理的 HITL 请求"""
        # 简化实现：返回空（实际应用应存储请求队列）
        return {}


# 全局管理器
# 注意: 全局单例在多租户/多 worker 环境下存在请求串扰风险。
# 生产环境应为每个租户或每个会话创建独立的 HITLManager 实例。
_hitl_manager = HITLManager()


def get_hitl_manager() -> HITLManager:
    """获取全局 HITL 管理器实例。

    警告: 在需要租户隔离的场景下，应直接实例化 HITLManager() 而非使用此单例。
    """
    return _hitl_manager
