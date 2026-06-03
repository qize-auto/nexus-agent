"""
NexusAgent v4.0+ — Mode Switch 模式切换检测器

职责:
    1. 自动检测用户输入是否应触发严格模式（任务型请求）
    2. 支持手动强制切换（strict / chat）
    3. 提供置信度分数，不触发误判

设计原则:
    - 快速: 纯规则检测，不调用 LLM（避免误判 + 节省 token）
    - 保守: 宁可漏判（闲聊当任务）也不误判（任务当闲聊）
    - 可覆盖: 手动开关优先级高于自动检测
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

logger = logging.getLogger("nexus.execution.mode_switch")


class ExecutionMode(str, Enum):
    """执行模式枚举"""
    AUTO = "auto"       # 自动检测（默认）
    STRICT = "strict"   # 强制严格模式
    CHAT = "chat"       # 强制闲聊模式


@dataclass
class ModeDetectionResult:
    """模式检测结果"""
    mode: ExecutionMode
    confidence: float           # 0.0-1.0，检测置信度
    reason: str                 # 决策理由
    is_task: bool               # 是否判定为任务请求
    suggested_mode: str         # "strict" | "chat"

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "is_task": self.is_task,
            "suggested_mode": self.suggested_mode,
        }


class StrictModeDetector:
    """
    严格模式检测器

    检测逻辑（优先级从高到低）:
        1. 手动强制模式（STRICT/CHAT）→ 直接返回
        2. 闲聊关键词命中 → CHAT
        3. 任务关键词命中 → STRICT
        4. 结构特征检测（文件路径、代码片段等）→ STRICT
        5. 默认 → CHAT（保守策略）
    """

    # ── 闲聊关键词（命中则强制不触发严格模式）──
    CHAT_KEYWORDS: List[str] = [
        "你好", "您好", "嗨", "hello", "hi",
        "谢谢", "感谢", "不客气",
        "再见", "拜拜", "bye",
        "哈哈", "嘿嘿", "嘻嘻",
        "今天", "昨天", "明天",
        "天气", "温度", "下雨",
        "新闻", "热点", "八卦", "娱乐",
        "你觉得", "你怎么看", "为什么", "怎么办",
        "推荐", "建议", "想法",
        "吃饭", "睡觉", "玩", "游戏",
        "多少钱", "价格", "贵不贵",
        "介绍一下", "讲讲", "说说",
    ]

    # ── 任务关键词（命中则倾向触发严格模式）──
    TASK_KEYWORDS: List[str] = [
        "帮我", "帮我写", "帮我改", "帮我做", "帮我查",
        "实现", "添加", "新增", "创建", "插入",
        "修改", "编辑", "更新", "调整", "改动",
        "删除", "移除", "清理", "干掉",
        "重构", "重写", "优化", "改进", "提升",
        "修复", "解决", "bug", "错误", "异常",
        "升级", "迁移", "转换", "适配",
        "部署", "发布", "上线", "配置",
        "写一个", "创建一个", "生成一个", "构建一个",
        "设计", "规划", "搭建", "架构",
        "测试", "验证", "检查", "确认",
        "跑一下", "执行", "运行", "启动",
        "分析", "统计", "计算", "汇总",
        "导出", "导入", "备份", "恢复",
        "合并", "拆分", "整理", "归类",
        "对比一下", "比较", "diff",
        "查一下", "搜索", "找", "定位",
        "解释一下", "说明", "文档",
    ]

    # ── 强任务信号（正则匹配，命中直接判定为任务）──
    TASK_PATTERNS: List[re.Pattern] = [
        re.compile(r"[\w/]+\.(py|js|ts|java|go|rs|cpp|c|h|yaml|yml|json|md|txt|sql)\b"),
        re.compile(r"\b(def |class |function |const |let |var |import |from |package |module)\b"),
        re.compile(r"\b(git |docker |npm |pip |pytest |python |node |bash |sh )\b"),
        re.compile(r"\b(README|CHANGELOG|LICENSE|Makefile|Dockerfile|docker-compose)\b"),
    ]

    # ── 闲聊强信号（命中直接判定为闲聊）──
    CHAT_PATTERNS: List[re.Pattern] = [
        re.compile(r"^(你好|您好|嗨|hello|hi)[!！]?$", re.I),
        re.compile(r"^(谢谢|感谢)[!！]?$"),
        re.compile(r"^(再见|拜拜|bye)[!！]?$"),
        re.compile(r"^(哈哈|嘿嘿|嘻嘻).*$"),
    ]

    def __init__(self):
        self._manual_mode: Optional[ExecutionMode] = None

    def set_manual_mode(self, mode: ExecutionMode) -> None:
        """手动设置模式（优先级最高）"""
        self._manual_mode = mode
        logger.info("手动模式切换: %s", mode.value)

    def clear_manual_mode(self) -> None:
        """清除手动模式，恢复自动检测"""
        self._manual_mode = None
        logger.info("手动模式已清除，恢复自动检测")

    def detect(self, user_message: str) -> ModeDetectionResult:
        """
        检测当前消息应使用的执行模式

        Args:
            user_message: 用户输入消息

        Returns:
            ModeDetectionResult
        """
        # 1. 手动强制模式
        if self._manual_mode == ExecutionMode.STRICT:
            return ModeDetectionResult(
                mode=ExecutionMode.STRICT,
                confidence=1.0,
                reason="手动强制严格模式",
                is_task=True,
                suggested_mode="strict",
            )
        if self._manual_mode == ExecutionMode.CHAT:
            return ModeDetectionResult(
                mode=ExecutionMode.CHAT,
                confidence=1.0,
                reason="手动强制闲聊模式",
                is_task=False,
                suggested_mode="chat",
            )

        # 2. 空消息
        msg = user_message.strip()
        if not msg:
            return ModeDetectionResult(
                mode=ExecutionMode.CHAT,
                confidence=0.9,
                reason="空消息",
                is_task=False,
                suggested_mode="chat",
            )

        msg_lower = msg.lower()

        # 3. 闲聊强信号
        for pattern in self.CHAT_PATTERNS:
            if pattern.match(msg):
                return ModeDetectionResult(
                    mode=ExecutionMode.CHAT,
                    confidence=0.95,
                    reason="闲聊强信号匹配",
                    is_task=False,
                    suggested_mode="chat",
                )

        # 4. 强任务信号（正则）
        for pattern in self.TASK_PATTERNS:
            if pattern.search(msg):
                return ModeDetectionResult(
                    mode=ExecutionMode.STRICT,
                    confidence=0.9,
                    reason="强任务信号（文件/代码/命令匹配）",
                    is_task=True,
                    suggested_mode="strict",
                )

        # 5. 关键词计分
        task_score = sum(1 for kw in self.TASK_KEYWORDS if kw in msg_lower)
        chat_score = sum(1 for kw in self.CHAT_KEYWORDS if kw in msg_lower)

        # 6. 决策
        if chat_score > 0 and task_score == 0:
            return ModeDetectionResult(
                mode=ExecutionMode.CHAT,
                confidence=min(0.5 + chat_score * 0.1, 0.9),
                reason="闲聊关键词命中",
                is_task=False,
                suggested_mode="chat",
            )

        if task_score > 0:
            # 有任务关键词但无闲聊关键词 → 严格
            if chat_score == 0:
                return ModeDetectionResult(
                    mode=ExecutionMode.STRICT,
                    confidence=min(0.6 + task_score * 0.05, 0.85),
                    reason="任务关键词命中",
                    is_task=True,
                    suggested_mode="strict",
                )
            # 同时有任务和闲聊关键词 → 比较分数（任务优先，相同时也优先任务）
            if task_score >= chat_score:
                return ModeDetectionResult(
                    mode=ExecutionMode.STRICT,
                    confidence=min(0.55 + (task_score - chat_score) * 0.05, 0.8),
                    reason="任务关键词占优",
                    is_task=True,
                    suggested_mode="strict",
                )

        # 7. 默认：闲聊（保守策略）
        return ModeDetectionResult(
            mode=ExecutionMode.CHAT,
            confidence=0.6,
            reason="无明显任务信号，默认闲聊模式",
            is_task=False,
            suggested_mode="chat",
        )
