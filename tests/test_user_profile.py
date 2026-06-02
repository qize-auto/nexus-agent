"""
NexusAgent v4.0+ — 用户画像系统测试
覆盖: UserProfileManager, UserProfiler, DreamEngine, ProfileAdapters
"""

import pytest
import time
import os
import tempfile

from nexusagent.memory.user_profile import (
    UserProfileManager,
    UserProfile,
    StaticTraits,
    DynamicTraits,
    BehavioralTraits,
    SecurityTraits,
)
from nexusagent.cognition.user_profiler import UserProfiler, ExtractedSignal
from nexusagent.cognition.dream_engine import DreamEngine, DreamReport


# ═══════════════════════════════════════════════════════════════
# UserProfileManager 测试
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    try:
        os.unlink(path)
    except PermissionError:
        pass  # Windows: SQLite connection may still be open


@pytest.fixture
def profile_mgr(temp_db):
    mgr = UserProfileManager(db_path=temp_db)
    yield mgr
    mgr.close()


class TestUserProfileManager:
    """UserProfileManager 测试"""

    @pytest.mark.asyncio
    async def test_create_and_load(self, profile_mgr):
        profile = await profile_mgr.create("user_1")
        assert profile.user_id == "user_1"
        assert profile.version == 1

        loaded = await profile_mgr.load("user_1")
        assert loaded is not None
        assert loaded.user_id == "user_1"

    @pytest.mark.asyncio
    async def test_get_or_create(self, profile_mgr):
        p1 = await profile_mgr.get_or_create("user_2")
        p2 = await profile_mgr.get_or_create("user_2")
        assert p1.user_id == p2.user_id == "user_2"

    @pytest.mark.asyncio
    async def test_update_trait(self, profile_mgr):
        profile = await profile_mgr.update_trait(
            "user_3", "static", "tech_stack", ["python", "rust"],
        )
        assert "python" in profile.static.tech_stack
        assert profile.version >= 2
        assert len(profile.changelog) > 0

    @pytest.mark.asyncio
    async def test_pending_traits(self, profile_mgr):
        await profile_mgr.add_pending_trait(
            "user_4", "static", "tech_stack", "go", confidence=0.8,
        )
        pending = await profile_mgr.get_pending_traits("user_4")
        assert len(pending) == 1
        assert pending[0]["key"] == "tech_stack"
        assert pending[0]["value"] == "go"

        cleared = await profile_mgr.clear_pending_traits("user_4")
        assert cleared == 1
        pending2 = await profile_mgr.get_pending_traits("user_4")
        assert len(pending2) == 0

    @pytest.mark.asyncio
    async def test_snapshot_and_rollback(self, profile_mgr):
        profile = await profile_mgr.get_or_create("user_5")
        await profile_mgr.save(profile)  # v1 snapshot

        profile.static.tech_stack = ["python"]
        await profile_mgr.save(profile)  # v2 snapshot

        history = await profile_mgr.get_history("user_5")
        assert len(history) >= 1

    @pytest.mark.asyncio
    async def test_gdpr_delete(self, profile_mgr):
        await profile_mgr.create("user_gdpr")
        await profile_mgr.add_pending_trait("user_gdpr", "static", "x", "y")
        await profile_mgr.delete_profile("user_gdpr")

        loaded = await profile_mgr.load("user_gdpr")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_export(self, profile_mgr):
        await profile_mgr.create("user_exp")
        exported = await profile_mgr.export_profile("user_exp")
        assert exported["export_metadata"]["user_id"] == "user_exp"
        assert "profile" in exported


# ═══════════════════════════════════════════════════════════════
# UserProfiler 测试
# ═══════════════════════════════════════════════════════════════

class TestUserProfiler:
    """UserProfiler 测试"""

    def test_extract_tech_stack(self):
        profiler = UserProfiler()
        signals = profiler.process_message(
            user_id="u1",
            message="我喜欢用Python和Docker做开发",
        )
        tech_signals = [s for s in signals if s.key == "tech_stack"]
        assert len(tech_signals) >= 2  # python + docker

    def test_extract_patience_low(self):
        profiler = UserProfiler()
        signals = profiler.process_message(
            user_id="u1",
            message="快点给我结果，我很没耐心",
        )
        patience = [s for s in signals if s.key == "patience_index"]
        assert len(patience) == 1
        assert patience[0].value < 0.5  # 低耐心

    def test_extract_patience_high(self):
        profiler = UserProfiler()
        signals = profiler.process_message(
            user_id="u1",
            message="慢慢来，仔细分析每个细节",
        )
        patience = [s for s in signals if s.key == "patience_index"]
        assert len(patience) == 1
        assert patience[0].value > 0.5  # 高耐心

    def test_explicit_learn(self):
        profiler = UserProfiler()
        signals = profiler.process_message(
            user_id="u1",
            message="记住我不喜欢Docker",
        )
        explicit = [s for s in signals if s.source == "explicit"]
        assert len(explicit) >= 1

    def test_negation_feedback(self):
        profiler = UserProfiler()
        signals = profiler.process_message(
            user_id="u1",
            message="不对，你说的错了",
            agent_output="之前的输出",
        )
        neg = [s for s in signals if s.source == "feedback"]
        assert len(neg) >= 1

    def test_no_signals_for_empty(self):
        profiler = UserProfiler()
        signals = profiler.process_message(user_id="u1", message="")
        assert len(signals) == 0


