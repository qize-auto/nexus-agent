"""
NexusAgent v3.3 — 安全层：信任积分 + 四级审查 + 凭证管理
来源: 设计稿第8章安全层 + P0-U2信任积分快速通道
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional

from nexusagent.security.sanitizer import InputSanitizer, PIIDesensitizer, SecurityError

logger = logging.getLogger("nexus.security")


# ═══════════════════════════════════════════════════════════════
# 信任积分系统 — 设计稿4.11 + P0-U2
# ═══════════════════════════════════════════════════════════════

class TrustTier(Enum):
    """信任等级 — 设计稿4.11.2"""
    NOVICE = (0, 20)       # 新手：STRICT审查
    LEARNER = (20, 50)     # 学习者：CONFIRM确认
    TRUSTED = (50, 80)     # 可信：TOAST提示
    EXPERT = (80, 101)     # 专家：SILENT放行


@dataclass
class TrustScore:
    """
    信任积分EMA加权模型
    公式: EMA_new = α × 最近行为分 + (1-α) × EMA_old
    α = 0.3 默认
    """
    user_id: str
    ema_score: float = 10.0          # 初始10分(新手)
    interaction_count: int = 0
    successful_count: int = 0
    failure_count: int = 0
    last_updated: float = field(default_factory=time.time)
    alpha: float = 0.3               # EMA平滑系数

    @property
    def tier(self) -> TrustTier:
        for tier in TrustTier:
            low, high = tier.value
            if low <= self.ema_score < high:
                return tier
        return TrustTier.EXPERT

    def record_success(self, complexity: float = 1.0) -> None:
        """记录成功交互 — 根据复杂度加权"""
        behavior_score = 100.0 * min(complexity, 1.0)
        self.ema_score = self.alpha * behavior_score + (1 - self.alpha) * self.ema_score
        self.interaction_count += 1
        self.successful_count += 1
        self.last_updated = time.time()

    def record_failure(self, severity: float = 0.5) -> None:
        """记录失败交互 — 根据严重性惩罚"""
        penalty = -30.0 * severity
        behavior_score = max(0, 50 + penalty)
        self.ema_score = self.alpha * behavior_score + (1 - self.alpha) * self.ema_score
        self.ema_score = max(0, self.ema_score)
        self.interaction_count += 1
        self.failure_count += 1
        self.last_updated = time.time()

    def get_prompt_level(self) -> "PermissionPromptLevel":
        """根据信任积分返回权限提示等级 — P0-U2"""
        from nexusagent.interface.adapter import PermissionPromptLevel
        if self.ema_score >= 80:
            return PermissionPromptLevel.SILENT
        elif self.ema_score >= 50:
            return PermissionPromptLevel.TOAST
        elif self.ema_score >= 20:
            return PermissionPromptLevel.CONFIRM
        return PermissionPromptLevel.STRICT


# ═══════════════════════════════════════════════════════════════
# 四级审查 — 设计稿第8章
# ═══════════════════════════════════════════════════════════════

class ReviewLevel(Enum):
    """审查等级 — 设计稿第8章四级审查"""
    DENY = auto()         # DenyList — 直接拒绝
    RED_LIGHT = auto()    # RedLight — 要求确认
    YELLOW = auto()       # ML分类器 — 可能风险
    GREEN = auto()        # 放行


@dataclass
class ReviewResult:
    """审查结果"""
    level: ReviewLevel
    reason: str = ""
    confidence: float = 1.0
    requires_user_approval: bool = False

    @property
    def is_denied(self) -> bool:
        return self.level == ReviewLevel.DENY

    @property
    def is_allowed(self) -> bool:
        return self.level in (ReviewLevel.GREEN, ReviewLevel.YELLOW)


class GuardrailsEngine:
    """
    四级审查引擎 — 设计稿第8章
    DenyList → RedLight → MLClassifier → YellowGreen
    """

    def __init__(self, deny_patterns: Optional[List[str]] = None, enable_semantic_injection: bool = True):
        self._sanitizer = InputSanitizer()
        self._pii_desensitizer = PIIDesensitizer()
        self._deny_patterns: List[str] = deny_patterns or []
        self._red_light_patterns: List[str] = [
            "rm -rf", "DROP TABLE", "DELETE FROM",
            "eval(", "exec(", "__import__",
        ]
        # ML分类器特征词库 — 用于启发式风险评分
        self._sensitive_keywords: List[str] = [
            "password", "secret", "api_key", "token",
            "credit card", "ssn", "身份证号", "银行卡",
        ]
        self._injection_markers: List[str] = [
            "ignore previous", "disregard", "override",
            "system prompt", "you are now", "DAN",
            "jailbreak", "prompt injection",
        ]
        # ML阈值（支持画像适配器动态调整）
        self.ml_threshold: float = 0.6
        # 语义注入检测器 (Phase 2)
        self._enable_semantic_injection = enable_semantic_injection
        self._injection_detector: Optional[Any] = None
        if enable_semantic_injection:
            try:
                from nexusagent.security.injection_detector import InjectionDetector
                self._injection_detector = InjectionDetector()
            except Exception as e:
                logger.warning("语义注入检测器初始化失败: %s", e)

    def _ml_score(self, content: str) -> float:
        """
        Level 3: 轻量ML分类器 — 基于启发式特征评分
        返回 0.0-1.0 的风险分数，>0.6 触发 YELLOW 审查
        """
        text = content.lower()
        score = 0.0

        # 特征1: 敏感信息密度
        sensitive_hits = sum(1 for kw in self._sensitive_keywords if kw in text)
        score += min(sensitive_hits * 0.15, 0.4)

        # 特征2: 提示注入标记
        injection_hits = sum(1 for marker in self._injection_markers if marker in text)
        score += min(injection_hits * 0.25, 0.5)

        # 特征3: 异常字符比例（编码混淆/绕过检测）
        if len(content) > 0:
            special_ratio = sum(1 for c in content if ord(c) > 127 or c in "\x00\x01\x02") / len(content)
            score += min(special_ratio * 2.0, 0.3)

        # 特征4: 长度异常
        if len(content) > 50000:
            score += 0.2
        elif len(content) > 10000:
            score += 0.05

        # 特征5: 重复模式（可能的填充攻击）
        words = text.split()
        if len(words) > 20:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.3:
                score += 0.2

        return min(score, 1.0)

    def review(self, content: str, context: Optional[Dict[str, Any]] = None) -> ReviewResult:
        """四级串联审查（同步版本 — 仅启发式注入检测）"""
        # Level 0: 启发式注入检测 (Phase 2 增强)
        if self._enable_semantic_injection and self._injection_detector:
            try:
                from nexusagent.security.injection_detector import HeuristicDetector
                inj_result = HeuristicDetector.detect(content)
                if inj_result.is_injection and inj_result.score >= 0.70:
                    return ReviewResult(
                        level=ReviewLevel.DENY,
                        reason=f"注入检测: {inj_result.reason} (score={inj_result.score})",
                        confidence=inj_result.score,
                        requires_user_approval=False,
                    )
            except Exception as e:
                logger.warning("注入检测异常: %s", e)

        # Level 0.5: Input Sanitization — 清洗并阻断 blatant 攻击
        try:
            content = self._sanitizer.sanitize(content, context="default")
        except SecurityError as se:
            return ReviewResult(
                level=ReviewLevel.DENY,
                reason=f"Sanitizer blocked: {se}",
                requires_user_approval=False,
            )
        except ValueError as ve:
            return ReviewResult(
                level=ReviewLevel.DENY,
                reason=f"Sanitizer blocked: {ve}",
                requires_user_approval=False,
            )

        # Level 1: DenyList
        for pattern in self._deny_patterns:
            if pattern.lower() in content.lower():
                return ReviewResult(
                    level=ReviewLevel.DENY,
                    reason=f"DenyList匹配: {pattern}",
                    requires_user_approval=False,
                )

        # Level 2: RedLight — 危险模式
        for pattern in self._red_light_patterns:
            if pattern in content:
                return ReviewResult(
                    level=ReviewLevel.RED_LIGHT,
                    reason=f"RedLight匹配: {pattern}",
                    requires_user_approval=True,
                )

        # Level 3: ML分类器 — 启发式风险评分
        ml_risk = self._ml_score(content)
        if ml_risk > self.ml_threshold:
            return ReviewResult(
                level=ReviewLevel.YELLOW,
                reason=f"ML分类器检测到潜在风险(评分={ml_risk:.2f})",
                confidence=ml_risk,
                requires_user_approval=True,
            )

        # Level 4: 放行
        return ReviewResult(level=ReviewLevel.GREEN)

    def review_output(self, content: str) -> ReviewResult:
        """
        输出审查 — ARC-039 Guardrails双层验证 Layer 2
        """
        # PII 脱敏前置处理
        content = self._pii_desensitizer.desensitize(content, level="full")
        sensitive_patterns = [
            "sk-", "api_key", "password", "secret", "token",
            "BEGIN RSA", "BEGIN OPENSSH",
        ]
        for pattern in sensitive_patterns:
            if pattern in content.lower():
                return ReviewResult(
                    level=ReviewLevel.DENY,
                    reason=f"输出包含疑似敏感信息: {pattern}",
                )
        dangerous = ["rm -rf", "eval(", "exec(", "__import__"]
        for pattern in dangerous:
            if pattern in content:
                return ReviewResult(
                    level=ReviewLevel.RED_LIGHT,
                    reason=f"输出包含危险指令: {pattern}",
                    requires_user_approval=True,
                )
        if len(content) > 100000:
            return ReviewResult(level=ReviewLevel.YELLOW, reason="输出长度异常")
        return ReviewResult(level=ReviewLevel.GREEN)

    async def areview(self, content: str, context: Optional[Dict[str, Any]] = None) -> ReviewResult:
        """异步审查 — 包含完整语义注入检测 (LLM-based)"""
        # Level 0: 完整语义注入检测
        if self._enable_semantic_injection and self._injection_detector:
            try:
                inj_result = await self._injection_detector.detect(content)
                if inj_result.is_injection:
                    return ReviewResult(
                        level=ReviewLevel.DENY,
                        reason=f"语义注入检测: {inj_result.reason} (score={inj_result.score})",
                        confidence=inj_result.score,
                        requires_user_approval=False,
                    )
            except Exception as e:
                logger.warning("语义注入检测异常: %s", e)

        # 复用同步 review 的其余逻辑
        return self.review(content, context)


# ═══════════════════════════════════════════════════════════════
# API Key密钥链 — 设计稿第8章
# ═══════════════════════════════════════════════════════════════

@dataclass
class CredentialEntry:
    """凭证条目 — 加密存储"""
    provider: str
    key_hash: str         # SHA256哈希(不存明文)
    encrypted_key: bytes  # AES-256加密后的密钥
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    usage_count: int = 0
    is_active: bool = True

    def record_usage(self) -> None:
        self.last_used = time.time()
        self.usage_count += 1


class CredentialPool:
    """
    凭证池 — 设计稿第8章 API Key密钥链
    支持多provider、密钥轮换、透明安全
    """

    def __init__(self):
        self._credentials: Dict[str, List[CredentialEntry]] = {}

    def add_credential(self, entry: CredentialEntry) -> None:
        """添加凭证"""
        if entry.provider not in self._credentials:
            self._credentials[entry.provider] = []
        self._credentials[entry.provider].append(entry)

    def get_credential(self, provider: str) -> Optional[CredentialEntry]:
        """获取活跃凭证（轮换策略: fill_first）"""
        entries = self._credentials.get(provider, [])
        for entry in entries:
            if entry.is_active:
                entry.record_usage()
                return entry
        return None

    def hash_key(self, key: str) -> str:
        """安全哈希密钥 — 不存明文"""
        return hashlib.sha256(key.encode()).hexdigest()

    def revoke(self, provider: str, key_hash: str) -> bool:
        """吊销凭证"""
        for entry in self._credentials.get(provider, []):
            if entry.key_hash == key_hash:
                entry.is_active = False
                return True
        return False
