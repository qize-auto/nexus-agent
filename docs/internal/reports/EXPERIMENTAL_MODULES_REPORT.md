# NexusAgent 实验性/未接入模块完整清单

> **生成日期**: 2026-06-02
> **审查范围**: 主流程 `main.py → NexusAgent.initialize() → process_message() → Orchestrator.process()`
> **原则**: 以下模块/类/函数均**不得删除**，仅作状态登记。

---

## 🔴 第一层：文件级完全未接入（主流程零 import）

以下文件在主流程（`main.py` / `orchestrator.py` / `run_cli.py`）中**从未被 import 或实例化**。它们仅在测试文件或独立脚本中被引用。

| 文件路径 | 核心类/函数 | 说明 | 测试覆盖 |
|---------|-----------|------|---------|
| `evals/framework.py` | `BaseEvaluator`, `ExactMatchEvaluator`, `ModelGradedEvaluator`, `EvalRunner` | 评估框架基类与实现 | ✅ `tests/test_evals.py` |
| `evals/regression.py` | `RegressionSuite`, `RegressionTestCase`, `RegressionResult` | 回归测试套件 | ✅ `tests/test_evals.py` |
| `memory/self_editing.py` | `SelfEditingMemory` | 自编辑记忆系统 | ✅ `tests/test_integration_e2e.py` |
| `observability/auto_tracer.py` | `trace_span`, `get_current_span`, `SimpleSpan` | 自动 OpenTelemetry 追踪装饰器 | ✅ `tests/test_tracing.py` |
| `security/rbac.py` | `RBACEngine`, `add_policy`, `can_invoke`, `add_role` | 基于角色的访问控制引擎 | ✅ `tests/test_security_advanced.py` |
| `security/sanitizer.py` | `PiiSanitizer`, `contains_pii`, `get_pii_types` | PII 脱敏与检测 | ❌ 无独立测试 |
| `tools/mcp_server.py` | `MCPServer`, `get_tools_manifest` | MCP 协议服务端 | ❌ 无独立测试 |
| `tools/plugin_manager.py` | `PluginManager`, `get_plugin_manager` | 插件发现与管理 | ✅ `tests/test_tools_extended.py` |
| `utils/retry.py` | `retry_async`, `exponential_backoff`, `RetryPolicy` | 通用重试工具 | ❌ 无独立测试 |

**注**: 以上 9 个文件中，前 4 个已标记 `🧪 EXPERIMENTAL` 注释；后 5 个尚未标记。

---

## 🟠 第二层：已初始化但"存而不用"（仅赋值，无方法调用）

以下 4 个 **ProfileAdapter** 在 `main.py` 的 `initialize()` 中被实例化并传入 `Orchestrator`，但 `Orchestrator.process()` 中**从未调用它们的任何方法**。

| 文件路径 | 类名 | 实例化位置 | 未调用方法 |
|---------|------|-----------|-----------|
| `agents/profile_adapter.py` | `SwarmProfileAdapter` | `main.py:199` | `recommend_specialists` |
| `memory/profile_adapter.py` | `MemoryProfileAdapter` | `main.py:226` | `enhance_query`, `get_memory_types_priority`, `adjust_importance_threshold` |
| `execution/profile_adapter.py` | `ReActProfileAdapter` | `main.py:239` | `apply`, `_compute_iterations`, `_build_prompt_suffix` |
| `tools/profile_adapter.py` | `ToolRegistryProfileAdapter` | `main.py:244` | `filter_tools`, `sort_tools`, `adjust_description` |

**状态分析**: 这些适配器的设计意图是"根据用户画像动态调整各子系统行为"，但 Orchestrator 中的画像驱动逻辑目前只调用了：
- `orchestration/profile_adapter.py` → `OrchestratorProfileAdapter`（已激活：调整策略和预算）
- `security/profile_adapter.py` → `GuardrailsProfileAdapter`（已激活：调整 ML 阈值）

其余 4 个适配器处于"接线完成但开关未打开"状态。

---

## 🟡 第三层：模块主体已联通，但子类/子函数失活

以下模块的**核心类已被主流程接入**，但模块内部定义了大量辅助类、数据模型或扩展功能，在主流程中从未被引用。

### 3.1 `cognition/systems.py` — 大量子系统失活

