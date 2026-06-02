"""
NexusAgent v4.0+ — MiroFish 融合层 [MIROFISH-INSPIRED]

基于 GitHub 666ghj/MiroFish (https://github.com/666ghj/MiroFish)
—— 一个基于 OASIS 框架的多智能体社会模拟引擎。

MiroFish 核心能力：
    1. 深度 Persona 生成：每个 Agent 有 MBTI、年龄、职业、兴趣、社交媒体行为等
    2. GraphRAG 社会图谱：实体关系网络，Agent 共享结构化记忆
    3. 时间感知模拟：模拟时钟、活跃时段、响应延迟
    4. 双平台并行：多环境同时模拟
    5. 参数自动生成：LLM 根据需求自动配置

融合策略：
    将 MiroFish 的"社会模拟"理念抽象为"协作预演"——
    在任务执行前，Agent 在虚拟协作空间进行一轮轻量级预演模拟，
    通过模拟发现最优协作路径，然后执行。
"""

from .persona_engine import PersonaEngine, AgentPersona
from .social_graph import SocialGraph, EntityNode, RelationEdge
from .simulation_clock import SimulationClock, TimeSlot
from .activity_config import AgentActivityConfig
from .scheduler import MiroFishScheduler, MiroFishResult

__all__ = [
    "PersonaEngine",
    "AgentPersona",
    "SocialGraph",
    "EntityNode",
    "RelationEdge",
    "SimulationClock",
    "TimeSlot",
    "AgentActivityConfig",
    "MiroFishScheduler",
    "MiroFishResult",
]
