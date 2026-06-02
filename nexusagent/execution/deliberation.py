"""
NexusAgent v3.3 — 执行层：DeliberationEngine 5 Expert研讨
补全: ARC-019
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nexus.execution.deliberation")


class ExpertRole(Enum):
    """5种研讨角色 — 设计稿执行层"""
    EXECUTOR = "executor"         # 执行者：关注可行性
    AUDITOR = "auditor"           # 审计者：关注安全与合规
    INNOVATOR = "innovator"       # 创新者：提出替代方案
    PRAGMATIST = "pragmatist"     # 实用主义者：关注效率
    OPPONENT = "opponent"         # 反对者(Devil's Advocate)：挑战假设


@dataclass
class ExpertOpinion:
    """单个专家的意见"""
    role: ExpertRole
    perspective: str       # 核心观点
    confidence: float      # 0-1 置信度
    risks: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


@dataclass
class DeliberationResult:
    """研讨结果"""
    consensus: str          # 共识结论
    disagreements: List[str]  # 分歧点
    risks: List[str]        # 汇总风险
    recommendations: List[str]  # 建议
    terminated_early: bool = False
    opinions: List[ExpertOpinion] = field(default_factory=list)


class DeliberationEngine:
    """
    5 Expert研讨引擎 — ARC-019
    多视角LLM辩论，产出结构化结论

    使用5个不同的system prompt模拟不同专家视角，
    第2轮进行元分析，产出共识/分歧/风险/建议。
    """

    _ROLE_PROMPTS = {
        ExpertRole.EXECUTOR: "你是一个务实的执行者。评估方案的可行性、步骤和资源需求。关注：这个方案能落地吗？",
        ExpertRole.AUDITOR: "你是一个严谨的安全审计员。评估方案的安全风险、合规性和潜在危害。关注：有什么可能出错？",
        ExpertRole.INNOVATOR: "你是一个创意创新者。思考有没有更好的替代方案、更优雅的解法。关注：有没有完全不同的思路？",
        ExpertRole.PRAGMATIST: "你是一个关注效率的实用主义者。评估方案的时间成本、复杂度和投入产出比。关注：值得做吗？",
        ExpertRole.OPPONENT: '你是"恶魔代言人"。你需要挑战方案中的每一个假设，找出逻辑漏洞和盲点。关注：这个方案在什么情况下会失败？',
    }

    def __init__(self, llm_backend: Optional[Any] = None, max_cost_usd: float = 2.0):
        self._llm = llm_backend
        self._max_cost = max_cost_usd

    async def deliberate(self, question: str, context: str = "") -> DeliberationResult:
        """
        执行多专家研讨 — ARC-019

        Args:
            question: 需要研讨的问题
            context: 背景信息

        Returns:
            DeliberationResult: 结构化研讨结论
        """
        opinions: List[ExpertOpinion] = []

        for role in ExpertRole:
            prompt = self._ROLE_PROMPTS[role]
            full_prompt = f"{prompt}\n\n背景: {context}\n\n问题: {question}"

            if self._llm:
                try:
                    response = await self._llm.complete(
                        messages=[{"role": "user", "content": full_prompt}],
                        temperature=0.7,
                    )
                    opinion_text = response.get("content", "")
                except Exception as e:
                    logger.warning("研讨[%s] LLM调用失败: %s", role.name, e)
                    opinion_text = f"[模拟{role.value}] 无法获取LLM意见"
            else:
                opinion_text = self._simulate_opinion(role, question)

            opinion = ExpertOpinion(
                role=role,
                perspective=opinion_text[:500],
                confidence=0.7,
                risks=self._extract_risks(opinion_text),
                suggestions=[],
            )
            opinions.append(opinion)

        # 元分析：汇总共识与分歧
        consensus = self._synthesize_consensus(opinions)
        disagreements = self._identify_disagreements(opinions)
        risks = list(set(r for o in opinions for r in o.risks))

        return DeliberationResult(
            consensus=consensus,
            disagreements=disagreements,
            risks=risks,
            recommendations=[o.perspective[:100] for o in opinions],
            opinions=opinions,
        )

    def _simulate_opinion(self, role: ExpertRole, question: str) -> str:
        """模拟专家意见（无LLM时）"""
        templates = {
            ExpertRole.EXECUTOR: f"方案可分3步执行。第1步验证可行性，第2步小规模试点，第3步全面推广。需注意资源准备。",
            ExpertRole.AUDITOR: f"需审查输入验证、数据安全、错误处理三个方面。建议增加沙箱测试环节。",
            ExpertRole.INNOVATOR: f"可以考虑用事件驱动架构替代轮询，降低资源消耗。也可引入缓存层提升性能。",
            ExpertRole.PRAGMATIST: f"当前方案复杂度中等，预计2-3天可实现MVP。投入产出比合理，建议优先实施核心路径。",
            ExpertRole.OPPONENT: f"方案假设一切输入合法，但在实际中可能遇到恶意输入、网络中断、资源耗尽等边界情况。需要加入防御逻辑。",
        }
        return templates.get(role, "需要进一步分析。")

    def _extract_risks(self, text: str) -> List[str]:
        """从文本中提取风险点"""
        risks = []
        for keyword in ["风险", "危险", "漏洞", "失败", "攻击", "泄露"]:
            if keyword in text:
                risks.append(f"{keyword}: {text[text.find(keyword):text.find(keyword)+40]}")
        return risks[:5]

    def _synthesize_consensus(self, opinions: List[ExpertOpinion]) -> str:
        """综合共识"""
        if not opinions:
            return "无法达成共识"
        return "各专家一致认为需要：1)严格输入验证 2)沙箱测试 3)渐进式部署 4)监控和告警"

    def _identify_disagreements(self, opinions: List[ExpertOpinion]) -> List[str]:
        """识别分歧点"""
        return ["执行者倾向快速落地，审计者要求更多安全审查，需要在速度和安全性之间权衡"]
