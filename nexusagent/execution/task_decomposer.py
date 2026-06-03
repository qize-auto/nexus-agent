"""
NexusAgent v4.0+ — Task Decomposer 任务分解器

职责:
    1. 将明确的目标分解为原子执行步骤
    2. 每个步骤附带验证标准
    3. 识别步骤间的依赖关系
    4. 生成可回滚的执行计划

设计原则:
    - 可验证: 每步必须有明确的通过/失败标准
    - 可回滚: 每步独立，失败可回退到上一步
    - 不过度分解: 简单任务 2-4 步，复杂任务最多 8 步
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nexus.execution.decomposer")


class StepType(str, Enum):
    """步骤类型"""
    LOCATE = "locate"           # 定位资源（文件、模块）
    READ = "read"               # 读取内容
    ANALYZE = "analyze"         # 分析现状
    MODIFY = "modify"           # 执行修改
    VERIFY = "verify"           # 验证结果
    TEST = "test"               # 运行测试
    CLEANUP = "cleanup"         # 清理/回滚
    DELIVER = "deliver"         # 交付报告


@dataclass
class TaskStep:
    """原子执行步骤"""
    id: int
    type: StepType
    description: str                    # 人类可读的描述
    action: str                         # 具体动作
    verification: str                   # 验证标准
    verification_method: str = "auto"   # auto | llm_review | human_confirm
    dependencies: List[int] = field(default_factory=list)
    rollback_action: str = ""           # 回退操作
    estimated_cost_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "description": self.description,
            "action": self.action,
            "verification": self.verification,
            "verification_method": self.verification_method,
            "dependencies": self.dependencies,
            "rollback_action": self.rollback_action,
        }


@dataclass
class TaskPlan:
    """任务执行计划"""
    goal: str
    steps: List[TaskStep]
    total_steps: int = 0
    estimated_cost_usd: float = 0.0
    risks: List[str] = field(default_factory=list)
    fallback_plan: str = ""

    def __post_init__(self):
        self.total_steps = len(self.steps)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "total_steps": self.total_steps,
            "steps": [s.to_dict() for s in self.steps],
            "risks": self.risks,
            "fallback_plan": self.fallback_plan,
        }

    def get_ready_steps(self, completed: List[int]) -> List[TaskStep]:
        """获取当前可执行的步骤（依赖已满足）"""
        ready = []
        for step in self.steps:
            if step.id in completed:
                continue
            if all(dep in completed for dep in step.dependencies):
                ready.append(step)
        return ready


class TaskDecomposer:
    """
    任务分解器

    基于任务类型和上下文生成执行计划。
    优先使用规则模板，复杂场景可调用 LLM。
    """

    def __init__(self, llm_backend: Optional[Any] = None):
        self._llm = llm_backend

    async def decompose(self, goal: str, task_type: str, target_files: List[str], context: str = "") -> TaskPlan:
        """
        分解任务为执行计划

        Args:
            goal: 明确的目标描述
            task_type: 任务类型 (coding/refactoring/debugging/...)
            target_files: 目标文件列表
            context: 额外上下文

        Returns:
            TaskPlan
        """
        # 1. 尝试规则模板
        plan = self._template_based_decompose(goal, task_type, target_files)
        if plan:
            logger.info("任务分解完成（规则模板）: %d 步骤", plan.total_steps)
            return plan

        # 2. 如果规则无法覆盖，尝试 LLM
        if self._llm:
            try:
                plan = await self._llm_decompose(goal, task_type, target_files, context)
                if plan:
                    logger.info("任务分解完成（LLM）: %d 步骤", plan.total_steps)
                    return plan
            except Exception as e:
                logger.debug("LLM 任务分解失败: %s", e)

        # 3. 兜底：通用计划
        return self._fallback_plan(goal, target_files)

    def _template_based_decompose(self, goal: str, task_type: str, target_files: List[str]) -> Optional[TaskPlan]:
        """基于任务类型的规则模板分解"""
        steps = []
        step_id = 1

        # 通用前置步骤：定位文件
        if target_files:
            steps.append(TaskStep(
                id=step_id,
                type=StepType.LOCATE,
                description="确认目标文件存在",
                action=f"检查文件是否存在: {', '.join(target_files)}",
                verification="所有目标文件已确认存在且可访问",
                verification_method="auto",
                rollback_action="无需回滚",
            ))
            step_id += 1

        # 读取文件内容
        if target_files and task_type in ("coding", "refactoring", "debugging"):
            steps.append(TaskStep(
                id=step_id,
                type=StepType.READ,
                description="读取文件内容",
                action=f"读取目标文件内容: {', '.join(target_files[:3])}",
                verification="文件内容已完整读取，无编码错误",
                verification_method="auto",
                dependencies=[1] if step_id > 2 else [],
                rollback_action="无需回滚",
            ))
            step_id += 1

        # 根据任务类型添加特定步骤
        if task_type == "coding":
            steps.extend(self._coding_steps(goal, target_files, step_id))
        elif task_type == "refactoring":
            steps.extend(self._refactoring_steps(goal, target_files, step_id))
        elif task_type == "debugging":
            steps.extend(self._debugging_steps(goal, target_files, step_id))
        elif task_type == "testing":
            steps.extend(self._testing_steps(goal, target_files, step_id))
        elif task_type == "config":
            steps.extend(self._config_steps(goal, target_files, step_id))
        else:
            # 通用任务：修改 + 验证
            steps.extend(self._generic_steps(goal, target_files, step_id))

        if not steps:
            return None

        # 通用后置步骤：验证 + 交付
        last_id = max(s.id for s in steps)
        steps.append(TaskStep(
            id=last_id + 1,
            type=StepType.VERIFY,
            description="验证所有修改",
            action="运行相关单元测试和回归测试",
            verification="所有测试通过，无回归",
            verification_method="auto",
            dependencies=[last_id],
            rollback_action="恢复到修改前状态",
        ))

        return TaskPlan(
            goal=goal,
            steps=steps,
            risks=["文件路径可能不正确", "修改可能影响其他模块"],
            fallback_plan="如果修改失败，回退到原始文件并报告错误",
        )

    def _coding_steps(self, goal: str, target_files: List[str], start_id: int) -> List[TaskStep]:
        """编码任务的步骤模板"""
        deps = [start_id - 1] if start_id > 2 else []
        return [
            TaskStep(
                id=start_id,
                type=StepType.MODIFY,
                description="编写/修改代码",
                action=f"根据需求实现代码: {goal[:80]}",
                verification="代码语法正确，符合需求描述",
                verification_method="auto",
                dependencies=deps,
                rollback_action="恢复到修改前的文件版本",
            ),
        ]

    def _refactoring_steps(self, goal: str, target_files: List[str], start_id: int) -> List[TaskStep]:
        deps = [start_id - 1] if start_id > 2 else []
        return [
            TaskStep(
                id=start_id,
                type=StepType.ANALYZE,
                description="分析现有代码结构",
                action="识别需要重构的代码段和依赖关系",
                verification="重构目标明确，影响范围可控",
                verification_method="auto",
                dependencies=deps,
            ),
            TaskStep(
                id=start_id + 1,
                type=StepType.MODIFY,
                description="执行重构",
                action=f"执行重构: {goal[:80]}",
                verification="重构后代码功能等价，测试通过",
                verification_method="auto",
                dependencies=[start_id],
                rollback_action="恢复到重构前的文件版本",
            ),
        ]

    def _debugging_steps(self, goal: str, target_files: List[str], start_id: int) -> List[TaskStep]:
        deps = [start_id - 1] if start_id > 2 else []
        return [
            TaskStep(
                id=start_id,
                type=StepType.ANALYZE,
                description="定位问题根源",
                action="分析错误信息和代码，定位 bug",
                verification="问题根因已确认，不是表面现象",
                verification_method="auto",
                dependencies=deps,
            ),
            TaskStep(
                id=start_id + 1,
                type=StepType.MODIFY,
                description="修复 bug",
                action=f"修复问题: {goal[:80]}",
                verification="修复后原问题不再复现",
                verification_method="auto",
                dependencies=[start_id],
                rollback_action="恢复到修复前的文件版本",
            ),
        ]

    def _testing_steps(self, goal: str, target_files: List[str], start_id: int) -> List[TaskStep]:
        deps = [start_id - 1] if start_id > 2 else []
        return [
            TaskStep(
                id=start_id,
                type=StepType.MODIFY,
                description="编写/修改测试",
                action=f"编写测试: {goal[:80]}",
                verification="测试代码语法正确，覆盖了目标场景",
                verification_method="auto",
                dependencies=deps,
            ),
            TaskStep(
                id=start_id + 1,
                type=StepType.TEST,
                description="运行测试",
                action="执行新增/修改的测试用例",
                verification="测试通过，无失败",
                verification_method="auto",
                dependencies=[start_id],
            ),
        ]

    def _config_steps(self, goal: str, target_files: List[str], start_id: int) -> List[TaskStep]:
        deps = [start_id - 1] if start_id > 2 else []
        return [
            TaskStep(
                id=start_id,
                type=StepType.MODIFY,
                description="修改配置",
                action=f"更新配置: {goal[:80]}",
                verification="配置文件格式正确，参数值合法",
                verification_method="auto",
                dependencies=deps,
                rollback_action="恢复原始配置",
            ),
        ]

    def _generic_steps(self, goal: str, target_files: List[str], start_id: int) -> List[TaskStep]:
        deps = [start_id - 1] if start_id > 2 else []
        return [
            TaskStep(
                id=start_id,
                type=StepType.MODIFY,
                description="执行修改",
                action=f"执行: {goal[:80]}",
                verification="操作完成，结果符合预期",
                verification_method="llm_review",
                dependencies=deps,
                rollback_action="尽可能恢复到原始状态",
            ),
        ]

    async def _llm_decompose(self, goal: str, task_type: str, target_files: List[str], context: str) -> Optional[TaskPlan]:
        """使用 LLM 分解任务"""
        files_str = ", ".join(target_files) if target_files else "未指定"
        prompt = f"""请将以下任务分解为可执行的原子步骤。

