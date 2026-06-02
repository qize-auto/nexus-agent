# NexusAgent v4.0 架构变更蓝图

> 致命短板自主攻克任务 — 架构设计文档
> 日期: 2026-05-31

---

## 一、调研结论与方案选型

### 1.1 图执行引擎

| 方案 | 核心思路 | 优点 | 缺点 | 适用场景 |
|------|---------|------|------|---------|
| **A: 自建轻量 StateGraph** | 参考 LangGraph Pregel 模型，节点=async callable，状态=TypedDict，边=静态/条件/并行 | 轻量、可控、可深度集成安全审查节点 | 需自行维护 | NexusAgent 嵌入式使用 |
| **B: 集成 Temporal** | Workflow(确定性)+Activity(非确定性)，事件历史重放 | 工业级持久化、人日级长时间运行 | 额外基础设施、学习曲线陡峭 | 企业级长时间工作流 |
| **倾向**: **方案A为主，预留Temporal接口** | 理由: NexusAgent 需要的是轻量级、可嵌入的图引擎，而非重编排平台。LangGraph 的 Pregel 模型（channel-driven message passing）已被验证有效[^1]，我们参考其实现但保持最小化。 |

### 1.2 多 Agent 编排

| 方案 | 核心思路 | 优点 | 缺点 | 适用场景 |
|------|---------|------|------|---------|
| **A: Supervisor-Worker (CrewAI式)** | Supervisor LLM 路由任务给 Specialist Worker Agents，结果聚合 | 直观、可控、易调试 | Supervisor 可能成为瓶颈 | 任务明确可分解的场景 |
| **B: Actor 消息总线 (AutoGen式)** | Actor 模型，异步消息传递，发布-订阅路由 | 高并发、分布式可扩展 | 调试困难、易出现循环 | 研究/探索性任务 |
| **倾向**: **方案A为主，消息总线为辅** | 理由: 生产环境优先可控性。CrewAI 的"角色-任务-团队"抽象已被 63% Fortune 500 验证[^2]。我们用 Supervisor 做高层路由，Worker 内部可用消息总线做细粒度协作。 |

### 1.3 容器化与多租户

| 方案 | 核心思路 | 优点 | 缺点 | 适用场景 |
|------|---------|------|------|---------|
| **A: 进程级隔离+行级多租户** | 单容器多进程，tenant_id 字段隔离数据 | 资源利用率高、部署简单 | 隔离性弱于容器级 | 中小规模 SaaS |
| **B: 容器 per Agent + K8s Namespace** | 每个 Agent/任务运行在独立容器，K8s Namespace+RBAC 隔离 | 强隔离、弹性伸缩 | 资源开销大、复杂度高 | 大规模企业级 |
| **倾向**: **方案A为默认，方案B为可选项** | 理由: OpenHands V1 的核心教训是"沙箱应是 opt-in，非强制"[^3]。默认单进程+行级隔离降低门槛，高风险任务可选 Docker 沙箱。 |

---

## 二、架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              NexusAgent v4.0                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  API Layer (aiohttp REST + WebSocket)                                        │
│  └── TenantContextMiddleware → 注入 tenant_id / user_id / security_level    │
├─────────────────────────────────────────────────────────────────────────────┤
│  Orchestration Layer                                                         │
│  ├── StateGraph (图执行引擎)                                                 │
│  │   ├── Nodes: ReActNode, ToolNode, GuardrailsNode, AgentNode, MergeNode   │
│  │   ├── Edges: StaticEdge, ConditionalEdge, ParallelEdge                   │
│  │   └── Checkpointer: SqliteCheckpointer / PostgresCheckpointer            │
│  └── AgentCrew (多Agent编排)                                                 │
│      ├── Supervisor: 任务分解 + 动态路由                                     │
│      ├── Workers: Specialist Agent (每个 = StateGraph 子图)                  │
│      └── MessageBus: async pub/sub for inter-agent comms                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  Core Engine Layer (existing)                                                │
│  ├── ReActEngine / REVEREngine / DeliberationEngine                          │
│  ├── ToolLayer (with Docker sandbox opt-in)                                  │
│  ├── MemoryStore (SQLite + FTS5 + sqlite-vec, tenant-scoped)                 │
│  └── Security: Guardrails, Sanitizer, Encryption, TrustScore                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  Deployment Layer                                                            │
│  ├── Docker Compose (dev / small prod)                                       │
│  └── Kubernetes (enterprise: Namespace + RBAC + ResourceQuota)               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、新增/修改模块清单

### 3.1 新增模块

