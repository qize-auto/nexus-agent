"""
Phase 3 — Reflexion 自我反思节点测试
"""

import pytest

from nexusagent.execution.reflexion import ReflexionNode, ReflectionReport


# ── Rule-based analysis ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_reflexion_timeout_error():
    node = ReflexionNode()
    report = await node.reflect(
        "fetch_data", TimeoutError("connection timed out"), {}, []
    )
    assert report.error_node == "fetch_data"
    assert "网络" in report.root_cause or "超时" in report.root_cause
    assert report.retry_strategy == "retry_same"
    assert report.should_retry is True


@pytest.mark.asyncio
async def test_reflexion_rate_limit():
    node = ReflexionNode()
    report = await node.reflect(
        "llm_call", RuntimeError("rate limit exceeded"), {}, []
    )
    assert "配额" in report.root_cause or "权限" in report.root_cause
    assert report.retry_strategy == "retry_alternative"
    assert report.should_retry is True


@pytest.mark.asyncio
async def test_reflexion_validation_error():
    node = ReflexionNode()
    report = await node.reflect(
        "parse_json", ValueError("invalid json"), {}, []
    )
    assert "格式" in report.root_cause or "验证" in report.root_cause
    assert report.retry_strategy == "retry_same"
    assert report.should_retry is True


@pytest.mark.asyncio
async def test_reflexion_fatal_error():
    node = ReflexionNode()
    report = await node.reflect(
        "process", MemoryError("out of memory"), {}, []
    )
    assert "严重" in report.root_cause
    assert report.retry_strategy == "abort"
    assert report.should_retry is False


@pytest.mark.asyncio
async def test_reflexion_unknown_error():
    node = ReflexionNode()
    report = await node.reflect(
        "unknown", RuntimeError("something weird"), {}, []
    )
    assert report.retry_strategy == "retry_same"
    assert report.should_retry is True


# ── LLM reflection ────────────────────────────────────────────────

class _FakeLLM:
    def __init__(self, content='{"root_cause": "test", "suggested_fix": "fix", "should_retry": true, "retry_strategy": "retry_same", "confidence": 0.9}'):
        self._content = content

    async def complete(self, messages, temperature=0.7):
        return {"content": self._content}


@pytest.mark.asyncio
async def test_reflexion_with_llm():
    node = ReflexionNode(llm_backend=_FakeLLM())
    report = await node.reflect("node1", RuntimeError("err"), {}, [])
    assert report.root_cause == "test"
    assert report.suggested_fix == "fix"
    assert report.confidence == 0.9


@pytest.mark.asyncio
async def test_reflexion_llm_bad_json_fallback():
    node = ReflexionNode(llm_backend=_FakeLLM("not json"))
    report = await node.reflect("node1", RuntimeError("err"), {}, [])
    # 应该回退到规则分析
    assert report.retry_strategy == "retry_same"
    assert report.confidence == 0.6


@pytest.mark.asyncio
async def test_reflexion_llm_exception_fallback():
    class _BadLLM:
        async def complete(self, messages, temperature=0.7):
            raise RuntimeError("llm fail")

    node = ReflexionNode(llm_backend=_BadLLM())
    report = await node.reflect("node1", RuntimeError("err"), {}, [])
    # 应该回退到规则分析
    assert report.retry_strategy == "retry_same"


# ── Callable interface ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reflexion_callable():
    node = ReflexionNode()
    state = {
        "__error__": {"node": "test_node", "error": "test error"},
        "__history__": [{"node": "prev", "iteration": 1}],
    }
    result = await node(state)
    assert "__reflection__" in result
    assert result["__reflection__"]["error_node"] == "test_node"
    assert result["__reflection__"]["should_retry"] is True