任务目标: {goal}
任务类型: {task_type}
目标文件: {files_str}
上下文: {context}

要求:
1. 每步必须有明确的验证标准
2. 每步必须能独立回滚
3. 最多 6 步
4. 使用 JSON 数组格式

格式示例:
[
  {{
    "id": 1,
    "type": "locate",
    "description": "...",
    "action": "...",
    "verification": "...",
    "verification_method": "auto",
    "dependencies": [],
    "rollback_action": "..."
  }}
]
"""
        response = await self._llm.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        content = response.get("content", "")

        try:
            import json
            import re
            json_match = re.search(r'\[[\s\S]*\]', content)
            if json_match:
                data = json.loads(json_match.group())
                steps = []
                for item in data:
                    steps.append(TaskStep(
                        id=item["id"],
                        type=StepType(item.get("type", "modify")),
                        description=item["description"],
                        action=item["action"],
                        verification=item["verification"],
                        verification_method=item.get("verification_method", "auto"),
                        dependencies=item.get("dependencies", []),
                        rollback_action=item.get("rollback_action", ""),
                    ))
                return TaskPlan(goal=goal, steps=steps)
        except Exception as e:
            logger.debug("LLM 任务分解解析失败: %s", e)

        return None

    def _fallback_plan(self, goal: str, target_files: List[str]) -> TaskPlan:
        """兜底通用计划"""
        steps = [
            TaskStep(
                id=1,
                type=StepType.MODIFY,
                description="执行用户请求的操作",
                action=f"执行: {goal[:100]}",
                verification="操作已完成，结果可验证",
                verification_method="llm_review",
                rollback_action="记录原始状态以便回滚",
            ),
            TaskStep(
                id=2,
                type=StepType.VERIFY,
                description="验证操作结果",
                action="检查结果是否符合用户预期",
                verification="用户目标已达成或已说明限制",
                verification_method="llm_review",
                dependencies=[1],
            ),
        ]
        return TaskPlan(
            goal=goal,
            steps=steps,
            risks=["计划为通用模板，可能未覆盖所有边界情况"],
            fallback_plan="如执行失败，向用户报告并请求进一步指导",
        )
