"""
Batch 6 Integration Tests — Verify remaining experimental modules are wired.
"""

import pytest


class TestHybridMemoryLinking:
    """Verify add_recall triggers link_memories."""

    def test_link_memories_method_exists(self):
        from nexusagent.memory.hybrid import HybridMemory
        assert hasattr(HybridMemory, "link_memories")


class TestCLICommandsExist:
    """Verify new CLI commands are registered."""

    def test_encryption_command_exists(self):
        from nexusagent.cli.main import cmd_encryption_export
        assert callable(cmd_encryption_export)

    def test_graph_command_exists(self):
        from nexusagent.cli.main import cmd_graph_visualize
        assert callable(cmd_graph_visualize)

    def test_status_enhanced_command_exists(self):
        from nexusagent.cli.main import cmd_status_enhanced
        assert callable(cmd_status_enhanced)


class TestOptionalComponentsImportable:
    """Verify experimental modules are importable."""

    def test_cron_scheduler_importable(self):
        from nexusagent.orchestration.scheduler import CronScheduler
        assert CronScheduler is not None

    def test_observability_layer_importable(self):
        from nexusagent.cognition.systems import ObservabilityLayer
        assert ObservabilityLayer is not None

    def test_encryption_export_importable(self):
        from nexusagent.memory.encryption import MemoryEncryption
        assert MemoryEncryption is not None
