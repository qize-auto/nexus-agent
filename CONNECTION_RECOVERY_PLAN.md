# NexusAgent 未接入模块深度调研与分批修复方案

> **版本**: v0.1.0-connection-recovery  
> **日期**: 2026-06-02  
> **状态**: 深度调研完成，待分批执行  
> **铁律**: 每批修改后必须运行全量测试（604 passed），任何失败立即停止修复

---

## 一、总体诊断结论

当前 NexusAgent 处于 **"核心心脏跳动，四肢休眠"** 状态：

- **已激活核心**: Orchestrator + ReActEngine + Guardrails + MemoryStore + HybridMemory + ToolRegistry + DreamEngine + AntiLaziness
- **休眠模块**: 9 个文件级孤岛 + 4 个 ProfileAdapter 存而不用 + 20+ 模块的子功能失活
- **测试覆盖**: 604 测试全部通过，证明休眠模块代码质量合格，仅需"接线"

---

## 二、依赖拓扑总图

```
                    ┌─────────────────────────────────────┐
                    │          main.py::initialize()        │
                    └─────────────────┬───────────────────┘
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        │                             │                             │
   ┌────▼────┐  ┌──────────┐  ┌──────▼──────┐  ┌──────────┐  ┌───▼────┐
   │ Guardrails│  │Orchestrator│  │ ReActEngine │  │ToolRegistry│  │Memory  │
   └────┬────┘  └─────┬────┘  └──────┬──────┘  └─────┬────┘  └───┬────┘
        │             │              │               │           │
   ┌────▼────┐  ┌─────▼──────┐  ┌────▼─────┐  ┌────▼────┐  ┌───▼────────┐
   │sanitizer│  │ProfileAdapters│  │tracker   │  │plugins  │  │self_editing│
   │(待接入) │  │(4个待接入)   │  │(部分激活)│  │(待接入) │  │(待接入)   │
   └─────────┘  └─────────────┘  └──────────┘  └─────────┘  └────────────┘
        │             │              │               │           │
   ┌────▼────┐  ┌─────▼──────┐  ┌────▼─────┐  ┌────▼────┐  ┌───▼────────┐
   │  rbac   │  │MemoryProfile │  │state_graph│  │mcp_server│  │HybridSearch│
   │(待接入) │  │(待接入)     │  │(部分激活)│  │(待接入) │  │(待接入)   │
   └─────────┘  └─────────────┘  └──────────┘  └─────────┘  └────────────┘
        │
   ┌────▼──────────────────────────────────────────────────────────────────┐
   │                          零依赖独立模块                                │
   │  utils/retry  |  observability/auto_tracer  |  evals/framework        │
   │  evals/regression  |  orchestration/scheduler  |  cognition/systems    │
   └───────────────────────────────────────────────────────────────────────┘
```

---

## 三、模块分级与风险评估

### 3.1 🔴 第一层：文件级完全未接入

| # | 模块 | 风险 | 被谁隐性依赖 | 接入阻力 | 破坏测试可能性 |
|---|------|------|-------------|---------|--------------|
| 1 | `utils/retry.py` | **LOW** | 无 | 零耦合 | 无 |
| 2 | `observability/auto_tracer.py` | **LOW** | 无 | 装饰器非侵入 | 无 |
| 3 | `evals/framework.py` | **LOW** | `evals/regression.py` | 纯离线 CLI | 无 |
| 4 | `evals/regression.py` | **LOW** | 无 | 纯离线 CLI | 无 |
| 5 | `tools/mcp_server.py` | **LOW** | 无 | 独立进程 | 无 |
| 6 | `security/sanitizer.py` | **MEDIUM** | `injection_detector.py` 引用 `SecurityError` | 需改 Guardrails | 低（新增阻断点）|
| 7 | `memory/self_editing.py` | **MEDIUM** | 无 | 需注册为工具 | 低（工具隔离）|
| 8 | `tools/plugin_manager.py` | **MEDIUM** | 无 | 与 Registry 功能重叠 | 中（需合并决策）|
| 9 | `security/rbac.py` | **HIGH** | 3 个测试文件 | 需改 Orchestrator 流程 | 高（默认拒绝策略）|

