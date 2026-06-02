# NexusAgent — Agent 开发指南

## 项目背景

NexusAgent v3.3 是一个面向个人用户的本地优先 AI 智能体系统。设计目标是在保证数据隐私和安全的前提下，提供多通道接入、多模型支持和可扩展的工具生态。

## 技术栈

- **后端**：Python 3.10+, asyncio, aiohttp, SQLite
- **桌面客户端**：Electron (Node.js) + 纯 HTML/CSS/JS 前端
- **安全**：cryptography (Fernet/AES-256), PBKDF2, SHA-256
- **数据**：Pydantic v2, YAML, JSON
- **测试**：pytest, pytest-asyncio, pytest-cov

## 代码规范

1. **类型注解**：所有公共函数必须带类型注解，使用 `from __future__ import annotations`
2. **异步优先**：IO 操作必须使用 `async/await`，阻塞操作通过 `run_in_executor`  offload
3. **错误处理**：不允许静默吞异常，必须记录日志并返回结构化错误
4. **安全默认**：所有数据收集默认关闭，PII 默认脱敏，高风险工具强制沙箱
5. **零 TODO 交付**：提交前移除所有 `TODO`、`pass`、`...` 占位符

## 关键约束

- **月度成本上限**：默认 $100/月，可配置
- **首次响应 SLA**：< 2s（本地缓存命中时 < 500ms）
- **数据留存**：默认 90 天，支持 GDPR 第 17 条被遗忘权
- **加密标准**：AES-256-GCM（通过 Fernet），PBKDF2 600k iterations
- **沙箱策略**：Docker 优先，降级为受限子进程（无网络、禁用危险模块）

## 构建与运行

```bash
# 安装依赖
pip install -r requirements.txt

# 运行测试（必须通过）
pytest tests/ -v

# CLI 模式
python run_cli.py

# Web 模式
python run_web.py

# 桌面模式
npm install && npm start
```

## 架构假设

- [ASSUMPTION] 架构设计稿（`.docx`）无法自动提取，所有实现基于代码内注释中的"设计稿第X章"引用推导
- [ASSUMPTION] 生产环境建议启用 Docker 以支持完整沙箱隔离
- [ASSUMPTION] LLM API Key 由用户通过 `.env` 文件提供，系统不内置任何默认密钥

## 文件修改日志

- 2025-05-31: 修复 orchestrator.py 重复执行 ReAct 的 bug（输出审查阶段复用 REVER 捕获的结果）
- 2025-05-31: 修复 run_web.py 路径遍历漏洞（`..` 过滤 + `resolve()` 校验）
- 2025-05-31: 增强 sandbox.py 降级逻辑（Docker 不可用时使用受限子进程 + 模块禁用）
- 2025-05-31: 增强 config/settings.py 配置解析健壮性（忽略未知字段）
- 2025-05-31: 增强 models/router.py 添加 `complete_with_fallback` 统一 Fallback 调用接口
- 2025-05-31: 完全重制 Electron 桌面客户端（现代化 UI、系统托盘、快捷键、通知）
- 2025-05-31: 添加 Moonshot (月之暗面) API 支持（`MoonshotLLMBackend` + `.env.example` + 桌面端模型选择）
- 2025-05-31: **全面审查修复** — 发现并修复 14 项问题/优化（详见下方）

### 2025-05-31 全面审查修复清单

**🔴 严重 Bug 修复（6项）**
1. `security/sandbox.py`: 修复 `_docker_test` duration 计算错误（误用 `time.time()` 代替 `start`）
2. `security/guardrails.py`: 修复 `ReviewResult.is_allowed` 对 `YELLOW` 级别返回 `False` 的问题（应为允许通过并增加监控）
3. `main.py`: 修复 `_CheckpointAdapter` 独立创建 `MemoryStore` 导致的连接泄漏（改为复用主 `MemoryStore`）
4. `run_web.py`: 修复静态文件服务端对二进制文件（PNG/JPG/ICO）使用 `read_text()` 导致内容损坏的问题
5. `cognition/systems.py`: 修复 `ComplianceEngine.right_to_be_forgotten` 混淆 `session_id` 与 `user_id` 的逻辑错误；新增 `MemoryStore.delete_by_user()` 真正实现数据删除
6. `memory/store.py`: 修复 `cleanup_expired()` 未同步清理 FTS5 虚拟表索引的 orphan 数据问题

