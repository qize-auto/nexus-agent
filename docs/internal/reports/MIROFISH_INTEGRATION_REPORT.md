# MiroFish 深度集成报告 [MIROFISH-INSPIRED]

> 生成时间: 2026-06-01
> 任务: MiroFish 多 Agent 协作逻辑深度集成
> 来源验证: GitHub 666ghj/MiroFish (https://github.com/666ghj/MiroFish)
> 最终测试: 400 passed / 0 failed (零回归)

---

## 一、MiroFish 调研报告

### 1.1 项目定位

**MiroFish** 是由 666ghj 开发、盛大集团战略支持的开源项目，基于 CAMEL-AI 的 **OASIS (Open Agent Social Interaction Simulations)** 框架。

> 定位: "A Simple and Universal Swarm Intelligence Engine, Predicting Anything"
> — 简洁通用的群体智能引擎，预测万物

它不是通用的多 Agent 任务协作框架，而是一个**社会演化模拟器**：
- 从真实世界种子信息构建高保真数字世界
- 数千个具有独立人格、长期记忆和行为逻辑的智能体自由交互
- 用于预测未来轨迹（政策推演、舆情预测、小说结局推演）

### 1.2 核心架构（5步工作流）

```
1. Graph Building    → Zep 图谱构建（实体-关系网络）+ GraphRAG
2. Environment Setup → 实体关系提取 + 角色生成(Persona) + Agent配置
3. Simulation        → Twitter + Reddit 双平台并行模拟
4. Report Generation → ReportAgent 深度交互后生成报告
5. Deep Interaction  → 与模拟世界中任何 Agent 聊天
```

### 1.3 核心代码组件

| 组件 | 文件 | 职责 |
|------|------|------|
| GraphBuilderService | `graph_builder.py` | Zep API 调用，构建知识图谱 |
| OasisProfileGenerator | `oasis_profile_generator.py` | 实体→Agent Profile 转换（MBTI/年龄/职业/兴趣） |
| SimulationConfigGenerator | `simulation_config_generator.py` | LLM 自动生成模拟参数（时间/活跃度/发言频率） |
| SimulationManager | `simulation_manager.py` | 模拟生命周期管理 |
| SimulationRunner | `simulation_runner.py` | 后台运行 OASIS，解析日志，记录 Agent 动作 |
| ReportAgent | `report_agent.py` | 报告生成 Agent |
| TaskManager | `models/task.py` | 单例模式任务状态管理 |

### 1.4 Agent 特征深度

每个 Agent 拥有远超常规框架的人设维度：
- **基础**: user_id, user_name, name, bio, persona
- **人格**: MBTI, age, gender, country, profession
- **行为**: activity_level, posts_per_hour, comments_per_hour, active_hours
- **社交**: response_delay, sentiment_bias, stance, influence_weight
- **平台适配**: Reddit karma / Twitter follower_count 等

### 1.5 对 NexusAgent 的增益点

| MiroFish 能力 | NexusAgent 现状 | 增益 |
|--------------|----------------|------|
| 深度 Persona (MBTI+职业+兴趣) | 简单 role/goal | Agent 差异化协作 |
| GraphRAG 社会图谱 | 纯文本记忆 | 结构化协作关系 |
| 时间感知模拟 (活跃时段+响应延迟) | 无时间概念 | 真实协作节奏 |
| 双平台并行 | 单环境执行 | 多环境并行预演 |
| 参数自动生成 | 人工配置 | 零配置启动 |
| 进度追踪回调 | 无进度可视化 | 长任务可观测 |

---

## 二、融合架构设计

### 2.1 设计原则

MiroFish 原始架构过重（Zep Cloud + OASIS + 双平台），不适合直接集成。提取**核心可复用组件**，以轻量级方式融入 NexusAgent：

> 核心理念: "协作预演" — 任务执行前，Agent 在虚拟空间进行轻量级预演模拟，发现最优协作路径。

### 2.2 架构图

```
用户任务输入
    │
    ▼
Orchestrator.process()
    │
    ├─ 输入审查 (Guardrails)
    │
    ├─ 任务复杂度检测
    │   ├─ 跨部门/协同/推演 → MiroFish 策略
    │   ├─ 多步骤/协作 → Swarm 策略
    │   └─ 简单查询 → ReAct 策略
    │
    ├─ MiroFishScheduler.run() [NEW]
    │   │
    │   ├─ Step 1: 任务分解 → TaskNode
    │   ├─ Step 2: Agent 竞标 (ContractNet)
    │   │         评分 = 能力匹配*0.35 + (1-负载)*0.25 + 活跃度*0.2 + 时段系数*0.2
    │   ├─ Step 3: 任务分配 → 最优 Agent 执行
    │   ├─ Step 4: 共识便签 → MiroBoard 结构化讨论
    │   └─ Step 5: 聚合输出 → 生成报告
    │
    ├─ 输出审查 (Guardrails)
    └─ 记忆持久化 (HybridMemory)
```

### 2.3 新增模块

```
orchestration/mirofish/
├── __init__.py          # 导出所有组件
├── persona_engine.py    # Agent 深度人设生成 (MBTI/职业/行为模式)
├── social_graph.py      # 轻量级社会图谱 (实体-关系网络)
├── simulation_clock.py  # 模拟时钟 (活跃时段/响应延迟/投标意愿)
├── activity_config.py   # Agent 活动配置 (立场/影响力/决策风格)
└── scheduler.py         # MiroFish 调度器 (协作预演引擎)
```

### 2.4 与现有架构的集成点

| 现有模块 | 集成方式 | 变更 |
|---------|---------|------|
| `agents/message_bus.py` | 新增 MiroFishTopics 常量 | `mirofish.bid/award/result/sticky/zone_sync` |
| `orchestration/orchestrator.py` | 新增 `mirofish_scheduler` 参数 + 策略路由 | `_is_complex_task()` 返回 `(bool, strategy)` |
| `main.py` | 初始化 MiroFishScheduler + 注册默认 Agents | 4 个 Specialist Agent 预注册 |

### 2.5 调度策略对比

| 策略 | 适用场景 | 核心机制 |
|------|---------|---------|
| **ReAct** | 简单查询、单步任务 | LLM 思考-行动循环 |
| **Swarm** | 多 Agent 并行协作 | Handoff/GroupChat/RoundRobin/LoadBalance |
| **MiroFish** [NEW] | 跨部门、深度协作、预演推演 | 协作预演模拟 + 深度人设 + 社会图谱 + 时间感知 |

---

## 三、实施验证

### 3.1 接入位置

| 文件 | 行号 | 变更 |
|------|------|------|
| `orchestration/mirofish/__init__.py` | 1-50 | 新模块导出 |
| `orchestration/mirofish/persona_engine.py` | 1-200 | Agent 深度人设生成 |
| `orchestration/mirofish/social_graph.py` | 1-150 | 社会图谱 (BFS 路径发现) |
| `orchestration/mirofish/simulation_clock.py` | 1-120 | 模拟时钟 (中国作息时间) |
| `orchestration/mirofish/activity_config.py` | 1-80 | Agent 活动配置 + 投标评分 |
| `orchestration/mirofish/scheduler.py` | 1-400 | MiroFish 调度器核心 |
| `agents/message_bus.py` | 35-50 | MiroFishTopics 消息常量 |
| `orchestration/orchestrator.py` | 244-260 | `mirofish_scheduler` 参数 + 策略路由 |
| `main.py` | 194-208 | MiroFishScheduler 初始化 + 默认 Agent 注册 |

### 3.2 测试覆盖

| 测试文件 | 测试数 | 覆盖 |
|----------|--------|------|
| `tests/test_mirofish.py` | 29 | PersonaEngine, SocialGraph, SimulationClock, ActivityConfig, MiroFishScheduler, LoadBalancing, MessageBusEvents |
| `tests/test_integration_v4.py` | 11 | ReAct+SlidingWindow, ToolRegistry, Orchestrator+Swarm |
| `tests/test_e2e_v4.py` | 3 | 全链路端到端 |

### 3.3 零回归验证

```
Before: 371 passed
After:  400 passed (+29 MiroFish tests)
Regression: 0
```

### 3.4 端到端演示

运行 `python examples/mirofish_demo.py` 输出：

```
============================================================
  MiroFish 端到端演示：跨部门报告生成
============================================================

[Step 1] 注册 Specialist Agents...
[Step 2] 构建社会协作图谱...
  - Agent 数量: 4
  - 关系边数: 4
[Step 3] 启动 MiroFish 协作预演模拟...
[Step 4] 模拟结果
  # MiroFish 协作结果: 基于 Q3 销售数据...
  ## 任务分配
  - [completed] 数据收集与分析 → 市场部-小李
  - [completed] 报告撰写与可视化 → 写手-阿文
  ## 共识便签
  - **市场部-小李** (neutral): ...
  - **写手-阿文** (neutral): ...
[Step 5] 协作统计
  Agent 总数: 4
  任务分解数: 2
  完成任务数: 2
  模拟轮次: 1
  共识便签数: 2
  执行时间: 0.00s
[Step 6] Agent 深度人设
  👤 市场部-小李 (researcher)
     MBTI: ESTJ | 年龄: 43 | 国家: China
     主动性: 0.9 | 细节导向: 0.8 | 风险承受: 0.4
     影响力: 1.2 | 友好度: 0.6
     Bio: 负责收集和整理市场数据，对数字极其敏感
  ...
```

---

## 四、超越 AutoGen GroupChat 的设计

| 维度 | AutoGen GroupChat | NexusAgent MiroFish |
|------|-------------------|---------------------|
| 任务分配 | 轮询/随机选择发言者 | **ContractNet 竞标** (能力匹配+负载+时段) |
| Agent 差异化 | 无 (所有 Agent 同质) | **深度 Persona** (MBTI/职业/行为模式) |
| 关系网络 | 无 | **社会图谱** (协作路径发现+关系强度) |
| 时间感知 | 无 | **模拟时钟** (活跃时段+响应延迟) |
| 协作可追溯 | 消息日志 | **共识便签板** (结构化讨论线程) |
| 预演优化 | 无 | **协作预演** (先模拟后执行) |
| 动态负载 | 无内置 | **负载感知投标** (过载 Agent 自动降权) |

---

## 五、已知注意事项

1. **MiroFish 原始依赖**: 原始项目依赖 Zep Cloud + OASIS + 双平台模拟，本集成提取核心逻辑并做了轻量级替代。
2. **Persona 生成**: 当前为规则模板生成，生产环境可接入 LLM 生成更丰富的 Agent 人设。
3. **社会图谱**: 当前为内存图，大规模场景可接入 Neo4j / Zep Graph。
4. **时间模拟**: 基于中国作息时间，国际化场景可配置其他时区。
5. **负载均衡惩罚**: `_assign_tasks()` 引入动态惩罚机制，已分配任务越多的 Agent 在后续分配中评分降低 15%，避免任务集中。
6. **MessageBus 事件**: 模拟全生命周期（SIM_START → BID → AWARD → RESULT → STICKY → SIM_END）通过 MessageBus 发布，外部可订阅监听进度。
7. **演示脚本路径**: `examples/mirofish_demo.py` 需要 `sys.path` 指向项目父目录（Desktop）才能正确导入 `nexusagent` 包。

---

## 六、引用来源

- **GitHub Repository**: https://github.com/666ghj/MiroFish
- **OASIS Framework**: https://github.com/camel-ai/oasis
- **Zep Cloud**: https://app.getzep.com/
- **盛大集团战略支持**: Shanda Group (https://www.shanda.com/)
- **在线 Demo**: https://666ghj.github.io/mirofish-demo/

---

**集成完成确认**: MiroFish 核心逻辑已深度融入 NexusAgent 多 Agent 协作体系，400 个测试全绿（含 29 个 MiroFish 专项测试），端到端演示脚本可正常运行，负载均衡与 MessageBus 事件机制已验证。
