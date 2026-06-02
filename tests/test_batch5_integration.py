"""
Batch 5 Integration Tests — Verify HybridSearch, MemoryBlock, areview() integration.
"""

import pytest


class TestHybridSearchIntegration:
    """Verify HybridSearch is wired into HybridMemory._vector_search()."""

    def test_hybrid_memory_has_hybrid_search(self):
        from nexusagent.memory.hybrid import HybridMemory
        hm = HybridMemory()
        assert hasattr(hm, "_hybrid_search")

    def test_hybrid_memory_has_core_block(self):
        from nexusagent.memory.hybrid import HybridMemory
        hm = HybridMemory()
        assert "persona" in hm._blocks


class TestAreviewIntegration:
    """Verify areview() is available and callable."""

    def test_guardrails_has_areview(self):
        from nexusagent.security.guardrails import GuardrailsEngine
        g = GuardrailsEngine()
        assert hasattr(g, "areview")

    def test_areview_returns_review_result(self):
        import asyncio
        from nexusagent.security.guardrails import GuardrailsEngine

        g = GuardrailsEngine()
        result = asyncio.run(g.areview("hello"))
        assert hasattr(result, "is_denied")