### 3.2 🟠 第二层：已初始化但"存而不用"

| # | ProfileAdapter | 风险 | 影响测试 | 需修改文件 |
|---|---------------|------|---------|-----------|
| 1 | `MemoryProfileAdapter` | **LOW** | 无 | `orchestrator.py` process() |
| 2 | `SwarmProfileAdapter` | **MEDIUM** | 无 | `orchestrator.py` _execute_core() swarm |
| 3 | `ToolRegistryProfileAdapter` | **MEDIUM** | 无 | `react_engine.py` + `orchestrator.py` |
| 4 | `ReActProfileAdapter` | **HIGH** | **潜在** | `react_engine.py` + `orchestrator.py` |

### 3.3 🟡 第三层：子功能失活

| # | 模块 | 失活子功能 | 风险 | 状态分类 |
|---|------|-----------|------|---------|
| 1 | `cognition/systems.py` | HybridSearch | **LOW** | **近期会被用到** |
| 2 | `cognition/systems.py` | ObservabilityLayer, OCELEngine, ComplianceEngine | **LOW-MEDIUM** | 可能未来启用 |
| 3 | `execution/state_graph.py` | astream(), NodeType/EdgeType/NodeSpec/EdgeSpec | **LOW** | **近期会被用到** |
| 4 | `execution/state_graph.py` | areplay(), to_mermaid() | **LOW-MEDIUM** | 可能未来启用 |
| 5 | `memory/hybrid.py` | MemoryBlock, get_core_blocks() | **LOW** | **近期会被用到** |
| 6 | `memory/hybrid.py` | link_memories(), get_related() | **MEDIUM** | 可能未来启用 |
| 7 | `security/guardrails.py` | areview() | **MEDIUM** | **近期会被用到** |
| 8 | `security/guardrails.py` | CredentialPool, TrustTier | **LOW-MEDIUM** | 可能未来启用 |
| 9 | `orchestration/scheduler.py` | CronScheduler, HeartbeatMonitor | **MEDIUM** | 可能未来启用 |
| 10 | `tools/registry.py` | discover_plugins(), discover_mcp_tools() | **LOW-MEDIUM** | 可能未来启用 |
| 11 | `memory/encryption.py` | export_key_bundle(), migrate_legacy_data() | **LOW-MEDIUM** | 可能未来启用 |
| 12 | `memory/encryption.py` | rotate_dek() | **HIGH** | 可能未来启用 |
| 13 | `execution/tracker.py` | add_step(), start_step(), skip_step() | **LOW** | 可能未来启用 |
| 14 | `execution/tracker.py` | track_execution() | **MEDIUM** | 可能未来启用 |

---

## 四、分批修复方案

> **核心原则**: 低风险优先 → 无依赖优先 → 被隐性依赖优先 → 高风险后置

---

### 批次 1：零依赖低风险工具层（🔴 第一层 LOW 风险）

**目标模块**: `utils/retry.py`, `observability/auto_tracer.py`, `evals/framework.py`, `evals/regression.py`, `tools/mcp_server.py`

**修改文件**:
1. `models/unified_backend.py` — 在 `_complete_aiohttp()` 中集成 `retry_async` 装饰器，为 LLM API 调用增加指数退避重试（3 次）
2. `main.py` — 用 `@trace_span` 装饰 `process_message()` 方法
3. `orchestration/orchestrator.py` — 用 `@trace_span` 装饰 `process()` 方法
4. `cli/main.py` — 新增 `cmd_eval()` 和 `cmd_regression()` 子命令，调用 `evals/framework.py` 和 `evals/regression.py`
5. `cli/main.py` — 新增 `cmd_mcp()` 子命令，启动 `tools/mcp_server.py`