**🟡 功能缺陷修复（5项）**
7. `desktop/app.js`: 修复 PyQt6 模式下 `checkBackendHealth()` 发起 HTTP fetch 导致状态显示"离线"的问题
8. `memory/store.py`: 修复 `search_fts()` 未捕获 `sqlite3.OperationalError`（FTS5 语法错误可导致查询崩溃）
9. `tools/layer.py`: 修复 `ToolLayer._is_sandbox_available()` 仅检查 `docker` 模块是否可导入，未验证 Daemon 是否可连接的误判问题
10. `desktop/main_window.py`: 修复系统托盘图标缺失（Windows 上显示空白）— 生成纯色 fallback 图标
11. `desktop/launch.py`: 修复直接启动 PyQt6 桌面端时未加载项目 `.env` 环境变量的问题

**🟢 架构优化（3项）**
12. `main.py`: 提取 `_create_llm()` 统一工厂方法，消除 `__init__` 与 `reload_llm` 中的重复 backend 创建逻辑
13. `config/settings.py` + `run_*.py`: 统一 `.env` 加载入口 `load_project_env()`，消除 4 处重复代码
14. `memory/store.py` + `main.py`: 集成 `MemoryEncryption`（AES-256）— 记忆内容自动加密存储，FTS5 索引仍保留明文以支持搜索
15. `models/router.py`: `DeepSeekLLMBackend` / `MoonshotLLMBackend` 改为懒加载复用 `aiohttp.ClientSession`，避免每次请求新建连接池
16. `orchestration/orchestrator.py`: 将 `REVERResult` 的动态属性 `_captured_output` 改为正式 dataclass 字段 `captured_output`，消除隐式属性

- 2025-05-31: **深度修复部分实现模块** — 将 Stub/占位实现替换为真实实现（详见下方）

### 2025-05-31 深度修复部分实现模块清单

**1. `tools/mcp_client.py` — MCP 协议客户端真实实现**
- 从空壳模拟实现重写为基于 `mcp` 包的真实 stdio 客户端
- 使用 `StdioServerParameters` + `stdio_client` + `ClientSession` 进行 JSON-RPC 2.0 通信
- 支持 `initialize` 握手、`list_tools` 工具发现、`call_tool` 工具调用
- 使用 `contextlib.AsyncExitStack` 管理连接生命周期
- 失败时优雅降级到离线模式（返回模拟数据，不中断主流程）

**2. `memory/store.py` — sqlite-vec 向量搜索真实集成**
- `_init_db()` 中加载 `sqlite-vec` SQLite 扩展（失败时自动降级，不影响其他功能）
- 新增 `memories_vec` 虚拟表（`vec0(embedding float[1536])`）
- `save()` 中若 `MemoryEntry.embedding` 存在，自动同步写入向量表
- 新增 `search_vector(embedding, limit)` — 基于 sqlite-vec 的 KNN 相似度搜索
- `cleanup_expired()` / `delete_by_session()` / `delete_by_user()` 同步清理向量表孤儿数据

**3. `cognition/systems.py` — `HybridSearch` 真实混合搜索**
- 从硬编码返回示例数据重写为基于 `MemoryStore` 的真实搜索引擎
- `search()` → 调用 `MemoryStore.search_fts()` 进行 FTS5 全文搜索
- `vector_search()` → 调用 `MemoryStore.search_vector()` 进行向量搜索
- `hybrid_search()` → **RRF (Reciprocal Rank Fusion)** 融合两种结果：`score = Σ 1/(60+rank)`
- 支持纯文本、纯向量、混合三种查询模式

**4. `interface/adapter.py` — `WebAdapter` 完整实现**
- 基于 `aiohttp` 的 HTTP REST + WebSocket 双模 Web 接入层
- 提供 `/ws` WebSocket 实时推送、`/api/chat` REST 消息、`/api/health` 健康检查、`/api/config` 配置保存
- 内置静态文件服务（安全路径校验，支持二进制文件）
- `register_message_callback()` 允许 Orchestrator 注册统一消息处理回调
- `send()` 向所有 WebSocket 客户端广播消息

**5. `run_web.py` — 重构为 WebAdapter 驱动**
- 从自行管理 aiohttp 应用重构为 `WebAdapter` 的简洁启动脚本
- 接入层逻辑完全统一到 `interface/adapter.py`，消除重复代码

