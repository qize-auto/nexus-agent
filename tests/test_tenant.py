"""
NexusAgent v4.0 — 多租户隔离测试
覆盖: TenantContext、TenantRegistry、MemoryStore 租户隔离
"""

import asyncio
import pytest

from nexusagent.tenant.context import TenantContext, TenantContextManager, get_tenant_id
from nexusagent.tenant.isolation import TenantQuota, TenantRegistry, get_registry
from nexusagent.memory.store import MemoryStore, MemoryEntry


class TestTenantContext:
    """租户上下文测试"""

    def test_default_tenant(self):
        TenantContextManager.reset()
        ctx = TenantContextManager.get_current()
        assert ctx.tenant_id == "default"
        assert ctx.is_default is True

    def test_set_current(self):
        ctx = TenantContext(tenant_id="acme", user_id="u1")
        TenantContextManager.set_current(ctx)
        assert get_tenant_id() == "acme"
        TenantContextManager.reset()

    def test_frozen_dataclass(self):
        ctx = TenantContext(tenant_id="x")
        with pytest.raises(AttributeError):
            ctx.tenant_id = "y"

    def test_security_level(self):
        from nexusagent.interface.adapter import SecurityLevel
        ctx = TenantContext(tenant_id="t1", security_level=SecurityLevel.HIGH)
        assert ctx.security_level == SecurityLevel.HIGH


class TestTenantRegistry:
    """租户注册表测试"""

    @pytest.mark.asyncio
    async def test_register_and_get_quota(self):
        reg = TenantRegistry()
        await reg.register("tenant_a", TenantQuota(max_agents=5, max_requests_per_min=10))
        quota = await reg.get_quota("tenant_a")
        assert quota.max_agents == 5
        assert quota.max_requests_per_min == 10

    @pytest.mark.asyncio
    async def test_check_and_increment_within_quota(self):
        reg = TenantRegistry()
        await reg.register("tenant_b", TenantQuota(max_agents=3))
        ok = await reg.check_and_increment("tenant_b", "agents")
        assert ok is True
        ok = await reg.check_and_increment("tenant_b", "agents", delta=2)
        assert ok is True  # 3/3
        ok = await reg.check_and_increment("tenant_b", "agents")
        assert ok is False  # 4/3 超出

    @pytest.mark.asyncio
    async def test_decrement(self):
        reg = TenantRegistry()
        await reg.register("tenant_c", TenantQuota(max_agents=5))
        await reg.check_and_increment("tenant_c", "agents", delta=3)
        await reg.decrement("tenant_c", "agents", delta=1)
        ok = await reg.check_and_increment("tenant_c", "agents", delta=3)
        assert ok is True  # 3-1+3 = 5/5

    @pytest.mark.asyncio
    async def test_reset_counters(self):
        reg = TenantRegistry()
        await reg.register("tenant_d", TenantQuota(max_requests_per_min=10))
        await reg.check_and_increment("tenant_d", "requests", delta=10)
        await reg.reset_counters("tenant_d")
        ok = await reg.check_and_increment("tenant_d", "requests")
        assert ok is True

    @pytest.mark.asyncio
    async def test_unregistered_tenant_allows_all(self):
        reg = TenantRegistry()
        ok = await reg.check_and_increment("unknown", "requests", delta=99999)
        assert ok is True

    @pytest.mark.asyncio
    async def test_global_registry(self):
        reg = await get_registry()
        assert isinstance(reg, TenantRegistry)


class TestMemoryStoreTenantIsolation:
    """MemoryStore 租户隔离测试"""

    @pytest.fixture
    def store(self, tmp_path):
        db = str(tmp_path / "tenant_mem.db")
        s = MemoryStore(db)
        yield s
        s.close()

    @pytest.mark.asyncio
    async def test_save_with_tenant(self, store):
        entry = MemoryEntry(session_id="s1", content="hello")
        mid = await store.save(entry, tenant_id="tenant_x")
        assert mid > 0

        # 按租户查询
        results = await store.get_by_tenant("tenant_x")
        assert len(results) == 1
        assert results[0].content == "hello"

        # 其他租户查不到
        results = await store.get_by_tenant("tenant_y")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_get_by_session_with_tenant(self, store):
        entry = MemoryEntry(session_id="s2", content="data")
        await store.save(entry, tenant_id="t1")
        await store.save(entry, tenant_id="t2")

        results = await store.get_by_session("s2", tenant_id="t1")
        assert len(results) == 1

        results_all = await store.get_by_session("s2")
        assert len(results_all) == 2

    @pytest.mark.asyncio
    async def test_checkpoint_tenant_isolation(self, store):
        await store.save_checkpoint("sess1", {"k": 1}, tenant_id="t_a")
        await store.save_checkpoint("sess1", {"k": 2}, tenant_id="t_b")

        state_a = await store.load_checkpoint("sess1", tenant_id="t_a")
        assert state_a["k"] == 1

        state_b = await store.load_checkpoint("sess1", tenant_id="t_b")
        assert state_b["k"] == 2

        # 不带 tenant_id 返回最新（t_b）
        state_latest = await store.load_checkpoint("sess1")
        assert state_latest["k"] == 2

    @pytest.mark.asyncio
    async def test_delete_by_session_with_tenant(self, store):
        entry = MemoryEntry(session_id="s3", content="del_me")
        await store.save(entry, tenant_id="t1")
        await store.save(entry, tenant_id="t2")

        deleted = await store.delete_by_session("s3", tenant_id="t1")
        assert deleted == 1

        results = await store.get_by_tenant("t1")
        assert len(results) == 0
        results = await store.get_by_tenant("t2")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_tenant_metadata(self, store):
        meta = await store.get_or_create_tenant(
            "corp_1", display_name="Corp One",
            quota={"max_agents": 20},
        )
        assert meta["tenant_id"] == "corp_1"
        assert meta["display_name"] == "Corp One"
        assert meta["quota"]["max_agents"] == 20

        # 再次获取返回已有
        meta2 = await store.get_or_create_tenant("corp_1")
        assert meta2["display_name"] == "Corp One"

    @pytest.mark.asyncio
    async def test_tenant_quota_retrieval(self, store):
        await store.get_or_create_tenant("q_t", quota={"max_memory_mb": 1024})
        quota = await store.get_tenant_quota("q_t")
        assert quota["max_memory_mb"] == 1024


class TestTenantContextAsync:
    """异步上下文中的租户隔离"""

    @pytest.mark.asyncio
    async def test_contextvar_isolation_across_tasks(self):
        async def task_a():
            TenantContextManager.set_current(TenantContext(tenant_id="task_a"))
            await asyncio.sleep(0.05)
            return get_tenant_id()

        async def task_b():
            TenantContextManager.set_current(TenantContext(tenant_id="task_b"))
            await asyncio.sleep(0.05)
            return get_tenant_id()

        results = await asyncio.gather(task_a(), task_b())
        assert sorted(results) == ["task_a", "task_b"]
        TenantContextManager.reset()
