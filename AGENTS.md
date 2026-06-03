# NexusAgent — Agent Development Guide

## Project Background

NexusAgent v3.3 is a local-first AI agent system for individual users. Design goals: multi-channel access, multi-model support, and an extensible tool ecosystem, all while preserving data privacy and security.

## Tech Stack

- **Backend**: Python 3.10+, asyncio, aiohttp, SQLite
- **Desktop Client**: Electron (Node.js) + pure HTML/CSS/JS frontend
- **Security**: cryptography (Fernet/AES-256), PBKDF2, SHA-256
- **Data**: Pydantic v2, YAML, JSON
- **Testing**: pytest, pytest-asyncio, pytest-cov

## Code Standards

1. **Type annotations**: All public functions must have type annotations, use `from __future__ import annotations`
2. **Async-first**: IO operations must use `async/await`; blocking operations offloaded via `run_in_executor`
3. **Error handling**: No silently swallowing exceptions; log and return structured errors
4. **Security by default**: All data collection off by default, PII redacted by default, high-risk tools sandboxed
5. **Zero TODO delivery**: Remove all `TODO`, `pass`, `...` placeholders before committing

## Key Constraints

- **Monthly cost cap**: Default $100/month, configurable
- **First response SLA**: < 2s (< 500ms with local cache hit)
- **Data retention**: Default 90 days, GDPR Article 17 right to erasure supported
- **Encryption**: AES-256-GCM (via Fernet), PBKDF2 600k iterations
- **Sandbox**: Docker preferred, fallback to restricted subprocess (no network, dangerous modules disabled)

## Build & Run

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests (must pass)
pytest tests/ -v

# CLI mode
python run_cli.py

# Web mode
python run_web.py

