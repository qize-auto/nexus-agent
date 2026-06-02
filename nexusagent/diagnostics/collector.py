"""
NexusAgent Diagnostics Collector

Shared diagnostic data collection used by:
- WebAdapter HTTP handlers
- CLI doctor command
- Programmatic health checks

All functions are async and return plain dicts (JSON-serializable).
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional


async def collect_health(adapter_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Full health dashboard — aggregates all subsystem status."""
    from nexusagent.observability.metrics import metrics_collector
    from nexusagent.models.health_monitor import get_health_monitor
    import sys, platform

    metrics = metrics_collector.snapshot()
    health_monitor = get_health_monitor()
    backends = {k: v.to_dict() for k, v in health_monitor.get_all_health().items()}

    # System stats
    system_stats = {
        "python_version": sys.version,
        "platform": platform.platform(),
        "processor": platform.processor() or "unknown",
    }
    try:
        import psutil
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(".")
        system_stats["memory"] = {
            "total_mb": round(mem.total / (1024 * 1024), 1),
            "available_mb": round(mem.available / (1024 * 1024), 1),
            "percent_used": mem.percent,
        }
        system_stats["disk"] = {
            "total_gb": round(disk.total / (1024 ** 3), 1),
            "free_gb": round(disk.free / (1024 ** 3), 1),
            "percent_used": round((disk.used / disk.total) * 100, 1),
        }
        system_stats["cpu_percent"] = psutil.cpu_percent(interval=0.1)
    except Exception:
        system_stats["memory"] = "psutil not available"
        system_stats["disk"] = "psutil not available"

    # Security subsystem deep check
    security_status = {}
    try:
        from nexusagent.security.guardrails import GuardrailsEngine
        g = GuardrailsEngine()
        security_status["guardrails"] = {
            "available": True,
            "ml_threshold": g.ml_threshold,
            "deny_patterns_count": len(g._deny_patterns),
            "red_light_patterns_count": len(g._red_light_patterns),
            "semantic_injection_enabled": g._enable_semantic_injection,
            "injection_detector_loaded": g._injection_detector is not None,
        }
    except Exception as e:
        security_status["guardrails"] = {"available": False, "error": str(e)}

    try:
        from nexusagent.security.sanitizer import InputSanitizer
        s = InputSanitizer()
        security_status["sanitizer"] = {"available": True, "name": s.__class__.__name__}
    except Exception as e:
        security_status["sanitizer"] = {"available": False, "error": str(e)}

    try:
        from nexusagent.security.rbac import RBACEngine
        r = RBACEngine(default_allow=True)
        security_status["rbac"] = {"available": True, "default_allow": True}
    except Exception as e:
        security_status["rbac"] = {"available": False, "error": str(e)}

    # Execution Tracker
    execution_status = {}
    try:
        from nexusagent.execution.tracker import ExecutionTracker
        et = ExecutionTracker()
        execution_status = et.get_stats()
    except Exception as e:
        execution_status = {"error": str(e)}

    # Hybrid Memory
    memory_status = {}
    try:
        from nexusagent.config.settings import get_config
        cfg = get_config()
        db_path = cfg.memory.db_path
        if db_path and os.path.exists(db_path):
            memory_status["db_file_size_mb"] = round(os.path.getsize(db_path) / (1024 * 1024), 2)
        else:
            memory_status["db_file_size_mb"] = 0
        try:
            from nexusagent.memory.hybrid import HybridMemory
            hm = HybridMemory(db_path=db_path)
            stats = await hm.stats()
            memory_status.update(stats)
            await hm.close()
        except Exception as e2:
            memory_status["stats_error"] = str(e2)
    except Exception as e:
        memory_status = {"error": str(e)}

    overall_healthy = all(
        b.get("is_healthy", True) for b in backends.values()
    ) if backends else True

    result = {
        "ok": True,
        "overall_healthy": overall_healthy,
        "timestamp": time.time(),
        "metrics": {
            "requests_total": metrics.requests_total,
            "requests_success": metrics.requests_success,
            "requests_error": metrics.requests_error,
            "avg_latency_ms": round(metrics.avg_latency_ms, 2),
            "active_sessions": metrics.active_sessions,
            "security_interceptions": metrics.security_interceptions,
            "token_usage_total": metrics.token_usage_total,
        },
        "backends": backends,
        "security": security_status,
        "execution": execution_status,
        "memory": memory_status,
        "system": system_stats,
    }
    if adapter_state:
        result["adapter"] = adapter_state
    return result


