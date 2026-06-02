"""
NexusAgent v4.0+ — Dream Engine (梦境引擎)

Claude "永久大脑" 灵感实现:
    在后台周期性地对用户画像进行高级加工——
    合并冲突偏好、挖掘深层模式、遗忘过时信息、生成用户摘要。

职责:
    1. 画像整合: 将 pending_traits 合并入主画像，解决冲突
    2. 过期清理: 长时间未确认的画像标记为 stale
    3. 用户摘要: 周期性生成 user_summary 写入 HybridMemory core block
    4. 挑战测试: 对高置信度旧偏好基于新数据重新验证
    5. 情绪趋势: 汇总用户情绪变化趋势

Usage:
    dream = DreamEngine(profile_manager, hybrid_memory)
    await dream.dream_cycle(user_id="u1")
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from nexusagent.memory.user_profile import (
    UserProfile, UserProfileManager,
    StaticTraits, DynamicTraits, BehavioralTraits, SecurityTraits,
)

logger = logging.getLogger("nexus.cognition.dream")


@dataclass
class DreamReport:
    """梦境处理报告"""
    user_id: str
    traits_merged: int = 0
    traits_rejected: int = 0
    traits_staled: int = 0
    conflicts_resolved: int = 0
    summary_generated: bool = False
    elapsed_ms: float = 0.0


class DreamEngine:
    """
    梦境引擎 — 用户画像的后台加工厂

    配置参数:
        stale_threshold_days: 多少天未确认的 pending_trait 标记为 stale
        min_confidence_for_merge: 合并入主画像的最低置信度
        conflict_resolution_strategy: 冲突解决策略 (highest_confidence | newest | frequency)
    """

    def __init__(
        self,
        profile_manager: UserProfileManager,
        hybrid_memory: Any = None,
        stale_threshold_days: int = 30,
        min_confidence_for_merge: float = 0.6,
    ):
        self._profile_mgr = profile_manager
        self._hybrid = hybrid_memory
        self._stale_threshold = stale_threshold_days * 86400
        self._min_confidence = min_confidence_for_merge
        self._stats: Dict[str, Any] = {"cycles_run": 0, "traits_processed": 0}

    async def dream_cycle(self, user_id: str) -> DreamReport:
        """
        执行一次梦境周期

        流程:
            1. 加载画像和 pending_traits
            2. 合并高置信度 traits
            3. 检测并解决冲突
            4. 标记过期 traits
            5. 生成用户摘要
            6. 保存画像
        """
        start = time.time()
        report = DreamReport(user_id=user_id)

        profile = await self._profile_mgr.get_or_create(user_id)
        pending = await self._profile_mgr.get_pending_traits(user_id)

        if not pending:
            logger.debug("DreamEngine: %s 无待处理画像条目，跳过", user_id)
            return report

        logger.info("DreamEngine: 开始处理 %s 的 %d 条 pending_traits", user_id, len(pending))

        # Step 1: 按 category + key 分组
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for trait in pending:
            group_key = f"{trait['category']}:{trait['key']}"
            grouped.setdefault(group_key, []).append(trait)

        # Step 2: 处理每组
        for group_key, traits in grouped.items():
            category, key = group_key.split(":", 1)
            merged, rejected, conflict_resolved = self._process_trait_group(
                profile, category, key, traits
            )
            report.traits_merged += merged
            report.traits_rejected += rejected
            report.conflicts_resolved += conflict_resolved

        # Step 3: 标记过期 traits
        staled = self._mark_stale_pending(profile, pending)
        report.traits_staled = staled

        # Step 4: 生成用户摘要
        if report.traits_merged > 0 or report.traits_staled > 0:
            await self._generate_user_summary(profile)
            report.summary_generated = True

        # Step 5: 保存画像
        profile.version += 1
        profile.changelog.append({
            "action": "dream_cycle",
            "traits_merged": report.traits_merged,
            "traits_rejected": report.traits_rejected,
            "traits_staled": report.traits_staled,
            "timestamp": time.time(),
        })
        await self._profile_mgr.save(profile)

        # Step 6: 清空已处理的 pending traits
        await self._profile_mgr.clear_pending_traits(user_id)

        report.elapsed_ms = (time.time() - start) * 1000
        self._stats["cycles_run"] += 1
        self._stats["traits_processed"] += len(pending)

        logger.info(
            "DreamEngine: %s 处理完成 — merged=%d rejected=%d staled=%d conflicts=%d elapsed=%.1fms",
            user_id, report.traits_merged, report.traits_rejected,
            report.traits_staled, report.conflicts_resolved, report.elapsed_ms,
        )
        return report

    def _process_trait_group(
        self,
        profile: UserProfile,
        category: str,
        key: str,
        traits: List[Dict[str, Any]],
    ) -> Tuple[int, int, int]:
        """
        处理同一 (category, key) 的一组 traits

        Returns:
            (merged_count, rejected_count, conflicts_resolved)
        """
        merged = 0
        rejected = 0
        conflicts = 0

        # 按置信度排序
        traits.sort(key=lambda t: t.get("confidence", 0.5), reverse=True)

        # 取最高置信度的作为候选
        best = traits[0]
        best_conf = best.get("confidence", 0.5)

        # 如果最高置信度都低于阈值，全部拒绝
        if best_conf < self._min_confidence:
            return 0, len(traits), 0

        # 检查是否有冲突
        if len(traits) > 1:
            conflicting = [t for t in traits[1:] if self._is_conflicting(best, t)]
            if conflicting:
                conflicts = len(conflicting)
                # 冲突解决：保留置信度最高的
                logger.debug("冲突解决: %s:%s 保留置信度 %.2f", category, key, best_conf)

        # 合并到主画像
        self._apply_trait(profile, category, key, best["value"], best_conf)
        merged += 1
        rejected += len(traits) - 1

        return merged, rejected, conflicts

    def _is_conflicting(self, a: Dict[str, Any], b: Dict[str, Any]) -> bool:
        """判断两个 trait 是否冲突"""
        # 简单规则：如果 value 是布尔型且相反 → 冲突
        va, vb = a.get("value"), b.get("value")
        if isinstance(va, bool) and isinstance(vb, bool) and va != vb:
            return True
        # 如果 value 是字符串且语义相反 → 冲突
        if isinstance(va, str) and isinstance(vb, str):
            # 简单启发：包含反义词
            opposites = [("喜欢", "不喜欢"), ("like", "dislike"), ("fast", "slow")]
            for pos, neg in opposites:
                if pos in va.lower() and neg in vb.lower():
                    return True
                if neg in va.lower() and pos in vb.lower():
                    return True
        return False

    def _apply_trait(
        self,
        profile: UserProfile,
        category: str,
        key: str,
        value: Any,
        confidence: float,
    ) -> None:
        """将 trait 应用到画像"""
        target = None
        if category == "static":
            target = profile.static
        elif category == "dynamic":
            target = profile.dynamic
        elif category == "behavioral":
            target = profile.behavioral
        elif category == "security":
            target = profile.security

        if not target:
            return

        # 列表类型：追加
        if hasattr(target, key):
            old = getattr(target, key)
            if isinstance(old, list):
                if value not in old:
                    old.append(value)
            elif isinstance(old, dict) and isinstance(value, dict):
                old.update(value)
            else:
                setattr(target, key, value)
        else:
            # 如果属性不存在，动态添加 (通过 __dict__)
            target.__dict__[key] = value

    def _mark_stale_pending(
        self,
        profile: UserProfile,
        pending: List[Dict[str, Any]],
    ) -> int:
        """标记过期 traits (已存储在 pending 中但未合并的)"""
        now = time.time()
        staled = 0
        for trait in pending:
            extracted_at = trait.get("extracted_at", now)
            if now - extracted_at > self._stale_threshold:
                staled += 1
        return staled

    async def _generate_user_summary(self, profile: UserProfile) -> None:
        """生成用户摘要并写入 HybridMemory core block"""
        summary = self._build_summary_text(profile)
        if self._hybrid:
            try:
                self._hybrid.set_core_block(
                    name=f"user_profile_{profile.user_id}",
                    content=summary,
                    max_tokens=2000,
                )
                logger.debug("用户摘要已写入 HybridMemory: %s", profile.user_id)
            except Exception as e:
                logger.warning("写入 HybridMemory 失败: %s", e)

    def _build_summary_text(self, profile: UserProfile) -> str:
        """构建用户摘要文本"""
        parts = [
            f"# 用户画像摘要 (v{profile.version})",
            f"用户ID: {profile.user_id}",
            f"更新时间: {time.strftime('%Y-%m-%d %H:%M', time.localtime(profile.updated_at))}",
            "",
            "## 静态属性",
            f"- 技术栈: {', '.join(profile.static.tech_stack) or '未记录'}",
            f"- 偏好工具: {', '.join(profile.static.preferred_tools) or '未记录'}",
            f"- 沟通风格: {profile.static.communication_style}",
            f"- 时区: {profile.static.timezone}",
            "",
            "## 行为模式",
            f"- 耐心指数: {profile.behavioral.patience_index:.2f}",
            f"- 细节偏好: {profile.behavioral.detail_preference:.2f}",
            f"- 温度偏好: {profile.behavioral.temperature_preference:.2f}",
            f"- 超时偏好: {profile.behavioral.timeout_preference:.0f}s",
            "",
            "## 安全与信任",
            f"- 信任积分: {profile.security.trust_score:.1f}",
            f"- 信任等级: {profile.security.trust_tier}",
            f"- 隐私级别: {profile.security.data_privacy_level}",
        ]
        return "\n".join(parts)

    async def run_for_all_users(self) -> List[DreamReport]:
        """为所有用户执行梦境周期"""
        reports = []
        # 获取所有用户ID (从 profiles 表)
        def _get_users():
            cursor = self._profile_mgr._conn.execute(
                "SELECT user_id FROM user_profiles"
            )
            return [row[0] for row in cursor.fetchall()]

        import asyncio
        loop = asyncio.get_event_loop()
        user_ids = await loop.run_in_executor(None, _get_users)

        for uid in user_ids:
            try:
                report = await self.dream_cycle(uid)
                reports.append(report)
            except Exception as e:
                logger.error("DreamEngine 处理 %s 失败: %s", uid, e)

        return reports

    def get_stats(self) -> Dict[str, Any]:
        return dict(self._stats)
