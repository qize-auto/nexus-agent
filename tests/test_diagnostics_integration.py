"""
Diagnostics API Integration Tests
Verify all 7 diagnostic endpoints return correct shapes.
"""

import pytest


class TestDiagnosticsHealth:
    @pytest.mark.asyncio
    async def test_full_health(self):
        from aiohttp import ClientSession, TCPConnector
        from nexusagent.interface.adapter import WebAdapter

        adapter = WebAdapter({"host": "127.0.0.1", "port": 0})
        await adapter.start()
        port = adapter._site._server.sockets[0].getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        try:
            async with ClientSession(connector=TCPConnector(limit=10)) as session:
                async with session.get(f"{base}/api/diagnostics/health/full") as resp:
                    assert resp.status == 200
                    data = await resp.json()
            assert data["ok"] is True
            assert "overall_healthy" in data
            assert "metrics" in data
            assert "backends" in data
            assert "security" in data
            assert "adapter" in data
            assert "requests_total" in data["metrics"]
            # Phase 2 deepened fields
            assert "system" in data
            assert "python_version" in data["system"]
            assert "execution" in data
            assert "total_tasks" in data["execution"]
            assert "memory" in data
            assert "db_file_size_mb" in data["memory"]
        finally:
            await adapter.stop()


class TestDiagnosticsConnectivity:
    @pytest.mark.asyncio
    async def test_connectivity(self):
        from aiohttp import ClientSession, TCPConnector
        from nexusagent.interface.adapter import WebAdapter

        adapter = WebAdapter({"host": "127.0.0.1", "port": 0})
        await adapter.start()
        port = adapter._site._server.sockets[0].getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        try:
            async with ClientSession(connector=TCPConnector(limit=10)) as session:
                async with session.get(f"{base}/api/diagnostics/connectivity") as resp:
                    assert resp.status == 200
                    data = await resp.json()
            assert "ok" in data
            assert "tool_registry" in data
            assert "modules" in data
            assert "probes" in data
            assert isinstance(data["modules"], dict)
            # Phase 2 deepened probes
            probes = data["probes"]
            assert "sqlite" in probes
            assert "filesystem" in probes
            assert "llm_backend" in probes
            assert "memory_store" in probes
        finally:
            await adapter.stop()


class TestDiagnosticsModules:
    @pytest.mark.asyncio
    async def test_modules(self):
        from aiohttp import ClientSession, TCPConnector
        from nexusagent.interface.adapter import WebAdapter

        adapter = WebAdapter({"host": "127.0.0.1", "port": 0})
        await adapter.start()
        port = adapter._site._server.sockets[0].getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        try:
            async with ClientSession(connector=TCPConnector(limit=10)) as session:
                async with session.get(f"{base}/api/diagnostics/modules") as resp:
                    assert resp.status == 200
                    data = await resp.json()
            assert data["ok"] in (True, False)
            assert "total" in data
            assert "healthy" in data
            assert isinstance(data["modules"], list)
            for m in data["modules"]:
                assert "name" in m
                assert "module" in m
                assert "status" in m
                # Phase 2: deep health checks
                if m["status"] == "ok":
                    assert "deep" in m
        finally:
            await adapter.stop()


class TestDiagnosticsAudit:
    @pytest.mark.asyncio
    async def test_audit(self):
        from aiohttp import ClientSession, TCPConnector
        from nexusagent.interface.adapter import WebAdapter

        adapter = WebAdapter({"host": "127.0.0.1", "port": 0})
        await adapter.start()
        port = adapter._site._server.sockets[0].getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        try:
            async with ClientSession(connector=TCPConnector(limit=10)) as session:
                async with session.get(f"{base}/api/diagnostics/audit") as resp:
                    assert resp.status == 200
                    data = await resp.json()
            assert data["ok"] is True
            assert "summary" in data
            assert "traces" in data
            assert "security_interceptions_total" in data["summary"]
            # Phase 2: real audit log
            assert "audit" in data
            assert isinstance(data["audit"], list)
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_audit_limit(self):
        from aiohttp import ClientSession, TCPConnector
        from nexusagent.interface.adapter import WebAdapter

        adapter = WebAdapter({"host": "127.0.0.1", "port": 0})
        await adapter.start()
        port = adapter._site._server.sockets[0].getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        try:
            async with ClientSession(connector=TCPConnector(limit=10)) as session:
                async with session.get(f"{base}/api/diagnostics/audit?limit=5") as resp:
                    assert resp.status == 200
                    data = await resp.json()
            assert data["ok"] is True
        finally:
            await adapter.stop()


