"""
NexusAgent v4.0+ — Delivery Report Generator 交付报告生成器

职责:
    1. 汇总任务执行全过程
    2. 生成结构化交付报告（Markdown）
    3. 包含完成状态、修改摘要、验证证据、已知限制

设计原则:
    - 人类可读: Markdown 格式，层次清晰
    - 完整透明: 成功/失败/回滚都如实记录
    - 可审计: 包含时间戳、步骤详情、验证结果
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from nexusagent.execution.task_decomposer import TaskPlan
from nexusagent.execution.verifier import VerificationResult

logger = logging.getLogger("nexus.execution.delivery")


@dataclass
class ExecutionRecord:
    """单步执行记录"""
    step_id: int
    step_description: str
    status: str  # success | failed | skipped
    duration_ms: float
    verification: Optional[VerificationResult] = None
    error: Optional[str] = None


@dataclass
class DeliveryReport:
    """交付报告"""
    goal: str
    total_steps: int
    completed_steps: int
    failed_steps: int
    execution_records: List[ExecutionRecord]
    modified_files: List[str]
    test_results: str
    limitations: List[str]
    generated_at: float = field(default_factory=time.time)

    @property
    def success_rate(self) -> float:
        if self.total_steps == 0:
            return 0.0
        return self.completed_steps / self.total_steps

    @property
    def is_success(self) -> bool:
        return self.failed_steps == 0 and self.completed_steps == self.total_steps


class DeliveryReportGenerator:
    """交付报告生成器"""

    def generate(self, plan: TaskPlan, records: List[ExecutionRecord], context: Dict[str, Any]) -> str:
        """
        生成 Markdown 格式的交付报告

        Args:
            plan: 原始执行计划
            records: 执行记录列表
            context: 额外上下文（修改的文件、测试结果等）

        Returns:
            Markdown 文本
        """
        completed = sum(1 for r in records if r.status == "success")
        failed = sum(1 for r in records if r.status == "failed")
        total = len(records)

        lines = []
        lines.append("## 执行结果")
        lines.append("")

        # 总体状态
        if failed == 0:
            lines.append("✅ **全部完成** — 所有步骤执行成功并通过验证")
        elif completed > 0:
            lines.append(f"⚠️ **部分完成** — {completed}/{total} 步骤成功，{failed} 步骤失败")
        else:
            lines.append("❌ **执行失败** — 未能完成目标")
        lines.append("")

        # 完成的任务
        lines.append("### 执行步骤")
        for record in records:
            icon = "✅" if record.status == "success" else "❌" if record.status == "failed" else "⏭️"
            lines.append(f"{icon} **步骤 {record.step_id}**: {record.step_description}")
            if record.verification:
                v = record.verification
                v_icon = "✓" if v.status.value == "passed" else "✗" if v.status.value == "failed" else "⚠"
                lines.append(f"   {v_icon} 验证 ({v.method}): {v.details}")
                if v.suggestions:
                    for s in v.suggestions:
                        lines.append(f"   💡 建议: {s}")
            if record.error:
                lines.append(f"   ⚠️ 错误: {record.error}")
            lines.append(f"   ⏱ 耗时: {record.duration_ms:.0f}ms")
            lines.append("")

        # 修改摘要
        modified_files = context.get("modified_files", [])
        if modified_files:
            lines.append("### 修改摘要")
            for f in modified_files:
                lines.append(f"- `{f}`")
            lines.append("")

        # 验证证据
        test_output = context.get("test_output", "")
        if test_output:
            lines.append("### 验证证据")
            lines.append("```")
            lines.append(test_output[-1000:])  # 截断防止过长
            lines.append("```")
            lines.append("")

        # 已知限制
        limitations = context.get("limitations", plan.risks if hasattr(plan, "risks") else [])
        if limitations:
            lines.append("### 已知限制")
            for lim in limitations:
                lines.append(f"- {lim}")
            lines.append("")

        # 时间戳
        lines.append(f"*报告生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}*")

        return "\n".join(lines)

    def generate_summary(self, report: DeliveryReport) -> str:
        """生成一句话摘要"""
        if report.is_success:
            return f"任务完成: {report.goal[:60]}... ({report.completed_steps}/{report.total_steps} 步骤成功)"
        elif report.completed_steps > 0:
            return f"任务部分完成: {report.goal[:60]}... ({report.completed_steps} 成功, {report.failed_steps} 失败)"
        else:
            return f"任务失败: {report.goal[:60]}..."
