"""
Phase 3 — Human-in-the-Loop 测试
"""

import asyncio

import pytest

from nexusagent.execution.hitl import (
    HITLManager,
    HITLRequest,
    HITLResponse,
    get_hitl_manager,
)


# ── Request approval ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hitl_approval():
    mgr = HITLManager()

    req = HITLRequest(
        thread_id="t1",
        node_name="deploy",
        question="确认部署？",
        context={},
        timeout_seconds=1.0,
    )

    async def submit_later():
        await asyncio.sleep(0.05)
        mgr.submit_response("t1", "deploy", HITLResponse(approved=True, feedback="go"))

    asyncio.create_task(submit_later())
    resp = await mgr.request_approval(req)
    assert resp.approved is True
    assert resp.feedback == "go"


@pytest.mark.asyncio
async def test_hitl_denial():
    mgr = HITLManager()

    req = HITLRequest(
        thread_id="t1",
        node_name="delete",
        question="确认删除？",
        context={},
        timeout_seconds=1.0,
    )

    async def submit_later():
        await asyncio.sleep(0.05)
        mgr.submit_response("t1", "delete", HITLResponse(approved=False, feedback="no"))

    asyncio.create_task(submit_later())
    resp = await mgr.request_approval(req)
    assert resp.approved is False
    assert resp.feedback == "no"


@pytest.mark.asyncio
async def test_hitl_timeout():
    mgr = HITLManager()
    req = HITLRequest(
        thread_id="t1",
        node_name="deploy",
        question="确认部署？",
        context={},
        timeout_seconds=0.05,
    )
    resp = await mgr.request_approval(req)
    assert resp.approved is False
    assert "超时" in resp.feedback


@pytest.mark.asyncio
async def test_hitl_submit_no_request():
    mgr = HITLManager()
    ok = mgr.submit_response("t1", "node", HITLResponse(approved=True))
    assert ok is False


@pytest.mark.asyncio
async def test_hitl_double_submit():
    mgr = HITLManager()
    req = HITLRequest(
        thread_id="t1", node_name="x", question="q", context={}, timeout_seconds=1.0
    )

    async def submit_twice():
        await asyncio.sleep(0.05)
        mgr.submit_response("t1", "x", HITLResponse(approved=True))
        # 第二次应该失败
        ok = mgr.submit_response("t1", "x", HITLResponse(approved=False))
        assert ok is False

    asyncio.create_task(submit_twice())
    resp = await mgr.request_approval(req)
    assert resp.approved is True


# ── Global manager ────────────────────────────────────────────────

def test_get_hitl_manager_singleton():
    m1 = get_hitl_manager()
    m2 = get_hitl_manager()
    assert m1 is m2


# ── Pending requests ──────────────────────────────────────────────

def test_get_pending_requests():
    mgr = HITLManager()
    assert mgr.get_pending_requests() == {}
