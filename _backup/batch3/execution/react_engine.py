"""
NexusAgent v3.3 — 执行层：ReAct主循环引擎
来源: 设计稿第5章 (5.2 ReAct主循环引擎)
特性: 三层Budget控制 + 三种退出路径 + 工具结果缓存 + Checkpoint
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

logger = logging.getLogger("nexus.execution")


# ═══════════════════════════════════════════════════════════════
# 类型定义 — 设计稿第5章
# ═══════════════════════════════════════════════════════════════

class ExitReason(Enum):
    """三种退出路径 + 三种异常 — 设计稿5.2.1 + RUL-064"""
    NORMAL_COMPLETION = auto()
    TOKEN_BUDGET_EXHAUSTED = auto()
    COST_BUDGET_EXHAUSTED = auto()  # 美元成本预算耗尽
    ITERATION_LIMIT = auto()
    TIME_BUDGET_EXHAUSTED = auto()
    CIRCUIT_BREAKER = auto()
    USER_CANCELLED = auto()


class TaskPriority(Enum):
    """任务优先级 — 设计稿5.16进程池调度"""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


@dataclass(frozen=True)
class ToolCall:
    """工具调用不可变描述"""
    tool_name: str
    arguments: Dict[str, Any]
    call_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def cache_key(self) -> str:
        args_str = "|".join(f"{k}={v}" for k, v in sorted(self.arguments.items()))
        return f"{self.tool_name}:{args_str}"


@dataclass
class ToolResult:
    """工具调用结果"""
    call: ToolCall
    output: Any
    execution_time_ms: float
    cached: bool = False
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None


@dataclass
class IterationRecord:
    """单次迭代记录 — 设计稿5.2.1 审计与回放"""
    iteration: int
    timestamp: float
    thought: str
    action: Optional[ToolCall] = None
    observation: Optional[ToolResult] = None
    tokens_consumed: int = 0


@dataclass
class ReActBudget:
    """
    三层Budget控制 — 设计稿5.2.1
    任一维度耗尽即触发退出
    """
    max_iterations: int = 25
    max_total_tokens: int = 8000
    max_time_seconds: float = 120.0

    _iterations_used: int = field(default=0, repr=False)
    _tokens_used: int = field(default=0, repr=False)
    _start_time: float = field(default_factory=time.monotonic, repr=False)

    def consume_iteration(self) -> bool:
        self._iterations_used += 1
        return self._iterations_used >= self.max_iterations

    def consume_tokens(self, count: int) -> bool:
        self._tokens_used += count
        return self._tokens_used >= self.max_total_tokens

    def time_remaining(self) -> float:
        return max(0.0, self.max_time_seconds - (time.monotonic() - self._start_time))

    def is_exhausted(self) -> Tuple[bool, Optional[ExitReason]]:
        if self._iterations_used >= self.max_iterations:
            return True, ExitReason.ITERATION_LIMIT
        if self._tokens_used >= self.max_total_tokens:
            return True, ExitReason.TOKEN_BUDGET_EXHAUSTED
        if self.time_remaining() <= 0:
            return True, ExitReason.TIME_BUDGET_EXHAUSTED
        return False, None

    def summary(self) -> Dict[str, Any]:
        elapsed = time.monotonic() - self._start_time
        return {
            "iterations": f"{self._iterations_used}/{self.max_iterations}",
            "tokens": f"{self._tokens_used}/{self.max_total_tokens}",
            "time": f"{elapsed:.1f}s/{self.max_time_seconds}s",
            "remaining_time": f"{self.time_remaining():.1f}s",
        }


@dataclass
class ReActResult:
    """ReAct执行结果"""
    answer: str
    exit_reason: ExitReason
    iterations: List[IterationRecord] = field(default_factory=list)
    total_tokens: int = 0
    elapsed_time_ms: float = 0.0
    tools_called: List[ToolCall] = field(default_factory=list)
    budget_summary: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
# 协议定义（依赖注入） — 设计稿5.2.1
# ═══════════════════════════════════════════════════════════════

class LLMBackend(Protocol):
    """LLM后端协议 — 设计稿第10章模型路由实现"""
    async def complete(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        ...


class ToolRegistry(Protocol):
    """工具注册表协议 — 设计稿第6章工具层"""
    def get_tool(self, name: str) -> Optional[Callable]: ...
    def describe_tools(self) -> List[Dict[str, Any]]: ...
    async def execute(self, name: str, arguments: Dict[str, Any]) -> Any: ...


class CheckpointStore(Protocol):
    """Checkpoint存储协议"""
    async def save(self, session_id: str, state: Dict[str, Any]) -> None: ...
    async def load(self, session_id: str) -> Optional[Dict[str, Any]]: ...


# ═══════════════════════════════════════════════════════════════
# ReActEngine — 主循环
# ═══════════════════════════════════════════════════════════════

class ReActEngine:
    """
    增强型ReAct循环引擎 — 设计稿第5章
    - 三层Budget控制 (token/迭代/时间)
    - 三种退出路径 (正常/预算耗尽/熔断)
    - 工具结果缓存 (相同参数复用)
    - 迭代间Checkpoint原子保存
    """

    def __init__(
        self,
        llm: LLMBackend,
        tools: ToolRegistry,
        checkpoint_store: CheckpointStore,
        budget: Optional[ReActBudget] = None,
        circuit_breaker_threshold: int = 3,
        cost_enforcer: Any = None,
        cost_per_1k_tokens: float = 0.0015,
        fallback_backends: Optional[Dict[str, LLMBackend]] = None,
        window_manager: Any = None,
        anti_compression: Any = None,
        completeness_validator: Any = None,
    ):
        self._llm = llm
        self._tools = tools
        self._checkpoint = checkpoint_store
        self._budget = budget or ReActBudget()
        self._circuit_threshold = circuit_breaker_threshold
        self._cost_enforcer = cost_enforcer
        self._cost_per_1k = cost_per_1k_tokens
        self._fallback_backends = fallback_backends or {}
        self._tool_cache: Dict[str, ToolResult] = {}
        self._error_count = 0
        self._fallback_chain: List[str] = []  # 动态记录本次使用的fallback链
        self._window_manager = window_manager  # SlidingWindow 上下文管理器
        self._anti_compression = anti_compression  # v4.0+ 防偷懒检测器
        self._completeness_validator = completeness_validator  # v4.0+ 完整性验证器

    def _validate_answer(self, answer: str, task_context: Any = None) -> str:
        """在输出前应用防偷懒和完整性验证 — v4.0+"""
        warnings: List[str] = []

        if self._anti_compression:
            try:
                ac_summary = self._anti_compression.get_summary(answer)
                if ac_summary.get("is_compressed"):
                    warnings.append(
                        f"[VALIDATION] 检测到输出压缩/偷懒行为: {ac_summary.get('by_pattern')}"
                    )
            except Exception as e:
                logger.debug("AntiCompression 验证失败 (可忽略): %s", e)

        if self._completeness_validator and task_context is not None:
            try:
                comp_summary = self._completeness_validator.get_summary(task_context, answer)
                if not comp_summary.get("is_complete"):
                    issues = comp_summary.get("issues_by_type", {})
                    warnings.append(
                        f"[VALIDATION] 输出可能不完整: {issues}"
                    )
            except Exception as e:
                logger.debug("Completeness 验证失败 (可忽略): %s", e)

        if warnings:
            return "\n".join(warnings) + "\n\n" + answer
        return answer

    def _prepare_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """使用 SlidingWindow 压缩上下文（如果配置了）"""
        if self._window_manager is None:
            return messages
        try:
            from nexusagent.context.sliding_window import Message as SWMessage
            sw_msgs = [
                SWMessage(role=m["role"], content=m["content"])
                for m in messages
            ]
            fitted = self._window_manager.fit_context(sw_msgs)
            return [{"role": m.role, "content": m.content} for m in fitted]
        except Exception as e:
            logger.debug("SlidingWindow 压缩失败，使用原始消息: %s", e)
            return messages

    async def _complete_with_fallback(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """
        带Fallback链的LLM调用 — 设计稿第10章四级Fallback

        策略:
        1. 尝试主 LLM (self._llm)
        2. 主模型失败/超时 → 按 fallback_backends 顺序尝试
        3. 全部失败 → 返回结构化错误（ReAct循环会将其作为 observation 处理）
        """
        tried: List[str] = []
        all_backends = [("primary", self._llm)]
        for name, backend in self._fallback_backends.items():
            all_backends.append((name, backend))

        for name, backend in all_backends:
            try:
                response = await asyncio.wait_for(
                    backend.complete(messages, tools, temperature),
                    timeout=60.0,
                )
                if name != "primary":
                    logger.warning("Fallback 生效: 主模型失败，降级到 %s", name)
                self._fallback_chain = tried
                return response
            except asyncio.TimeoutError:
                logger.warning("LLM %s 调用超时", name)
                tried.append(f"{name}: timeout")
            except Exception as e:
                logger.warning("LLM %s 调用失败: %s", name, e)
                tried.append(f"{name}: {e}")

        # 全部失败
        logger.error("所有LLM后端均不可用: %s", tried)
        return {
            "content": f"[NexusAgent] 所有模型均不可用。已尝试: {', '.join(tried)}",
            "tool_calls": [],
            "usage": {"total_tokens": 0},
            "_fallback_tried": tried,
        }

    async def run(
        self,
        session_id: str,
        system_prompt: str,
        user_message: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        task_context: Any = None,
    ) -> ReActResult:
        """
        执行ReAct循环

        Args:
            session_id: 会话ID
            system_prompt: 系统提示词
            user_message: 用户消息
            priority: 任务优先级
            task_context: 可选的任务上下文（用于 CompletenessValidator）

        Returns:
            ReActResult: 包含答案、退出原因、迭代记录
        """
        start_time = time.monotonic()
        iterations: List[IterationRecord] = []
        tools_called: List[ToolCall] = []
        total_tokens = 0

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        tool_descriptions = self._tools.describe_tools()

        # 恢复Checkpoint（如果存在）
        saved_state = await self._checkpoint.load(session_id)
        if saved_state:
            logger.info("Resumed from checkpoint: %s", session_id)

        # ── ReAct主循环 ──
        while True:
            # 检查Budget
            exhausted, reason = self._budget.is_exhausted()
            if exhausted:
                logger.warning("Budget exhausted: %s", reason)
                return ReActResult(
                    answer=self._validate_answer("Budget exhausted", task_context),
                    exit_reason=reason,
                    iterations=iterations,
                    total_tokens=total_tokens,
                    elapsed_time_ms=(time.monotonic() - start_time) * 1000,
                    tools_called=tools_called,
                    budget_summary=self._budget.summary(),
                )

            # 上下文滑动窗口压缩（如果配置了）
            llm_messages = self._prepare_messages(messages)

            # 调用LLM（带Fallback链）
            response = await self._complete_with_fallback(
                llm_messages, tool_descriptions, temperature=0.7
            )

            # 处理全部fallback失败的结构化错误
            if response.get("_fallback_tried"):
                self._error_count += 1
                if self._error_count >= self._circuit_threshold:
                    return ReActResult(
                        answer=self._validate_answer("Circuit breaker triggered: all LLM backends unavailable", task_context),
                        exit_reason=ExitReason.CIRCUIT_BREAKER,
                        iterations=iterations,
                        total_tokens=total_tokens,
                        elapsed_time_ms=(time.monotonic() - start_time) * 1000,
                        tools_called=tools_called,
                        budget_summary=self._budget.summary(),
                    )
                # 将错误信息作为 observation 让 ReAct 继续尝试
                messages.append({
                    "role": "system",
                    "content": f"LLM调用失败: {response['content']}",
                })
                continue

            # 消耗Token
            tokens = response.get("usage", {}).get("total_tokens", 500)
            total_tokens += tokens
            self._budget.consume_tokens(tokens)

            # ── 美元成本强制 — RUL-064/NFR-095 ──
            if self._cost_enforcer:
                estimated_cost = tokens * self._cost_per_1k / 1000.0
                if not self._cost_enforcer.check_and_consume(estimated_cost):
                    logger.warning("成本预算耗尽，强制退出 ReAct 循环")
                    return ReActResult(
                        answer=self._validate_answer("[成本预算] 当前任务成本超出预算限制，已停止执行。", task_context),
                        exit_reason=ExitReason.COST_BUDGET_EXHAUSTED,
                        iterations=iterations,
                        total_tokens=total_tokens,
                        elapsed_time_ms=(time.monotonic() - start_time) * 1000,
                        tools_called=tools_called,
                        budget_summary=self._budget.summary(),
                    )

            content = response.get("content", "")
            tool_calls_raw = response.get("tool_calls", [])

            # 迭代记录
            record = IterationRecord(
                iteration=len(iterations),
                timestamp=time.time(),
                thought=content[:200] if content else "",
                tokens_consumed=tokens,
            )
            iterations.append(record)

            # 路径1: 正常完成（无工具调用）
            if not tool_calls_raw:
                return ReActResult(
                    answer=self._validate_answer(content, task_context),
                    exit_reason=ExitReason.NORMAL_COMPLETION,
                    iterations=iterations,
                    total_tokens=total_tokens,
                    elapsed_time_ms=(time.monotonic() - start_time) * 1000,
                    tools_called=tools_called,
                    budget_summary=self._budget.summary(),
                )

            # 路径2: 执行工具调用
            for tc in tool_calls_raw:
                tool_name = tc.get("name", "")
                arguments = tc.get("arguments", {})

                call = ToolCall(tool_name=tool_name, arguments=arguments)
                tools_called.append(call)
                record.action = call

                # 检查缓存
                cache_key = call.cache_key()
                if cache_key in self._tool_cache:
                    result = self._tool_cache[cache_key]
                    result.cached = True
                else:
                    # 执行工具
                    try:
                        output = await asyncio.wait_for(
                            self._tools.execute(tool_name, arguments),
                            timeout=30.0,
                        )
                        result = ToolResult(
                            call=call,
                            output=output,
                            execution_time_ms=0,
                        )
                        self._tool_cache[cache_key] = result
                        self._error_count = 0  # 重置错误计数
                    except Exception as e:
                        logger.error("Tool execution error: %s", e)
                        self._error_count += 1
                        result = ToolResult(
                            call=call,
                            output=None,
                            execution_time_ms=0,
                            error=str(e),
                        )
                        if self._error_count >= self._circuit_threshold:
                            return ReActResult(
                                answer=self._validate_answer(f"Circuit breaker triggered after {self._error_count} errors", task_context),
                                exit_reason=ExitReason.CIRCUIT_BREAKER,
                                iterations=iterations,
                                total_tokens=total_tokens,
                                elapsed_time_ms=(time.monotonic() - start_time) * 1000,
                                tools_called=tools_called,
                                budget_summary=self._budget.summary(),
                            )

                record.observation = result
                messages.append({
                    "role": "tool",
                    "content": str(result.output) if result.success else f"Error: {result.error}",
                    "tool_call_id": call.call_id,
                })

            # Checkpoint保存
            await self._checkpoint.save(session_id, {
                "iteration": len(iterations),
                "total_tokens": total_tokens,
                "messages": messages,
            })

            # 消耗迭代
            if self._budget.consume_iteration():
                logger.warning("Iteration limit reached")
                return ReActResult(
                    answer=self._validate_answer("Iteration limit reached", task_context),
                    exit_reason=ExitReason.ITERATION_LIMIT,
                    iterations=iterations,
                    total_tokens=total_tokens,
                    elapsed_time_ms=(time.monotonic() - start_time) * 1000,
                    tools_called=tools_called,
                    budget_summary=self._budget.summary(),
                )
