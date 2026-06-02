"""
NexusAgent v4.0+ — User Profiler

实时用户画像提取器。
作为中间件挂载在对话处理管道中，从每条消息、每个工具调用、每个错误反馈中提取原子偏好。

设计原则:
    - 轻量规则提取为主，LLM 深度分析仅在梦境周期执行
    - 提取结果写入 pending_traits 队列，不直接覆盖稳定画像
    - 支持显式教学 ("记住我不喜欢Docker")
    - 支持否定反馈降权 ("不，不是这样")
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nexus.cognition.user_profiler")


@dataclass
class ExtractedSignal:
    """提取到的原子偏好信号"""
    category: str           # static | dynamic | behavioral | security
    key: str                # 属性名
    value: Any              # 属性值
    confidence: float = 0.5  # 置信度 (0-1)
    source: str = "implicit"  # explicit | implicit | feedback | error
    context: str = ""       # 原始上下文片段


class UserProfiler:
    """
    用户画像实时提取器

    Usage:
        profiler = UserProfiler()
        signals = profiler.process_message(
            user_id="u1",
            message="我喜欢用Python，快点给我结果",
            agent_output="",
        )
        # signals → [tech_stack=Python, patience_index=low, ...]
    """

    # ── 技术栈关键词库 ──
    TECH_KEYWORDS: Dict[str, List[str]] = {
        "python": ["python", "py", "django", "flask", "fastapi", "pandas", "numpy"],
        "javascript": ["javascript", "js", "node.js", "nodejs", "react", "vue", "angular", "typescript", "ts"],
        "java": ["java", "spring", "springboot", "maven", "gradle"],
        "go": ["golang", "go语言"],
        "rust": ["rust", "cargo"],
        "docker": ["docker", "container", "容器"],
        "kubernetes": ["kubernetes", "k8s", "helm"],
        "sql": ["sql", "mysql", "postgresql", "sqlite", "mongodb", "redis"],
        "cloud": ["aws", "azure", "gcp", "阿里云", "腾讯云", "华为云"],
    }

    # ── 情绪/耐心信号词 ──
    PATIENCE_LOW = [
        "快点", " hurry", "立刻", "马上", " asap", "赶紧", "不耐烦",
        "太慢了", "太慢", "浪费时间", "效率太低",
    ]
    PATIENCE_HIGH = [
        "慢慢来", "不着急", "仔细", "详细", " thorough", "慢慢说",
        "深入", "全面", "完整",
    ]

    MOOD_POSITIVE = [
        "谢谢", "感谢", "不错", "很好", "完美", " awesome", " great",
        " helpful", " useful", " brilliant",
    ]
    MOOD_NEGATIVE = [
        "不好", "错了", "不对", "垃圾", "没用", " bad", " wrong",
        " terrible", " useless", " frustrating", " annoying",
    ]

    # ── 显式教学模式 ──
    EXPLICIT_LEARN_PATTERNS = [
        re.compile(r"记住[，,:：]?\s*我(.+)"),
        re.compile(r"记住[，,:：]?\s*(.+?)"),
        re.compile(r"我的(.+?)是(.+)"),
        re.compile(r"I\s+(?:prefer|like|enjoy|hate|dislike)\s+(.+)", re.IGNORECASE),
        re.compile(r"(?:don't|never|always)\s+(.+)", re.IGNORECASE),
    ]

    # ── 否定反馈模式 ──
    NEGATION_PATTERNS = [
        re.compile(r"不[是對对][:：,，]?\s*(.+)"),
        re.compile(r"错了[:：,，]?\s*(.+)"),
        re.compile(r"(?:not|no,)\s+(?:that'?s?\s+)?(.+)", re.IGNORECASE),
        re.compile(r"(?:wrong|incorrect)[:：,，]?\s*(.+)"),
    ]

    def __init__(self):
        self._extraction_stats: Dict[str, int] = {
            "messages_processed": 0,
            "signals_extracted": 0,
            "explicit_learn": 0,
            "negation_feedback": 0,
        }

    def process_message(
        self,
        user_id: str,
        message: str,
        agent_output: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        errors: Optional[List[str]] = None,
    ) -> List[ExtractedSignal]:
        """
        处理单条用户消息，提取所有偏好信号

        Returns:
            List[ExtractedSignal]: 提取到的信号列表
        """
        signals: List[ExtractedSignal] = []
        text = message or ""

        # 1. 显式教学提取 (最高置信度)
        explicit = self._extract_explicit(text)
        signals.extend(explicit)

        # 2. 技术栈偏好提取
        tech = self._extract_tech_stack(text)
        signals.extend(tech)

        # 3. 耐心指数信号
        patience = self._extract_patience(text)
        if patience:
            signals.append(patience)

        # 4. 情绪倾向信号
        mood = self._extract_mood(text)
        if mood:
            signals.append(mood)

        # 5. 否定反馈检测
        negations = self._extract_negation(text, agent_output)
        signals.extend(negations)

        # 6. 工具调用模式
        if tool_calls:
            tool_signals = self._extract_tool_patterns(tool_calls)
            signals.extend(tool_signals)

        # 7. 错误模式
        if errors:
            error_signals = self._extract_error_patterns(errors)
            signals.extend(error_signals)

        self._extraction_stats["messages_processed"] += 1
        self._extraction_stats["signals_extracted"] += len(signals)

        return signals

    # ── 提取器实现 ──

    def _extract_explicit(self, text: str) -> List[ExtractedSignal]:
        """显式教学提取"""
        signals = []
        for pattern in self.EXPLICIT_LEARN_PATTERNS:
            match = pattern.search(text)
            if match:
                groups = match.groups()
                if len(groups) >= 2:
                    # "我的时区是北京" → key=时区, value=北京
                    key, value = groups[0].strip(), groups[1].strip()
                    signals.append(ExtractedSignal(
                        category="static",
                        key=key,
                        value=value,
                        confidence=0.95,
                        source="explicit",
                        context=text[:100],
                    ))
                elif len(groups) == 1:
                    # "记住我不喜欢Docker" → 解析为偏好
                    content = groups[0].strip()
                    # 尝试解析为 "不喜欢X" 或 "喜欢X"
                    pref_match = re.search(r"(?:不喜欢|讨厌|dislike|hate)\s+(.+)", content)
                    if pref_match:
                        signals.append(ExtractedSignal(
                            category="static",
                            key="disliked_tools",
                            value=pref_match.group(1).strip(),
                            confidence=0.95,
                            source="explicit",
                            context=text[:100],
                        ))
                    else:
                        signals.append(ExtractedSignal(
                            category="static",
                            key="preference_note",
                            value=content,
                            confidence=0.9,
                            source="explicit",
                            context=text[:100],
                        ))
                self._extraction_stats["explicit_learn"] += 1
        return signals

    def _extract_tech_stack(self, text: str) -> List[ExtractedSignal]:
        """技术栈偏好提取"""
        signals = []
        text_lower = text.lower()
        for tech, keywords in self.TECH_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text_lower:
                    # 检查是否是负面语境
                    neg_context = re.search(rf"(?:不喜欢|讨厌|不用|不用了|hate|dislike)\s*{kw}", text_lower)
                    if neg_context:
                        signals.append(ExtractedSignal(
                            category="static",
                            key="disliked_tools",
                            value=tech,
                            confidence=0.7,
                            source="implicit",
                            context=text[:80],
                        ))
                    else:
                        signals.append(ExtractedSignal(
                            category="static",
                            key="tech_stack",
                            value=tech,
                            confidence=0.6,
                            source="implicit",
                            context=text[:80],
                        ))
                    break  # 同一技术只记录一次
        return signals

    def _extract_patience(self, text: str) -> Optional[ExtractedSignal]:
        """耐心指数提取"""
        low_count = sum(1 for p in self.PATIENCE_LOW if p.lower() in text.lower())
        high_count = sum(1 for p in self.PATIENCE_HIGH if p.lower() in text.lower())

        if low_count > high_count:
            # 急躁信号更强
            return ExtractedSignal(
                category="behavioral",
                key="patience_index",
                value=max(0.0, 0.5 - 0.15 * low_count),
                confidence=min(0.9, 0.5 + 0.1 * low_count),
                source="implicit",
                context=text[:80],
            )
        elif high_count > low_count:
            return ExtractedSignal(
                category="behavioral",
                key="patience_index",
                value=min(1.0, 0.5 + 0.15 * high_count),
                confidence=min(0.9, 0.5 + 0.1 * high_count),
                source="implicit",
                context=text[:80],
            )
        return None

    def _extract_mood(self, text: str) -> Optional[ExtractedSignal]:
        """情绪倾向提取"""
        pos_count = sum(1 for w in self.MOOD_POSITIVE if w.lower() in text.lower())
        neg_count = sum(1 for w in self.MOOD_NEGATIVE if w.lower() in text.lower())

        if pos_count > neg_count and pos_count >= 1:
            return ExtractedSignal(
                category="dynamic",
                key="mood_trend",
                value="positive",
                confidence=min(0.85, 0.5 + 0.1 * pos_count),
                source="implicit",
                context=text[:80],
            )
        elif neg_count > pos_count and neg_count >= 1:
            return ExtractedSignal(
                category="dynamic",
                key="mood_trend",
                value="negative",
                confidence=min(0.85, 0.5 + 0.1 * neg_count),
                source="implicit",
                context=text[:80],
            )
        return None

    def _extract_negation(self, text: str, agent_output: Optional[str]) -> List[ExtractedSignal]:
        """否定反馈提取"""
        signals = []
        for pattern in self.NEGATION_PATTERNS:
            match = pattern.search(text)
            if match:
                correction = match.group(1).strip() if match.groups() else text
                signals.append(ExtractedSignal(
                    category="behavioral",
                    key="feedback_negative",
                    value={"correction": correction, "agent_output": (agent_output or "")[:200]},
                    confidence=0.8,
                    source="feedback",
                    context=text[:100],
                ))
                self._extraction_stats["negation_feedback"] += 1
        return signals

    def _extract_tool_patterns(self, tool_calls: List[Dict[str, Any]]) -> List[ExtractedSignal]:
        """工具调用模式提取"""
        signals = []
        tool_names = [tc.get("name", "") for tc in tool_calls]
        for name in set(tool_names):
            signals.append(ExtractedSignal(
                category="behavioral",
                key="workflow_frequency",
                value={"tool": name, "count": tool_names.count(name)},
                confidence=0.7,
                source="implicit",
                context=f"tools: {tool_names}",
            ))
        return signals

    def _extract_error_patterns(self, errors: List[str]) -> List[ExtractedSignal]:
        """错误模式提取"""
        signals = []
        for err in errors:
            # 简单分类
            category = "general"
            if "timeout" in err.lower() or "time" in err.lower():
                category = "timeout"
            elif "permission" in err.lower() or "denied" in err.lower():
                category = "permission"
            elif "not found" in err.lower():
                category = "not_found"

            signals.append(ExtractedSignal(
                category="behavioral",
                key="error_patterns",
                value={"category": category, "message": err[:200]},
                confidence=0.6,
                source="error",
                context=err[:100],
            ))
        return signals

    def get_stats(self) -> Dict[str, int]:
        return dict(self._extraction_stats)
