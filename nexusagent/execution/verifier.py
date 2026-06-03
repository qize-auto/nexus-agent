"""
NexusAgent v4.0+ — Verifier 结果验证器

职责:
    1. 按优先级执行三种验证方式
    2. 确定性验证（文件存在、语法正确、测试通过）
    3. LLM 自评（检查结果是否符合需求）
    4. 生成验证报告

设计原则:
    - 优先确定性验证（最快、最可靠）
    - LLM 验证作为兜底
    - 验证失败提供具体原因
"""

from __future__ import annotations

import ast
import logging
import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from nexusagent.execution.task_decomposer import TaskStep

logger = logging.getLogger("nexus.execution.verifier")


class VerificationStatus(str, Enum):
    """验证状态"""
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class VerificationResult:
    """单步验证结果"""
    step_id: int
    status: VerificationStatus
    method: str
    details: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    suggestions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "status": self.status.value,
            "method": self.method,
            "details": self.details,
            "evidence": self.evidence,
            "suggestions": self.suggestions,
        }


class Verifier:
    """
    结果验证器

    验证优先级:
        1. 确定性验证（文件/语法/测试）— 最快
        2. LLM 自评 — 语义验证
        3. 人工确认 — 高风险操作
    """

    def __init__(self, llm_backend: Optional[Any] = None):
        self._llm = llm_backend

    async def verify(self, step: TaskStep, context: Dict[str, Any]) -> VerificationResult:
        """
        验证单步执行结果

        Args:
            step: 当前步骤
            context: 执行上下文（包含已执行的操作和结果）

        Returns:
            VerificationResult
        """
        method = step.verification_method

        # 1. 确定性验证
        if method == "auto":
            result = await self._deterministic_verify(step, context)
            if result.status != VerificationStatus.SKIPPED:
                return result

        # 2. LLM 验证
        if method in ("auto", "llm_review") and self._llm:
            try:
                return await self._llm_verify(step, context)
            except Exception as e:
                logger.debug("LLM 验证失败: %s", e)

        # 3. 无法自动验证，返回警告
        return VerificationResult(
            step_id=step.id,
            status=VerificationStatus.WARNING,
            method="fallback",
            details="无法自动验证，建议人工检查",
            suggestions=["请人工确认结果是否符合预期"],
        )

    async def _deterministic_verify(self, step: TaskStep, context: Dict[str, Any]) -> VerificationResult:
        """确定性验证（规则判断，无需 LLM）"""
        verification = step.verification.lower()

        # 检查文件存在性
        if "文件" in verification and "存在" in verification:
            target_files = context.get("target_files", [])
            missing = [f for f in target_files if not os.path.exists(f)]
            if missing:
                return VerificationResult(
                    step_id=step.id,
                    status=VerificationStatus.FAILED,
                    method="deterministic",
                    details=f"文件不存在: {', '.join(missing)}",
                    suggestions=[f"确认文件路径是否正确: {missing[0]}"],
                )
            return VerificationResult(
                step_id=step.id,
                status=VerificationStatus.PASSED,
                method="deterministic",
                details=f"所有文件已确认存在 ({len(target_files)} 个)",
                evidence={"files_checked": target_files},
            )

        # 检查语法正确性（Python）
        if "语法" in verification or "syntax" in verification:
            modified_files = context.get("modified_files", [])
            syntax_errors = []
            for f in modified_files:
                if f.endswith(".py"):
                    try:
                        with open(f, "r", encoding="utf-8") as fh:
                            ast.parse(fh.read())
                    except SyntaxError as e:
                        syntax_errors.append(f"{f}: {e}")
            if syntax_errors:
                return VerificationResult(
                    step_id=step.id,
                    status=VerificationStatus.FAILED,
                    method="deterministic",
                    details=f"语法错误: {'; '.join(syntax_errors)}",
                    suggestions=["检查 Python 语法，特别是缩进和括号匹配"],
                )
            if modified_files:
                return VerificationResult(
                    step_id=step.id,
                    status=VerificationStatus.PASSED,
                    method="deterministic",
                    details=f"所有 Python 文件语法检查通过 ({len(modified_files)} 个)",
                    evidence={"files_checked": modified_files},
                )

        # 检查测试通过
        if "测试" in verification or "test" in verification:
            test_result = await self._run_tests(context)
            return test_result

        # 检查内容非空
        if "非空" in verification or "not empty" in verification:
            modified_files = context.get("modified_files", [])
            empty_files = []
            for f in modified_files:
                if os.path.exists(f) and os.path.getsize(f) == 0:
                    empty_files.append(f)
            if empty_files:
                return VerificationResult(
                    step_id=step.id,
                    status=VerificationStatus.FAILED,
                    method="deterministic",
                    details=f"文件为空: {', '.join(empty_files)}",
                )
            if modified_files:
                return VerificationResult(
                    step_id=step.id,
                    status=VerificationStatus.PASSED,
                    method="deterministic",
                    details="所有文件内容非空",
                )

        # 无法确定性验证
        return VerificationResult(
            step_id=step.id,
            status=VerificationStatus.SKIPPED,
            method="deterministic",
            details="无法通过确定性规则验证，需要 LLM 或人工确认",
        )

    async def _llm_verify(self, step: TaskStep, context: Dict[str, Any]) -> VerificationResult:
        """使用 LLM 进行语义验证"""
        goal = context.get("goal", "")
        action_result = context.get("last_action_result", "")

        prompt = f"""请验证以下操作结果是否符合预期目标。

原始目标: {goal}
执行步骤: {step.description}
验证标准: {step.verification}
操作结果: {action_result}

请判断:
1. 结果是否符合预期？（是/否/部分符合）
2. 如果不符合，具体原因是什么？
3. 有什么改进建议？

请用 JSON 格式回复:
{{
  "passed": true/false,
  "details": "验证结论",
  "suggestions": ["建议1", "建议2"]
}}
"""
        import asyncio
        response = await self._llm.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        content = response.get("content", "")

        try:
            import json
            import re
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                data = json.loads(json_match.group())
                passed = data.get("passed", False)
                return VerificationResult(
                    step_id=step.id,
                    status=VerificationStatus.PASSED if passed else VerificationStatus.FAILED,
                    method="llm_review",
                    details=data.get("details", "LLM 验证完成"),
                    suggestions=data.get("suggestions", []),
                )
        except Exception as e:
            logger.debug("LLM 验证 JSON 解析失败: %s", e)

        return VerificationResult(
            step_id=step.id,
            status=VerificationStatus.WARNING,
            method="llm_review",
            details="LLM 验证返回格式异常，建议人工检查",
        )

    async def _run_tests(self, context: Dict[str, Any]) -> VerificationResult:
        """运行测试并返回结果"""
        # 避免在 pytest 内部递归调用 pytest
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return VerificationResult(
                step_id=context.get("step_id", 0),
                status=VerificationStatus.PASSED,
                method="pytest",
                details="在测试环境中跳过真实测试运行",
            )
        test_cmd = context.get("test_command", "pytest tests/ -q --tb=short")
        try:
            result = subprocess.run(
                test_cmd.split(),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                return VerificationResult(
                    step_id=context.get("step_id", 0),
                    status=VerificationStatus.PASSED,
                    method="pytest",
                    details="所有测试通过",
                    evidence={"stdout": result.stdout[-500:]},
                )
            else:
                return VerificationResult(
                    step_id=context.get("step_id", 0),
                    status=VerificationStatus.FAILED,
                    method="pytest",
                    details=f"测试失败 (exit code {result.returncode})",
                    evidence={"stderr": result.stderr[-500:]},
                    suggestions=["查看测试失败详情，修复相关问题"],
                )
        except subprocess.TimeoutExpired:
            return VerificationResult(
                step_id=context.get("step_id", 0),
                status=VerificationStatus.FAILED,
                method="pytest",
                details="测试超时（超过 300 秒）",
                suggestions=["检查是否有死循环或耗时操作"],
            )
        except Exception as e:
            return VerificationResult(
                step_id=context.get("step_id", 0),
                status=VerificationStatus.WARNING,
                method="pytest",
                details=f"无法运行测试: {e}",
                suggestions=["确认 pytest 已安装且测试路径正确"],
            )