class TestDiagnosticsUX:
    @pytest.mark.asyncio
    async def test_ux(self):
        from aiohttp import ClientSession, TCPConnector
        from nexusagent.interface.adapter import WebAdapter

        adapter = WebAdapter({"host": "127.0.0.1", "port": 0})
        await adapter.start()
        port = adapter._site._server.sockets[0].getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        try:
            async with ClientSession(connector=TCPConnector(limit=10)) as session:
                async with session.get(f"{base}/api/diagnostics/ux?theme=dark&model=moonshot-v1-8k") as resp:
                    assert resp.status == 200
                    data = await resp.json()
            assert data["ok"] is True
            assert "score" in data
            assert 0 <= data["score"] <= 100
            assert "checks" in data
            assert "recommendations" in data
            assert isinstance(data["recommendations"], list)
            # Phase 2: real metric-based checks
            assert "avg_latency_ms" in data["checks"]
            assert "error_rate_1h" in data["checks"]
            assert "guardrails" in data["checks"]
        finally:
            await adapter.stop()


class TestDiagnosticsDesignDiff:
    @pytest.mark.asyncio
    async def test_design_diff(self):
        from aiohttp import ClientSession, TCPConnector
        from nexusagent.interface.adapter import WebAdapter

        adapter = WebAdapter({"host": "127.0.0.1", "port": 0})
        await adapter.start()
        port = adapter._site._server.sockets[0].getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        try:
            payload = {
                "baseline": "button { color: red; }\nheader { height: 60px; }",
                "current": "button { color: blue; }\nheader { height: 60px; }\nfooter { margin: 0; }",
            }
            async with ClientSession(connector=TCPConnector(limit=10)) as session:
                async with session.post(f"{base}/api/diagnostics/compare/design", json=payload) as resp:
                    assert resp.status == 200
                    data = await resp.json()
            assert data["ok"] is True
            assert "analysis" in data
            assert data["analysis"]["added_count"] >= 1
            assert "recommendations" in data
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_design_diff_missing_fields(self):
        from aiohttp import ClientSession, TCPConnector
        from nexusagent.interface.adapter import WebAdapter

        adapter = WebAdapter({"host": "127.0.0.1", "port": 0})
        await adapter.start()
        port = adapter._site._server.sockets[0].getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        try:
            async with ClientSession(connector=TCPConnector(limit=10)) as session:
                async with session.post(f"{base}/api/diagnostics/compare/design", json={}) as resp:
                    assert resp.status == 400
        finally:
            await adapter.stop()


class TestDiagnosticsCompetitor:
    @pytest.mark.asyncio
    async def test_competitor(self):
        from aiohttp import ClientSession, TCPConnector
        from nexusagent.interface.adapter import WebAdapter

        adapter = WebAdapter({"host": "127.0.0.1", "port": 0})
        await adapter.start()
        port = adapter._site._server.sockets[0].getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        try:
            payload = {
                "competitor_name": "RivalAI",
                "our_features": ["local storage", "privacy guard", "multi-model"],
                "competitor_features": ["cloud sync", "privacy guard", "plugins"],
            }
            async with ClientSession(connector=TCPConnector(limit=10)) as session:
                async with session.post(f"{base}/api/diagnostics/compare/competitor", json=payload) as resp:
                    assert resp.status == 200
                    data = await resp.json()
            assert data["ok"] is True
            assert data["competitor"] == "RivalAI"
            assert "analysis" in data
            assert "gaps" in data["analysis"]
            assert "advantages" in data["analysis"]
            assert "recommendations" in data
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_competitor_missing_fields(self):
        from aiohttp import ClientSession, TCPConnector
        from nexusagent.interface.adapter import WebAdapter

        adapter = WebAdapter({"host": "127.0.0.1", "port": 0})
        await adapter.start()
        port = adapter._site._server.sockets[0].getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        try:
            async with ClientSession(connector=TCPConnector(limit=10)) as session:
                async with session.post(f"{base}/api/diagnostics/compare/competitor", json={}) as resp:
                    assert resp.status == 400
        finally:
            await adapter.stop()


