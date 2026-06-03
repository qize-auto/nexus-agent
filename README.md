<div align="center">

<h1>NexusAgent</h1>

<p><strong>An AI agent framework that executes tasks with the rigor of a senior engineer.</strong></p>

<p>
  <a href="https://github.com/qize-auto/nexus-agent/actions"><img src="https://img.shields.io/badge/tests-968%20passed-brightgreen?style=flat-square&logo=pytest&logoColor=white" alt="Tests"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue?style=flat-square" alt="License"></a>
</p>

</div>

---

## The Problem

Most AI agents today are great at *starting* tasks. They break problems down, invoke tools, and produce output. But they are terrible at *finishing* with confidence:

- They skip steps when outputs get long.
- They miss files when refactoring across a codebase.
- They guess when a user's request is ambiguous.
- They never verify whether what they did actually worked.
- They treat a 50-line task the same as a 5,000-line project.

**NexusAgent is built on the belief that an agent should work like a senior engineer:** clarify before building, verify after every step, and deliver a report you can audit.

---

## What Makes It Different

### 1. Strict Execution Mode

Not every message is a task. NexusAgent analyzes intent first. If it's a task, it enters **Strict Mode**:

```
User: "Refactor the auth module to use async"

NexusAgent:
  1. Intent Analysis   → "This is a refactoring task, target: auth.py"
  2. Ask if unclear    → "Which auth module: server/auth.py or client/auth.py?"
  3. Decompose         → [Analyze] → [Refactor] → [Test] → [Verify]
  4. 5-Expert Review   → Architect + Security + PM + QA + Ops debate the plan
  5. Execute & Verify  → Run each step, verify before next
  6. Reflect & Retry   → On failure, analyze root cause and replan
  7. Deliver Report    → Markdown: what changed, why, how to verify
```

If it's just chat ("How's the weather?"), it skips all of this and replies naturally.

### 2. It Thinks While You Sleep

- **DreamEngine**: When idle, the agent consolidates your user profile — merging preferences, resolving conflicts, and forgetting outdated traits.
- **EvolutionEngine**: Periodically analyzes runtime metrics and proposes configuration optimizations. High-confidence changes auto-deploy; low-confidence ones wait for your approval.

### 3. Anti-Laziness Guards

Built-in mechanisms detect and recover from sloppy execution:

| Guard | What It Catches |
|-------|-----------------|
| `AntiCompression` | Output truncation, skipped reasoning steps |
| `CompletenessValidator` | Missed files, incomplete refactors |
| `ErrorRecovery` | Tool failures → auto-switch tool, retry, or escalate |
| `ExecutionTracker` | Every step timed, costed, and logged |

### 4. Modular by Design

55+ core modules register through a unified `ModuleRegistry`. Dependencies are topologically sorted and initialized automatically. Each module exposes its own `health_check()` — if one fails, the system degrades gracefully instead of crashing.

---

## Quick Start

```bash
# Clone
git clone https://github.com/qize-auto/nexus-agent.git
cd nexus-agent

# Install
pip install -e .

# Set master key (auto-generated if omitted)
export NEXUS_MASTER_KEY=$(python -c 'import base64,os;print(base64.b64encode(os.urandom(32)).decode())')

# Run
python -m nexusagent.main
```

Then type any task. The agent decides whether to enter **Strict Mode** (for tasks) or **Chat Mode** (for conversation).

### Switch Modes Manually

```bash
nexus mode strict    # Force strict execution
nexus mode chat      # Force chat mode
nexus mode auto      # Auto-detect (default)
nexus mode status    # Show current settings
```

---

## Architecture

NexusAgent is organized in **seven layers**. Each layer is independent — you can use the ReAct engine without the web UI, or the memory layer without the evolution system.