# Desktop mode
npm install && npm start
```

## Architecture Assumptions

- [ASSUMPTION] Architecture design doc (`.docx`) cannot be auto-extracted; all implementations inferred from "Design Doc Chapter X" references in code comments
- [ASSUMPTION] Production deployment should use Docker for full sandbox isolation
- [ASSUMPTION] LLM API keys provided by user via `.env` file; no default keys built in

## File Modification Log

### 2025-05-31: Fix orchestrator.py duplicate ReAct execution bug
- Reuse REVER-captured results during output review phase

### 2025-05-31: Fix run_web.py path traversal vulnerability
- `..` filtering + `resolve()` validation

### 2025-05-31: Enhance sandbox.py fallback logic
- Use restricted subprocess + module blacklist when Docker unavailable

### 2025-05-31: Enhance config/settings.py robustness
- Ignore unknown fields during config parsing

### 2025-05-31: Enhance models/router.py
- Add `complete_with_fallback` unified fallback interface

### 2025-05-31: Full Electron desktop client rebuild
- Modern UI, system tray, hotkeys, notifications

### 2025-05-31: Add Moonshot API support
- `MoonshotLLMBackend` + `.env.example` + desktop model selector

### 2025-05-31: Comprehensive audit — 14 fixes

**Critical bugs fixed (6)**
1. `security/sandbox.py`: Fix `_docker_test` duration calculation (used `time.time()` instead of `start`)
2. `security/guardrails.py`: Fix `ReviewResult.is_allowed` returning `False` for YELLOW (should allow with monitoring)
3. `main.py`: Fix `_CheckpointAdapter` creating separate `MemoryStore` causing connection leak (reuse main store)
4. `run_web.py`: Fix static file server using `read_text()` for binary files (PNG/JPG/ICO) corrupting content
5. `cognition/systems.py`: Fix `ComplianceEngine.right_to_be_forgotten` confusing `session_id` with `user_id`; add `MemoryStore.delete_by_user()` for actual deletion
6. `memory/store.py`: Fix `cleanup_expired()` not cleaning FTS5 virtual table orphan data

**Feature fixes (5)**
7. `desktop/app.js`: Fix PyQt6 mode `checkBackendHealth()` doing HTTP fetch causing "offline" status
8. `memory/store.py`: Fix `search_fts()` not catching `sqlite3.OperationalError` (FTS5 syntax errors crash queries)
9. `tools/layer.py`: Fix `_is_sandbox_available()` only checking if `docker` module is importable, not if daemon is connectable
10. `desktop/main_window.py`: Fix missing system tray icon on Windows (blank icon) — generate solid fallback icon
11. `desktop/launch.py`: Fix PyQt6 desktop launch not loading project `.env` environment variables

**Architecture improvements (3)**
12. `main.py`: Extract `_create_llm()` unified factory method, eliminate duplicate backend creation in `__init__` and `reload_llm`
13. `config/settings.py` + `run_*.py`: Unify `.env` loading entry `load_project_env()`, eliminate 4 duplicate code locations
14. `memory/store.py` + `main.py`: Integrate `MemoryEncryption` (AES-256) — memory content auto-encrypted, FTS5 index kept plaintext for search
15. `models/router.py`: `DeepSeekLLMBackend` / `MoonshotLLMBackend` lazy-load reuse `aiohttp.ClientSession`
16. `orchestration/orchestrator.py`: Convert `REVERResult` dynamic attribute `_captured_output` to formal dataclass field `captured_output`

### 2025-05-31: Deep fix — stub/placeholder implementations replaced with real ones

**1. `tools/mcp_client.py` — Real MCP protocol client**
- Rewritten from empty shell to real stdio client using `mcp` package
- `StdioServerParameters` + `stdio_client` + `ClientSession` for JSON-RPC 2.0
- Support `initialize` handshake, `list_tools`, `call_tool`
- `contextlib.AsyncExitStack` for connection lifecycle
- Graceful offline fallback on failure

**2. `memory/store.py` — sqlite-vec vector search integration**
- Load `sqlite-vec` extension in `_init_db()` (auto-degrade on failure)
- Add `memories_vec` virtual table (`vec0(embedding float[1536])`)
- Auto-sync to vector table when `MemoryEntry.embedding` present
- `search_vector(embedding, limit)` — KNN similarity search via sqlite-vec
- Sync cleanup in `cleanup_expired()` / `delete_by_session()` / `delete_by_user()`

**3. `cognition/systems.py` — `HybridSearch` real implementation**
- Rewritten from hardcoded example data to real `MemoryStore`-based search
- `search()` → `MemoryStore.search_fts()` for FTS5 full-text
- `vector_search()` → `MemoryStore.search_vector()` for vector search
- `hybrid_search()` → **RRF (Reciprocal Rank Fusion)**: `score = Σ 1/(60+rank)`
- Supports pure text, pure vector, and hybrid query modes

**4. `interface/adapter.py` — `WebAdapter` full implementation**
- aiohttp-based HTTP REST + WebSocket dual-mode web layer
- Endpoints: `/ws`, `/api/chat`, `/api/health`, `/api/config`
- Static file service with safe path validation, binary file support
- `register_message_callback()` for Orchestrator unified handler
- `send()` broadcasts to all WebSocket clients

**5. `run_web.py` — Refactored to WebAdapter-driven**
- Simplified launch script using `WebAdapter`
- All access layer logic unified in `interface/adapter.py`

**6. `main.py` + `execution/react_engine.py` — Dollar cost budget enforcement**
- `ReActEngine` adds `cost_enforcer` and `cost_per_1k_tokens`
- Auto-estimate cost per call: `tokens × cost_per_1k / 1000`
- Return `COST_BUDGET_EXHAUSTED` and halt if budget exceeded
- Model-specific pricing in `main.py` initialize()
- Close `aiohttp.ClientSession` in `shutdown()`

### 2025-06-01: MiroFish collective intelligence collaboration system — 6 modules

**Modules (`mirofish/`)**
1. `scheduler.py` — Collective intelligence scheduler, `run(task, max_rounds)`
2. `agents.py` — 6 simulation roles: Moderator/Expert/Reviewer/Resource/Timer/Recorder
3. `message.py` — Structured Message / RoundResult / SimulationSummary
4. `consensus.py` — Borda count + majority + threshold pass
5. `persistence.py` — SQLite persistence for Round/Summary/Report
6. `integration.py` — MessageBus events + Orchestrator callback

**Optimizations**
- `max_agents` load balancing
- MessageBus events: `SIMULATION_STARTED`, `ROUND_COMPLETED`, `CONSENSUS_REACHED`
- 29 tests, 400 total passed

### 2025-06-01: User profile dynamic evolution system — full implementation

**Core modules**
1. `profile/manager.py` — `UserProfileManager` persistence + confidence threshold writes
2. `profile/profiler.py` — `UserProfiler` real-time message feature extraction (8 signal types)
3. `profile/dream.py` — `DreamEngine` nightly self-reflection profile evolution

**Adapters (`profile/adapters/`)**
- `llm.py`, `database.py`, `tool.py`, `memory.py`, `cognition.py`, `orchestration.py`

**CLI extensions**
- `nexus profile` — view/edit/export user profile
- `nexus dream` — trigger manual self-reflection

**Tests**: 19 profile tests, 419 total passed

### 2025-06-01: Anti-Laziness execution guard system — 5 interception points

**Goal**: Prevent agent from slacking/skipping steps/compressing output/pretending to forget

**5 Interception Points**
1. Post-strategy-selection → `ExecutionTracker` records task steps and evidence
2. Pre-tool-call → `ForcedChunkedReader` enforces chunked reading of large files
3. Post-tool-call → `ExecutionTracker` records tool call evidence
4. Pre-output-review → `AntiCompressionDetector` + `CompletenessValidator` detect compression and incompleteness
5. Pre-REVER-evaluate → `WorkMemory` persists context to prevent fake amnesia

**Core modules (`execution/`)**
1. `tracker.py` — `ExecutionTracker` / `TaskContext` / `Step` / `Evidence` / `@track_execution`
2. `anti_compression.py` — `AntiCompressionDetector` (5 compression pattern types)
3. `completeness.py` — `CompletenessValidator` (missing steps/code/files/length)
4. `chunked_reader.py` — `ForcedChunkedReader` (prevents TL;DR)
5. `work_memory.py` — `WorkMemory` (execution snapshot persistence + loop detection + retry prompt generation)

**Integration**
- `Orchestrator._execute_core()` — extracted core execution logic
- `Orchestrator.process()` — auto-retry on quality failure (max 2), WorkMemory injects history hints
- `main.py` — initializes all 5 anti-laziness components and passes to Orchestrator

**Tests**: 60+ anti-laziness tests, 521 total passed

### 2025-06-01: Tool capability audit and completion — full execution and editing coverage

**Audit scope**: All tools in `tools/` against 17 required capabilities checklist

**Existing tool status**
| Tool | Status | Notes |
|------|--------|-------|
| `browser.visit` | Available | Playwright/requests dual-mode, SSRF protection |
| `code_interpreter.execute` | Available | E2B sandbox preferred, local fallback (needs `NEXUS_ALLOW_LOCAL_EXECUTION`) |
| `MockToolRegistry` (read/write/search) | Not registered | Exists in `layer.py` but **not in ToolRegistry**, ReActEngine cannot call |

**Completed tools**

P0 (blocking — completed)
| Tool | Class | Security |
|------|-------|----------|
| `file.read` | `FileReadTool` | Path traversal protection |
| `file.read_binary` | `FileReadBinaryTool` | base64 return, 1MB limit |
| `file.write` | `FileWriteTool` | Needs `NEXUS_ALLOW_FILE_OPS=1` |
| `file.list` | `FileListTool` | Path traversal protection |
| `file.move` | `FileMoveTool` | Needs `NEXUS_ALLOW_FILE_OPS=1` |
| `file.delete` | `FileDeleteTool` | Needs `NEXUS_ALLOW_FILE_OPS=1` |
| `shell.execute` | `ShellExecuteTool` | Needs `NEXUS_ALLOW_SHELL=1`, dangerous command blacklist, 30s timeout |
| `code.search_replace` | `CodeSearchReplaceTool` | Needs `NEXUS_ALLOW_FILE_OPS=1` |
| `code.insert` | `CodeInsertTool` | Needs `NEXUS_ALLOW_FILE_OPS=1` |
| `code.delete` | `CodeDeleteTool` | Needs `NEXUS_ALLOW_FILE_OPS=1` |

P1 (serious — completed)
| Tool | Class | Security |
|------|-------|----------|
| `api.request` | `APIRequestTool` | SSRF protection (blocks internal/local addresses) |

P2 (general — completed)
| Tool | Class | Security |
|------|-------|----------|
| `archive.pack_unpack` | `ArchiveTool` | Needs `NEXUS_ALLOW_FILE_OPS=1`, Zip/Tar Slip protection |
| `database.query` | `DatabaseTool` | SQLite only, DDL/DML writes need `NEXUS_ALLOW_FILE_OPS=1` |

**Registration & connectivity**
- `tools/registry.py` `_builtin_modules` expanded to include all 10 built-in modules
- `ToolRegistry.discover_builtin_tools()` auto-discovers all tools
- ReActEngine gets full tool descriptions via `describe_tools()` for LLM selection
- End-to-end verified: `read → edit → shell execute → write` chain passes (`test_tools_end_to_end.py`)

**Test coverage**
- `test_tools_file_ops.py` — 20 tests
- `test_tools_shell.py` — 8 tests
- `test_tools_code_edit.py` — 16 tests
- `test_tools_api_client.py` — 10 tests
- `test_tools_archive.py` — 4 tests
- `test_tools_database.py` — 5 tests
- `test_tools_end_to_end.py` — 4 tests
- **67 new tool tests, 592 total passed, zero regression**

**Final statement**: NexusAgent now has complete execution, editing, code modification, and software operation capabilities. All tools are registered and available.

### 2025-06-01: MiroFishScheduler communication & load balancing optimization

**Original issues**
1. `_collect_bids` / `_simulate_execution` were internal direct calls, not using expanded MessageBus
2. `_assign_tasks` only had per-round linear penalty `round_assigned * 0.15`, no cross-round accumulation, no concurrency cap

**Communication layer refactor**
- Added `communication_mode` parameter (`"direct"` default / `"messagebus"`)
- New MessageBus topics: `BID_REQUEST`, `BID_RESPONSE`, `EXECUTE_REQUEST`, `EXECUTE_RESPONSE`
- `_collect_bids()` keeps sync backward compatibility; `run()` selects `_collect_bids_direct()` / `await _collect_bids_bus()` by mode
- `_simulate_execution()` branches: `_simulate_execution_direct()` / `_simulate_execution_bus()`
- `_setup_bus_handlers()` lazy-loads bid/execute request/response handlers per agent
- Serialization reuses existing `AgentMessage.payload`

**Load balancing enhancement**
- 3D penalty model:
  - Round penalty: `round_assigned * 0.15` (existing)
  - Historical accumulation: `total_assignments * 0.05 * exp(-0.1 * rounds_since)` (new, exponential decay)
  - Concurrency cap: `max(2, tasks_per_hour // 2)` (new, hard truncation)
- Modified `_assign_tasks(bids, round_num)` interface (added optional `round_num` for decay)

**Tests**
- `test_mirofish_optimization.py` — 12 tests
  - MessageBus bid collection, execution, full run, backward compatibility
  - Load balancing concentration check (<70%), accumulation penalty decay, concurrency cap, multi-round assignment
- Original `test_mirofish.py` — 29 tests all pass
- **604 total passed, zero regression**

**Legacy items**
- MessageBus mode not enabled by default (`communication_mode="direct"`) — distributed deployment not yet a production requirement
- Enable: `MiroFishScheduler(bus=MessageBus(), communication_mode="messagebus")`

**Final confirmation**: MiroFishScheduler now supports configurable MessageBus communication and load balancing. All tests pass, no regression.

### 2025-06-02: UI diagnostics & comparison integration — 5 phases

**Goal**: Unified, deep, visual system health diagnostics across Desktop / Web / CLI

**Phase 1 — UI Entry**
- Desktop: sidebar "Diagnostics" button + drawer dashboard
- Web: diag-bar quick diagnostic buttons (Health / Connectivity / Audit / Modules / UX / Design Diff / Competitor)

**Phase 2 — Backend diagnostics deepening**
- `diagnostics/collector.py` — shared diagnostic collector
  - `collect_health()`: backends / security / execution / memory / system / adapter 6-dimension health
  - `collect_connectivity()`: tool_registry / modules / probes (sqlite / filesystem / llm_backend / memory_store)
  - `collect_audit()`: real audit logs + security interception stats
  - `collect_modules()`: module import + deep health check
  - `collect_ux()`: real metric-driven UX scoring
- `interface/adapter.py` — 7 diagnostic handlers delegate to collector, reduced from ~600 to ~80 lines

**Phase 3 — Frontend visualization**
- Dashboard HTML rendering: cards/tables/progress bars/badges
- Health: status matrix + backend table + system info
- Connectivity: health ratio + probe list
- Modules: status table + deep details
- Audit: interception stats + audit log table
- UX: score ring + checklist + suggestion cards
- Design Diff: change stats + 3-column comparison
- Competitor: matrix comparison + strength/weakness analysis

**Phase 4 — CLI alignment**
- `nexus doctor` — colored terminal diagnostic report
- `nexus doctor --json` — structured JSON output
- CLI and Web share `diagnostics/collector.py`, zero duplicate code

**Phase 5 — Diagnostic automation (WebSocket real-time alerts)**
- `diagnostics/scheduler.py`:
  - `AlertRuleEngine` — 5 rules (overall_healthy / probe failed / module error / error_rate / latency)
  - `DiagnosticScheduler` — scheduled background patrol, default 5-minute interval
  - Alert deduplication — same alert not pushed again within 10 minutes
- `interface/adapter.py` — `_broadcast_alert()` broadcasts to all WebSocket clients
- Desktop frontend:
  - `initWebSocket()` — WebSocket connection, 5s auto-reconnect on disconnect
  - `showAlertToast()` — floating alert notifications (critical/error/warning/info 4 levels)
  - `.alert-toast` CSS — slide in/out animation + auto-dismiss

**Phase 6 — Diagnostic data persistence**
- `diagnostics/persistence.py` — `DiagnosticStore` (SQLite WAL, reuses nexus_memory.db)
  - `save_snapshot(category, data, alert_count)` — insert snapshot
  - `get_history(category, hours)` — time range query, returns time series
  - `cleanup(keep_days)` — auto cleanup (default 30 days)
- `diagnostics/scheduler.py` — `_tick()` writes health/connectivity/modules snapshots via `asyncio.to_thread`
- `interface/adapter.py` — `/api/diagnostics/history` returns `{ok, category, hours, points: [{timestamp, data, alert_count}]}`
- Desktop frontend:
  - History section — category/hours selector + Load button
  - `renderHistoryChart()` — pure CSS bar chart, smart downsample to 24 bars, color grading (green/yellow/red)
  - `renderHistoryTable()` — last 10 snapshots table
- Web UI — sync History button + chart rendering

**Extension — Real-time auto-refresh**
- Desktop: Diagnostics drawer auto-refetches every 30s when open
  - `autoRefreshEnabled` state, localStorage persistence
  - drawer header Auto-refresh toggle checkbox
  - `refreshCurrentDiagnostic()` — silent refresh, no button state flicker
- Web UI: diag-bar Auto-refresh toggle
  - `runDiagSilent()` — updates last diagnostic message in place, no duplicate appending
  - Auto-resets timer on diagnostic type switch

**Extension — Alert history page**
- `diagnostics/persistence.py` — `diagnostics_alerts` table
  - `save_alert(alert)` — alert persistence
  - `get_alerts(level_filter, hours, limit, acknowledged)` — multi-dimensional filtering
  - `acknowledge_alert(alert_id)` — mark as read
  - `count_unacknowledged_alerts(hours)` — unread count
- `diagnostics/scheduler.py` — `_tick()` writes to store on alert trigger
- `interface/adapter.py`:
  - `/api/diagnostics/alerts` — alert list (supports level/hours/limit/acknowledged filters)
  - `/api/diagnostics/alerts/ack` (POST) — mark as read
- Desktop frontend:
  - Diagnostics drawer new **Alerts** section
  - Level filter buttons (All / Critical / Error / Warning / Info)
  - Alert table: time, level badge, title, source, Ack button
  - Sidebar Diagnostics button shows unread alert count badge
- Web UI: diag-bar new Alerts button

**Extension — Diagnostic config panel**
- `diagnostics/config.py` — `DiagnosticConfig` dataclass
  - `scheduler_interval_seconds` / `latency_warning_ms` / `latency_critical_ms`
  - `error_rate_warning` / `error_rate_critical`
  - `history_keep_days` / `alerts_keep_days`
  - `load_config()` / `save_config()` / `with_overrides()`
- `interface/adapter.py`:
  - `/api/diagnostics/config` (GET) — current config
  - `/api/diagnostics/config` (POST) — save and hot-reload scheduler interval
- Desktop frontend:
  - Settings drawer new **Diagnostics** section
  - 7-item config form + save button

**Extension — Report export**
- `diagnostics/report.py` — `generate_report(store)` generates Markdown report
  - Title page, Health/Connectivity/Modules summary, 24h alert stats, history trends, suggestion list
- `interface/adapter.py` — `/api/diagnostics/export` (GET) returns Markdown
- `cli/main.py` — `nexus doctor --export <path>` exports to file
- Desktop frontend:
  - Diagnostics drawer new **Export** section
  - Format selector (Markdown / JSON) + Export button triggers download
- Web UI: diag-bar new Export button

**Tests**: 37 diagnostic tests (API 12 + RuleEngine 8 + Scheduler 2 + WebSocket 1 + Persistence 4 + Alerts 5 + Config 3 + Export 2), all pass, zero regression
