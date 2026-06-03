# NexusAgent Feature Verification Checklist

> Records verification methods and status for all implemented features.
> Last updated: 2026-06-02
> Test baseline: 968 passed, 3 skipped

---

## Features Covered by Automated Tests

The following features are verified by unit/integration tests and require no manual testing:

| Feature | Test File | Status |
|---------|-----------|--------|
| ReAct engine core loop | `test_react_*.py` | 968 tests |
| Tool registry | `test_tool_registry.py` | Pass |
| Multi-model backends (13+ providers) | `test_batch*.py` | Pass |
| Security layer (Guardrails + RBAC) | `test_security*.py` | Pass |
| Memory system (SQLite + ChromaDB) | `test_user_profile.py`, `test_rag_integration.py` | Pass |
| Error self-recovery | `test_error_recovery.py` | Pass |
| Anti-laziness system | `test_anti_compression.py`, `test_completeness.py` | Pass |
| StateGraph engine | `test_stategraph.py` | Pass |
| Diagnostics system | `test_diagnostics_integration.py` | Pass |
| Benchmark framework | `test_benchmark.py` | Pass |
| Regression test framework | `test_regression*.py` | Pass |
| Module registration standardization | `test_bootstrap.py`, `test_core_registry.py` | Pass |
| Dream engine | `test_dream_engine_e2e.py` | 6 tests |
| Self-evolution system | `test_evolution_e2e.py` | 7 tests |
| 5-Expert deliberation | `test_deliberation_e2e.py` | 5 tests |
| Strict execution mode | `test_mode_switch.py`, `test_intent_analyzer.py`, `test_task_decomposer.py`, `test_strict_mode.py` | 75 tests |

---

## Features Requiring Manual Verification

### Web UI / SSE Streaming

**Location**: `nexusagent/interface/adapter.py` — `WebAdapter._handle_stream()`

**Steps**:

1. **Start the web service**
   ```bash
   cd /path/to/nexusagent
   export NEXUS_MASTER_KEY=$(python -c 'import base64,os;print(base64.b64encode(os.urandom(32)).decode())')
   python -c "
   import asyncio
   from nexusagent.interface.adapter import WebAdapter
   adapter = WebAdapter({'port': 8080})
   asyncio.run(adapter.start())
   "
   ```

2. **Test SSE endpoint**
   ```bash
   curl -N "http://localhost:8080/api/stream?message=hello&session=test1"
   ```
   **Expected**: SSE event stream starting with `data:`, ending with `data: [DONE]`

3. **Test Web UI page**
   Open browser at `http://localhost:8080/`
   **Expected**: Interactive interface, message send/receive works

4. **Verification checklist**
   - [ ] SSE connection establishes
   - [ ] `event: start` received
   - [ ] `event: token` or `event: step` intermediate events received
   - [ ] `event: complete` end event received
   - [ ] `data: [DONE]` received at the end
   - [ ] If LLM backend supports `complete_stream`, tokens stream one by one
   - [ ] If LLM backend does not support streaming, fallback to simulated chunked output works

---

### Docker Compose Deployment

**Location**: `docker-compose.yml`

**Steps**:

1. **Check file exists**
   ```bash
   ls docker-compose.yml
   ```

2. **Build image**
   ```bash
   docker-compose build
   ```
   **Expected**: Build succeeds with no errors

3. **Start services**
   ```bash
   docker-compose up -d
   ```
   **Expected**: Containers start normally

4. **Health check**
   ```bash
   curl http://localhost:8080/api/health
   ```
   **Expected**: Returns JSON `{"status": "healthy"}`

5. **Send test message**
   ```bash
   curl -X POST http://localhost:8080/api/message \
     -H "Content-Type: application/json" \
     -d '{"message": "hello", "session_id": "test"}'
   ```
   **Expected**: Returns JSON with `content` field

6. **Stop services**
   ```bash
   docker-compose down
   ```

---

### Multi-Channel Adapters (Telegram / Discord / Feishu)

**Location**: `nexusagent/interface/multi_channel.py`

**Prerequisite**: Real Bot Token / Webhook URL required

**Steps**:

#### Telegram
1. Create bot via `@BotFather`, get token
2. Configure `config.yaml`:
   ```yaml
   channels:
     enabled_channels: ["telegram"]
     telegram:
       token: "your-token"
   ```
3. Start agent
4. Send message to bot in Telegram
5. **Expected**: Bot replies

#### Discord
1. Create bot in Discord Developer Portal, get token
2. Configure `config.yaml`
3. Start agent
4. @bot in Discord and send message
5. **Expected**: Bot replies

#### Feishu
1. Create robot in Feishu Open Platform, get webhook_url
2. Configure `config.yaml`
3. Start agent
4. @robot in Feishu and send message
5. **Expected**: Robot replies

---

### MCP Server

**Location**: `nexusagent/tools/mcp_server.py`

**Steps**:

```bash
# Start MCP Server
python -m nexusagent.cli.main mcp

# Test from another terminal (using mcp-cli or similar)
# Expected: NexusAgent tool list visible
```

---

## Known Limitations

| Limitation | Description | Plan |
|------------|-------------|------|
| Strict mode clarification loop | Currently returns clarification prompt directly instead of multi-round StateGraph loop | Interactive clarification in future version |
| Web UI manual verification | SSE logic verified by code review but not tested in real browser | Verify via Section 2.1 steps |
| Docker deployment | Compose file syntax verified but not actually built and run | Verify via Section 2.2 steps |
| External channels | Requires real API tokens, cannot be tested in automation | Verify via Section 2.3 steps |