| 未引用类/函数 | 说明 |
|-------------|------|
| `EventKind` | 事件类型枚举 |
| `AgentEvent` | 统一通信事件模型 |
| `HybridSearch` | sqlite-vec 混合搜索 |
| `ObservabilityLayer` | Trace/Metrics/Log 可观测性层 |
| `OCELEngine` | OCEL 循环进化引擎 |
| `ComplianceEngine` | GDPR/PIPL 合规模块 |
| `EvolutionAction` | 进化动作枚举 |
| `setup_structured_logging()` | 结构化日志初始化 |
| `to_json()` | AgentEvent 序列化 |
| `hybrid_search()` | 混合搜索执行函数 |
| `export_to_file()` | 可观测数据导出 |
| `get_evolution_plan()` | 进化计划生成 |
| `get_usage()` | 成本用量统计 |

**已激活部分**: `CostEnforcer`（被 `main.py` 和 `ReActEngine` 使用）。

### 3.2 `execution/deliberation.py` — 数据模型未引用

| 未引用类 | 说明 |
|---------|------|
| `ExpertRole` | 专家角色枚举 |
| `ExpertOpinion` | 单条专家意见 |
| `DeliberationResult` | 研讨结果数据类 |

**已激活部分**: `DeliberationEngine`（被 `Orchestrator._execute_core()` 调用）。

### 3.3 `execution/hitl.py` — 辅助类未引用

| 未引用类/函数 | 说明 |
|-------------|------|
| `HITLResponse` | 人工响应数据类 |
| `submit_response()` | 提交人工响应（独立函数） |
| `get_pending_requests()` | 获取待处理请求（独立函数） |
| `get_hitl_manager()` | 获取全局单例（独立函数） |

**已激活部分**: `HITLManager.request_approval()`（被 `Orchestrator.process()` 调用）。

### 3.4 `execution/reflexion.py` — 数据模型未引用

| 未引用类 | 说明 |
|---------|------|
| `ReflectionReport` | 反思报告数据类 |
| `_FakeError` | 内部模拟错误类 |

**已激活部分**: `ReflexionNode.reflect()`（被 `Orchestrator._execute_core()` 调用）。

### 3.5 `execution/state_graph.py` — 大量高级 API 未引用

| 未引用类/函数 | 说明 |
|-------------|------|
| `NodeType`, `EdgeType` | 节点/边类型枚举 |
| `NodeSpec`, `EdgeSpec` | 节点/边规格数据类 |
| `StateGraphValidationError` | 校验异常 |
| `add_parallel_edges()` | 并行边添加 |
| `set_reducer()` | Reducer 设置 |
| `astream()` | 异步流式执行 |
| `areplay()` | 异步回放 |
| `to_mermaid()` | Mermaid 图导出 |

**已激活部分**: `StateGraph.add_node()`, `add_edge()`, `compile()`, `ainvoke()`（被 `Orchestrator._run_enhanced_graph()` 调用）。

### 3.6 `execution/tracker.py` — 辅助方法未引用

| 未引用函数 | 说明 |
|-----------|------|
| `add_step()` | 手动添加步骤 |
| `get_step()` | 按 ID 获取步骤 |
| `get_evidence_for_step()` | 获取步骤证据 |
| `validate_completeness()` | 手动触发完整性验证 |
| `completion_ratio()` | 完成度比率 |
| `start_step()` | 手动开始步骤 |
| `skip_step()` | 跳过步骤 |
| `track_execution()` | 装饰器式追踪 |

**已激活部分**: `create_task()`, `auto_plan_from_message()`, `record_evidence()`, `validate()`（被 `Orchestrator` 调用）。

### 3.7 `execution/work_memory.py` — 查询方法未引用

| 未引用类/函数 | 说明 |
|-------------|------|
| `MemorySnapshot` | 快照数据类 |
| `get_snapshots()` | 获取全部快照 |
| `get_latest_snapshot()` | 获取最新快照 |
| `is_duplicate()` | 重复检测 |
| `detect_cycle()` | 循环检测 |
| `get_execution_trace()` | 执行轨迹导出 |
| `get_retry_count()` | 重试计数 |

**已激活部分**: `save_snapshot()`, `get_memory_for_retry()`（被 `Orchestrator` 调用）。

### 3.8 `memory/encryption.py` — 高级加密 API 未引用

| 未引用类/函数 | 说明 |
|-------------|------|
| `KeyBundle` | 密钥束数据类 |
| `export_key_bundle()` | 导出密钥 |
| `from_key_bundle()` | 从密钥束恢复 |
| `encrypt_bytes()` | 字节级加密 |
| `decrypt_bytes()` | 字节级解密 |
| `rotate_dek()` | DEK 轮换 |
| `is_legacy_ciphertext()` | 遗留密文检测 |
| `migrate_value()` | 单值迁移 |
| `migrate_legacy_data()` | 批量数据迁移 |
| `derive_kek()` | 密钥派生 |

