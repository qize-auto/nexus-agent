"""
NexusAgent v4.0+ — Execution Tracker

任务执行追踪器。
设计参考:
- Temporal Workflow Execution History: 每个步骤持久化记录
- Prefect Task Run States: PENDING → RUNNING → COMPLETED / FAILED

职责:
    1. 为每个任务创建原子性步骤记录
    2. 记录每步的执行证据 (工具调用、文件读取、中间产物)
    3. 验证任务完整性：所有步骤都有对应证据
    4. 发现跳步时抛 RetryRequiredException 触发重试
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("nexus.execution.tracker")


# ═══════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════

class StepStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    SKIPPED = auto()
    BLOCKED = auto()


class EvidenceType(Enum):
    TOOL_CALL = "tool_call"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    LLM_OUTPUT = "llm_output"
    USER_CONFIRM = "user_confirm"
    CHECKPOINT = "checkpoint"


@dataclass
class Step:
    """任务步骤"""
    step_id: str
    description: str
    status: StepStatus = StepStatus.PENDING
    required_evidence_types: List[EvidenceType] = field(default_factory=list)
    completed_evidence: List[str] = field(default_factory=list)  # evidence_id 列表
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_complete(self) -> bool:
        if not self.required_evidence_types:
            return self.status == StepStatus.COMPLETED
        # 每个 required 类型至少有一个证据
        return len(self.completed_evidence) >= len(self.required_evidence_types)


@dataclass
class Evidence:
    """执行证据"""
    evidence_id: str
    step_id: str
    evidence_type: EvidenceType
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskContext:
    """任务上下文 — 完整的执行追踪记录"""
    task_id: str
    user_message: str
    plan_steps: List[Step] = field(default_factory=list)
    evidence_log: List[Evidence] = field(default_factory=list)
    status: str = "pending"  # pending | running | completed | failed | incomplete
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_step(self, step_id: str) -> Optional[Step]:
        for s in self.plan_steps:
            if s.step_id == step_id:
                return s
        return None

    def get_evidence_for_step(self, step_id: str) -> List[Evidence]:
        return [e for e in self.evidence_log if e.step_id == step_id]

    def validate_completeness(self) -> tuple[bool, List[str]]:
        """
        验证任务完整性

        Returns:
            (is_complete, missing_steps)
        """
        missing = []
        for step in self.plan_steps:
            if step.status == StepStatus.SKIPPED:
                continue
            if not step.is_complete():
                missing.append(f"{step.step_id}: {step.description}")
        return len(missing) == 0, missing

    def completion_ratio(self) -> float:
        """完成比例 0.0-1.0"""
        if not self.plan_steps:
            return 1.0
        completed = sum(1 for s in self.plan_steps if s.is_complete() or s.status == StepStatus.SKIPPED)
        return completed / len(self.plan_steps)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_message": self.user_message,
            "status": self.status,
            "completion_ratio": self.completion_ratio(),
            "steps": [
                {
                    "step_id": s.step_id,
                    "description": s.description,
                    "status": s.status.name,
                    "required_evidence": [e.value for e in s.required_evidence_types],
                    "completed_evidence": s.completed_evidence,
                }
                for s in self.plan_steps
            ],
            "evidence_count": len(self.evidence_log),
            "created_at": self.created_at,
        }


# ═══════════════════════════════════════════════════════════════
# 异常
# ═══════════════════════════════════════════════════════════════

class RetryRequiredException(Exception):
    """
    检测到偷懒/跳步/不完整，需要重试

    被 REVEREngine 捕获后会自动重试
    """
    def __init__(self, reason: str, missing_items: Optional[List[str]] = None, task_context: Optional[TaskContext] = None):
        super().__init__(f"[执行保障] {reason}")
        self.reason = reason
        self.missing_items = missing_items or []
        self.task_context = task_context


# ═══════════════════════════════════════════════════════════════
# ExecutionTracker
# ═══════════════════════════════════════════════════════════════

class ExecutionTracker:
    """
    任务执行追踪器

    Usage:
        tracker = ExecutionTracker()

        # 创建任务
        ctx = tracker.create_task("task_1", "分析所有 py 文件")

        # 定义步骤
        tracker.add_step("task_1", Step("s1", "读取文件列表", required_evidence_types=[EvidenceType.TOOL_CALL]))
        tracker.add_step("task_1", Step("s2", "分析每个文件", required_evidence_types=[EvidenceType.FILE_READ]))

        # 记录证据
        tracker.record_evidence("task_1", Evidence("e1", "s1", EvidenceType.TOOL_CALL, "file_list"))
        tracker.record_evidence("task_1", Evidence("e2", "s2", EvidenceType.FILE_READ, "content of a.py"))

        # 验证
        is_complete, missing = tracker.validate("task_1")
    """

    def __init__(self):
        self._tasks: Dict[str, TaskContext] = {}

    def create_task(self, task_id: str, user_message: str) -> TaskContext:
        """创建任务追踪上下文"""
        ctx = TaskContext(task_id=task_id, user_message=user_message, status="pending")
        self._tasks[task_id] = ctx
        logger.debug("ExecutionTracker: 创建任务 %s", task_id)
        return ctx

    def get_task(self, task_id: str) -> Optional[TaskContext]:
        return self._tasks.get(task_id)

    def add_step(self, task_id: str, step: Step) -> None:
        """为任务添加步骤"""
        ctx = self._tasks.get(task_id)
        if not ctx:
            logger.warning("ExecutionTracker: 任务 %s 不存在，无法添加步骤", task_id)
            return
        ctx.plan_steps.append(step)
        logger.debug("ExecutionTracker: 任务 %s 添加步骤 %s", task_id, step.step_id)

    def start_step(self, task_id: str, step_id: str) -> None:
        """标记步骤开始"""
        step = self._get_step(task_id, step_id)
        if step:
            step.status = StepStatus.RUNNING

    def complete_step(self, task_id: str, step_id: str) -> None:
        """标记步骤完成"""
        step = self._get_step(task_id, step_id)
        if step:
            step.status = StepStatus.COMPLETED
            step.completed_at = time.time()

    def skip_step(self, task_id: str, step_id: str) -> None:
        """标记步骤跳过"""
        step = self._get_step(task_id, step_id)
        if step:
            step.status = StepStatus.SKIPPED

    def record_evidence(self, task_id: str, evidence: Evidence) -> None:
        """记录执行证据"""
        ctx = self._tasks.get(task_id)
        if not ctx:
            return
        ctx.evidence_log.append(evidence)

        # 自动关联到对应步骤
        step = self._get_step(task_id, evidence.step_id)
        if step and evidence.evidence_id not in step.completed_evidence:
            step.completed_evidence.append(evidence.evidence_id)
            # 如果该步骤所需的证据类型都已满足，自动标记完成
            if step.required_evidence_types:
                existing_types = {
                    e.evidence_type for e in ctx.get_evidence_for_step(step.step_id)
                }
                if all(req in existing_types for req in step.required_evidence_types):
                    step.status = StepStatus.COMPLETED
                    step.completed_at = time.time()

        logger.debug("ExecutionTracker: 任务 %s 记录证据 %s (type=%s)", task_id, evidence.evidence_id, evidence.evidence_type.value)

    def validate(self, task_id: str) -> tuple[bool, List[str]]:
        """验证任务完整性"""
        ctx = self._tasks.get(task_id)
        if not ctx:
            return False, ["任务不存在"]
        return ctx.validate_completeness()

    def auto_plan_from_message(self, task_id: str) -> TaskContext:
        """
        从用户消息自动生成执行计划（启发式）

        识别关键词：
            - "所有" / "每个" / "全部" → 添加枚举步骤
            - "分析" → 添加分析步骤
            - "修复" → 添加修复步骤
            - "生成报告" → 添加报告步骤
        """
        ctx = self._tasks.get(task_id)
        if not ctx:
            return self.create_task(task_id, "")

        msg = ctx.user_message.lower()

        steps = []
        step_idx = 0

        # 文件/目录枚举步骤
        if any(kw in msg for kw in ("所有", "每个", "全部", "all", "every")):
            steps.append(Step(
                step_id=f"step_{step_idx}",
                description="枚举目标范围内的所有条目",
                required_evidence_types=[EvidenceType.TOOL_CALL],
            ))
            step_idx += 1

        # 读取/分析步骤
        if any(kw in msg for kw in ("分析", "读取", "检查", "analyze", "read", "check")):
            steps.append(Step(
                step_id=f"step_{step_idx}",
                description="逐条读取并分析目标内容",
                required_evidence_types=[EvidenceType.FILE_READ],
            ))
            step_idx += 1

        # 修复/修改步骤
        if any(kw in msg for kw in ("修复", "修改", "fix", "repair", "update")):
            steps.append(Step(
                step_id=f"step_{step_idx}",
                description="执行修复或修改操作",
                required_evidence_types=[EvidenceType.FILE_WRITE],
            ))
            step_idx += 1

        # 输出/报告步骤
        if any(kw in msg for kw in ("报告", "输出", "生成", "report", "output", "generate")):
            steps.append(Step(
                step_id=f"step_{step_idx}",
                description="汇总结果并生成最终输出",
                required_evidence_types=[EvidenceType.LLM_OUTPUT],
            ))
            step_idx += 1

        # 默认步骤：至少有一个执行步骤
        if not steps:
            steps.append(Step(
                step_id="step_0",
                description="执行用户请求",
                required_evidence_types=[],
            ))

        for s in steps:
            ctx.plan_steps.append(s)

        logger.info("ExecutionTracker: 任务 %s 自动生成 %d 个步骤", task_id, len(steps))
        return ctx

    def _get_step(self, task_id: str, step_id: str) -> Optional[Step]:
        ctx = self._tasks.get(task_id)
        if not ctx:
            return None
        return ctx.get_step(step_id)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_tasks": len(self._tasks),
            "by_status": {
                "pending": sum(1 for t in self._tasks.values() if t.status == "pending"),
                "running": sum(1 for t in self._tasks.values() if t.status == "running"),
                "completed": sum(1 for t in self._tasks.values() if t.status == "completed"),
                "failed": sum(1 for t in self._tasks.values() if t.status == "failed"),
                "incomplete": sum(1 for t in self._tasks.values() if t.status == "incomplete"),
            },
        }


# ═══════════════════════════════════════════════════════════════
# 装饰器
# ═══════════════════════════════════════════════════════════════

def track_execution(tracker: ExecutionTracker, task_id_factory: Optional[Callable[[], str]] = None):
    """
    执行追踪装饰器

    Usage:
        tracker = ExecutionTracker()

        @track_execution(tracker)
        async def my_operation():
            ...
    """
    def decorator(fn: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            tid = (task_id_factory or (lambda: str(uuid.uuid4())))()
            user_msg = kwargs.get("user_message", "") or (args[2] if len(args) > 2 else "")

            ctx = tracker.create_task(tid, user_msg)
            tracker.auto_plan_from_message(tid)
            ctx.status = "running"

            try:
                result = await fn(*args, **kwargs)
                ctx.status = "completed"
                ctx.completed_at = time.time()

                # 验证完整性
                is_complete, missing = tracker.validate(tid)
                if not is_complete:
                    ctx.status = "incomplete"
                    raise RetryRequiredException(
                        reason=f"任务执行不完整，缺失步骤: {missing}",
                        missing_items=missing,
                        task_context=ctx,
                    )

                return result
            except RetryRequiredException:
                raise
            except Exception as e:
                ctx.status = "failed"
                logger.warning("ExecutionTracker: 任务 %s 执行失败: %s", tid, e)
                raise

        return wrapper
    return decorator
