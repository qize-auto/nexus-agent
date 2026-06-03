"""
Tests for StrictModeDetector — 模式检测器
"""

import pytest
from nexusagent.execution.mode_switch import StrictModeDetector, ModeDetectionResult


@pytest.fixture
def detector():
    return StrictModeDetector()


class TestStrictModeDetector:
    """模式检测器测试集"""

    def test_chat_greeting(self, detector):
        """纯问候语应检测为对话模式"""
        result = detector.detect("你好")
        assert result.mode == "chat"
        assert result.confidence > 0.5
        assert "闲聊" in result.reason or "chat" in result.reason

    def test_chat_weather(self, detector):
        """天气询问应检测为对话模式"""
        result = detector.detect("今天天气怎么样？")
        assert result.mode == "chat"
        assert result.confidence > 0.5

    def test_task_keyword_bangwo(self, detector):
        """'帮我'开头应检测为任务模式"""
        result = detector.detect("帮我写一个Python函数")
        assert result.mode == "strict"
        assert result.confidence > 0.5

    def test_task_keyword_shixian(self, detector):
        """'实现'关键词应检测为任务模式"""
        result = detector.detect("实现一个用户登录功能")
        assert result.mode == "strict"
        assert result.confidence > 0.5

    def test_task_keyword_refactor(self, detector):
        """'重构'关键词应检测为任务模式"""
        result = detector.detect("重构这个类")
        assert result.mode == "strict"

    def test_task_keyword_fix(self, detector):
        """'修复'关键词应检测为任务模式"""
        result = detector.detect("修复这个bug")
        assert result.mode == "strict"

    def test_task_keyword_optimize(self, detector):
        """'优化'关键词应检测为任务模式"""
        result = detector.detect("优化查询性能")
        assert result.mode == "strict"

    def test_task_keyword_add(self, detector):
        """'添加'关键词应检测为任务模式"""
        result = detector.detect("添加日志记录功能")
        assert result.mode == "strict"

    def test_task_keyword_delete(self, detector):
        """'删除'关键词应检测为任务模式"""
        result = detector.detect("删除过时代码")
        assert result.mode == "strict"

    def test_task_regex_create(self, detector):
        """正则匹配: 创建...文件"""
        result = detector.detect("创建一个 config.yaml 文件")
        assert result.mode == "strict"

    def test_task_regex_update(self, detector):
        """正则匹配: 更新...文件"""
        result = detector.detect("更新 README.md")
        assert result.mode == "strict"

    def test_task_regex_modify(self, detector):
        """正则匹配: 修改...文件"""
        result = detector.detect("修改 main.py 文件")
        assert result.mode == "strict"

    def test_task_regex_implement(self, detector):
        """正则匹配: 在...中实现"""
        result = detector.detect("在 utils.py 中实现新函数")
        assert result.mode == "strict"

    def test_task_regex_add_method(self, detector):
        """正则匹配: 添加...方法/函数"""
        result = detector.detect("添加一个计算函数")
        assert result.mode == "strict"

    def test_empty_message(self, detector):
        """空消息应检测为对话模式"""
        result = detector.detect("")
        assert result.mode == "chat"

    def test_whitespace_message(self, detector):
        """纯空白消息应检测为对话模式"""
        result = detector.detect("   ")
        assert result.mode == "chat"

    def test_mixed_task_and_chat(self, detector):
        """混合任务和聊天关键词，任务优先"""
        result = detector.detect("你好，帮我看看这个代码")
        assert result.mode == "strict"

    def test_confidence_range(self, detector):
        """置信度应在 [0,1] 范围内"""
        for msg in ["你好", "帮我写代码", "今天天气", "实现功能"]:
            result = detector.detect(msg)
            assert 0.0 <= result.confidence <= 1.0

    def test_result_has_reason(self, detector):
        """结果应包含原因说明"""
        result = detector.detect("帮我")
        assert result.reason
        assert len(result.reason) > 0

    def test_result_to_dict(self, detector):
        """to_dict 应返回有效字典"""
        result = detector.detect("实现功能")
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "mode" in d
        assert "confidence" in d
        assert "reason" in d