**风险分析**:
- `utils/retry.py`: 纯装饰器，非侵入式。原有代码逻辑不变，仅在异常时触发重试。
- `auto_tracer.py`: 装饰器式 AOP，与现有 `tracing.py` 的显式埋点互补，不冲突。
- `evals/*`: 纯 CLI 离线工具，不参与主流程。
- `mcp_server.py`: 独立进程/子命令，不影响主流程。

**验收标准**:
- `pytest tests/` 604 passed
- `python -c "from nexusagent.models.unified_backend import UnifiedLLMBackend; b = UnifiedLLMBackend('mock'); print('retry ok')"` 无异常
- `nexus eval --help` 可显示帮助

---

### 批次 2：安全层与记忆层接入（🔴 第一层 MEDIUM 风险）

**目标模块**: `security/sanitizer.py`, `memory/self_editing.py`, `tools/plugin_manager.py`

**修改文件**:
1. `security/guardrails.py`:
   - `review()` 方法中，DenyList 检查之前增加 `InputSanitizer.sanitize()` 调用
   - `review_output()` 方法中增加 `PIIDesensitizer.desensitize()` 调用
   - 保留所有现有逻辑不变，仅新增前置/后置处理层
2. `tools/registry.py`:
   - `discover_builtin_tools()` 中扫描 `memory.self_editing` 模块
   - 注册 `memory.update`, `memory.delete`, `memory.query` 三个工具
   - `discover_plugins()` 中调用 `PluginManager` 作为元数据管理层（Registry 仍主导扫描，PluginManager 提供元数据）
3. `memory/self_editing.py`: 确保 `to_tool_spec()` 返回的工具名称与 Registry 扫描逻辑兼容

**风险分析**:
- `sanitizer.py`: 新增 sanitize 层可能在极端情况下引入新的阻断（如误杀合法输入）。需确保 `sanitize()` 默认策略为"清洗"而非"阻断"，只有在发现 SQL 注入/路径遍历/XSS 时才抛异常。
- `self_editing.py`: 注册为工具后，ReActEngine 可能在执行中调用记忆修改。需确保 Agent 只能修改当前 session 的记忆，不能跨 session 操作（已在 `SelfEditingMemory` 中通过 `session_id` 隔离）。
- `plugin_manager.py`: 与 Registry 的 `discover_plugins()` 存在功能重叠。决策：Registry 保留扫描逻辑，PluginManager 负责插件元数据管理和版本控制，两者共存。

**验收标准**:
- `pytest tests/test_security.py tests/test_security_advanced.py` 全绿
- `pytest tests/test_tools_extended.py` 全绿
- `pytest tests/` 604 passed
- Guardrails 的 DenyList 测试不受影响（sanitize 在 DenyList 之前，但默认不阻断）

---

### 批次 3：ProfileAdapters 低风险接入（🟠 第二层 LOW-MEDIUM 风险）

**目标模块**: `MemoryProfileAdapter`, `SwarmProfileAdapter`, `ToolRegistryProfileAdapter`

**修改文件**:
1. `orchestration/orchestrator.py`:
   - 在 `process()` 方法中，画像加载后（第 747-751 行附近），增加记忆检索上下文注入：
     ```python
     if self._memory_profile_adapter and profile:
         enhanced_query = self._memory_profile_adapter.enhance_query(profile, message)
         # 从 HybridMemory 检索相关记忆
         related = await self._hybrid.retrieve(enhanced_query, session_id=session_id)
         if related:
             memory_context = "\n".join([r.content for r in related])
             message = f"[相关记忆]\n{memory_context}\n\n[用户消息]\n{message}"
     ```
   - 在 `_execute_core()` 的 swarm 分支中，调用 `self._swarm_profile_adapter.recommend_strategy()` 覆盖硬编码 `"handoff"`，用 `recommend_specialists()` 选择初始 agent
2. `execution/react_engine.py`:
   - `run()` 方法签名增加 `tools_override: Optional[List[Dict]] = None` 参数
   - 若传入 `tools_override`，则使用传入列表替代 `self._tools.describe_tools()`
