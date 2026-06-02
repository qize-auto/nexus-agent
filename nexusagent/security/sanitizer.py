"""
NexusAgent v3.3 — 安全层：输入消毒 + PII脱敏
补全: NFR-080, NFR-097
依赖: security/guardrails ✅
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Pattern

logger = logging.getLogger("nexus.security.sanitizer")


class InputSanitizer:
    """
    输入消毒器 — NFR-080
    对所有外部输入进行清洗：SQL注入、XSS、路径穿越、Unicode混淆
    """

    # SQL注入模式
    _SQL_PATTERNS: List[Pattern] = [
        re.compile(r"(?i)(\bSELECT\b.*\bFROM\b|\bDROP\s+TABLE\b|\bINSERT\s+INTO\b|\bDELETE\s+FROM\b|\bUPDATE\b.*\bSET\b|\bALTER\s+TABLE\b|\bUNION\s+SELECT\b)"),
        re.compile(r"(?i)(--\s*$|;\s*$|\bOR\s+1\s*=\s*1\b|\bAND\s+1\s*=\s*1\b)"),
    ]

    # 路径穿越模式
    _PATH_TRAVERSAL = re.compile(r"(\.\./|\.\.\\|%2e%2e|%252e)")

    # XSS模式
    _XSS_PATTERNS: List[Pattern] = [
        re.compile(r"<script[^>]*>", re.IGNORECASE),
        re.compile(r"javascript\s*:", re.IGNORECASE),
        re.compile(r"on\w+\s*=\s*[\"']", re.IGNORECASE),
    ]

    # Unicode混淆检测（同形异义字攻击）
    _UNICODE_CONFUSABLE = re.compile(r"[\u0400-\u04FF\u2000-\u206F\uFF00-\uFFEF]")

    def __init__(self, max_input_length: int = 100_000):
        self._max_length = max_input_length

    def sanitize(self, text: str, context: str = "default") -> str:
        """
        消毒输入文本

        Args:
            text: 原始输入
            context: 使用场景（"sql"/"path"/"html"/"default"）

        Returns:
            str: 消毒后的安全文本

        Raises:
            ValueError: 输入包含不可恢复的危险内容
        """
        if not text:
            return ""

        # 长度限制
        if len(text) > self._max_length:
            logger.warning("输入截断: %d → %d", len(text), self._max_length)
            text = text[:self._max_length]

        # Unicode混淆检测
        if self._UNICODE_CONFUSABLE.search(text):
            logger.warning("检测到Unicode混淆字符，已规范化")
            text = self._normalize_unicode(text)

        # 上下文特定的消毒
        if context == "sql" or context == "default":
            text = self._sanitize_sql(text)
        if context == "path" or context == "default":
            text = self._sanitize_path(text)
        if context == "html" or context == "default":
            text = self._sanitize_xss(text)

        return text

    def _sanitize_sql(self, text: str) -> str:
        """SQL注入防护 — 检测并阻断危险输入

        当检测到明显的SQL注入模式时，抛出 SecurityError 阻断处理流程。
        此拦截层与参数化查询形成纵深防御：sanitize 阻断 blatant 攻击，
        参数化查询消除 residual risk。
        """
        for pattern in self._SQL_PATTERNS:
            if pattern.search(text):
                logger.error("SQL注入拦截: 模式匹配 %s", pattern.pattern[:50])
                raise SecurityError(
                    f"输入包含被禁止的SQL模式，已阻断。"
                    f"匹配规则: {pattern.pattern[:50]}..."
                )
        return text


    def _sanitize_path(self, text: str) -> str:
        """路径穿越防护"""
        if self._PATH_TRAVERSAL.search(text):
            logger.warning("检测到路径穿越: %s", text[:100])
            raise ValueError("输入包含路径穿越字符")
        return text

    def _sanitize_xss(self, text: str) -> str:
        """XSS防护"""
        for pattern in self._XSS_PATTERNS:
            text = pattern.sub("[XSS_REMOVED]", text)
        return text

    def _normalize_unicode(self, text: str) -> str:
        """Unicode规范化（NFKC）"""
        import unicodedata
        return unicodedata.normalize("NFKC", text)


class SecurityError(ValueError):
    """安全异常 — 输入被安全层阻断"""
    pass


class PIIDesensitizer:
    """
    PII脱敏器 — NFR-097
    自动检测并脱敏个人身份信息：身份证号、手机号、邮箱、银行卡号
    """

    # 中国身份证号 (18位, 兼容中文边界)
    _ID_CARD = re.compile(r'(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)')

    # 中国手机号 (使用非\b边界，兼容中文)
    _PHONE_CN = re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)')

    # 邮箱 (兼容中文边界 — 仅当前方非邮箱字符时才匹配)
    _EMAIL = re.compile(r'(?<![a-zA-Z0-9._%+\-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![a-zA-Z0-9.])')

    # 银行卡号 (16-19位)
    _BANK_CARD = re.compile(r'\b\d{16,19}\b')

    # IP地址
    _IP_ADDR = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')

    def desensitize(self, text: str, level: str = "full") -> str:
        """
        PII脱敏

        Args:
            text: 原始文本
            level: 脱敏级别 "full"(全遮蔽) / "partial"(部分遮蔽)

        Returns:
            str: 脱敏后的文本
        """
        if not text:
            return ""

        if level == "full":
            text = self._ID_CARD.sub("[身份证号已脱敏]", text)
            text = self._PHONE_CN.sub("[手机号已脱敏]", text)
            text = self._EMAIL.sub("[邮箱已脱敏]", text)
            text = self._BANK_CARD.sub("[银行卡号已脱敏]", text)
        elif level == "partial":
            text = self._PHONE_CN.sub(lambda m: m.group()[:3] + "****" + m.group()[-4:], text)
            text = self._EMAIL.sub(lambda m: m.group()[0] + "***@" + m.group().split("@")[1], text)

        return text

    def contains_pii(self, text: str) -> bool:
        """检测文本是否包含PII"""
        return bool(
            self._ID_CARD.search(text) or
            self._PHONE_CN.search(text) or
            self._EMAIL.search(text)
        )

    def get_pii_types(self, text: str) -> List[str]:
        """获取文本中包含的PII类型列表"""
        types = []
        if self._ID_CARD.search(text):
            types.append("身份证号")
        if self._PHONE_CN.search(text):
            types.append("手机号")
        if self._EMAIL.search(text):
            types.append("邮箱")
        if self._BANK_CARD.search(text):
            types.append("银行卡号")
        return types