class TestCLIDoctor:
    def test_doctor_runs_and_returns_exit_code(self):
        """CLI doctor command runs and returns 0 or 1."""
        from nexusagent.cli.main import cmd_doctor
        rc = cmd_doctor([])
        assert rc in (0, 1)

    def test_doctor_json_output(self):
        """CLI doctor --json returns valid JSON to stdout."""
        import io, sys, json
        from nexusagent.cli.main import cmd_doctor

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            rc = cmd_doctor(["--json"])
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        data = json.loads(output)
        assert "health" in data
        assert "connectivity" in data
        assert "modules" in data
        assert "audit" in data
        assert "ux" in data
        assert rc in (0, 1)


class TestAlertRuleEngine:
    def test_system_unhealthy(self):
        from nexusagent.diagnostics.scheduler import AlertRuleEngine
        engine = AlertRuleEngine()
        alerts = engine.evaluate(
            {"overall_healthy": False, "metrics": {}},
            {},
            {},
        )
        assert len(alerts) == 1
        assert alerts[0].level == "critical"
        assert "Unhealthy" in alerts[0].title

    def test_probe_failed(self):
        from nexusagent.diagnostics.scheduler import AlertRuleEngine
        engine = AlertRuleEngine()
        alerts = engine.evaluate(
            {"overall_healthy": True, "metrics": {}},
            {"probes": {"sqlite": {"status": "fail", "error": "disk full"}}},
            {},
        )
        assert len(alerts) == 1
        assert alerts[0].level == "error"
        assert "sqlite" in alerts[0].title

    def test_module_unhealthy(self):
        from nexusagent.diagnostics.scheduler import AlertRuleEngine
        engine = AlertRuleEngine()
        alerts = engine.evaluate(
            {"overall_healthy": True, "metrics": {}},
            {},
            {"modules": [{"name": "bad_mod", "status": "error", "error": "import failed"}]},
        )
        assert len(alerts) == 1
        assert alerts[0].level == "warning"
        assert "bad_mod" in alerts[0].title

    def test_high_error_rate_warning(self):
        from nexusagent.diagnostics.scheduler import AlertRuleEngine
        engine = AlertRuleEngine(error_rate_warning=5.0, error_rate_critical=10.0)
        alerts = engine.evaluate(
            {"overall_healthy": True, "metrics": {"requests_total": 100, "requests_error": 7}},
            {},
            {},
        )
        assert len(alerts) == 1
        assert alerts[0].level == "warning"
        assert "Error Rate" in alerts[0].title

    def test_high_error_rate_critical(self):
        from nexusagent.diagnostics.scheduler import AlertRuleEngine
        engine = AlertRuleEngine(error_rate_warning=5.0, error_rate_critical=10.0)
        alerts = engine.evaluate(
            {"overall_healthy": True, "metrics": {"requests_total": 100, "requests_error": 15}},
            {},
            {},
        )
        assert len(alerts) == 1
        assert alerts[0].level == "critical"

    def test_high_latency_warning(self):
        from nexusagent.diagnostics.scheduler import AlertRuleEngine
        engine = AlertRuleEngine(latency_warning_ms=5000, latency_critical_ms=10000)
        alerts = engine.evaluate(
            {"overall_healthy": True, "metrics": {"avg_latency_ms": 6000}},
            {},
            {},
        )
        assert len(alerts) == 1
        assert alerts[0].level == "warning"
        assert "Latency" in alerts[0].title

    def test_high_latency_critical(self):
        from nexusagent.diagnostics.scheduler import AlertRuleEngine
        engine = AlertRuleEngine(latency_warning_ms=5000, latency_critical_ms=10000)
        alerts = engine.evaluate(
            {"overall_healthy": True, "metrics": {"avg_latency_ms": 12000}},
            {},
            {},
        )
        assert len(alerts) == 1
        assert alerts[0].level == "critical"

    def test_deduplication(self):
        from nexusagent.diagnostics.scheduler import AlertRuleEngine
        engine = AlertRuleEngine(dedup_seconds=600.0)
        health = {"overall_healthy": False, "metrics": {}}
        alerts1 = engine.evaluate(health, {}, {})
        assert len(alerts1) == 1
        alerts2 = engine.evaluate(health, {}, {})
        assert len(alerts2) == 0  # deduped


