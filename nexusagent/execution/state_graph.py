"""
NexusAgent v4.0 — 图状态机执行引擎 (StateGraph)

设计参考:
- LangGraph Pregel 模型: https://arxiv.org/pdf/2603.27299
  "Nodes fire when their trigger channels receive writes, producing state updates
   and routing writes to branch channels"
- 简化版: 单线程串行执行 + 条件分支 + 循环 + 并行分支聚合

核心抽象:
    Node: async (state) -> partial_state_update
    Edge: Static | Conditional | Parallel
    State: Dict[str, Any] — 共享可变状态（通过reducer合并更新）
    CompiledGraph: 编译后的可执行图
"""

from __future__ import annotations

import asyncio
import copy
import inspect
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("nexus.execution.state_graph")

# ── 类型别名 ──
StateType = Dict[str, Any]
NodeFunc = Callable[[StateType], Awaitable[StateType]]
ConditionFunc = Callable[[StateType], Awaitable[str]]
ReducerFunc = Callable[[Any, Any], Any]


class NodeType(Enum):
    NORMAL = auto()
    START = auto()
    END = auto()
    MERGE = auto()  # 聚合并行分支


class EdgeType(Enum):
    STATIC = auto()
    CONDITIONAL = auto()
    PARALLEL = auto()


@dataclass
class NodeSpec:
    name: str
    func: NodeFunc
    node_type: NodeType = NodeType.NORMAL
    generation_config: Optional[GenerationConfig] = None


@dataclass
class EdgeSpec:
    source: str
    edge_type: EdgeType
    targets: List[str] = field(default_factory=list)
    condition: Optional[ConditionFunc] = None
    condition_map: Optional[Dict[str, str]] = None


@dataclass
class GenerationConfig:
    """节点级生成配置"""
    temperature: float = 0.7
    top_p: float = 1.0
    max_tokens: int = 4096
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0


@dataclass
class StreamEvent:
    """流式执行事件"""
    event_type: str  # node_start | node_end | chunk | error | complete
    node_name: str
    data: Any = None
    timestamp: float = field(default_factory=time.time)


StepCallback = Callable[[str, StateType, int], Awaitable[None]]


@dataclass
class RunConfig:
    """图运行配置"""
    thread_id: str = ""  # 唯一运行标识，用于checkpoint
    tenant_id: str = "default"
    user_id: str = ""
    max_iterations: int = 50  # 防止无限循环
    debug: bool = False
    checkpointer: Optional[Any] = None  # BaseCheckpointer instance
    on_step: Optional[StepCallback] = None  # 每步回调（用于tracing/streaming）
    generation_config: Optional[GenerationConfig] = None


@dataclass
class Checkpoint:
    """单步检查点"""
    thread_id: str
    node_name: str
    state: StateType
    timestamp: float
    iteration: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class StateGraphError(Exception):
    pass


class StateGraphValidationError(StateGraphError):
    pass


# ═══════════════════════════════════════════════════════════════
# StateGraph 构建器
# ═══════════════════════════════════════════════════════════════

