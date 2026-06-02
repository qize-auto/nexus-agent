"""
NexusAgent v4.0+ — Persona Engine [MIROFISH-INSPIRED]

基于 MiroFish 的 OasisProfileGenerator 理念：
    - 每个 Agent 有深度人设（MBTI、年龄、职业、兴趣、行为模式）
    - 人设影响 Agent 的协作风格（沟通方式、决策偏好、响应速度）
    - 人设用于差异化 Agent 行为，避免"千篇一律"

来源: MiroFish backend/app/services/oasis_profile_generator.py
      OasisAgentProfile 数据结构 + LLM 增强人设生成
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentPersona:
    """Agent 深度人设 — 基于 MiroFish OasisAgentProfile"""

    agent_id: str
    name: str
    role: str = "generalist"

    # 人格特征
    mbti: str = "INTJ"  # 16种 MBTI 类型
    age: Optional[int] = None
    gender: Optional[str] = None
    country: Optional[str] = None
    profession: Optional[str] = None

    # 行为模式
    bio: str = ""  # 个人简介
    persona: str = ""  # 角色设定描述
    interested_topics: List[str] = field(default_factory=list)

    # 协作风格 (0-1)
    proactivity: float = 0.5       # 主动性：高=主动发言/提建议
    detail_orientation: float = 0.5  # 细节导向：高=关注细节/严谨
    risk_tolerance: float = 0.5    # 风险承受：高=愿意尝试新方法
    consensus_seeking: float = 0.5  # 共识追求：高=倾向于达成一致

    # 社交属性
    influence_weight: float = 1.0  # 影响力权重（决定发言被采纳概率）
    friendliness: float = 0.5      # 友好度
    argumentativeness: float = 0.3  # 争辩倾向

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "mbti": self.mbti,
            "age": self.age,
            "gender": self.gender,
            "country": self.country,
            "profession": self.profession,
            "bio": self.bio,
            "persona": self.persona,
            "interested_topics": self.interested_topics,
            "proactivity": self.proactivity,
            "detail_orientation": self.detail_orientation,
            "risk_tolerance": self.risk_tolerance,
            "consensus_seeking": self.consensus_seeking,
            "influence_weight": self.influence_weight,
            "friendliness": self.friendliness,
            "argumentativeness": self.argumentativeness,
        }


class PersonaEngine:
    """
    Agent 人设生成引擎

    Usage:
        engine = PersonaEngine()
        persona = engine.generate("researcher", "张三")
        # 或从角色描述生成
        persona = engine.generate_from_description("market_analyst", "深度市场分析师，擅长数据挖掘")
    """

    _MBTI_TYPES = [
        "INTJ", "INTP", "ENTJ", "ENTP",
        "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ",
        "ISTP", "ISFP", "ESTP", "ESFP",
    ]

    _COUNTRIES = ["China", "US", "UK", "Japan", "Germany", "France", "Canada"]

    # 角色 → 默认协作风格映射
    _ROLE_STYLES: Dict[str, Dict[str, float]] = {
        "researcher": {"proactivity": 0.7, "detail_orientation": 0.9, "risk_tolerance": 0.4, "consensus_seeking": 0.6},
        "analyst": {"proactivity": 0.6, "detail_orientation": 0.95, "risk_tolerance": 0.3, "consensus_seeking": 0.7},
        "writer": {"proactivity": 0.8, "detail_orientation": 0.6, "risk_tolerance": 0.6, "consensus_seeking": 0.5},
        "critic": {"proactivity": 0.5, "detail_orientation": 0.8, "risk_tolerance": 0.3, "consensus_seeking": 0.4},
        "coordinator": {"proactivity": 0.9, "detail_orientation": 0.5, "risk_tolerance": 0.5, "consensus_seeking": 0.9},
        "creative": {"proactivity": 0.85, "detail_orientation": 0.4, "risk_tolerance": 0.8, "consensus_seeking": 0.4},
    }

    def generate(
        self,
        role: str,
        name: str,
        agent_id: str = "",
        custom_traits: Optional[Dict[str, Any]] = None,
    ) -> AgentPersona:
        """生成 Agent 人设"""
        role_lower = role.lower()
        base_style = self._ROLE_STYLES.get(role_lower, {})

        # 根据角色生成默认 bio 和 persona
        bio, persona = self._generate_bio_and_persona(role, name)

        persona_data = {
            "agent_id": agent_id or f"agent_{random.randint(1000, 9999)}",
            "name": name,
            "role": role,
            "mbti": random.choice(self._MBTI_TYPES),
            "age": random.randint(22, 55),
            "gender": random.choice(["male", "female", None]),
            "country": random.choice(self._COUNTRIES),
            "profession": role,
            "bio": bio,
            "persona": persona,
            "interested_topics": self._generate_interested_topics(role),
            "proactivity": base_style.get("proactivity", 0.5),
            "detail_orientation": base_style.get("detail_orientation", 0.5),
            "risk_tolerance": base_style.get("risk_tolerance", 0.5),
            "consensus_seeking": base_style.get("consensus_seeking", 0.5),
            "influence_weight": round(random.uniform(0.8, 1.5), 2),
            "friendliness": round(random.uniform(0.3, 0.8), 2),
            "argumentativeness": round(random.uniform(0.1, 0.6), 2),
        }

        if custom_traits:
            persona_data.update(custom_traits)

        return AgentPersona(**persona_data)

    def generate_batch(
        self,
        role_name_pairs: List[tuple],
    ) -> List[AgentPersona]:
        """批量生成人设"""
        return [
            self.generate(role, name, agent_id=f"agent_{i}")
            for i, (role, name) in enumerate(role_name_pairs)
        ]

    def _generate_bio_and_persona(self, role: str, name: str) -> tuple:
        """根据角色生成 bio 和 persona 描述"""
        templates = {
            "researcher": (
                f"{name} 是一位资深研究员，擅长通过数据驱动的方法发现问题本质。",
                f"{name} 在研究中总是追根溯源，不轻易接受表面结论。喜欢在讨论中提出尖锐但有建设性的问题。",
            ),
            "analyst": (
                f"{name} 是一位数据分析师，对数字极其敏感，能从复杂数据中发现规律。",
                f"{name} 的分析风格严谨细致，倾向于用数据说话。在团队协作中经常扮演'数据守门人'的角色。",
            ),
            "writer": (
                f"{name} 是一位内容创作者，善于将复杂概念转化为易懂的表达。",
                f"{name} 的写作风格生动有趣，能够在保持准确性的同时增强可读性。乐于接受反馈并快速迭代。",
            ),
            "critic": (
                f"{name} 是一位批判性思维专家，善于发现方案中的漏洞和风险。",
                f"{name} 在团队中扮演'魔鬼代言人'角色，专门挑战假设和寻找盲点。虽然有时让人不舒服，但能显著提升方案质量。",
            ),
            "coordinator": (
                f"{name} 是一位团队协调者，擅长整合资源和管理进度。",
                f"{name} 善于倾听各方意见，能够在冲突中找到平衡点。习惯用清晰的任务分解推动团队前进。",
            ),
            "creative": (
                f"{name} 是一位创意专家，思维跳跃，常能提出出人意料的解决方案。",
                f"{name} 喜欢在自由讨论中激发灵感，不拘泥于传统方法。有时想法过于激进，需要分析师帮助落地。",
            ),
        }
        return templates.get(role.lower(), (
            f"{name} 是一位多才多艺的专业人士。",
            f"{name} 在团队中能够灵活适应各种角色，是可靠的协作者。",
        ))

    def _generate_interested_topics(self, role: str) -> List[str]:
        """根据角色生成兴趣话题"""
        topic_map = {
            "researcher": ["数据科学", "机器学习", "学术前沿", "实验设计"],
            "analyst": ["财务报表", "市场趋势", "统计建模", "风险评估"],
            "writer": ["内容策略", "叙事技巧", "读者心理", "SEO优化"],
            "critic": ["逻辑谬误", "认知偏差", "风险管理", "质量控制"],
            "coordinator": ["项目管理", "团队动力学", "沟通技巧", "流程优化"],
            "creative": ["设计思维", "跨界创新", "用户体验", "视觉表达"],
        }
        topics = topic_map.get(role.lower(), ["通用知识"])
        # 随机选择 2-3 个
        count = min(random.randint(2, 3), len(topics))
        return random.sample(topics, count)