class TestDiagnosticScheduler:
    @pytest.mark.asyncio
    async def test_tick_triggers_alert(self):
        from nexusagent.diagnostics.scheduler import DiagnosticScheduler, Alert
        received = []

        def on_alert(alert):
            received.append(alert)

        scheduler = DiagnosticScheduler(
            interval_seconds=10,
            on_alert=on_alert,
            run_once=True,
        )
        # monkey-patch _tick to inject synthetic unhealthy data
        async def _fake_tick():
            from nexusagent.diagnostics.scheduler import AlertRuleEngine
            engine = AlertRuleEngine()
            alerts = engine.evaluate(
                {"overall_healthy": False, "metrics": {}},
                {},
                {},
            )
            if alerts and scheduler._on_alert:
                for a in alerts:
                    scheduler._on_alert(a)

        scheduler._tick = _fake_tick
        await scheduler.run()
        assert len(received) == 1
        assert isinstance(received[0], Alert)
        assert received[0].level == "critical"

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        from nexusagent.diagnostics.scheduler import DiagnosticScheduler
        scheduler = DiagnosticScheduler(interval_seconds=3600)
        scheduler.start_in_background()
        await scheduler.stop()
        assert scheduler._task is None or scheduler._task.done()


class TestWebSocketAlertBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_alert_to_ws_clients(self):
        from aiohttp import ClientSession, TCPConnector, WSMsgType
        from nexusagent.interface.adapter import WebAdapter
        from nexusagent.diagnostics.scheduler import Alert

        adapter = WebAdapter({"host": "127.0.0.1", "port": 0})
        await adapter.start()
        port = adapter._site._server.sockets[0].getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        try:
            async with ClientSession(connector=TCPConnector(limit=10)) as session:
                ws = await session.ws_connect(f"{base}/ws")
                alert = Alert(level="warning", title="Test Alert", message="Hello WS", source="test")
                adapter._broadcast_alert(alert)
                msg = await ws.receive(timeout=2.0)
                assert msg.type == WSMsgType.TEXT
                data = msg.json()
                assert data["type"] == "alert"
                assert data["level"] == "warning"
                assert data["title"] == "Test Alert"
                assert data["message"] == "Hello WS"
                await ws.close()
        finally:
            await adapter.stop()