# ═══════════════════════════════════════════════════════════════
# DreamEngine 测试
# ═══════════════════════════════════════════════════════════════

class TestDreamEngine:
    """DreamEngine 测试"""

    @pytest.mark.asyncio
    async def test_dream_cycle_empty(self, temp_db):
        mgr = UserProfileManager(db_path=temp_db)
        try:
            dream = DreamEngine(profile_manager=mgr)
            report = await dream.dream_cycle("user_empty")
            assert report.traits_merged == 0
        finally:
            mgr.close()

    @pytest.mark.asyncio
    async def test_dream_cycle_merge(self, temp_db):
        mgr = UserProfileManager(db_path=temp_db)
        try:
            await mgr.create("user_merge")
            await mgr.add_pending_trait("user_merge", "static", "tech_stack", "python", confidence=0.8)
            await mgr.add_pending_trait("user_merge", "static", "tech_stack", "rust", confidence=0.7)

            dream = DreamEngine(profile_manager=mgr)
            report = await dream.dream_cycle("user_merge")
            assert report.traits_merged >= 1

            profile = await mgr.load("user_merge")
            assert "python" in profile.static.tech_stack or "rust" in profile.static.tech_stack
        finally:
            mgr.close()

    @pytest.mark.asyncio
    async def test_dream_cycle_low_confidence_rejected(self, temp_db):
        mgr = UserProfileManager(db_path=temp_db)
        try:
            await mgr.create("user_reject")
            await mgr.add_pending_trait("user_reject", "static", "tech_stack", "cobol", confidence=0.3)

            dream = DreamEngine(profile_manager=mgr, min_confidence_for_merge=0.6)
            report = await dream.dream_cycle("user_reject")
            assert report.traits_rejected >= 1
            assert report.traits_merged == 0
        finally:
            mgr.close()

    @pytest.mark.asyncio
    async def test_dream_summary_generation(self, temp_db):
        mgr = UserProfileManager(db_path=temp_db)
        try:
            await mgr.create("user_summary")
            await mgr.add_pending_trait("user_summary", "static", "tech_stack", "python", confidence=0.9)

            dream = DreamEngine(profile_manager=mgr)
            report = await dream.dream_cycle("user_summary")
            assert report.summary_generated is True
        finally:
            mgr.close()


# ═══════════════════════════════════════════════════════════════
# 集成场景测试
# ═══════════════════════════════════════════════════════════════

class TestProfileIntegration:
    """端到端集成测试"""

    @pytest.mark.asyncio
    async def test_session_evolution(self, temp_db):
        """模拟两会话画像进化"""
        mgr = UserProfileManager(db_path=temp_db)
        try:
            profiler = UserProfiler()
            dream = DreamEngine(profile_manager=mgr)

            msg1 = "我喜欢用Python，不喜欢JavaScript，快点给我结果"
            signals1 = profiler.process_message("u_evolve", msg1)
            for sig in signals1:
                await mgr.add_pending_trait("u_evolve", sig.category, sig.key, sig.value, sig.confidence)

            report = await dream.dream_cycle("u_evolve")
            assert report.traits_merged > 0

            profile = await mgr.load("u_evolve")
            assert "python" in profile.static.tech_stack
            assert profile.behavioral.patience_index < 0.5

            msg2 = "写个数据分析脚本"
            signals2 = profiler.process_message("u_evolve", msg2)
            tech_signals = [s for s in signals2 if s.key == "tech_stack"]
        finally:
            mgr.close()

    @pytest.mark.asyncio
    async def test_profile_versioning(self, temp_db):
        mgr = UserProfileManager(db_path=temp_db)
        try:
            p = await mgr.create("u_version")
            assert p.version == 1

            await mgr.update_trait("u_version", "behavioral", "patience_index", 0.3)
            p2 = await mgr.load("u_version")
            assert p2.version >= 2

            history = await mgr.get_history("u_version")
            assert len(history) >= 1
        finally:
            mgr.close()