| 模块 | 路径 | 职责 |
|------|------|------|
| StateGraph 引擎 | `execution/state_graph.py` | 图构建、编译、执行、状态管理 |
| Checkpointer | `execution/checkpoint.py` | 节点级状态持久化、重放、恢复 |
| AgentCrew | `agents/crew.py` | Supervisor-Worker 编排、任务分解、结果聚合 |
| MessageBus | `agents/message_bus.py` | Agent 间异步消息传递 |
| TenantContext | `tenant/context.py` | 租户上下文管理、注入、校验 |
| TenantIsolation | `tenant/isolation.py` | 资源隔离、Quota 管理 |

### 3.2 修改模块

| 模块 | 修改内容 |
|------|---------|
| `execution/react_engine.py` | 适配为 StateGraph 的 ReActNode |
| `memory/store.py` | 所有表增加 `tenant_id` 字段，查询自动过滤 |
| `interface/adapter.py` | WebAdapter 增加 TenantContextMiddleware |
| `main.py` | 初始化 StateGraph + AgentCrew |

---

## 四、数据流与控制流

### 4.1 复杂任务执行流程

```
用户请求 (tenant_id=T1)
    │
    ▼
┌──────────────┐
│  Supervisor  │ ──分解任务──┬──> [子任务A: 财报分析]
│  (AgentCrew) │             ├──> [子任务B: 竞品监测]
└──────────────┘             └──> [子任务C: PPT生成]
    │
    ▼
每个子任务 = StateGraph 实例
    │
    ▼
┌─────────────────────────────────────┐
│  StateGraph 执行 (per sub-task)     │
│  START → GuardrailsNode → ReActNode│
│  → ToolNode → MergeNode → END      │
└─────────────────────────────────────┘
    │
    ▼
结果汇总 → Supervisor → 最终响应
```

### 4.2 Checkpoint 与恢复

```
执行中: START → Node1 → Node2 → [CRASH]
恢复后: SqliteCheckpointer 读取 checkpoint
        → 找到最后完成的 Node2
        → 从 Node3 开始重放 (Node1/Node2 结果从 checkpoint 读取，不重新执行)
```

### 4.3 多租户数据隔离

```
所有数据库表增加 tenant_id:
  memories(tenant_id, id, session_id, ...)
  checkpoints(tenant_id, thread_id, state_json, ...)
  agent_runs(tenant_id, run_id, status, ...)

查询自动过滤:
  SELECT * FROM memories WHERE tenant_id = ? AND ...

资源配额 (per tenant):
  max_agents: 10
  max_memory_mb: 100
  max_requests_per_min: 100
```

---

## 五、公开接口定义

### 5.1 StateGraph API

```python
class StateGraph:
    def add_node(self, name: str, func: NodeFunc) -> None
    def add_edge(self, src: str, dst: str) -> None
    def add_conditional_edges(self, src: str, condition: ConditionFunc, targets: Dict[str, str]) -> None
    def compile(self) -> CompiledGraph

class CompiledGraph:
    async def ainvoke(self, state: dict, config: RunConfig) -> dict
    async def areplay(self, thread_id: str, from_node: Optional[str] = None) -> dict
```

### 5.2 AgentCrew API

```python
class AgentCrew:
    def __init__(self, supervisor: SupervisorAgent, workers: List[WorkerAgent])
    async def execute(self, task: str, tenant_id: str) -> CrewResult

class WorkerAgent:
    name: str
    role: str
    goal: str
    tools: List[Tool]
    graph: CompiledGraph  # 每个 Worker 内部是 StateGraph
```

### 5.3 Tenant API

```python
class TenantContext:
    tenant_id: str
    user_id: str
    security_level: SecurityLevel
    quota: TenantQuota

# FastAPI-style dependency注入
async def get_tenant_context(request) -> TenantContext:
    ...
```

---

## 六、外部依据引用

[^1]: LangGraph Pregel 模型 — `https://arxiv.org/pdf/2603.27299` (Appendix A: LangGraph v1.1.3 source code analysis)
[^2]: CrewAI 企业采用率 — `https://latenode.com/blog/crewai-agent-framework` (63% Fortune 500)
[^3]: OpenHands V1 架构原则 — `https://arxiv.org/html/2511.03690v1` (Optional isolation principle)
[^4]: AutoGen Actor 模型 — `https://www.microsoft.com/en-us/research/articles/autogen-v0-4-reimagining-the-foundation-of-agentic-ai-for-scale-extensibility-and-robustness/`
[^5]: Dify Docker Compose 部署 — `https://github.com/langgenius/dify` (docker-compose.yml 参考)