**已激活部分**: `MemoryEncryption.encrypt()`, `decrypt()`（被 `MemoryStore` 使用）。

### 3.9 `memory/hybrid.py` — 高级记忆 API 未引用

| 未引用类/函数 | 说明 |
|-------------|------|
| `RetrievalResult` | 检索结果数据类 |
| `MemoryBlock` | 记忆块数据类 |
| `get_core_blocks()` | 获取核心块 |
| `add_archival()` | 添加归档记忆 |
| `retrieve()` | 通用检索 |
| `link_memories()` | 记忆关联 |
| `get_related()` | 获取关联记忆 |
| `update_core_block()` | 更新核心块 |

**已激活部分**: `add_recall()`（被 `Orchestrator.process()` 调用）。

### 3.10 `memory/user_profile.py` — 画像管理 API 未引用

| 未引用函数 | 说明 |
|-----------|------|
| `get_history()` | 获取画像变更历史 |
| `rollback()` | 画像回滚 |
| `export_profile()` | 画像导出 |
| `update_trait()` | 直接更新画像属性 |

**已激活部分**: `load()`, `save()`, `get_or_create()`, `add_pending_trait()`, `get_pending_traits()`（被 `Orchestrator` 和 `DreamEngine` 使用）。

### 3.11 `tools/registry.py` — 高级发现 API 未引用

| 未引用函数 | 说明 |
|-----------|------|
| `discover_plugins()` | 插件自动发现 |
| `discover_mcp_tools()` | MCP 服务器工具发现 |

**已激活部分**: `discover_builtin_tools()`（被 `get_registry()` 调用）。

### 3.12 `security/guardrails.py` — 扩展功能未引用

| 未引用类/函数 | 说明 |
|-------------|------|
| `TrustTier` | 信任层级枚举 |
| `CredentialEntry` | 凭证条目 |
| `CredentialPool` | 凭证池 |
| `areview()` | 异步审查 |
| `record_usage()` | 用量记录 |
| `add_credential()` | 添加凭证 |
| `get_credential()` | 获取凭证 |
| `hash_key()` | 密钥哈希 |
| `revoke()` | 凭证吊销 |

**已激活部分**: `review()`, `review_output()`（被 `Orchestrator` 调用）。

### 3.13 `security/e2b_sandbox.py` — 部分 API 未引用

| 未引用类/函数 | 说明 |
|-------------|------|
| `E2BConfig` | 配置数据类 |
| `is_available()` | 可用性检测（类方法） |
| `execute_browser_task()` | 浏览器任务执行 |

**已激活部分**: `E2BSandbox.execute_code()`（被 `CodeInterpreterTool` 调用）。

### 3.14 `security/sandbox.py` — 子类未引用

| 未引用类/函数 | 说明 |
|-------------|------|
| `EvolutionSandbox` | 进化沙箱 |
| `MCPSandbox` | MCP 沙箱 |
| `execute_tool()` | 工具执行 |

**已激活部分**: `Sandbox` 基类（被 `ToolLayer` 引用）。

### 3.15 `orchestration/scheduler.py` — 整个模块基本未激活

| 未引用类/函数 | 说明 |
|-------------|------|
| `CronJob` | 定时任务 |
| `should_run()` | 执行判断 |
| `CronScheduler` | 定时调度器 |
| `HeartbeatStatus` | 心跳状态 |
| `HeartbeatMonitor` | 心跳监控器 |
| `get_status()` | 状态获取 |
| `get_all_status()` | 全部状态 |
| `is_all_healthy()` | 健康度判断 |

**说明**: 该模块未被 `Orchestrator` 或 `main.py` 引用。`MiroFishScheduler` 在 `orchestration/mirofish/scheduler.py` 中，与此文件无关。

### 3.16 `orchestration/mirofish/*.py` — 子功能失活

`MiroFishScheduler` 主体已接入，但以下辅助类/方法在主流程中未被调用：

| 文件 | 未引用类/函数 |
|------|-------------|
| `activity_config.py` | `calculate_consensus_weight()` |
| `persona_engine.py` | `generate_batch()` |
| `scheduler.py` | `TaskNode`, `SimulationRound`, `on_bid_request()`, `on_execute_request()` |
| `simulation_clock.py` | `is_agent_active()`, `calculate_response_delay()`, `get_bid_willingness()` |
| `social_graph.py` | `get_entity()`, `get_relations()`, `find_collaboration_path()`, `suggest_collaborators()`, `get_collaboration_strength()` |