async def collect_connectivity() -> Dict[str, Any]:
    """Connectivity test — real connection probes + module imports."""
    from nexusagent.tools.registry import get_registry

    registry = get_registry()
    tool_stats = registry.get_stats()

    # Module import checks
    modules = {}
    key_modules = [
        "nexusagent.models.unified_backend",
        "nexusagent.memory.hybrid",
        "nexusagent.execution.tracker",
        "nexusagent.security.guardrails",
        "nexusagent.orchestration.orchestrator",
        "nexusagent.observability.metrics",
    ]
    for mod_name in key_modules:
        try:
            __import__(mod_name)
            modules[mod_name] = {"status": "ok"}
        except Exception as e:
            modules[mod_name] = {"status": "error", "error": str(e)}

    # Real connection probes
    probes = {}

    # 1. SQLite database probe
    try:
        from nexusagent.config.settings import get_config
        cfg = get_config()
        db_path = cfg.memory.db_path
        import sqlite3
        conn = sqlite3.connect(db_path, timeout=2)
        cursor = conn.execute("SELECT 1")
        cursor.fetchone()
        conn.close()
        probes["sqlite"] = {"status": "ok", "db_path": db_path}
    except Exception as e:
        probes["sqlite"] = {"status": "error", "error": str(e)}

    # 2. Filesystem write probe
    try:
        nexus_dir = os.path.join(os.path.expanduser("~"), ".nexusagent")
        os.makedirs(nexus_dir, exist_ok=True)
        test_path = os.path.join(nexus_dir, ".diag_write_test")
        with open(test_path, "w") as f:
            f.write("ok")
        os.remove(test_path)
        probes["filesystem"] = {"status": "ok", "path": nexus_dir}
    except Exception as e:
        probes["filesystem"] = {"status": "error", "error": str(e)}

    # 3. LLM backend initialization probe
    try:
        from nexusagent.models.unified_backend import UnifiedLLMBackend
        backend = UnifiedLLMBackend()
        providers = getattr(backend, "_providers", {})
        probes["llm_backend"] = {
            "status": "ok",
            "initialized_providers": list(providers.keys()) if providers else [],
        }
    except Exception as e:
        probes["llm_backend"] = {"status": "error", "error": str(e)}

    # 4. Memory store deep probe
    try:
        from nexusagent.memory.store import MemoryStore
        from nexusagent.config.settings import get_config
        cfg = get_config()
        store = MemoryStore(cfg.memory.db_path)
        has_conn = store._conn is not None
        vec_avail = store._vec_available
        store.close()
        probes["memory_store"] = {
            "status": "ok",
            "connected": has_conn,
            "vector_search_available": vec_avail,
        }
    except Exception as e:
        probes["memory_store"] = {"status": "error", "error": str(e)}

    all_ok = all(m["status"] == "ok" for m in modules.values()) and all(
        p.get("status") == "ok" for p in probes.values()
    )

    return {
        "ok": all_ok,
        "tool_registry": tool_stats,
        "modules": modules,
        "probes": probes,
    }