3. `orchestration/orchestrator.py`:
   - 在 `_execute_core()` 的 react 分支中，调用 `self._tools_profile_adapter.filter_tools()` 和 `sort_tools()`，将过滤后的工具列表通过 `tools_override` 传入 `self._react.run()`

**风险分析**:
- `MemoryProfileAdapter`: 记忆检索是"锦上添花"，检索失败或为空时系统可优雅降级（不注入上下文）。不影响任何现有测试断言。
- `SwarmProfileAdapter`: 仅影响 swarm 路径。现有测试使用 FakeSwarm，即使接入代码也不会被触发（`if self._swarm_profile_adapter and self._swarm:` 守卫条件）。
- `ToolRegistryProfileAdapter`: 需要修改 `ReActEngine.run()` 签名。这是一个接口变更，但为新增可选参数（默认 None），不影响现有调用方。

**验收标准**:
- `pytest tests/test_swarm.py tests/test_mirofish.py` 全绿
- `pytest tests/test_integration_v4.py tests/test_e2e_v4.py` 全绿
- `pytest tests/` 604 passed

---

### 批次 4：高风险 ProfileAdapter + RBAC（🟠 第二层 HIGH + 🔴 第一层 HIGH）

**目标模块**: `ReActProfileAdapter`, `security/rbac.py`

**修改文件**:
1. `execution/react_engine.py`:
   - `run()` 方法签名增加 `budget_override: Optional[ReActBudget] = None` 和 `system_prompt_suffix: str = ""` 参数
   - 若传入 `budget_override`，则临时替换 `self._budget`（执行后恢复）
   - 将 `system_prompt_suffix` 拼接到 system_prompt 中
   - temperature 的处理：由于 LLM 后端在 `_complete_with_fallback()` 中统一控制，可将 temperature 通过 messages 中的 system role 注入（或通过后端支持）
2. `orchestration/orchestrator.py`:
   - 在 `_execute_core()` 的 react 分支中，调用 `self._react_profile_adapter.apply(profile)` 获取调整参数
   - 将调整参数通过新增的可选参数传入 `self._react.run()`
3. `orchestration/orchestrator.py`:
   - 在 `process()` 方法中，信任积分检查之后、REVER 执行之前，增加 RBAC 权限检查：
     ```python
     if self._rbac:
         allowed = self._rbac.can_invoke(user_id, message, tools=self._tools.list_tools())
         if not allowed:
             result.answer = "[权限检查] 您没有权限执行此操作。"
             result.exit_reason = "rbac_denied"
             return result
     ```
   - 在 `main.py` 的 `initialize()` 中，初始化 RBAC 并加载默认策略（**默认允许所有**，避免破坏现有测试）

**风险分析**:
- `ReActProfileAdapter`: **风险最高**。直接修改 ReActBudget 的 `max_iterations` 可能导致复杂任务提前退出。缓解措施：
  - 设置最低底线：`max_iterations = max(10, adjusted_iterations)`，确保不会低于 10 次
  - `system_prompt_suffix` 的追加不影响逻辑，只影响风格
  - 所有修改通过可选参数传入，现有调用方不受影响
- `RBAC`: 默认拒绝策略会直接导致现有测试中的工具调用被拒绝。缓解措施：
  - 初始化时加载 "default_allow" 策略（空 deny-list）
  - 只有在用户显式配置了 RBAC 策略时才启用权限检查
  - 接入代码包裹在 `if self._rbac and self._rbac.is_enabled():` 守卫条件中

**验收标准**:
- `pytest tests/test_core.py`（含 ReActEngine 测试）全绿
- `pytest tests/test_anti_laziness_integration.py` 全绿
- `pytest tests/test_security.py tests/test_security_advanced.py` 全绿
- `pytest tests/` 604 passed

---

### 批次 5：第三层"近期会被用到"子功能激活

**目标模块**: `HybridSearch`, `astream()`, `MemoryBlock`, `areview()`, `NodeType/EdgeType`

