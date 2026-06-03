"""
NexusAgent v4.0+ — Clarifier 澄清问题生成器

职责:
    1. 维护澄清会话状态（多轮对话上下文）
    2. 生成针对性的澄清问题
    3. 评估是否已获取足够信息
    4. 最多 3 轮澄清，超时降级执行

设计原则:
    - 会话有状态: 记录已澄清的信息
    - 智能合并: 将多轮回答合并为完整需求
    - 防循环: 3 轮上限，避免无限追问
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from nexusagent.execution.intent_analyzer import IntentAnalysis

logger = logging.getLogger("nexus.execution.clarifier")


@dataclass
class ClarificationSession:
    """澄清会话状态"""
    session_id: str
    original_message: str
    intent: IntentAnalysis
    rounds: List[Dict[str, Any]] = field(default_factory=list)
    merged_requirements: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    max_rounds: int = 3
    is_complete: bool = False

    @property
    def current_round(self) -> int:
        return len(self.rounds)

    @property
    def can_continue(self) -> bool:
        return self.current_round < self.max_rounds and not self.is_complete

    def add_round(self, question: str, answer: str) -> None:
        self.rounds.append({
            "round": self.current_round + 1,
            "question": question,
            "answer": answer,
            "timestamp": time.time(),
        })

    def get_context(self) -> str:
        """获取完整对话上下文"""
        lines = [f"原始请求: {self.original_message}"]
        for r in self.rounds:
            lines.append(f"Q{r['round']}: {r['question']}")
            lines.append(f"A{r['round']}: {r['answer']}")
        return "\n".join(lines)


class Clarifier:
    """
    澄清问题管理器

    Usage:
        clarifier = Clarifier()
        session = clarifier.start_session(user_msg, intent_analysis)

        # 第一轮
        question = clarifier.generate_question(session)
        # ... 用户回答 ...
        clarifier.receive_answer(session, answer)

        if clarifier.is_clear_enough(session):
            requirements = clarifier.merge_requirements(session)
    """

    def __init__(self, llm_backend: Optional[Any] = None):
        self._llm = llm_backend
        self._sessions: Dict[str, ClarificationSession] = {}

    def start_session(self, session_id: str, original_message: str, intent: IntentAnalysis) -> ClarificationSession:
        """启动新的澄清会话"""
        session = ClarificationSession(
            session_id=session_id,
            original_message=original_message,
            intent=intent,
        )
        self._sessions[session_id] = session
        logger.info("澄清会话启动: %s (ambiguity=%.2f)", session_id, intent.ambiguity_score)
        return session

    def get_session(self, session_id: str) -> Optional[ClarificationSession]:
        """获取会话"""
        return self._sessions.get(session_id)

    async def generate_question(self, session: ClarificationSession) -> str:
        """
        生成下一轮澄清问题

        策略:
            1. 优先使用 intent 中建议的问题
            2. 已问过的问题不再重复
            3. 如果所有问题都问完了，生成通用问题
        """
        if not session.can_continue:
            return ""

        # 收集已问过的问题
        asked = {r["question"] for r in session.rounds}

        # 从 intent 的建议问题中找未问过的
        for q in session.intent.suggested_questions:
            if q not in asked:
                return q

        # 根据已收集的信息生成新问题
        if self._llm:
            try:
                return await self._llm_generate_question(session)
            except Exception as e:
                logger.debug("LLM 问题生成失败: %s", e)

        # 兜底：通用问题
        return self._fallback_question(session)

    def receive_answer(self, session: ClarificationSession, answer: str) -> None:
        """接收用户回答"""
        # 获取本轮的问题
        if session.rounds:
            last_question = session.rounds[-1]["question"]
        else:
            last_question = "（初始请求）"

        session.add_round(last_question, answer)
        logger.debug("澄清会话 %s 第 %d 轮完成", session.session_id, session.current_round)

        # 尝试评估是否已足够明确
        if self._evaluate_clarity(session):
            session.is_complete = True
            logger.info("澄清会话 %s 已完成（%d 轮）", session.session_id, session.current_round)

    def is_clear_enough(self, session: ClarificationSession) -> bool:
        """判断是否已足够明确"""
        if session.is_complete:
            return True

        # 如果没有缺失信息，且模糊度低
        if not session.intent.missing_info and session.intent.ambiguity_score < 0.3:
            return True

        # 如果已经超过最大轮数
        if session.current_round >= session.max_rounds:
            logger.warning("澄清会话 %s 达到最大轮数，强制结束", session.session_id)
            session.is_complete = True
            return True

        return False

    def merge_requirements(self, session: ClarificationSession) -> Dict[str, Any]:
        """
        将所有澄清轮次合并为完整需求

        返回:
            {
                "original": "原始请求",
                "clarifications": [{"question": "...", "answer": "..."}],
                "merged_goal": "合并后的明确目标",
                "target_files": [...],
                "constraints": [...],
            }
        """
        result = {
            "original": session.original_message,
            "clarifications": [
                {"question": r["question"], "answer": r["answer"]}
                for r in session.rounds
            ],
            "target_files": session.intent.target_files,
            "target_modules": session.intent.target_modules,
            "task_type": session.intent.task_type,
        }

        # 合并目标描述
        parts = [session.original_message]
        for r in session.rounds:
            parts.append(f"（澄清: {r['question']} → {r['answer']}）")
        result["merged_goal"] = " ".join(parts)

        # 提取约束条件
        constraints = []
        for r in session.rounds:
            ans = r["answer"].lower()
            if "不要" in ans or "不能" in ans or "禁止" in ans:
                constraints.append(r["answer"])
            if "必须" in ans or "一定要" in ans or "务必" in ans:
                constraints.append(r["answer"])
        result["constraints"] = constraints

        session.merged_requirements = result
        return result

    def end_session(self, session_id: str) -> Optional[ClarificationSession]:
        """结束会话"""
        return self._sessions.pop(session_id, None)

    # ── 内部方法 ──

    def _evaluate_clarity(self, session: ClarificationSession) -> bool:
        """评估当前会话的明确程度"""
        # 简单规则：如果有文件路径回答，且回答了所有缺失信息
        for r in session.rounds:
            ans = r["answer"]
            # 如果回答中包含文件路径
            if "/" in ans or "\\" in ans or ".py" in ans:
                return True
            # 如果回答明确且具体（超过 10 个字）
            if len(ans) > 10 and "不知道" not in ans and "随便" not in ans:
                # 检查是否覆盖了所有 missing_info
                if session.current_round >= len(session.intent.missing_info):
                    return True

        return False

    async def _llm_generate_question(self, session: ClarificationSession) -> str:
        """使用 LLM 生成问题"""
        context = session.get_context()
        prompt = f"""基于以下对话上下文，请生成一个最关键的澄清问题，帮助我们理解用户的真实需求。

{context}

已澄清 {session.current_round}/{session.max_rounds} 轮。

请只回复一个问题，不要添加任何其他内容。"""

        response = await self._llm.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return response.get("content", "").strip().split("\n")[0]

    def _fallback_question(self, session: ClarificationSession) -> str:
        """兜底问题生成"""
        fallbacks = [
            "能否请您提供更具体的要求？比如涉及哪些文件、需要达到什么效果？",
            "为了更准确地帮您完成，能否补充一些背景信息或约束条件？",
            "您能否给出一个具体的示例或期望的输出格式？",
        ]
        idx = min(session.current_round, len(fallbacks) - 1)
        return fallbacks[idx]
