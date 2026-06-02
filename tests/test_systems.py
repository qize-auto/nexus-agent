"""
补充测试: MCP客户端 + 进程池 + 可观测性 + 合规 + 审计 + 并发控制
覆盖: ARC-020, ARC-022, ARC-044, ARC-041/042/043, ARC-033/NFR-084/085,
      ARC-013, ARC-030, NFR-091/092/093
"""

import pytest
import asyncio


class TestMCPClient:
    """ARC-022: MCP客户端"""

    def test_connect_disconnect(self):
        from nexusagent.tools.mcp_client import MCPClient
        async def _t():
            # echo test 不是有效 MCP 服务器，connect 应失败并优雅降级
            client = MCPClient(server_command="echo test")
            ok = await client.connect()
            assert not ok  # 非 JSON-RPC 服务器，连接失败
            assert not client.is_connected
            await client.disconnect()  # 应不抛异常
            assert not client.is_connected
        asyncio.run(_t())

    def test_list_tools(self):
        from nexusagent.tools.mcp_client import MCPClient
        async def _t():
            client = MCPClient()
            await client.connect()
            tools = await client.list_tools()
            assert len(tools) > 0
            assert tools[0]["name"] == "mcp.echo"
        asyncio.run(_t())

    def test_call_tool(self):
        from nexusagent.tools.mcp_client import MCPClient
        async def _t():
            client = MCPClient()
            await client.connect()
            result = await client.call_tool("mcp.echo", {"msg": "hello"})
            assert result["tool"] == "mcp.echo"
        asyncio.run(_t())


class TestProcessPool:
    """ARC-020: 进程池隔离"""

    def test_submit_within_limit(self):
        from nexusagent.tools.guard import ProcessPool

        async def _t():
            pool = ProcessPool(max_workers=2)
            async def task():
                import asyncio
                await asyncio.sleep(0.01)
                return "done"
            r1 = await pool.submit(task())
            r2 = await pool.submit(task())
            assert r1 == "done"
            assert r2 == "done"
        asyncio.run(_t())


class TestObservability:
    """ARC-044: Trace/Metrics/Log"""

    def test_trace_lifecycle(self):
        from nexusagent.cognition.systems import ObservabilityLayer
        obs = ObservabilityLayer()
        tid = obs.start_trace("test_op")
        assert len(tid) > 0
        obs.end_trace(tid)
        # trace should have duration
        traces = obs._traces
        assert len(traces) == 1
        assert "duration_ms" in traces[0]

    def test_metrics_recording(self):
        from nexusagent.cognition.systems import ObservabilityLayer
        obs = ObservabilityLayer()
        obs.record_metric("latency_ms", 100)
        obs.record_metric("latency_ms", 200)
        metrics = obs.get_metrics()
        assert "latency_ms" in metrics
        assert metrics["latency_ms"]["avg"] == 150.0


class TestOCELEngine:
    """ARC-041/042/043: OCEL循环 + 信号检测 + 进化"""

    def test_observe_and_evaluate(self):
        from nexusagent.cognition.systems import OCELEngine, SignalType
        engine = OCELEngine()
        engine.observe(SignalType.ERROR_RATE, 0.1)
        engine.observe(SignalType.LATENCY, 50)
        actions = engine.evaluate()
        assert isinstance(actions, list)

    def test_high_error_triggers_alert(self):
        from nexusagent.cognition.systems import OCELEngine, SignalType
        engine = OCELEngine()
        for _ in range(10):
            engine.observe(SignalType.ERROR_RATE, 1.0)
        actions = engine.evaluate()
        assert len(actions) >= 1


class TestCompliance:
    """ARC-033/NFR-084/085: GDPR + PIPL"""

    def test_right_to_be_forgotten(self):
        from nexusagent.cognition.systems import ComplianceEngine
        async def _t():
            engine = ComplianceEngine()
            result = await engine.right_to_be_forgotten("user_123")
            assert result["status"] == "completed"
        asyncio.run(_t())

    def test_export_data(self):
        from nexusagent.cognition.systems import ComplianceEngine
        async def _t():
            engine = ComplianceEngine()
            result = await engine.export_data("user_123")
            assert "exported_at" in result
        asyncio.run(_t())

    def test_retention_policy(self):
        from nexusagent.cognition.systems import ComplianceEngine
        engine = ComplianceEngine()
        policy = engine.get_data_retention_policy()
        assert policy["encryption"] == "AES-256"
        assert policy["gdpr_compliant"] == True


class TestAuditLogger:
    """ARC-013: 审计日志轮转"""

    def test_log_and_rotate(self):
        from nexusagent.tools.guard import AuditLogger
        import tempfile, os
        tmp = tempfile.mkdtemp()
        logger = AuditLogger(log_dir=tmp, retention_days=90)
        logger.log("TEST_EVENT", "test detail")

        async def _t():
            deleted = await logger.rotate()
            assert deleted >= 0
        asyncio.run(_t())


class TestWriteQueue:
    """ARC-030: 统一写入队列"""

    def test_enqueue_and_process(self):
        from nexusagent.tools.guard import WriteQueue

        async def _t():
            results = []
            def writer(x):
                results.append(x)

            q = WriteQueue()
            await q.start()
            await q.enqueue(writer, "item1")
            await q.enqueue(writer, "item2")
            await asyncio.sleep(0.1)
            await q.stop()
            assert "item1" in results
            assert "item2" in results
        asyncio.run(_t())


class TestConcurrency:
    """NFR-091/092/093: 并发控制"""

    def test_file_lock(self):
        from nexusagent.tools.guard import FileLock

        async def _t():
            lock = FileLock()
            await lock.acquire("/tmp/test")
            lock.release("/tmp/test")
        asyncio.run(_t())

    def test_blackboard_mvcc(self):
        from nexusagent.tools.guard import BlackboardMVCC
        bb = BlackboardMVCC()
        v1 = bb.write("key1", {"data": "v1"})
        v2 = bb.write("key1", {"data": "v2"})
        assert v2 > v1
        assert bb.read("key1")["data"] == "v2"
        assert bb.read("key1", version=1)["data"] == "v1"

    def test_ordered_parallel(self):
        from nexusagent.tools.guard import OrderedParallel

        async def _t():
            op = OrderedParallel()
            results = await op.execute([
                lambda: "a",
                lambda: "b",
                lambda: "c",
            ])
            assert results == ["a", "b", "c"]
        asyncio.run(_t())
