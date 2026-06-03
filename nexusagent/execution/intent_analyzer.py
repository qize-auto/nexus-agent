"""
NexusAgent v4.0+ — Intent Analyzer 意图分析器

职责:
    1. 深度分析用户意图（模糊度、目标类型、所需信息）
    2. 识别缺失的关键参数
    3. 生成澄清建议问题

设计原则:
    - 结构化输出: 必须返回标准格式的 JSON
    - 不依赖 LLM 时也能工作: 规则兜底
    - 快速: 优先规则检测，复杂场景才用 LLM
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nexus.execution.intent")


@dataclass
class IntentAnalysis:
    """意图分析结果"""
    is_task: bool = False
    ambiguity_score: float = 0.0      # 0.0=明确, 1.0=完全模糊
    task_type: str = ""               # coding | refactoring | debugging | analysis | config | other
    missing_info: List[str] = field(default_factory=list)
    suggested_questions: List[str] = field(default_factory=list)
    target_files: List[str] = field(default_factory=list)
    target_modules: List[str] = field(default_factory=list)
    confidence: float = 0.5

    def is_clear_enough(self, threshold: float = 0.3) -> bool:
        """判断是否足够明确（模糊度低于阈值）"""
        return self.ambiguity_score <= threshold and not self.missing_info

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_task": self.is_task,
            "ambiguity_score": self.ambiguity_score,
            "task_type": self.task_type,
            "missing_info": self.missing_info,
            "suggested_questions": self.suggested_questions,
            "target_files": self.target_files,
            "target_modules": self.target_modules,
            "confidence": self.confidence,
        }


class IntentAnalyzer:
    """
    意图分析器

    两阶段分析:
        1. 规则快速检测（无 LLM）— 检测文件路径、代码特征等
        2. LLM 深度分析（可选）— 生成结构化 JSON
    """

    # 文件路径正则（使用非捕获组避免 findall 返回元组）
    FILE_PATTERN = re.compile(
        r"(?:[\w\-]+/)*[\w\-]+\.(?:py|js|ts|java|go|rs|cpp|c|h|yaml|yml|json|md|txt|sql|html|css|sh)",
        re.I,
    )

    # 模块路径正则
    MODULE_PATTERN = re.compile(
        r"([a-z_][a-z0-9_]*\.)+[a-z_][a-z0-9_]*",
        re.I,
    )

    # 模糊信号词
    AMBIGUITY_SIGNALS = [
        "一下", "一下下", "一下就好",
        "稍微", "略微", "稍微改",
        "优化", "改进", "提升性能",
        "好看", "美观", "漂亮",
        "好用", "方便", "顺手",
        "差不多", "大概", "可能",
        "随便", "看着办", "你定",
    ]

    # 任务类型关键词映射
    TASK_TYPE_KEYWORDS = {
        "coding": ["写", "创建", "添加", "实现", "新增", "插入", "定义"],
        "refactoring": ["重构", "重写", "整理", "拆分", "合并", "解耦"],
        "debugging": ["修复", "解决", "bug", "错误", "异常", "崩溃", "报错"],
        "analysis": ["分析", "检查", "查看", "排查", "诊断", "评估"],
        "config": ["配置", "设置", "部署", "环境", "变量", "参数"],
        "testing": ["测试", "验证", "断言", "覆盖率", "单元测试"],
        "documentation": ["文档", "注释", "说明", "README", "CHANGELOG"],
    }

    def __init__(self, llm_backend: Optional[Any] = None):
        self._llm = llm_backend

    async def analyze(self, user_message: str) -> IntentAnalysis:
        """
        分析用户意图

        先走规则快速路径，如果规则无法确定再尝试 LLM（如可用）
        """
        # 1. 规则分析
        result = self._rule_based_analysis(user_message)

        # 2. 如果规则结果置信度低且有 LLM，尝试 LLM 增强
        if result.confidence < 0.7 and self._llm:
            try:
                llm_result = await self._llm_enhanced_analysis(user_message)
                if llm_result:
                    # 合并：LLM 的 missing_info 和 suggested_questions 优先
                    result.missing_info = llm_result.missing_info or result.missing_info
                    result.suggested_questions = llm_result.suggested_questions or result.suggested_questions
                    result.ambiguity_score = llm_result.ambiguity_score
                    result.confidence = max(result.confidence, llm_result.confidence)
            except Exception as e:
                logger.debug("LLM 意图分析失败: %s", e)

        return result

    # 聊天关键词（命中则判定为非任务）
    CHAT_KEYWORDS = [
        "你好", "您好", "嗨", "hello", "hi",
        "谢谢", "感谢", "再见", "拜拜", "bye",
        "哈哈", "嘿嘿", "嘻嘻",
        "今天", "昨天", "明天", "天气", "温度", "下雨",
        "新闻", "热点", "八卦", "娱乐",
        "你觉得", "你怎么看", "为什么", "怎么办",
        "推荐", "建议", "想法",
        "吃饭", "睡觉", "玩", "游戏",
        "多少钱", "价格", "贵不贵",
        "介绍一下", "讲讲", "说说",
    ]

    def _rule_based_analysis(self, user_message: str) -> IntentAnalysis:
        """基于规则的分析（无 LLM）"""
        msg = user_message.strip()
        msg_lower = msg.lower()

        # 空消息 → 非任务
        if not msg:
            return IntentAnalysis(is_task=False, confidence=1.0)

        # 聊天关键词检测 → 非任务
        chat_score = sum(1 for kw in self.CHAT_KEYWORDS if kw in msg_lower)
        if chat_score > 0 and len(msg) < 30:
            return IntentAnalysis(is_task=False, confidence=0.8, ambiguity_score=0.0)

        result = IntentAnalysis(is_task=True, confidence=0.5)

        # 提取文件路径
        file_matches = self.FILE_PATTERN.findall(msg)
        result.target_files = [
            (m[0] if isinstance(m, tuple) else m)
            for m in file_matches
            if (m[0] if isinstance(m, tuple) else m)
        ]

        # 提取模块路径
        module_matches = self.MODULE_PATTERN.findall(msg)
        result.target_modules = [m for m in module_matches if m]

        # 检测任务类型（按优先级顺序，避免 coding 覆盖 testing）
        type_scores = {}
        for task_type, keywords in self.TASK_TYPE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in msg_lower)
            if score > 0:
                type_scores[task_type] = score
        if type_scores:
            # testing 优先级高于 coding
            priority = ["testing", "debugging", "refactoring", "config", "documentation", "analysis", "coding"]
            for t in priority:
                if t in type_scores:
                    result.task_type = t
                    break
            if not result.task_type:
                result.task_type = max(type_scores, key=type_scores.get)

        # 计算模糊度
        ambiguity_signals = sum(1 for sig in self.AMBIGUITY_SIGNALS if sig in msg_lower)
        has_file = len(result.target_files) > 0
        has_module = len(result.target_modules) > 0

        # 模糊度计算
        if has_file or has_module:
            base_ambiguity = 0.2
        else:
            base_ambiguity = 0.5

        result.ambiguity_score = min(base_ambiguity + ambiguity_signals * 0.15, 1.0)

        # 识别缺失信息
        missing = []

        if not has_file and not has_module and result.task_type in ("coding", "refactoring", "debugging"):
            missing.append("目标文件路径或模块名")

        if ambiguity_signals > 0:
            missing.append("具体的修改范围或标准")

        if not result.task_type:
            missing.append("具体的操作类型（添加/修改/删除/查询）")

        result.missing_info = missing

        # 生成建议问题
        questions = self._generate_questions(result, msg)
        result.suggested_questions = questions

        # 调整置信度
        if not missing and result.ambiguity_score < 0.3:
            result.confidence = 0.9
        elif len(missing) <= 1:
            result.confidence = 0.7
        else:
            result.confidence = 0.5

        return result

    def _generate_questions(self, analysis: IntentAnalysis, original_msg: str) -> List[str]:
        """基于缺失信息生成澄清问题"""
        questions = []

        for missing in analysis.missing_info:
            if "文件路径" in missing:
                questions.append("您想修改哪个文件？请提供文件路径。")
            elif "模块名" in missing:
                questions.append("您指的是哪个模块？请提供模块路径。")
            elif "修改范围" in missing or "标准" in missing:
                questions.append("您希望修改到什么程度？能否给出一个具体的标准或示例？")
            elif "操作类型" in missing:
                questions.append("您希望我执行什么操作？（添加功能 / 修改现有代码 / 删除 / 查询信息）")
            else:
                questions.append(f"关于『{missing}』，能否请您补充说明？")

        # 去重 + 限制数量
        seen = set()
        unique = []
        for q in questions:
            if q not in seen:
                seen.add(q)
                unique.append(q)
                if len(unique) >= 2:
                    break

        return unique

    async def _llm_enhanced_analysis(self, user_message: str) -> Optional[IntentAnalysis]:
        """使用 LLM 进行增强分析"""
        prompt = f"""你是一个需求分析专家。请分析以下用户请求，判断目标是否明确、缺少什么信息。

用户请求: {user_message}

请用 JSON 格式回复，不要添加任何其他文字:
{{
  "is_task": true/false,
  "ambiguity_score": 0.0-1.0,
  "task_type": "coding/refactoring/debugging/analysis/config/testing/documentation/other",
  "missing_info": ["缺少的信息1", "缺少的信息2"],
  "suggested_questions": ["建议的澄清问题1", "建议的澄清问题2"],
  "target_files": ["提取的文件路径"],
  "confidence": 0.0-1.0
}}
"""
        response = await self._llm.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        content = response.get("content", "")

        # 尝试提取 JSON
        try:
            # 查找 JSON 块
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                data = json.loads(json_match.group())
                return IntentAnalysis(
                    is_task=data.get("is_task", True),
                    ambiguity_score=float(data.get("ambiguity_score", 0.5)),
                    task_type=data.get("task_type", ""),
                    missing_info=data.get("missing_info", []),
                    suggested_questions=data.get("suggested_questions", []),
                    target_files=data.get("target_files", []),
                    confidence=float(data.get("confidence", 0.5)),
                )
        except Exception as e:
            logger.debug("LLM 意图分析 JSON 解析失败: %s", e)

        return None