**修改文件**:
1. `memory/hybrid.py`:
   - `_vector_search()` 方法：从直接返回 `[]` 改为调用 `HybridSearch.hybrid_search()`（需要实例化 `HybridSearch` 并注入 `MemoryStore`）
   - `__init__()` 中增加 `set_core_block("persona", "You are NexusAgent, a local-first AI assistant.")`
   - `retrieve()` 方法中，将 `get_core_blocks()` 的结果注入到检索结果头部
2. `execution/state_graph.py`:
   - 确保 `NodeType`, `EdgeType`, `NodeSpec`, `EdgeSpec` 在 `StateGraph` 的 `add_node()`/`add_edge()` 内部被正确使用（它们已经是内部类型，只需确认主流程可访问）
3. `security/guardrails.py`:
   - 新增 `async def areview()` 方法，将同步 `review()` 的内部逻辑提取为共享 helper
   - `Orchestrator.process()` 中，将 `self._guardrails.review(message)` 改为 `await self._guardrails.areview(message)`（GuardrailsEngine 已实例化，只需添加 async 方法）
4. `interface/adapter.py`:
   - WebAdapter 的 SSE 处理器中，将 `compiled.ainvoke()` 替换为 `compiled.astream()`，将 `StreamEvent` 实时推送给客户端

**风险分析**:
- `HybridSearch`: 替换空向量搜索为真实搜索，可能召回更多记忆（或召回不相关记忆）。缓解：HybridSearch 使用 RRF 融合 FTS5 和向量搜索，已有测试覆盖。
- `astream()`: 仅影响 Web 端 SSE 输出，不影响 CLI 和核心流程。
- `MemoryBlock`: 注入 persona 到 core block 中，增强角色一致性，不影响逻辑。
- `areview()`: 将同步改为异步，需确保 `InjectionDetector` 的 LLM 调用延迟可接受。缓解：使用极短超时（0.05s fire-and-forget，与现有 HITL 逻辑一致）。

**验收标准**:
- `pytest tests/test_hybrid_memory.py` 全绿
- `pytest tests/test_streaming.py` 全绿
- `pytest tests/test_stategraph.py` 全绿
- `pytest tests/test_security.py` 全绿
- `pytest tests/` 604 passed

---

### 批次 6：第三层"可能未来启用"储备激活

**目标模块**: CredentialPool, TrustTier, CronScheduler, HeartbeatMonitor, ComplianceEngine, ObservabilityLayer, OCELEngine, discover_plugins(), discover_mcp_tools(), encryption 高级 API, tracker 装饰器, areplay(), to_mermaid(), link_memories()

**修改文件**:
1. `main.py`:
   - 初始化 `CronScheduler` 并注册定时任务（记忆清理、成本报告）
   - 初始化 `HeartbeatMonitor` 并注册组件健康检查
   - 初始化 `ComplianceEngine`（GDPR 数据保留策略）
   - 初始化 `ObservabilityLayer`（OpenTelemetry 埋点）
2. `tools/registry.py`:
   - `main.py` 初始化后调用 `discover_plugins()` 和 `discover_mcp_tools()`（根据配置决定是否启用）
3. `cli/main.py`:
   - 新增 `nexus encryption export` 命令
   - 新增 `nexus encryption rotate` 命令
   - 新增 `nexus graph visualize` 命令（调用 `to_mermaid()`）
   - 新增 `nexus status` 命令（调用 `HeartbeatMonitor.check()`）
4. `memory/hybrid.py`:
   - `add_recall()` 后自动触发 `link_memories()`（基于向量相似度）

**风险分析**:
- 这批模块全部是**新增功能**，不修改现有核心流程。
- 所有初始化代码包裹在 `if config.xxx_enabled:` 条件中，默认不启用。
- 唯一高风险：`rotate_dek()` 若启用必须同步启用 `migrate_legacy_data()`，否则历史数据无法解密。缓解：加密轮换功能默认关闭，仅在 CLI 命令中手动触发。