### 3.17 `interface/adapter.py` — 内部类失活

| 未引用类/函数 | 说明 |
|-------------|------|
| `Attachment` | 附件数据类 |
| `MemoryTokenBucket` | 内存令牌桶 |
| `RedisTokenBucket` | Redis 令牌桶 |
| `IdempotencyStore` | 幂等存储 |
| `RateLimiter` | 限流器类 |
| `from_string()` | 字符串反序列化 |
| `health_status()` | 健康状态查询 |

**已激活部分**: `ChannelAdapter`, `MessageEnvelope`, `UserIdentity` 等基类（被多通道系统使用）。

### 3.18 `tools/layer.py` — 内部类失活

| 未引用类 | 说明 |
|---------|------|
| `ToolInvocation` | 调用描述 |
| `NativeExecutor` | 原生执行器 |
| `ToolExecutor` | 执行器基类 |

**已激活部分**: `ToolSpec`, `ToolLayer`（被测试使用，主流程目前由 `ToolRegistry` 替代）。

### 3.19 `tools/guard.py` — 内部类失活

| 未引用类 | 说明 |
|---------|------|
| `ScanResult` | 扫描结果 |
| `SkillGuard` | 技能守卫 |
| `LazyLoader` | 懒加载器 |

**已激活部分**: `AuditLogger`（被 `main.py` 使用）。

### 3.20 `cognition/dream_engine.py` — 批量方法未引用

| 未引用函数 | 说明 |
|-----------|------|
| `run_for_all_users()` | 批量处理所有用户画像 |

**已激活部分**: `dream_cycle()`（被 `main.py:_trigger_dream()` 自动触发）。

---

## 🔵 第四层：仅 CLI / Web / Desktop 入口使用（非核心对话流程）

以下模块/函数**仅在特定入口文件中被调用**，不参与 `run_cli.py` 的默认对话流程：

| 入口 | 调用的独立模块 | 说明 |
|------|--------------|------|
| `nexus doctor` | `cli/doctor.py` — `NexusDoctor`, `CheckResult`, `run_all`, `print_report` | 环境诊断工具 |
| `nexus init` | `cli/main.py` — `cmd_init()` | 项目初始化 |
| `nexus dev` | `cli/main.py` — `cmd_dev()` | 开发模式 |
| `nexus status` | `cli/main.py` — `cmd_status()` | 状态查看 |
| `nexus deploy` | `cli/main.py` — `cmd_deploy()` | 部署命令 |
| `nexus eval` | `cli/main.py` — `cmd_eval()` | 评估命令 |
| `nexus profile` | `cli/main.py` — `cmd_profile()` | 画像查看 |
| `nexus dream` | `cli/main.py` — `cmd_dream()` | 手动触发 DreamEngine |
| `run_web.py` | `interface/adapter.py` — `WebAdapter` | Web 服务端 |
| `run_desktop.py` | `desktop/main_window.py`, `desktop/bridge.py`, `desktop/worker.py` | 桌面客户端 |
| `examples/mirofish_demo.py` | `demo_cross_department_report()` | 独立演示脚本 |

---

## 📊 统计汇总

| 层级 | 类别 | 数量 |
|------|------|------|
| 🔴 第一层 | 文件级完全未接入 | **9 个文件** |
| 🟠 第二层 | 已初始化但"存而不用" | **4 个 ProfileAdapter** |
| 🟡 第三层 | 模块主体已联通，子功能失活 | **20+ 个模块，约 120+ 个类/函数** |
| 🔵 第四层 | 仅独立入口使用 | **11 个 CLI/Web/Desktop 入口** |

---

## 💡 建议与备注

1. **第一层**的 9 个文件是真正的"孤岛模块"。建议要么：
   - 在 `README.md` 中诚实声明为 `@experimental`
   - 或接入主流程（如 `RBACEngine` 可接入 `Guardrails` 作为权限校验层）

2. **第二层**的 4 个 ProfileAdapter 是"接线完成但未通电"。建议：
   - 在 `Orchestrator.process()` 中补充调用逻辑，或在文档中声明为预留接口

3. **第三层**的大量子功能属于"过度设计但保留备用"。这是大型项目的正常现象，无需焦虑，但建议在文档中说明哪些 API 是稳定的、哪些是预留的。

4. **所有模块均已保留**，未删除任何代码。测试覆盖率保持完整（604 passed）。