class StateGraph:
    """
    状态图构建器 — 参考 LangGraph StateGraph 的简化实现

    Usage:
        graph = StateGraph()
        graph.add_node("agent", agent_node)
        graph.add_node("tools", tools_node)
        graph.add_conditional_edges("agent", route_tools, {"tools": "tools", END: END})
        graph.add_edge("tools", "agent")
        graph.set_entry_point("agent")
        compiled = graph.compile()
        result = await compiled.ainvoke({"messages": []}, config=RunConfig(thread_id="123"))
    """

    def __init__(self):
        self._nodes: Dict[str, NodeSpec] = {}
        self._edges: List[EdgeSpec] = []
        self._entry_point: Optional[str] = None
        self._reducers: Dict[str, ReducerFunc] = {}

    # ── 节点管理 ──

    def add_node(self, name: str, func: NodeFunc) -> StateGraph:
        """添加普通节点"""
        if name in self._nodes:
            raise StateGraphValidationError(f"节点 '{name}' 已存在")
        if not asyncio.iscoroutinefunction(func):
            raise StateGraphValidationError(f"节点 '{name}' 必须是 async 函数")
        self._nodes[name] = NodeSpec(name=name, func=func, node_type=NodeType.NORMAL)
        return self

    def set_entry_point(self, name: str) -> StateGraph:
        """设置入口节点"""
        self._entry_point = name
        return self

    # ── 边管理 ──

    def add_edge(self, source: str, target: str) -> StateGraph:
        """添加静态边: source -> target"""
        self._edges.append(EdgeSpec(
            source=source,
            edge_type=EdgeType.STATIC,
            targets=[target],
        ))
        return self

    def add_conditional_edges(
        self,
        source: str,
        condition: ConditionFunc,
        targets: Dict[str, str],
    ) -> StateGraph:
        """
        添加条件边

        Args:
            source: 源节点名
            condition: async (state) -> key
            targets: {key: target_node_name, ...}
        """
        if not asyncio.iscoroutinefunction(condition):
            raise StateGraphValidationError("condition 必须是 async 函数")
        self._edges.append(EdgeSpec(
            source=source,
            edge_type=EdgeType.CONDITIONAL,
            condition=condition,
            condition_map=targets,
            targets=list(targets.values()),
        ))
        return self

    def add_parallel_edges(
        self,
        source: str,
        branches: List[str],
        merge_node: str,
    ) -> StateGraph:
        """
        添加并行分支: source 同时触发多个分支，最终汇聚到 merge_node
        """
        # 为每个分支创建一个隐藏的中间节点
        for i, branch in enumerate(branches):
            intermediate = f"__parallel_{source}_{i}__"
            self._edges.append(EdgeSpec(
                source=source, edge_type=EdgeType.STATIC, targets=[intermediate]
            ))
            self._edges.append(EdgeSpec(
                source=intermediate, edge_type=EdgeType.STATIC, targets=[branch]
            ))
        # 汇聚边
        for branch in branches:
            self._edges.append(EdgeSpec(
                source=branch, edge_type=EdgeType.STATIC, targets=[merge_node]
            ))
        # 注册 merge_node 为特殊节点
        self._nodes[merge_node] = NodeSpec(
            name=merge_node,
            func=self._default_merge,
            node_type=NodeType.MERGE,
        )
        return self

    @staticmethod
    async def _default_merge(state: StateType) -> StateType:
        """默认合并节点 — 收集所有分支结果"""
        return {}

    # ── Reducer ──

    def set_reducer(self, key: str, reducer: ReducerFunc) -> StateGraph:
        """
        为 state 的某个 key 设置 reducer 函数
        默认行为: 新值覆盖旧值
        典型 reducer: messages 列表追加
        """
        self._reducers[key] = reducer
        return self

    # ── 编译 ──

    def compile(self) -> CompiledGraph:
        """编译图，验证完整性"""
        if not self._entry_point:
            raise StateGraphValidationError("未设置 entry_point")
        if self._entry_point not in self._nodes:
            raise StateGraphValidationError(f"entry_point '{self._entry_point}' 不存在")

        # 验证所有边引用的节点都存在
        for edge in self._edges:
            if edge.source not in self._nodes and edge.source != "__start__":
                raise StateGraphValidationError(f"边引用了不存在的源节点: {edge.source}")
            for t in edge.targets:
                if t not in self._nodes and t != END:
                    raise StateGraphValidationError(f"边引用了不存在的目标节点: {t}")

        # 验证无孤立节点
        reachable: Set[str] = set()
        self._dfs_reachable(self._entry_point, reachable)
        unreachable = set(self._nodes.keys()) - reachable
        if unreachable:
            logger.warning("编译警告: 以下节点不可达 — %s", unreachable)

        return CompiledGraph(
            nodes=self._nodes,
            edges=self._edges,
            entry_point=self._entry_point,
            reducers=self._reducers,
        )

    def _dfs_reachable(self, node: str, visited: Set[str]) -> None:
        if node in visited or node == END:
            return
        visited.add(node)
        for edge in self._edges:
            if edge.source == node:
                for t in edge.targets:
                    self._dfs_reachable(t, visited)


# ═══════════════════════════════════════════════════════════════
# CompiledGraph — 可执行图
# ═══════════════════════════════════════════════════════════════

END = "__end__"
START = "__start__"


