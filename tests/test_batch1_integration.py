"""
Batch 1 Integration Tests — Verify zero-dependency modules are wired in.

Modules tested:
    - utils/retry.py (exponential_backoff on UnifiedLLMBackend._complete_aiohttp)
    - observability/auto_tracer.py (@trace_span on process_message and orchestrator.process)
    - cli/main.py (eval-framework, regression, mcp commands registered)
    - scripts/run_mcp_server.py (importable and exposes expected entrypoint)
"""

import asyncio
import inspect
from pathlib import Path

import pytest


class TestRetryIntegration:
    """Verify retry.py is integrated into network calls."""

    def test_aiohttp_has_retry_decorator(self):
        from nexusagent.models.unified_backend import UnifiedLLMBackend
        from nexusagent.utils.retry import exponential_backoff

        method = UnifiedLLMBackend._complete_aiohttp
        # The decorator wraps the method; check that it is NOT the raw coroutine
        # by looking at __wrapped__ or a marker attribute.
        assert hasattr(method, "__wrapped__") or method.__name__ != "_complete_aiohttp", (
            "_complete_aiohttp should be wrapped by exponential_backoff"
        )

    def test_retry_decorator_signature_preserved(self):
        from nexusagent.models.unified_backend import UnifiedLLMBackend
        sig = inspect.signature(UnifiedLLMBackend._complete_aiohttp)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "messages" in params
        assert "tools" in params
        assert "temperature" in params
        assert "max_tokens" in params


class TestAutoTracerIntegration:
    """Verify auto_tracer.py is applied to core lifecycle methods."""

    def test_process_message_has_trace_span(self):
        from nexusagent.main import NexusAgent
        from nexusagent.observability.auto_tracer import trace_span

        method = NexusAgent.process_message
        assert hasattr(method, "__wrapped__") or method.__name__ != "process_message", (
            "process_message should be wrapped by trace_span"
        )

    def test_orchestrator_process_has_trace_span(self):
        from nexusagent.orchestration.orchestrator import Orchestrator
        from nexusagent.observability.auto_tracer import trace_span

        method = Orchestrator.process
        assert hasattr(method, "__wrapped__") or method.__name__ != "process", (
            "Orchestrator.process should be wrapped by trace_span"
        )

    def test_trace_span_produces_span_on_call(self):
        from nexusagent.observability.auto_tracer import trace_span, get_current_span, SimpleSpan

        @trace_span("test.span")
        def dummy():
            span = get_current_span()
            return span

        span = dummy()
        assert isinstance(span, SimpleSpan)
        assert span.name == "test.span"
        assert span.end_time is not None
        assert span.attributes.get("status") == "ok"


class TestEvalCLIIntegration:
    """Verify evals/* are exposed through CLI."""

    def test_eval_framework_command_exists(self):
        from nexusagent.cli.main import cmd_eval_framework
        assert callable(cmd_eval_framework)

    def test_regression_command_exists(self):
        from nexusagent.cli.main import cmd_regression
        assert callable(cmd_regression)

    def test_eval_framework_runs_exact_match(self):
        from nexusagent.cli.main import cmd_eval_framework
        # exact match: input=hello, output=hello, expected=hello → pass
        rc = cmd_eval_framework(["hello", "hello", "hello"])
        assert rc == 0

    def test_eval_framework_fails_on_mismatch(self):
        from nexusagent.cli.main import cmd_eval_framework
        rc = cmd_eval_framework(["hello", "world", "hello"])
        assert rc == 1

    def test_regression_command_fails_without_test_file(self):
        from nexusagent.cli.main import cmd_regression
        rc = cmd_regression(["/nonexistent/tests.json"])
        assert rc == 1


class TestMCPIntegration:
    """Verify mcp_server.py is importable and script exists."""

    def test_mcp_server_importable(self):
        from nexusagent.tools.mcp_server import MCPServer
        assert MCPServer is not None

    def test_mcp_cli_command_exists(self):
        from nexusagent.cli.main import cmd_mcp
        assert callable(cmd_mcp)

    def test_mcp_server_script_exists(self):
        script = Path(__file__).parent.parent / "scripts" / "run_mcp_server.py"
        assert script.exists()
        content = script.read_text(encoding="utf-8")
        assert "MCPServer" in content
        assert "async def main" in content

    def test_mcp_manifest_returns_list(self):
        from nexusagent.tools.mcp_server import MCPServer
        from nexusagent.tools.registry import get_registry

        registry = get_registry()
        registry.discover_builtin_tools()
        server = MCPServer(registry)
        manifest = server.get_tools_manifest()
        assert isinstance(manifest, list)
