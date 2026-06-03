"""
端到端测试: DreamEngine 梦境引擎

验证:
    1. 无 pending traits 时返回空报告
    2. 高置信度 traits 正确合并入主画像
    3. 低置信度 traits 被拒绝
    4. 冲突 traits 正确解决（保留高置信度）
    5. 过期 traits 被标记
    6. 用户摘要生成
"""

import pytest
import pytest_asyncio
import asyncio
import tempfile
import os

from nexusagent.cognition.dream_engine import DreamEngine, DreamReport
from nexusagent.memory.user_profile import UserProfileManager, UserProfile


@pytest_asyncio.fixture
async def dream_setup():
    """创建临时数据库和 DreamEngine"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    # 设置 master key 避免加密报错
    os.environ.setdefault("NEXUS_MASTER_KEY", "dGVzdC1rZXktZm9yLXRlc3Rpbmctb25seS1ub3QtcHJvZHVjdGlvbg==")

    mgr = UserProfileManager(db_path=db_path)
    dream = DreamEngine(profile_manager=mgr, stale_threshold_days=1)

    yield mgr, dream

    # 清理
    try:
        os.unlink(db_path)
    except Exception:
        pass


class TestDreamEngineE2E:
    """梦境引擎端到端测试"""

    @pytest.mark.asyncio
    async def test_empty_pending_returns_empty_report(self, dream_setup):
        """无 pending traits 时返回空报告"""
        mgr, dream = dream_setup
        report = await dream.dream_cycle("user_empty")
        assert isinstance(report, DreamReport)
        assert report.traits_merged == 0
        assert report.traits_rejected == 0
        assert report.traits_staled == 0
        assert report.conflicts_resolved == 0
        assert report.summary_generated is False

    @pytest.mark.asyncio
    async def test_high_confidence_trait_merged(self, dream_setup):
        """高置信度 trait 应合并入主画像"""
        mgr, dream = dream_setup
        user_id = "user_merge"

        # 添加高置信度 pending trait
        await mgr.add_pending_trait(
            user_id=user_id,
            category="static",
            key="tech_stack",
            value="Python",
            confidence=0.9,
            source="explicit",
        )

        # 获取画像确认 pending 存在
        pending = await mgr.get_pending_traits(user_id)
        assert len(pending) == 1

        report = await dream.dream_cycle(user_id)
        assert report.traits_merged == 1
        assert report.traits_rejected == 0
        assert report.summary_generated is True

        # 确认已清空 pending
        pending_after = await mgr.get_pending_traits(user_id)
        assert len(pending_after) == 0

    @pytest.mark.asyncio
    async def test_low_confidence_trait_rejected(self, dream_setup):
        """低置信度 trait 应被拒绝"""
        mgr, dream = dream_setup
        user_id = "user_reject"

        await mgr.add_pending_trait(
            user_id=user_id,
            category="static",
            key="tech_stack",
            value="Rust",
            confidence=0.3,  # 低于默认阈值 0.6
            source="inferred",
        )

        report = await dream.dream_cycle(user_id)
        assert report.traits_merged == 0
        assert report.traits_rejected == 1

    @pytest.mark.asyncio
    async def test_conflict_resolution(self, dream_setup):
        """冲突 traits 应保留高置信度"""
        mgr, dream = dream_setup
        user_id = "user_conflict"

        # 添加两个语义冲突的字符串 trait
        await mgr.add_pending_trait(
            user_id=user_id,
            category="static",
            key="communication_style",
            value="喜欢详细解释",
            confidence=0.85,
            source="explicit",
        )
        await mgr.add_pending_trait(
            user_id=user_id,
            category="static",
            key="communication_style",
            value="不喜欢详细解释",
            confidence=0.60,
            source="inferred",
        )

        report = await dream.dream_cycle(user_id)
        assert report.traits_merged == 1
        assert report.traits_rejected == 1
        assert report.conflicts_resolved == 1

        # 确认主画像保留了高置信度的值
        profile = await mgr.get_or_create(user_id)
        assert profile.static.communication_style == "喜欢详细解释"

    @pytest.mark.asyncio
    async def test_multiple_traits_processing(self, dream_setup):
        """多个不同 category 的 traits 同时处理"""
        mgr, dream = dream_setup
        user_id = "user_multi"

        await mgr.add_pending_trait(user_id, "static", "tech_stack", "Python", 0.9, "explicit")
        await mgr.add_pending_trait(user_id, "behavioral", "patience_index", 0.8, 0.8, "explicit")
        await mgr.add_pending_trait(user_id, "dynamic", "current_project", "NexusAgent", 0.7, "explicit")

        report = await dream.dream_cycle(user_id)
        assert report.traits_merged == 3
        assert report.traits_rejected == 0

        # 确认画像已更新
        profile = await mgr.get_or_create(user_id)
        assert "Python" in profile.static.tech_stack
        assert profile.behavioral.patience_index > 0.5
        assert profile.dynamic.current_project == "NexusAgent"

    @pytest.mark.asyncio
    async def test_profile_version_incremented(self, dream_setup):
        """梦境周期后画像版本应增加"""
        mgr, dream = dream_setup
        user_id = "user_version"

        profile_before = await mgr.get_or_create(user_id)
        version_before = profile_before.version

        await mgr.add_pending_trait(user_id, "static", "tech_stack", "Go", 0.9, "explicit")
        await dream.dream_cycle(user_id)

        profile_after = await mgr.get_or_create(user_id)
        assert profile_after.version == version_before + 1
        assert len(profile_after.changelog) > 0
        assert profile_after.changelog[-1]["action"] == "dream_cycle"