**6. `main.py` + `execution/react_engine.py` — 美元成本预算强制**
- `ReActEngine` 新增 `cost_enforcer` 和 `cost_per_1k_tokens` 参数
- 每次 LLM 调用后自动估算成本：`tokens × cost_per_1k / 1000`
- 若超出预算，立即返回 `COST_BUDGET_EXHAUSTED` 退出，不再继续消耗
- `main.py` `initialize()` 中按模型配置不同价格（DeepSeek/Moonshot/OpenAI）
- `main.py` `shutdown()` 中关闭 LLM backend 的 `aiohttp.ClientSession` 连接池

- 2025-06-01: **MiroFish 群体智能协作预演系统** — 6模块完整集成（详见下方）

### 2025-06-01 MiroFish 集成清单

**模块（`mirofish/`）**
1. `scheduler.py` — 群体智能调度器，支持 `run(task, max_rounds)` 预演协作
2. `agents.py` — 6类预演角色：Moderator/Expert/Reviewer/Resource/Timer/Recorder
3. `message.py` — 结构化 Message / RoundResult / SimulationSummary
4. `consensus.py` — Borda计数 + 多数决 + 阈值通过 三层共识
5. `persistence.py` — SQLite 持久化 Round/Summary/Report
6. `integration.py` — MessageBus 事件 + Orchestrator 回调接入

**优化**
- 添加 `max_agents` 负载均衡控制
- MessageBus 事件触发（`SIMULATION_STARTED`, `ROUND_COMPLETED`, `CONSENSUS_REACHED`）
- 29 个测试，400 total passed

- 2025-06-01: **用户画像动态演化系统** — 完整实现（详见下方）

### 2025-06-01 用户画像系统清单

**核心模块**
1. `profile/manager.py` — `UserProfileManager` 持久化 + 置信度门限写入
2. `profile/profiler.py` — `UserProfiler` 实时消息特征提取（8类信号）
3. `profile/dream.py` — `DreamEngine` 夜间自反思画像演化

**适配器（`profile/adapters/`）**
- `llm.py`, `database.py`, `tool.py`, `memory.py`, `cognition.py`, `orchestration.py` — 6个跨模块画像消费适配器

**CLI 扩展**
- `nexus profile` — 查看/编辑/导出用户画像
- `nexus dream` — 触发手动自反思

**测试**: 19 个画像测试，419 total passed

- 2025-06-01: **Anti-Laziness 防偷懒执行保障系统** — 5拦截点完整实现（详见下方）

### 2025-06-01 Anti-Laziness 防偷懒系统清单

**目标**: 防止 Agent 偷懒/跳步/压缩输出/假装忘记

**5个拦截点**
1. **Post-strategy-selection** → `ExecutionTracker` 记录任务步骤和证据
2. **Pre-tool-call** → `ForcedChunkedReader` 强制分块阅读大文件
3. **Post-tool-call** → `ExecutionTracker` 记录工具调用证据
4. **Pre-output-review** → `AntiCompressionDetector` + `CompletenessValidator` 检测压缩和不完整
5. **Pre-REVER-evaluate** → `WorkMemory` 持久化上下文，防止假装失忆

**核心模块（`execution/`）**
1. `tracker.py` — `ExecutionTracker` / `TaskContext` / `Step` / `Evidence` / `@track_execution`
2. `anti_compression.py` — `AntiCompressionDetector`（5类压缩模式检测）
3. `completeness.py` — `CompletenessValidator`（缺失步骤/代码/文件/长度验证）
4. `chunked_reader.py` — `ForcedChunkedReader`（强制分块阅读，防止TL;DR）
5. `work_memory.py` — `WorkMemory`（执行快照持久化 + 循环检测 + 重试提示生成）

**集成**
- `Orchestrator._execute_core()` — 提取核心执行逻辑
- `Orchestrator.process()` — 质量验证失败时自动重试（最多2次），WorkMemory 注入历史提示
- `main.py` — 初始化全部5个防偷懒组件并传入 Orchestrator

**测试**: 60+ 个防偷懒测试（tracker 20 + anti_compression 18 + completeness 17 + chunked_reader 24 + work_memory 22 + integration 21），521 total passed

