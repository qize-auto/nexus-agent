# MiroFishScheduler 优化设计方案

## 1. 原始问题回顾

### 问题 1：通信层未利用 MessageBus
- `_collect_bids`、`_assign_tasks`、`_simulate_execution` 均为内部直接方法调用
- 虽然已有 `_publish_event` 发布通知事件（BID/AWARD/RESULT/STICKY），但核心协作流程（投标→分配→执行）仍是同步内联逻辑
- 无法支持未来分布式部署（Scheduler 与 Agent 不在同一进程）

### 问题 2：负载均衡机制过弱
- 当前 `_assign_tasks` 仅有 `round_assigned.get(agent_id, 0) * 0.15` 的线性惩罚
- 惩罚仅在本轮（round）内生效，跨轮次不累积
- 无并发上限控制，高能力 Agent 仍可能被持续选中

---

## 2. 通信层改造方案

### 2.1 设计原则
- **向后兼容**：默认 `communication_mode="direct"`，现有行为和测试不受影响
- **策略切换**：通过构造函数参数切换，无需修改调用方代码
- **最小侵入**：不改动公开接口 `run()` / `register_agent()` / `register_agents()`
- **异步兼容**：MessageBus 本身已是 async，与现有 async 方法无缝衔接

### 2.2 新增主题常量

```python
class MiroFishTopics:
    BID_REQUEST = "mirofish.bid.request"      # Scheduler -> Agent: 请求投标
    BID_RESPONSE = "mirofish.bid.response"    # Agent -> Scheduler: 投标响应
    EXECUTE_REQUEST = "mirofish.execute.request"   # Scheduler -> Agent: 请求执行
    EXECUTE_RESPONSE = "mirofish.execute.response" # Agent -> Scheduler: 执行结果
    # 已有: BID, AWARD, RESULT, STICKY, SIM_START, SIM_END
```

### 2.3 架构

```
┌─────────────────┐     direct call      ┌─────────────┐
│  Scheduler      │ ───────────────────> │   Agent     │
│  (direct mode)  │                      │  handler    │
└─────────────────┘                      └─────────────┘

┌─────────────────┐     BID_REQUEST      ┌─────────────┐
│  Scheduler      │ ───────────────────> │   Agent     │
│  (bus mode)     │ <─────────────────── │  handler    │
│                 │     BID_RESPONSE     │             │
│                 │     EXECUTE_REQUEST  │             │
│                 │ ───────────────────> │             │
│                 │ <─────────────────── │             │
│                 │     EXECUTE_RESPONSE │             │
└─────────────────┘                      └─────────────┘
```

### 2.4 实现细节

**Scheduler 侧**（`MiroFishScheduler`）：
- 新增 `communication_mode: str` 参数（`"direct"` / `"messagebus"`）
- 新增 `_bid_responses` / `_execute_responses` 缓冲字典
- 新增 `_on_bid_response()` / `_on_execute_response()` 内部 handler
- 新增 `_setup_bus_handlers()` 懒加载方法（在 `run()` 中首次调用）
- `_collect_bids()` 分支：DIRECT → 现有逻辑；MESSAGEBUS → 发布 BID_REQUEST，等待 BID_RESPONSE
- `_simulate_execution()` 分支：DIRECT → 现有逻辑；MESSAGEBUS → 发布 EXECUTE_REQUEST，等待 EXECUTE_RESPONSE

**Agent 侧**（在 Scheduler 中代理注册）：
- `register_agent()` 时，如果 mode == MESSAGEBUS，记录 `self._bus_agent_handlers[agent_id] = handler`
- `_setup_bus_handlers()` 中为每个已注册 Agent 订阅 BID_REQUEST 和 EXECUTE_REQUEST
- Agent 收到 BID_REQUEST 后计算 score，发布 BID_RESPONSE
- Agent 收到 EXECUTE_REQUEST 后调用 handler，发布 EXECUTE_RESPONSE

**序列化**：复用 `AgentMessage.payload: Dict[str, Any]`，无需新增适配器。

---

## 3. 负载均衡方案

### 3.1 惩罚因子设计

引入 **三维惩罚模型**：

| 维度 | 符号 | 说明 | 衰减方式 |
|------|------|------|----------|
| 本轮惩罚 | `round_penalty` | 当前 round 内已分配数 | 每轮清零 |
| 历史惩罚 | `cumulative_penalty` | 跨轮次历史总分配数 | 指数衰减 |
| 并发上限 | `max_concurrent` | Agent 同时处理任务上限 | 硬截断 |

**惩罚公式**：
```
adjusted_score = raw_score - round_penalty - cumulative_penalty
round_penalty = round_assigned[agent] * 0.15  (已有)
cumulative_penalty = total_assignments[agent] * 0.05 * exp(-0.1 * rounds_since_last)
```

**并发上限**：
```python
max_concurrent = max(1, config.tasks_per_hour // 4)  # 假设每轮 15min
if current_load[agent] >= max_concurrent:
    skip(agent)
```

### 3.2 修改位置

- `_assign_tasks()`：应用三维惩罚
- `run()` 循环中：每轮结束后更新 `_agent_total_assignments` 和 `_agent_last_round`
- 新增 `_get_max_concurrent()` 辅助方法

---

## 4. 测试策略

### 4.1 MessageBus 通信测试
- `test_collect_bids_via_bus()`：启用 MESSAGEBUS 模式，验证 `_collect_bids` 通过 MessageBus 收集到投标
- `test_simulate_execution_via_bus()`：验证 EXECUTE_REQUEST / EXECUTE_RESPONSE 流程
- `test_backward_compatibility()`：默认 DIRECT 模式下，所有现有测试行为不变

### 4.2 负载均衡测试
- `test_load_balance_penalty()`：3 个 Agent，6 个任务，验证无 Agent 获得超过 70% 的任务
- `test_cumulative_penalty_decay()`：多轮模拟，验证历史惩罚随轮次指数衰减
- `test_concurrent_limit()`：设置低并发上限，验证 Agent 不会超载

### 4.3 回归测试
- 运行全部 `tests/test_mirofish.py`（29 tests）
- 运行全量 `pytest tests/`

---

## 5. 实施步骤

1. 新增 `MiroFishTopics.BID_REQUEST/BID_RESPONSE/EXECUTE_REQUEST/EXECUTE_RESPONSE`
2. 修改 `MiroFishScheduler.__init__`：接受 `communication_mode`
3. 新增 `_setup_bus_handlers` / `_on_bid_response` / `_on_execute_response`
4. 重构 `_collect_bids`：提取 `_collect_bids_direct`，新增 `_collect_bids_bus`
5. 重构 `_simulate_execution`：提取 `_simulate_execution_direct`，新增 `_simulate_execution_bus`
6. 增强 `_assign_tasks`：引入累积惩罚 + 并发上限
7. 写测试 → 运行全量测试 → 输出报告
