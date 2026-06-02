"""
NexusAgent Diagnostics — Shared diagnostic collection for Web, CLI, and programmatic use.
"""

from .collector import (
    collect_health,
    collect_connectivity,
    collect_audit,
    collect_modules,
    collect_ux,
    compare_design,
    compare_competitor,
)
from .scheduler import Alert, DiagnosticScheduler, AlertRuleEngine

__all__ = [
    "collect_health",
    "collect_connectivity",
    "collect_audit",
    "collect_modules",
    "collect_ux",
    "compare_design",
    "compare_competitor",
    "Alert",
    "AlertRuleEngine",
    "DiagnosticScheduler",
]