async def collect_audit(limit: int = 20, level_filter: str = "") -> Dict[str, Any]:
    """Audit viewer — reads real audit.log + execution traces summary."""
    from nexusagent.observability.tracing import trace_collector
    from nexusagent.observability.metrics import metrics_collector

    traces = trace_collector.list_traces(limit=limit)
    metrics = metrics_collector.snapshot()

    audit_entries = []
    audit_file = os.path.join(os.path.expanduser("~"), ".nexusagent", "audit", "audit.log")
    try:
        if os.path.exists(audit_file):
            with open(audit_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                parts = line.split(" ", 2)
                if len(parts) >= 3 and parts[1].startswith("[") and parts[1].endswith("]"):
                    timestamp = parts[0]
                    level = parts[1][1:-1]
                    rest = parts[2]
                    if " | " in rest:
                        event, detail = rest.split(" | ", 1)
                    else:
                        event, detail = rest, ""
                    if level_filter and level != level_filter:
                        continue
                    audit_entries.append({
                        "timestamp": timestamp,
                        "level": level,
                        "event": event,
                        "detail": detail,
                    })
                    if len(audit_entries) >= limit:
                        break
    except Exception as e:
        audit_entries = [{"error": f"Failed to read audit log: {e}"}]

    return {
        "ok": True,
        "summary": {
            "security_interceptions_total": metrics.security_interceptions,
            "recent_traces_count": len(traces),
            "requests_total_1h": metrics.requests_total,
            "audit_entries_loaded": len(audit_entries),
        },
        "traces": [t.to_dict() for t in traces],
        "audit": audit_entries,
    }


async def collect_modules() -> Dict[str, Any]:
    """Module status — import check + deep health check."""
    core_modules = [
        ("models.unified_backend", "Unified LLM Backend"),
        ("models.router", "Model Router"),
        ("memory.hybrid", "Hybrid Memory"),
        ("execution.tracker", "Execution Tracker"),
        ("execution.react_engine", "ReAct Engine"),
        ("security.guardrails", "Guardrails Engine"),
        ("security.sanitizer", "Input Sanitizer"),
        ("security.rbac", "RBAC Policy"),
        ("orchestration.orchestrator", "Orchestrator"),
        ("orchestration.scheduler", "Scheduler"),
        ("observability.metrics", "Metrics Collector"),
        ("observability.tracing", "Trace Collector"),
        ("tools.registry", "Tool Registry"),
        ("cognition.user_profiler", "User Profiler"),
        ("config.settings", "Settings Manager"),
    ]

    results = []
    for mod_path, display_name in core_modules:
        full_path = f"nexusagent.{mod_path}"
        try:
            mod = __import__(full_path)
            info = {"name": display_name, "module": full_path, "status": "ok"}

            if mod_path == "security.guardrails":
                try:
                    from nexusagent.security.guardrails import GuardrailsEngine
                    g = GuardrailsEngine()
                    info["deep"] = {
                        "ml_threshold": g.ml_threshold,
                        "injection_detector_loaded": g._injection_detector is not None,
                    }
                except Exception as e:
                    info["deep"] = {"error": str(e)}

            elif mod_path == "memory.hybrid":
                try:
                    from nexusagent.memory.hybrid import HybridMemory
                    from nexusagent.config.settings import get_config
                    cfg = get_config()
                    hm = HybridMemory(db_path=cfg.memory.db_path)
                    stats = await hm.stats()
                    info["deep"] = {
                        "total_memories": stats.get("total", 0),
                        "core_blocks": stats.get("core_blocks", 0),
                    }
                    await hm.close()
                except Exception as e:
                    info["deep"] = {"error": str(e)}

            elif mod_path == "execution.tracker":
                try:
                    from nexusagent.execution.tracker import ExecutionTracker
                    et = ExecutionTracker()
                    info["deep"] = et.get_stats()
                except Exception as e:
                    info["deep"] = {"error": str(e)}

            elif mod_path == "tools.registry":
                try:
                    from nexusagent.tools.registry import get_registry
                    r = get_registry()
                    s = r.get_stats()
                    info["deep"] = {"total_tools": s.get("total", 0), "enabled": s.get("enabled", 0)}
                except Exception as e:
                    info["deep"] = {"error": str(e)}

            elif mod_path == "config.settings":
                try:
                    from nexusagent.config.settings import get_config
                    cfg = get_config()
                    info["deep"] = {
                        "debug": cfg.debug,
                        "default_provider": cfg.model.default_provider,
                        "default_model": cfg.model.default_model,
                        "db_path": cfg.memory.db_path,
                    }
                except Exception as e:
                    info["deep"] = {"error": str(e)}

            else:
                info["deep"] = {"import_check": "passed"}

            results.append(info)
        except Exception as e:
            results.append({"name": display_name, "module": full_path, "status": "error", "error": str(e)[:120]})

    ok_count = sum(1 for r in results if r["status"] == "ok")

    return {
        "ok": ok_count == len(core_modules),
        "total": len(core_modules),
        "healthy": ok_count,
        "modules": results,
    }


async def collect_ux(theme: str = "dark", model: str = "") -> Dict[str, Any]:
    """UX Advisor — analyze real metrics, config, and security state."""
    from nexusagent.observability.metrics import metrics_collector

    recommendations = []
    checks = {}
    metrics = metrics_collector.snapshot()

    checks["theme"] = theme
    if theme == "system":
        recommendations.append("System theme may cause flashing on load; consider defaulting to dark.")

    checks["model"] = model or "unknown"
    if model and "8k" in model:
        recommendations.append("8k context window may truncate long conversations; consider 32k/128k for power users.")

    checks["avg_latency_ms"] = round(metrics.avg_latency_ms, 1)
    if metrics.avg_latency_ms > 5000:
        recommendations.append(f"Critical: average latency ({round(metrics.avg_latency_ms, 0)}ms) is very high. Streaming responses or progress indicators are strongly recommended.")
    elif metrics.avg_latency_ms > 3000:
        recommendations.append(f"Average latency ({round(metrics.avg_latency_ms, 0)}ms) is high; consider streaming responses or progress indicators.")

    total = metrics.requests_total
    errors = metrics.requests_error
    error_rate = (errors / total * 100) if total > 0 else 0.0
    checks["error_rate_1h"] = round(error_rate, 2)
    if error_rate > 10:
        recommendations.append(f"High error rate ({round(error_rate, 1)}% in last hour); users may experience frequent failures.")
    elif error_rate > 5:
        recommendations.append(f"Elevated error rate ({round(error_rate, 1)}% in last hour); investigate backend health.")

    try:
        from nexusagent.security.guardrails import GuardrailsEngine
        g = GuardrailsEngine()
        checks["guardrails"] = "enabled"
        checks["guardrails_ml_threshold"] = g.ml_threshold
        if g.ml_threshold < 0.4:
            recommendations.append("Guardrails ML threshold is very low (<0.4); users may see excessive false-positive blocks.")
        if not g._injection_detector:
            recommendations.append("Semantic injection detector is not loaded; prompt injection protection may be weaker.")
    except Exception as e:
        checks["guardrails"] = "disabled"
        recommendations.append(f"Guardrails unavailable ({str(e)}); user-facing safety warnings may be missing.")

    try:
        from nexusagent.config.settings import get_config
        cfg = get_config()
        checks["debug_mode"] = cfg.debug
        if cfg.debug:
            recommendations.append("Debug mode is enabled; this may expose sensitive information in logs.")
        checks["cache_enabled"] = cfg.cache.enabled
        if not cfg.cache.enabled:
            recommendations.append("Semantic cache is disabled; users may experience higher latency and costs.")
        checks["telemetry"] = cfg.security.telemetry_enabled
        if cfg.security.telemetry_enabled:
            recommendations.append("Telemetry is enabled; ensure users have consented to data collection.")
    except Exception as e:
        checks["config_error"] = str(e)

    try:
        from nexusagent.config.settings import get_config
        import os
        cfg = get_config()
        if cfg.memory.db_path and os.path.exists(cfg.memory.db_path):
            size_mb = round(os.path.getsize(cfg.memory.db_path) / (1024 * 1024), 1)
            checks["memory_db_size_mb"] = size_mb
            if size_mb > 500:
                recommendations.append(f"Memory database is large ({size_mb}MB); consider compaction or archival.")
    except Exception:
        pass

    checks["session_persistence"] = "localStorage"
    recommendations.append("Sessions stored in localStorage; warn users about data loss on browser clear.")

    score = max(0, 100 - len(recommendations) * 8)

    return {
        "ok": True,
        "score": score,
        "checks": checks,
        "recommendations": recommendations,
    }


def compare_design(baseline: str, current: str) -> Dict[str, Any]:
    """Design diff — compare baseline vs current design spec."""
    b_lines = baseline.splitlines()
    c_lines = current.splitlines()
    added = [l for l in c_lines if l and l not in b_lines]
    removed = [l for l in b_lines if l and l not in c_lines]

    return {
        "ok": True,
        "analysis": {
            "baseline_lines": len(b_lines),
            "current_lines": len(c_lines),
            "added_count": len(added),
            "removed_count": len(removed),
            "added": added[:50],
            "removed": removed[:50],
        },
        "recommendations": [
            "Review added lines for consistency with design system.",
            "Ensure removed lines are intentionally deprecated.",
            "Run visual regression tests after design changes.",
        ],
    }


def compare_competitor(
    our_features: List[str],
    competitor_features: List[str],
    competitor_name: str = "Competitor",
) -> Dict[str, Any]:
    """Competitor analysis — gap analysis between our features and competitor."""
    ours_set = set(f.lower().strip() for f in our_features)
    comp_set = set(f.lower().strip() for f in competitor_features)

    gaps = list(comp_set - ours_set)
    advantages = list(ours_set - comp_set)
    common = list(ours_set & comp_set)

    return {
        "ok": True,
        "competitor": competitor_name,
        "analysis": {
            "our_feature_count": len(ours_set),
            "competitor_feature_count": len(comp_set),
            "common_features": common,
            "gaps": gaps,
            "advantages": advantages,
        },
        "recommendations": [
            f"Consider adding {len(gaps)} missing features to close gap with {competitor_name}." if gaps else "Feature parity achieved.",
            f"Leverage {len(advantages)} unique advantages in marketing." if advantages else "No unique advantages detected.",
        ],
    }