```
┌─────────────────────────────────────────────────────────────────┐
│                         INPUT LAYER                              │
│    CLI │ Web UI (PWA) │ Desktop │ Telegram │ Discord │ Feishu    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                       SECURITY LAYER                             │
│         Guardrails │ RBAC │ Injection Detection │ Sandbox        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      STRATEGY ROUTER                             │
│              MiroFish Scheduler ── Complexity Detection          │
│     Simple │ Multi-agent │ Simulation │ Team │ Deep Reasoning    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      EXECUTION LAYER                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────────┐ │
│  │  ReAct   │  │  Swarm   │  │   Crew   │  │  StateGraph +   │ │
│  │  Engine  │  │          │  │          │  │  Deliberation   │ │
│  └──────────┘  └──────────┘  └──────────┘  └─────────────────┘ │
│                              ↓                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              STRICT EXECUTION PIPELINE                    │  │
│  │  Intent → Clarify → Decompose → 5-Expert → Execute      │  │
│  │         → Verify → Reflect → Retry → Deliver            │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      SAFETY LAYER                                │
│     AntiCompression │ Completeness │ ErrorRecovery │ Tracker    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                       MEMORY LAYER                               │
│    SQLite Store │ ChromaDB Vector │ User Profile │ Encryption    │
│                              ↓                                   │
│                         DreamEngine                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     EVOLUTION LAYER                              │
│    EvolutionEngine ── A/B Test ── HITL Approval ── Rollback     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     OBSERVABILITY                                │
│       Audit Log │ Health Check │ Benchmark │ Regression Suite    │
└─────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Local-first** | Your data stays on your machine. Cloud is optional, not mandatory. |
| **Async everywhere** | All I/O-bound operations are `async`. No `run_until_complete()` hacks. |
| **Fail-soft** | Every optional component (Evolution, Dream, Strict Mode) initializes in a try/except. If it fails, the core agent still works. |
| **Zero config** | Sensible defaults for everything. Override via `config.yaml` or env vars only when needed. |

---

## Feature Matrix

| Feature | Status | Notes |
|---------|--------|-------|
| Strict Execution Mode | ✅ v4.0+ | Intent analysis → clarification → decomposition → 5-expert review → execute/verify → reflect → deliver |
| DreamEngine (idle profile processing) | ✅ v4.0+ | Auto-triggers after 30s of user inactivity |
| EvolutionEngine (self-optimization) | ✅ v4.0+ | Three modes: off / notify / auto |
| Anti-Laziness Guards | ✅ v4.0+ | AntiCompression + CompletenessValidator + ErrorRecovery |
| Multi-Strategy Routing | ✅ v3.3+ | ReAct / Swarm / MiroFish / Crew / StateGraph |
| 5-Expert Deliberation | ✅ v4.0+ | Architect, Security, PM, QA, Ops |
| Tool Registry | ✅ v4.0+ | 55+ tools, unified registration standard |
| Memory System | ✅ v3.3+ | SQLite + ChromaDB + user profiles, AES-256 encrypted |
| LLM Provider Support | ✅ v3.3+ | DeepSeek, Moonshot, OpenAI, Claude, Gemini, Azure, Groq, Ollama, ... |
| Multi-Channel | ✅ v3.3+ | CLI / Web / Desktop / Telegram / Discord / Feishu |
| SSE Streaming | ✅ v4.0+ | Real-time token streaming via `/api/stream` |
| Observability | ✅ v4.0+ | Audit logs, `nexus doctor`, benchmark framework |
| MCP Server | ✅ v4.0+ | Expose tool registry as MCP server |

---

## LLM Providers

| Region | Provider | Env Var | Models |
|--------|----------|---------|--------|
| 🇨🇳 Domestic | **DeepSeek** | `DEEPSEEK_API_KEY` | deepseek-chat, deepseek-v4-pro |
| 🇨🇳 Domestic | **Moonshot** | `MOONSHOT_API_KEY` | moonshot-v1-8k/32k/128k |
| 🇨🇳 Domestic | **Qwen** | `DASHSCOPE_API_KEY` | qwen-max, qwen-plus |
| 🇨🇳 Domestic | **Wenxin** | `QIANFAN_API_KEY` | ernie-bot |
| 🇨🇳 Domestic | **GLM** | `ZHIPU_API_KEY` | glm-4 |
| 🇨🇳 Domestic | **Ollama** | — | llama3.2, qwen2.5, ... (local) |
| 🌍 International | **OpenAI** | `OPENAI_API_KEY` | gpt-4o, gpt-4o-mini |
| 🌍 International | **Anthropic** | `ANTHROPIC_API_KEY` | claude-3-5-sonnet |
| 🌍 International | **Google** | `GOOGLE_API_KEY` | gemini-1.5-pro |
| 🌍 International | **Azure** | `AZURE_OPENAI_API_KEY` | azure/gpt-4o |
| 🌍 International | **Groq** | `GROQ_API_KEY` | llama-3.3-70b |

Runtime hot-swap:

```python
agent.reload_llm("deepseek", "deepseek-chat")
agent.reload_llm("anthropic", "claude-3-5-sonnet")
agent.reload_llm("ollama", "llama3.2")
```

---

## CLI Commands

```bash
nexus mode <auto|strict|chat|status>     # Execution mode
nexus evolution <status|review|run>       # Self-evolution system
nexus dream now                            # Trigger dream cycle
nexus tool <ls|info|search>                # Tool management
nexus profile <show|learn|forget>          # User profiling
nexus backup <create|list|restore>         # Memory backup
nexus benchmark                            # LLM benchmark
nexus doctor                               # Full diagnostics
```

---

## Testing

```bash
pytest tests/
```

**Current baseline:** `968 passed, 3 skipped`

| Test Category | Count | Scope |
|---------------|-------|-------|
| Unit tests | 600+ | Core engine, security, memory, tools |
| Integration tests | 100+ | ReAct, RAG, multi-model, streaming |
| End-to-end tests | 18 | DreamEngine, Evolution, Deliberation |
| Regression tests | 50+ | Cross-version compatibility |

---

## Project Structure

```
nexus-agent/
├── nexusagent/
│   ├── execution/          # ReAct, StateGraph, Strict Mode, Anti-Laziness
│   ├── orchestration/      # Orchestrator, MiroFish Scheduler
│   ├── security/           # Guardrails, RBAC, Sandbox
│   ├── memory/             # SQLite, ChromaDB, Profiles, Backup
│   ├── agents/             # AgentSwarm, AgentCrew
│   ├── tools/              # Tool registry, 55+ built-in tools
│   ├── interface/          # CLI, Web, Multi-channel adapters
│   ├── cognition/          # DreamEngine, UserProfiler
│   ├── evolution/          # EvolutionEngine, A/B Test, HITL
│   ├── models/             # Model router, 13+ provider backends
│   ├── benchmark/          # Performance benchmark framework
│   ├── diagnostics/        # Health check, diagnostics
│   └── core/               # Module registry, bootstrap
├── tests/                  # 968 tests
├── docs/                   # Documentation
├── desktop/                # PWA desktop client
├── templates/              # Module scaffolding templates
├── docker-compose.yml      # Docker deployment
└── README.md               # This file
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [`docs/QUICKSTART.md`](docs/QUICKSTART.md) | Full quickstart guide |
| [`docs/VERIFICATION_CHECKLIST.md`](docs/VERIFICATION_CHECKLIST.md) | Feature verification & manual testing steps |
| [`STABILIZATION_PLAN.md`](STABILIZATION_PLAN.md) | Risk assessment & stabilization roadmap |
| [`AGENTS.md`](AGENTS.md) | Coding conventions for agent developers |

---

## Contributing

1. Fork the repository
2. Create a branch: `git checkout -b feature/amazing-feature`
3. Commit: `git commit -m 'Add amazing feature'`
4. Push: `git push origin feature/amazing-feature`
5. Open a Pull Request

**Requirements:**
- All tests must pass (`pytest tests/` → 968+ passed)
- New features need unit tests + integration tests
- No async/sync mixing. No bare `except Exception`.

---

## License

[Apache License 2.0](LICENSE)