- 2025-06-01: **工具能力专项审查与补全** — 完整执行与编辑能力覆盖（详见下方）

### 2025-06-01 工具能力专项审查报告

**审查范围**: `tools/` 目录全部工具，对照 17 项必要能力检查表

**已有工具状态**
| 工具 | 状态 | 说明 |
|------|------|------|
| `browser.visit` | ✅ 可用 | Playwright/requests 双模，SSRF 防护 |
| `code_interpreter.execute` | ✅ 可用 | E2B 沙箱优先，本地降级（需 `NEXUS_ALLOW_LOCAL_EXECUTION`） |
| `MockToolRegistry` (read_file/write_file/search_files) | ⚠️ 未注册 | 存在于 `layer.py` 但**未进入 ToolRegistry**，ReActEngine 不可调用 |

**补全工具清单**

P0（阻断级 — 已补全）
| 工具 | 类 | 安全控制 |
|------|-----|----------|
| `file.read` | `FileReadTool` | 路径遍历防护 |
| `file.read_binary` | `FileReadBinaryTool` | base64 返回，1MB 限制 |
| `file.write` | `FileWriteTool` | 需 `NEXUS_ALLOW_FILE_OPS=1` |
| `file.list` | `FileListTool` | 路径遍历防护 |
| `file.move` | `FileMoveTool` | 需 `NEXUS_ALLOW_FILE_OPS=1` |
| `file.delete` | `FileDeleteTool` | 需 `NEXUS_ALLOW_FILE_OPS=1` |
| `shell.execute` | `ShellExecuteTool` | 需 `NEXUS_ALLOW_SHELL=1`，危险命令黑名单，30s 超时 |
| `code.search_replace` | `CodeSearchReplaceTool` | 需 `NEXUS_ALLOW_FILE_OPS=1` |
| `code.insert` | `CodeInsertTool` | 需 `NEXUS_ALLOW_FILE_OPS=1` |
| `code.delete` | `CodeDeleteTool` | 需 `NEXUS_ALLOW_FILE_OPS=1` |

P1（严重级 — 已补全）
| 工具 | 类 | 安全控制 |
|------|-----|----------|
| `api.request` | `APIRequestTool` | SSRF 防护（禁止内网/本地地址） |

P2（一般级 — 已补全）
| 工具 | 类 | 安全控制 |
|------|-----|----------|
| `archive.pack_unpack` | `ArchiveTool` | 需 `NEXUS_ALLOW_FILE_OPS=1`，Zip/Tar Slip 防护 |
| `database.query` | `DatabaseTool` | 仅 SQLite，DDL/DML 写操作需 `NEXUS_ALLOW_FILE_OPS=1` |

**注册与联通性**
- `tools/registry.py` `_builtin_modules` 已扩展包含全部 10 个内置模块
- `ToolRegistry.discover_builtin_tools()` 自动发现所有工具
- ReActEngine 可通过 `describe_tools()` 获取全部工具描述供 LLM 选择
- 端到端验证: `read → edit → shell execute → write` 全链条通过（`test_tools_end_to_end.py`）

**测试覆盖**
- `test_tools_file_ops.py` — 20 tests
- `test_tools_shell.py` — 8 tests
- `test_tools_code_edit.py` — 16 tests
- `test_tools_api_client.py` — 10 tests
- `test_tools_archive.py` — 4 tests
- `test_tools_database.py` — 5 tests
- `test_tools_end_to_end.py` — 4 tests
- **新增 67 个工具测试，592 total passed，零回归**

**最终声明**: NexusAgent 现已具备完整的执行、编辑、代码修改及软件操作能力，所有工具均已注册可用。

- 2025-06-01: **MiroFishScheduler 通信与负载均衡优化** — 可插拔 MessageBus + 三维惩罚模型（详见下方）

### 2025-06-01 MiroFishScheduler 优化报告

**原始问题**
1. MiroFishScheduler 的 `_collect_bids` / `_simulate_execution` 为内部直接调用，未使用已扩展的 MessageBus
2. `_assign_tasks` 仅有本轮线性惩罚 `round_assigned * 0.15`，跨轮次不累积，无并发上限