class CompiledGraph:
    """编译后的状态图 — 支持执行、重放、并行"""

    def __init__(
        self,
        nodes: Dict[str, NodeSpec],
        edges: List[EdgeSpec],
        entry_point: str,
        reducers: Dict[str, ReducerFunc],
    ):
        self._nodes = nodes
        self._edges = edges
        self._entry_point = entry_point
        self._reducers = reducers
        self._edge_map: Dict[str, List[EdgeSpec]] = {}
        for edge in edges:
            self._edge_map.setdefault(edge.source, []).append(edge)

    # ── 核心执行 ──

    async def _execute_node(
        self,
        node_name: str,
        state: StateType,
        config: RunConfig,
        iteration: int,
    ) -> Tuple[StateType, Optional[Exception]]:
        """
        执行单个节点，返回 (新状态, 异常)
        内部方法，被 ainvoke 和 astream 共享
        """
        node_spec = self._nodes.get(node_name)
        if not node_spec:
            raise StateGraphError(f"节点 '{node_name}' 不存在")

        if config.debug:
            logger.debug("[thread=%s] 执行节点: %s (iter=%d)", config.thread_id, node_name, iteration)

        try:
            update = await node_spec.func(state)
        except Exception as e:
            logger.error("[thread=%s] 节点 '%s' 执行失败: %s", config.thread_id, node_name, e)
            return state, e

        if update:
            state = self._merge_state(state, update)

        # 安全准则: 不假设 __history__ 已存在（外部直接调用 _execute_node 时可能缺失）
        history = state.setdefault("__history__", [])
        history.append({
            "node": node_name,
            "timestamp": time.time(),
            "iteration": iteration,
        })

        return state, None

    async def ainvoke(
        self,
        initial_state: StateType,
        config: Optional[RunConfig] = None,
    ) -> StateType:
        """
        异步执行图

        Args:
            initial_state: 初始状态
            config: 运行配置

        Returns:
            最终状态
        """
        config = config or RunConfig()
        thread_id = config.thread_id or f"thread_{time.time()}"
        config.thread_id = thread_id

        state = copy.deepcopy(initial_state)
        state["__thread_id__"] = thread_id
        state["__iteration__"] = 0
        state["__history__"] = []  # 执行历史: [(node_name, timestamp), ...]

        current = self._entry_point
        iteration = 0

        logger.info("[thread=%s] StateGraph 开始执行, entry=%s", thread_id, current)

        while current != END and iteration < config.max_iterations:
            iteration += 1
            state["__iteration__"] = iteration

            # 1. Checkpoint 保存（执行前）
            if config.checkpointer:
                await config.checkpointer.save(Checkpoint(
                    thread_id=thread_id,
                    node_name=current,
                    state=copy.deepcopy(state),
                    timestamp=time.time(),
                    iteration=iteration,
                    metadata={"phase": "pre_execute", "tenant_id": config.tenant_id},
                ))

            # on_step 回调（执行前）
            if config.on_step:
                await config.on_step(current, state, iteration)

            # 2. 执行节点
            state, error = await self._execute_node(current, state, config, iteration)
            if error:
                state["__error__"] = {"node": current, "error": str(error), "iteration": iteration}
                next_node = self._find_error_edge(current)
                if next_node:
                    current = next_node
                    continue
                raise StateGraphError(f"节点 '{current}' 执行失败: {error}") from error

            # 4. Checkpoint 保存（执行后）
            if config.checkpointer:
                await config.checkpointer.save(Checkpoint(
                    thread_id=thread_id,
                    node_name=current,
                    state=copy.deepcopy(state),
                    timestamp=time.time(),
                    iteration=iteration,
                    metadata={"phase": "post_execute", "tenant_id": config.tenant_id},
                ))

            # 5. 确定下一个节点
            next_node = await self._determine_next(current, state)

            if config.debug:
                logger.debug("[thread=%s] %s -> %s", thread_id, current, next_node)

            current = next_node

        if iteration >= config.max_iterations:
            logger.warning("[thread=%s] 达到最大迭代次数限制 (%d)", thread_id, config.max_iterations)
            state["__truncated__"] = True

        logger.info("[thread=%s] StateGraph 执行完成, 总迭代=%d", thread_id, iteration)
        return state

    async def astream(
        self,
        initial_state: StateType,
        config: Optional[RunConfig] = None,
    ):
        """
        流式异步执行图 — 每步 yield StreamEvent

        Yields:
            StreamEvent: 执行事件流
                - event_type="node_start": 节点开始执行
                - event_type="node_end": 节点执行完成
                - event_type="error": 节点执行错误
                - event_type="complete": 图执行完成

        Usage:
            async for event in compiled.astream({"messages": []}):
                print(event.node_name, event.event_type)
        """
        config = config or RunConfig()
        thread_id = config.thread_id or f"thread_{time.time()}"
        config.thread_id = thread_id

        state = copy.deepcopy(initial_state)
        state["__thread_id__"] = thread_id
        state["__iteration__"] = 0
        state["__history__"] = []

        current = self._entry_point
        iteration = 0

        logger.info("[thread=%s] StateGraph 流式执行开始, entry=%s", thread_id, current)

        while current != END and iteration < config.max_iterations:
            iteration += 1
            state["__iteration__"] = iteration

            # Checkpoint 保存（执行前）
            if config.checkpointer:
                await config.checkpointer.save(Checkpoint(
                    thread_id=thread_id,
                    node_name=current,
                    state=copy.deepcopy(state),
                    timestamp=time.time(),
                    iteration=iteration,
                    metadata={"phase": "pre_execute", "tenant_id": config.tenant_id},
                ))

            # on_step 回调
            if config.on_step:
                await config.on_step(current, state, iteration)

            # Yield: 节点开始
            yield StreamEvent(
                event_type="node_start",
                node_name=current,
                data={"iteration": iteration, "thread_id": thread_id},
            )

            # 执行节点
            state, error = await self._execute_node(current, state, config, iteration)

            if error:
                state["__error__"] = {"node": current, "error": str(error), "iteration": iteration}
                yield StreamEvent(
                    event_type="error",
                    node_name=current,
                    data={"error": str(error), "iteration": iteration},
                )
                next_node = self._find_error_edge(current)
                if next_node:
                    current = next_node
                    continue
                # 无错误恢复边，终止
                break

            # Checkpoint 保存（执行后）
            if config.checkpointer:
                await config.checkpointer.save(Checkpoint(
                    thread_id=thread_id,
                    node_name=current,
                    state=copy.deepcopy(state),
                    timestamp=time.time(),
                    iteration=iteration,
                    metadata={"phase": "post_execute", "tenant_id": config.tenant_id},
                ))

            # Yield: 节点完成
            yield StreamEvent(
                event_type="node_end",
                node_name=current,
                data={
                    "iteration": iteration,
                    "state_snapshot": {k: v for k, v in state.items() if not k.startswith("__")},
                },
            )

            # 确定下一个节点
            next_node = await self._determine_next(current, state)
            current = next_node

        if iteration >= config.max_iterations:
            state["__truncated__"] = True

        # Yield: 执行完成
        yield StreamEvent(
            event_type="complete",
            node_name="__end__",
            data={
                "final_state": state,
                "total_iterations": iteration,
                "thread_id": thread_id,
            },
        )

        logger.info("[thread=%s] StateGraph 流式执行完成, 总迭代=%d", thread_id, iteration)

    # ── 重放/恢复 ──

    async def areplay(
        self,
        thread_id: str,
        from_node: Optional[str] = None,
        checkpointer: Optional[Any] = None,
    ) -> StateType:
        """
        从 Checkpoint 重放执行

        Args:
            thread_id: 运行线程ID
            from_node: 从指定节点开始重放（None则从最后一个checkpoint继续）
            checkpointer: Checkpointer 实例

        Returns:
            最终状态
        """
        if not checkpointer:
            raise StateGraphError("重放需要提供 checkpointer")

        # 加载最新 checkpoint
        checkpoint = await checkpointer.load(thread_id)
        if not checkpoint:
            raise StateGraphError(f"未找到 thread_id='{thread_id}' 的 checkpoint")

        state = copy.deepcopy(checkpoint.state)
        iteration = checkpoint.iteration

        if from_node:
            # 从指定节点重放：寻找该节点的 pre-execute checkpoint
            pre_cp = None
            if checkpointer:
                for cp in await checkpointer.list_checkpoints(thread_id):
                    if cp.node_name == from_node and cp.metadata.get("phase") == "pre_execute":
                        pre_cp = cp
                        break
            if pre_cp:
                checkpoint = pre_cp
                state = copy.deepcopy(checkpoint.state)
                iteration = checkpoint.iteration
            current = from_node
            logger.info("[thread=%s] 从节点 '%s' 重放", thread_id, from_node)
        else:
            # 从 checkpoint 的下一个节点继续
            current = await self._determine_next(checkpoint.node_name, state)
            logger.info("[thread=%s] 从节点 '%s' 之后继续执行 -> %s",
                        thread_id, checkpoint.node_name, current)

        # 复用 ainvoke 的执行循环
        config = RunConfig(
            thread_id=thread_id,
            checkpointer=checkpointer,
            max_iterations=50,
        )
        state["__replayed_from__"] = from_node or checkpoint.node_name
        state["__iteration__"] = iteration

        while current != END and iteration < config.max_iterations:
            iteration += 1
            state["__iteration__"] = iteration

            await checkpointer.save(Checkpoint(
                thread_id=thread_id, node_name=current, state=copy.deepcopy(state),
                timestamp=time.time(), iteration=iteration, metadata={"phase": "replay"},
            ))

            node_spec = self._nodes.get(current)
            if not node_spec:
                raise StateGraphError(f"节点 '{current}' 不存在")

            update = await node_spec.func(state)
            if update:
                state = self._merge_state(state, update)

            state["__history__"].append({"node": current, "timestamp": time.time(), "iteration": iteration})

            await checkpointer.save(Checkpoint(
                thread_id=thread_id, node_name=current, state=copy.deepcopy(state),
                timestamp=time.time(), iteration=iteration, metadata={"phase": "post_replay"},
            ))

            current = await self._determine_next(current, state)

        return state

    # ── 内部方法 ──

    async def _determine_next(self, current: str, state: StateType) -> str:
        """根据当前节点和状态确定下一个节点"""
        edges = self._edge_map.get(current, [])
        if not edges:
            return END

        # 优先处理条件边
        for edge in edges:
            if edge.edge_type == EdgeType.CONDITIONAL and edge.condition:
                key = await edge.condition(state)
                if edge.condition_map and key in edge.condition_map:
                    return edge.condition_map[key]
                # 如果返回的 key 不在映射中，fallback到静态边
                logger.warning("条件边返回未知 key '%s'，fallback 到静态边", key)

        # 静态边
        for edge in edges:
            if edge.edge_type == EdgeType.STATIC:
                return edge.targets[0]

        return END

    def _find_error_edge(self, node: str) -> Optional[str]:
        """查找错误恢复边（可扩展）"""
        return None  # 默认无错误恢复

    def _merge_state(self, state: StateType, update: StateType) -> StateType:
        """合并状态更新，应用 reducer"""
        merged = copy.deepcopy(state)
        for key, value in update.items():
            if key.startswith("__"):
                # 元数据key直接覆盖
                merged[key] = value
            elif key in self._reducers:
                merged[key] = self._reducers[key](merged.get(key), value)
            else:
                # 默认覆盖
                merged[key] = value
        return merged

    # ── 可视化 ──

    def to_mermaid(self) -> str:
        """导出为 Mermaid 流程图语法"""
        lines = ["graph TD"]
        lines.append(f"    START((START)) --> {self._entry_point}")
        for name, spec in self._nodes.items():
            shape = "(( ))" if spec.node_type == NodeType.MERGE else "[ ]"
            lines.append(f"    {name}{shape[0]}{name}{shape[1]}")
        for edge in self._edges:
            if edge.edge_type == EdgeType.STATIC:
                for t in edge.targets:
                    if t != END:
                        lines.append(f"    {edge.source} --> {t}")
            elif edge.edge_type == EdgeType.CONDITIONAL:
                for key, t in (edge.condition_map or {}).items():
                    if t != END:
                        lines.append(f"    {edge.source} --|{key}| --> {t}")
        lines.append(f"    END_NODE((END))")
        return "\n".join(lines)