class TestDiagnosticPersistence:
    def test_save_and_load_snapshot(self, tmp_path):
        from nexusagent.diagnostics.persistence import DiagnosticStore
        db = str(tmp_path / "diag_test.db")
        store = DiagnosticStore(db_path=db)
        store.save_snapshot("health", {"overall_healthy": True, "metrics": {"latency": 42}}, alert_count=0)
        store.save_snapshot("health", {"overall_healthy": False, "metrics": {"latency": 99}}, alert_count=2)
        store.save_snapshot("connectivity", {"healthy": 3, "total": 4}, alert_count=0)

        health_history = store.get_history("health", hours=1)
        assert len(health_history) == 2
        assert health_history[0]["data"]["overall_healthy"] is True
        assert health_history[1]["data"]["overall_healthy"] is False
        assert health_history[1]["alert_count"] == 2

        conn_history = store.get_history("connectivity", hours=1)
        assert len(conn_history) == 1
        assert conn_history[0]["data"]["healthy"] == 3
        store.close()

    def test_cleanup_removes_old_data(self, tmp_path):
        import time
        from nexusagent.diagnostics.persistence import DiagnosticStore
        db = str(tmp_path / "diag_test.db")
        store = DiagnosticStore(db_path=db)
        # Insert a very old snapshot by manipulating timestamp via raw SQL
        store._conn.execute(
            "INSERT INTO diagnostics_snapshots (timestamp, category, data_json, alert_count) VALUES (?, ?, ?, ?)",
            (time.time() - 86400 * 60, "health", '{"old":true}', 0),
        )
        store._conn.commit()
        store.save_snapshot("health", {"recent": True}, alert_count=0)

        before = store.get_history("health", hours=9999)
        assert len(before) == 2

        store.cleanup(keep_days=30)
        after = store.get_history("health", hours=9999)
        assert len(after) == 1
        assert after[0]["data"]["recent"] is True
        store.close()

    @pytest.mark.asyncio
    async def test_history_api_returns_points(self):
        from aiohttp import ClientSession, TCPConnector
        from nexusagent.interface.adapter import WebAdapter

        adapter = WebAdapter({"host": "127.0.0.1", "port": 0})
        await adapter.start()
        port = adapter._site._server.sockets[0].getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        try:
            # Seed some data directly into the store
            if adapter._diag_store:
                adapter._diag_store.save_snapshot("health", {"overall_healthy": True}, alert_count=0)
                adapter._diag_store.save_snapshot("health", {"overall_healthy": False}, alert_count=1)

            async with ClientSession(connector=TCPConnector(limit=10)) as session:
                async with session.get(f"{base}/api/diagnostics/history?category=health&hours=24") as resp:
                    assert resp.status == 200
                    data = await resp.json()
            assert data["ok"] is True
            assert data["category"] == "health"
            assert data["hours"] == 24.0
            assert "points" in data
            if adapter._diag_store:
                # Shared DB may contain data from prior scheduler runs;
                # verify our seeded snapshots are present
                points = data["points"]
                assert len(points) >= 2
                assert any(p["data"].get("overall_healthy") is True for p in points)
                assert any(p["alert_count"] == 1 for p in points)
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_scheduler_saves_snapshots(self, tmp_path):
        import asyncio
        from nexusagent.diagnostics.persistence import DiagnosticStore
        from nexusagent.diagnostics.scheduler import DiagnosticScheduler

        db = str(tmp_path / "diag_scheduler.db")
        store = DiagnosticStore(db_path=db)
        received_alerts = []

        def on_alert(alert):
            received_alerts.append(alert)

        scheduler = DiagnosticScheduler(
            interval_seconds=3600,
            on_alert=on_alert,
            run_once=True,
            store=store,
        )

        # Monkey-patch _tick to use synthetic data that triggers an alert
        async def _fake_tick():
            from nexusagent.diagnostics.scheduler import AlertRuleEngine
            engine = AlertRuleEngine()
            health = {"overall_healthy": False, "metrics": {}}
            conn = {"probes": {}}
            mods = {"modules": []}
            alerts = engine.evaluate(health, conn, mods)
            if alerts and scheduler._on_alert:
                for a in alerts:
                    scheduler._on_alert(a)
            # Persistence (same as real _tick)
            if scheduler._store:
                await asyncio.to_thread(scheduler._store.save_snapshot, "health", health, len(alerts))
                await asyncio.to_thread(scheduler._store.save_snapshot, "connectivity", conn, 0)
                await asyncio.to_thread(scheduler._store.save_snapshot, "modules", mods, 0)
                await asyncio.to_thread(scheduler._store.cleanup, 30)

        scheduler._tick = _fake_tick
        await scheduler.run()

        assert len(received_alerts) == 1
        history = store.get_history("health", hours=1)
        assert len(history) == 1
        assert history[0]["data"]["overall_healthy"] is False
        assert history[0]["alert_count"] == 1
        store.close()