**通信层改造**
- 新增 `communication_mode` 参数（`"direct"` 默认 / `"messagebus"`）
- 新增 MessageBus 主题：`BID_REQUEST`, `BID_RESPONSE`, `EXECUTE_REQUEST`, `EXECUTE_RESPONSE`
- `_collect_bids()` 保持同步向后兼容；`run()` 中根据 mode 选择 `_collect_bids_direct()` / `await _collect_bids_bus()`
- `_simulate_execution()` 分支：`_simulate_execution_direct()` / `_simulate_execution_bus()`
- `_setup_bus_handlers()` 懒加载：为每个 Agent 注册 bid/execute 的 request/response handler
- 序列化复用现有 `AgentMessage.payload`，无需额外适配器

**负载均衡增强**
- 三维惩罚模型：
  - 本轮惩罚：`round_assigned * 0.15`（已有）
  - 历史累积惩罚：`total_assignments * 0.05 * exp(-0.1 * rounds_since)`（新增，指数衰减）
  - 并发上限：`max(2, tasks_per_hour // 2)`（新增，硬截断）
- 修改 `_assign_tasks(bids, round_num)` 接口（新增可选 `round_num` 参数用于衰减计算）

**测试**
- `test_mirofish_optimization.py` — 12 tests
  - MessageBus bid 收集、执行、完整 run、向后兼容
  - 负载均衡集中度检查（<70%）、累积惩罚衰减、并发上限、多轮分配
- 原 `test_mirofish.py` — 29 tests 全部通过
- **全量 604 passed，零回归**

**遗留项**
- MessageBus 模式默认不启用（`communication_mode="direct"`），因为分布式部署尚未是生产需求
- 启用方法：`MiroFishScheduler(bus=MessageBus(), communication_mode="messagebus")`

**最终确认**: MiroFishScheduler 现已支持可配置的 MessageBus 通信和负载均衡，所有测试通过，无功能回归。

- 2025-06-02: **UI 诊断与对比功能集成** — 5 阶段完整实现（详见下方）

### 2025-06-02 诊断系统集成清单

**目标**: 在 Desktop / Web / CLI 三端提供统一、深度、可视化的系统健康诊断能力

**Phase 1 — UI 入口**
- Desktop: sidebar 新增 "Diagnostics" 按钮 + 抽屉式仪表盘
- Web: diag-bar 快捷诊断按钮（Health / Connectivity / Audit / Modules / UX / Design Diff / Competitor）

**Phase 2 — 后端诊断深度化**
- `diagnostics/collector.py` — 共享诊断收集器，采集真实运行时数据
  - `collect_health()`: backends / security / execution / memory / system / adapter 六维健康
  - `collect_connectivity()`: tool_registry / modules / probes（sqlite / filesystem / llm_backend / memory_store）
  - `collect_audit()`: 真实审计日志 + 安全拦截统计
  - `collect_modules()`: 模块导入 + 深度健康检查
  - `collect_ux()`: 真实指标驱动的 UX 评分
- `interface/adapter.py` — 7 个诊断 handler 委托到 collector，代码从 ~600 行降至 ~80 行

**Phase 3 — 前端可视化**
- Dashboard HTML 渲染：卡片/表格/进度条/徽章
- Health: 状态矩阵 + 后端表格 + 系统信息
- Connectivity: 健康比例 + 探针列表
- Modules: 状态表格 + 深度详情
- Audit: 拦截统计 + 审计日志表格
- UX: 评分圆环 + 检查项列表 + 建议卡片
- Design Diff: 变更统计 + 三栏对比
- Competitor: 矩阵对比 + 优劣势分析

**Phase 4 — CLI 对齐**
- `nexus doctor` — 彩色终端诊断报告
- `nexus doctor --json` — 结构化 JSON 输出
- CLI 与 Web 共享 `diagnostics/collector.py`，零重复代码

**Phase 5 — 诊断自动化（WebSocket 实时告警）**
- `diagnostics/scheduler.py`:
  - `AlertRuleEngine` — 5 条规则（overall_healthy / probe failed / module error / error_rate / latency）
  - `DiagnosticScheduler` — 定时后台巡检，默认 5 分钟间隔
  - 告警去重 — 同一告警 10 分钟内不重复推送
- `interface/adapter.py` — `_broadcast_alert()` 向所有 WebSocket 客户端广播
- Desktop 前端:
  - `initWebSocket()` — WebSocket 连接，断线 5s 自动重连
  - `showAlertToast()` — 浮动告警通知（critical/error/warning/info 四级）
  - `.alert-toast` CSS — 滑入滑出动画 + 自动消失