**验收标准**:
- `pytest tests/` 604 passed
- `nexus status` 命令可正常输出
- `nexus encryption export` 可正常导出密钥包

---

## 五、接口变更清单

以下接口将在修复过程中发生变更，需同步更新所有调用方：

| # | 变更接口 | 变更内容 | 影响文件 | 批次 |
|---|---------|---------|---------|------|
| 1 | `ReActEngine.run()` | 新增 `task_context` 参数（已在前一阶段添加） | `orchestrator.py` | 已完成 |
| 2 | `ReActEngine.run()` | 新增 `tools_override: Optional[List[Dict]] = None` | `orchestrator.py` | 批次 3 |
| 3 | `ReActEngine.run()` | 新增 `budget_override` 和 `system_prompt_suffix` | `orchestrator.py` | 批次 4 |
| 4 | `ToolRegistry.discover_plugins()` | 委托给 `PluginManager` 提供元数据 | `registry.py`, `plugin_manager.py` | 批次 2 |
| 5 | `GuardrailsEngine.review()` | 前置增加 `InputSanitizer.sanitize()` | `guardrails.py` | 批次 2 |
| 6 | `GuardrailsEngine` | 新增 `async areview()` 方法 | `orchestrator.py` | 批次 5 |
| 7 | `HybridMemory._vector_search()` | 从 `return []` 改为调用 `HybridSearch` | `hybrid.py` | 批次 5 |
| 8 | `UnifiedLLMBackend` | 集成 `retry_async` 装饰器 | `unified_backend.py` | 批次 1 |

---

## 六、测试保护策略

每批次执行后必须运行的测试组合：

| 批次 | 必跑测试文件 | 通过标准 |
|------|-------------|---------|
| 批次 1 | `pytest tests/test_tracing.py tests/test_evals.py tests/test_tools_extended.py` | 全绿 |
| 批次 2 | `pytest tests/test_security.py tests/test_security_advanced.py tests/test_tools_extended.py` | 全绿 |
| 批次 3 | `pytest tests/test_swarm.py tests/test_mirofish.py tests/test_integration_v4.py tests/test_e2e_v4.py` | 全绿 |
| 批次 4 | `pytest tests/test_core.py tests/test_anti_laziness_integration.py tests/test_security.py` | 全绿 |
| 批次 5 | `pytest tests/test_hybrid_memory.py tests/test_streaming.py tests/test_stategraph.py tests/test_security.py` | 全绿 |
| 批次 6 | `pytest tests/`（全量） | **604 passed** |

---

## 七、回滚策略

每批次的修改必须满足：
1. **备份**: 修改前创建 `_backup/batch{N}/` 目录，保存被修改文件的原始版本
2. **原子性**: 每批次内的修改要么全部成功，要么全部回滚
3. **快速回滚**: 若某批次导致测试失败，执行：
   ```bash
   cp _backup/batch{N}/*.py .
   pytest tests/  # 验证回滚后 604 passed
   ```

---

## 八、时间估算

| 批次 | 预计工作量 | 预计耗时 |
|------|-----------|---------|
| 批次 1 | 5 个模块，纯接入 | 1-2 天 |
| 批次 2 | 3 个模块，需合并决策 | 2-3 天 |
| 批次 3 | 3 个 Adapter，接口变更 | 2-3 天 |
| 批次 4 | 1 个 HIGH Adapter + RBAC | 3-4 天 |
| 批次 5 | 5 个子功能激活 | 2-3 天 |
| 批次 6 | 10+ 储备功能，CLI 扩展 | 3-5 天 |
| **总计** | | **13-20 天** |

---

## 九、最终声明

**经深度调研，NexusAgent 所有休眠模块均具备完整代码质量和测试覆盖，不存在"坏死代码"。接入工作本质是"接线"而非"重构"。按本方案分 6 批次执行，每批次有明确的修改文件清单、风险分析和验收标准，可确保 604 测试全部通过的前提下，逐步激活所有功能模块。**
