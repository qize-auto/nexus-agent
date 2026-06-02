"""
Batch 4 Integration Tests — Verify ReActProfileAdapter and RBAC are wired safely.
"""

import pytest
import inspect


class TestReActProfileAdapterIntegration:
    """Verify ReActProfileAdapter adjustments respect safety floors."""

    def test_apply_returns_adjustments(self):
        from nexusagent.execution.profile_adapter import ReActProfileAdapter
        from nexusagent.memory.user_profile import UserProfile

        adapter = ReActProfileAdapter(react_engine=None)
        profile = UserProfile(user_id="test")
        adjustments = adapter.apply(profile)
        assert "max_iterations" in adjustments
        assert "max_time_seconds" in adjustments
        assert "system_prompt_suffix" in adjustments

    def test_compute_iterations_respects_floor(self):
        from nexusagent.execution.profile_adapter import ReActProfileAdapter
        from nexusagent.memory.user_profile import UserProfile

        adapter = ReActProfileAdapter(react_engine=None)
        profile = UserProfile(user_id="test")
        profile.behavioral.patience_index = 0.0  # Very impatient
        iterations = adapter._compute_iterations(profile)
        # The adapter itself doesn't enforce floor 10; run() does
        # But the computed value should be >= 5 (its own internal floor)
        assert iterations >= 5


class TestReActEngineBudgetOverride:
    """Verify ReActEngine.run() accepts budget_override with floors."""

    def test_run_accepts_budget_override(self):
        from nexusagent.execution.react_engine import ReActEngine
        sig = inspect.signature(ReActEngine.run)
        assert "budget_override" in sig.parameters
        assert "system_prompt_suffix" in sig.parameters

    def test_budget_override_is_optional(self):
        from nexusagent.execution.react_engine import ReActEngine
        sig = inspect.signature(ReActEngine.run)
        assert sig.parameters["budget_override"].default is None
        assert sig.parameters["system_prompt_suffix"].default == ""


class TestRBACIntegration:
    """Verify RBAC has enable/disable and default-allow mode."""

    def test_rbac_default_deny_without_policy(self):
        from nexusagent.security.rbac import RBACEngine
        rbac = RBACEngine()
        assert rbac.can_invoke("t1", "u1", "tool.x") is False

    def test_rbac_default_allow_mode(self):
        from nexusagent.security.rbac import RBACEngine
        rbac = RBACEngine(default_allow=True)
        assert rbac.can_invoke("t1", "u1", "tool.x") is True

    def test_rbac_is_enabled_false_by_default(self):
        from nexusagent.security.rbac import RBACEngine
        rbac = RBACEngine()
        assert rbac.is_enabled() is False

    def test_rbac_enable_disable(self):
        from nexusagent.security.rbac import RBACEngine
        rbac = RBACEngine()
        rbac.enable()
        assert rbac.is_enabled() is True
        rbac.disable()
        assert rbac.is_enabled() is False


class TestOrchestratorRBAC:
    """Verify Orchestrator accepts rbac parameter."""

    def test_orchestrator_accepts_rbac(self):
        from nexusagent.orchestration.orchestrator import Orchestrator
        import inspect

        sig = inspect.signature(Orchestrator.__init__)
        assert "rbac" in sig.parameters