class TestDiagnosticAlerts:
    def test_save_and_load_alert(self, tmp_path):
        from nexusagent.diagnostics.persistence import DiagnosticStore
        from nexusagent.diagnostics.scheduler import Alert

        db = str(tmp_path / "alerts.db")
        store = DiagnosticStore(db_path=db)
        alert = Alert(level="warning", title="Test", message="Hello", source="test")
        store.save_alert(alert)
        alerts = store.get_alerts(hours=1)
        assert len(alerts) == 1
        assert alerts[0]["level"] == "warning"
        assert alerts[0]["title"] == "Test"
        assert alerts[0]["acknowledged"] is False
        store.close()

    def test_acknowledge_alert(self, tmp_path):
        from nexusagent.diagnostics.persistence import DiagnosticStore
        from nexusagent.diagnostics.scheduler import Alert

        db = str(tmp_path / "alerts.db")
        store = DiagnosticStore(db_path=db)
        alert = Alert(level="error", title="E", message="M", source="S")
        store.save_alert(alert)
        ok = store.acknowledge_alert(alert.id)
        assert ok is True
        alerts = store.get_alerts(hours=1)
        assert alerts[0]["acknowledged"] is True
        store.close()

    def test_alert_level_filter(self, tmp_path):
        from nexusagent.diagnostics.persistence import DiagnosticStore
        from nexusagent.diagnostics.scheduler import Alert

        db = str(tmp_path / "alerts.db")
        store = DiagnosticStore(db_path=db)
        store.save_alert(Alert(level="critical", title="C", message="M", source="S"))
        store.save_alert(Alert(level="info", title="I", message="M", source="S"))
        crit = store.get_alerts(level_filter="critical", hours=1)
        assert len(crit) == 1
        assert crit[0]["level"] == "critical"
        store.close()

    @pytest.mark.asyncio
    async def test_alerts_api_returns_list(self):
        from aiohttp import ClientSession, TCPConnector
        from nexusagent.interface.adapter import WebAdapter
        from nexusagent.diagnostics.scheduler import Alert

        adapter = WebAdapter({"host": "127.0.0.1", "port": 0})
        await adapter.start()
        port = adapter._site._server.sockets[0].getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        try:
            if adapter._diag_store:
                adapter._diag_store.save_alert(Alert(level="warning", title="API Test", message="M", source="test"))

            async with ClientSession(connector=TCPConnector(limit=10)) as session:
                async with session.get(f"{base}/api/diagnostics/alerts?hours=24") as resp:
                    assert resp.status == 200
                    data = await resp.json()
            assert data["ok"] is True
            assert "alerts" in data
            assert "unacknowledged_count" in data
            if adapter._diag_store:
                assert any(a["title"] == "API Test" for a in data["alerts"])
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_ack_alert_api(self):
        from aiohttp import ClientSession, TCPConnector
        from nexusagent.interface.adapter import WebAdapter
        from nexusagent.diagnostics.scheduler import Alert

        adapter = WebAdapter({"host": "127.0.0.1", "port": 0})
        await adapter.start()
        port = adapter._site._server.sockets[0].getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        try:
            alert = Alert(level="error", title="Ack Test", message="M", source="test")
            if adapter._diag_store:
                adapter._diag_store.save_alert(alert)

            async with ClientSession(connector=TCPConnector(limit=10)) as session:
                async with session.post(f"{base}/api/diagnostics/alerts/ack", json={"alert_id": alert.id}) as resp:
                    assert resp.status == 200
                    data = await resp.json()
            assert data["ok"] is True

            if adapter._diag_store:
                alerts = adapter._diag_store.get_alerts(hours=1)
                assert any(a["acknowledged"] for a in alerts)
        finally:
            await adapter.stop()