**Phase 6 — 诊断数据持久化**
- `diagnostics/persistence.py` — `DiagnosticStore` 诊断快照存储（SQLite WAL，复用 nexus_memory.db）
  - `save_snapshot(category, data, alert_count)` — 插入快照
  - `get_history(category, hours)` — 时间范围查询，返回时间序列
  - `cleanup(keep_days)` — 自动清理过期数据（默认 30 天）
- `diagnostics/scheduler.py` — `_tick()` 末尾通过 `asyncio.to_thread` 将 health/connectivity/modules 快照写入 store
- `interface/adapter.py` — 新增 `/api/diagnostics/history` API，返回 `{ok, category, hours, points: [{timestamp, data, alert_count}]}`
- Desktop 前端:
  - History section — category/hours 选择器 + Load 按钮
  - `renderHistoryChart()` — 纯 CSS 柱状图，智能降采样至 24 柱，颜色分级（绿/黄/红）
  - `renderHistoryTable()` — 最近 10 条快照表格
- Web UI — 同步 History 按钮 + 图表渲染

**扩展 — 实时自动刷新**
- Desktop: Diagnostics drawer 开启后每 30s 自动重新 fetch 当前诊断数据
  - `autoRefreshEnabled` 状态，localStorage 持久化
  - drawer header 新增 Auto-refresh toggle checkbox
  - `refreshCurrentDiagnostic()` — 静默刷新，无按钮状态闪烁
- Web UI: diag-bar 旁新增 Auto-refresh toggle
  - `runDiagSilent()` — 原位更新最后一条诊断消息，不重复追加
  - 切换诊断类型时自动重置定时器

**扩展 — 告警历史页面**
- `diagnostics/persistence.py` — 新增 `diagnostics_alerts` 表
  - `save_alert(alert)` — 告警持久化
  - `get_alerts(level_filter, hours, limit, acknowledged)` — 多维度筛选查询
  - `acknowledge_alert(alert_id)` — 标记已读
  - `count_unacknowledged_alerts(hours)` — 未读计数
- `diagnostics/scheduler.py` — `_tick()` alert 触发后同时写入 store
- `interface/adapter.py`:
  - `/api/diagnostics/alerts` — 告警列表（支持 level/hours/limit/acknowledged 筛选）
  - `/api/diagnostics/alerts/ack` (POST) — 标记已读
- Desktop 前端:
  - Diagnostics drawer 新增 **Alerts** section
  - 级别筛选按钮组（All / Critical / Error / Warning / Info）
  - 告警表格：时间、级别徽章、标题、来源、Ack 按钮
  - Sidebar Diagnostics 按钮显示未读告警计数徽章
- Web UI: diag-bar 新增 Alerts 按钮

**扩展 — 诊断配置面板**
- `diagnostics/config.py` — `DiagnosticConfig` dataclass
  - `scheduler_interval_seconds` / `latency_warning_ms` / `latency_critical_ms`
  - `error_rate_warning` / `error_rate_critical`
  - `history_keep_days` / `alerts_keep_days`
  - `load_config()` / `save_config()` / `with_overrides()`
- `interface/adapter.py`:
  - `/api/diagnostics/config` (GET) — 返回当前配置
  - `/api/diagnostics/config` (POST) — 保存并热重载 scheduler interval
- Desktop 前端:
  - Settings drawer 新增 **Diagnostics** section
  - 7 项配置表单 + 保存按钮

**扩展 — 报告导出**
- `diagnostics/report.py` — `generate_report(store)` 生成 Markdown 报告
  - 标题页、Health/Connectivity/Modules 摘要、24h 告警统计、历史趋势、建议清单
- `interface/adapter.py` — `/api/diagnostics/export` (GET) 返回 Markdown
- `cli/main.py` — `nexus doctor --export <path>` 导出报告到文件
- Desktop 前端:
  - Diagnostics drawer 新增 **Export** section
  - Format 选择（Markdown / JSON）+ Export 按钮触发下载
- Web UI: diag-bar 新增 Export 按钮

**测试**: 37 个诊断测试（API 12 + RuleEngine 8 + Scheduler 2 + WebSocket 1 + Persistence 4 + Alerts 5 + Config 3 + Export 2），全量通过，零回归
