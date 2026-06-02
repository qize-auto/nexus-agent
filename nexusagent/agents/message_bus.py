"""
NexusAgent v4.0 — Agent 间异步消息总线

设计参考:
- AutoGen Actor 模型: https://www.microsoft.com/en-us/research/articles/autogen-v0-4-reimagining-the-foundation-of-agentic-ai-for-scale-extensibility-and-robustness/
  "asynchronous message exchange between agents... decouples how messages are delivered from how agents handle them"
- 简化版: 基于 asyncio Queue 的发布-订阅模型
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("nexus.agents.message_bus")


@dataclass
class AgentMessage:
    """Agent 间消息"""
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    topic: str = ""          # 主题，如 "task.delegation"
    sender: str = ""         # 发送者 agent_id
    recipient: str = ""      # 接收者 agent_id (空=广播)
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    correlation_id: str = ""  # 关联ID，用于追踪同一任务链
    reply_to: str = ""        # 回复地址

    # v4.0+ MiroFish 扩展字段
    persona: Dict[str, Any] = field(default_factory=dict)  # 发送者人设快照
    stance: str = ""          # 发送者立场 (supportive|opposing|neutral|observer)
    influence: float = 1.0    # 发送者影响力权重
    consensus_thread: str = ""  # 共识便签线程ID


class MiroFishTopics:
    """MiroFish 消息主题常量 [MIROFISH-INSPIRED]"""
    BID = "mirofish.bid"                     # 合同网投标（通知事件）
    BID_REQUEST = "mirofish.bid.request"     # Scheduler -> Agent: 请求投标
    BID_RESPONSE = "mirofish.bid.response"   # Agent -> Scheduler: 投标响应
    AWARD = "mirofish.award"                 # 合同网中标
    RESULT = "mirofish.result"               # 任务结果
    STICKY = "mirofish.sticky"               # MiroBoard 便签
    ZONE_SYNC = "mirofish.zone_sync"         # 区域状态同步
    SIM_START = "mirofish.sim.start"         # 模拟开始
    SIM_END = "mirofish.sim.end"             # 模拟结束
    EXECUTE_REQUEST = "mirofish.execute.request"    # Scheduler -> Agent: 请求执行
    EXECUTE_RESPONSE = "mirofish.execute.response"  # Agent -> Scheduler: 执行结果


class ProfileTopics:
    """用户画像消息主题常量"""
    UPDATED = "profile.updated"           # 画像更新
    TRAIT_ADDED = "profile.trait_added"   # 新画像条目
    DREAM_COMPLETE = "profile.dream_complete"  # 梦境处理完成
    PENDING_TRAIT = "profile.pending_trait"    # 新待验证条目
    PROFILE_DELETED = "profile.deleted"        # 画像删除 (GDPR)
    PREFERENCE_CHANGED = "profile.preference_changed"  # 偏好变更


MessageHandler = Callable[[AgentMessage], asyncio.Future]


class MessageBus:
    """
    轻量级异步消息总线

    每个 Agent 可以:
        - subscribe(topic, handler) 订阅主题
        - publish(msg) 发布消息
        - send_direct(recipient, msg) 点对点发送
    """

    def __init__(self):
        self._subscriptions: Dict[str, List[Callable[[AgentMessage], Any]]] = {}
        self._queues: Dict[str, asyncio.Queue] = {}  # per-agent 队列
        self._lock = asyncio.Lock()

    async def subscribe(self, topic: str, handler: Callable[[AgentMessage], Any]) -> None:
        """订阅主题"""
        async with self._lock:
            self._subscriptions.setdefault(topic, []).append(handler)
        logger.debug("消息总线: 订阅 topic=%s", topic)

    async def unsubscribe(self, topic: str, handler: Callable[[AgentMessage], Any]) -> None:
        """取消订阅"""
        async with self._lock:
            if topic in self._subscriptions:
                self._subscriptions[topic] = [h for h in self._subscriptions[topic] if h != handler]

    async def publish(self, msg: AgentMessage) -> None:
        """发布消息到主题（广播）"""
        handlers: List[Callable] = []
        async with self._lock:
            handlers = list(self._subscriptions.get(msg.topic, []))

        if not handlers:
            logger.warning("消息总线: topic=%s 无订阅者", msg.topic)
            return

        # 并发调用所有订阅者
        tasks = []
        for handler in handlers:
            if asyncio.iscoroutinefunction(handler):
                tasks.append(asyncio.create_task(handler(msg)))
            else:
                handler(msg)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def register_agent(self, agent_id: str) -> asyncio.Queue:
        """为 Agent 注册点对点接收队列"""
        async with self._lock:
            if agent_id not in self._queues:
                self._queues[agent_id] = asyncio.Queue()
        return self._queues[agent_id]

    async def send_direct(self, recipient: str, msg: AgentMessage) -> None:
        """点对点发送消息"""
        async with self._lock:
            queue = self._queues.get(recipient)
        if queue:
            await queue.put(msg)
        else:
            logger.warning("消息总线: Agent '%s' 未注册，消息丢弃", recipient)

    async def get_queue(self, agent_id: str) -> Optional[asyncio.Queue]:
        """获取 Agent 的接收队列"""
        async with self._lock:
            return self._queues.get(agent_id)

    async def drain(self) -> None:
        """清空所有队列"""
        async with self._lock:
            for q in self._queues.values():
                while not q.empty():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        break