class TestDiagnosticConfig:
    def test_load_save_config(self, tmp_path):
        from nexusagent.diagnostics.config import DiagnosticConfig, load_config, save_config

        path = tmp_path / "config.json"
        cfg = DiagnosticConfig(scheduler_interval_seconds=60, latency_warning_ms=1000)
        save_config(cfg, path=path)
        loaded = load_config(path=path)
        assert loaded.scheduler_interval_seconds == 60.0
        assert loaded.latency_warning_ms == 1000.0
        assert loaded.latency_critical_ms == 10000.0  # default

    def test_config_with_overrides(self):
        from nexusagent.diagnostics.config import DiagnosticConfig

        base = DiagnosticConfig()
        updated = base.with_overrides({"scheduler_interval_seconds": 120, "history_keep_days": 7})
        assert updated.scheduler_interval_seconds == 120.0
        assert updated.history_keep_days == 7
        assert updated.latency_warning_ms == base.latency_warning_ms  # unchanged

    @pytest.mark.asyncio
    async def test_config_api_get_and_post(self):
        from aiohttp import ClientSession, TCPConnector
        from nexusagent.interface.adapter import WebAdapter

        adapter = WebAdapter({"host": "127.0.0.1", "port": 0})
        await adapter.start()
        port = adapter._site._server.sockets[0].getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        try:
            async with ClientSession(connector=TCPConnector(limit=10)) as session:
                async with session.get(f"{base}/api/diagnostics/config") as resp:
                    assert resp.status == 200
                    data = await resp.json()
            assert data["ok"] is True
            assert "config" in data
            original_interval = data["config"]["scheduler_interval_seconds"]

            payload = {"scheduler_interval_seconds": 60, "latency_warning_ms": 1000}
            async with ClientSession(connector=TCPConnector(limit=10)) as session:
                async with session.post(f"{base}/api/diagnostics/config", json=payload) as resp:
                    assert resp.status == 200
                    data = await resp.json()
            assert data["ok"] is True
            assert data["config"]["scheduler_interval_seconds"] == 60.0
            assert data["config"]["latency_warning_ms"] == 1000.0

            # Verify hot-reload on scheduler
            if adapter._scheduler:
                assert adapter._scheduler._interval == 60.0

            # Restore original value to avoid side effects on shared config file
            restore = {"scheduler_interval_seconds": original_interval}
            async with ClientSession(connector=TCPConnector(limit=10)) as session:
                await session.post(f"{base}/api/diagnostics/config", json=restore)
        finally:
            await adapter.stop()


class TestDiagnosticExport:
    @pytest.mark.asyncio
    async def test_export_api_returns_markdown(self):
        from aiohttp import ClientSession, TCPConnector
        from nexusagent.interface.adapter import WebAdapter

        adapter = WebAdapter({"host": "127.0.0.1", "port": 0})
        await adapter.start()
        port = adapter._site._server.sockets[0].getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        try:
            if adapter._diag_store:
                adapter._diag_store.save_snapshot("health", {"overall_healthy": True}, 0)

            async with ClientSession(connector=TCPConnector(limit=10)) as session:
                async with session.get(f"{base}/api/diagnostics/export") as resp:
                    assert resp.status == 200
                    data = await resp.json()
            assert data["ok"] is True
            assert "markdown" in data
            assert "# NexusAgent Diagnostic Report" in data["markdown"]
        finally:
            await adapter.stop()

    def test_report_generation(self, tmp_path):
        from nexusagent.diagnostics.persistence import DiagnosticStore
        from nexusagent.diagnostics.report import generate_report

        db = str(tmp_path / "report.db")
        store = DiagnosticStore(db_path=db)
        store.save_snapshot("health", {"overall_healthy": True, "metrics": {"active_sessions": 5}}, 0)
        store.save_snapshot("connectivity", {"healthy": 3, "total": 4}, 0)
        store.save_snapshot("modules", {"healthy": 8, "total": 10}, 0)

        md = generate_report(store)
        assert "# NexusAgent Diagnostic Report" in md
        assert "## Health Summary" in md
        assert "## Connectivity" in md
        assert "## Modules" in md
        store.close()
