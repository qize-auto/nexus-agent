# 🧪 EXPERIMENTAL / 实验性模块
# 该模块尚未接入 NexusAgent 主执行流程。
# 功能完整且在测试中被引用，但 API 可能不稳定。
# This module is not yet wired into the main NexusAgent execution flow.
# Fully functional in isolation with test coverage, but APIs may change.
"""
NexusAgent v4.0+ — 回归测试套件

职责:
    1. 加载历史 golden answers
    2. 对新版本模型输出进行评估
    3. 退化超过阈值时阻断发布
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from nexusagent.evals.framework import EvalRunner, EvalResult, ExactMatchEvaluator, ContainsEvaluator

logger = logging.getLogger("nexus.evals.regression")


@dataclass
class RegressionTestCase:
    """回归测试用例"""
    id: str
    input_data: str
    expected_output: str
    tags: List[str] = field(default_factory=list)


@dataclass
class RegressionResult:
    """回归测试结果"""
    test_id: str
    input_data: str
    expected: str
    actual: str
    eval_results: List[EvalResult]
    overall_passed: bool


class RegressionSuite:
    """
    回归测试套件

    Usage:
        suite = RegressionSuite.from_json("regression_tests.json")
        results = await suite.run(agent)
        if not suite.is_acceptable(results):
            raise RuntimeError("回归测试失败，阻断发布")
    """

    def __init__(self, test_cases: List[RegressionTestCase], threshold: float = 0.8):
        self._test_cases = test_cases
        self._threshold = threshold
        self._eval_runner = EvalRunner()
        self._eval_runner.add_evaluator(ExactMatchEvaluator())
        self._eval_runner.add_evaluator(ContainsEvaluator())

    @classmethod
    def from_json(cls, path: str) -> "RegressionSuite":
        """从 JSON 文件加载测试用例"""
        data = Path(path).read_text(encoding="utf-8")
        items = json.loads(data)
        cases = [
            RegressionTestCase(
                id=item.get("id", f"case_{i}"),
                input_data=item["input"],
                expected_output=item["expected"],
                tags=item.get("tags", []),
            )
            for i, item in enumerate(items)
        ]
        return cls(cases)

    async def run(self, agent_fn) -> List[RegressionResult]:
        """运行回归测试"""
        results = []
        for case in self._test_cases:
            try:
                actual = await agent_fn(case.input_data)
                eval_results = await self._eval_runner.run(
                    case.input_data, actual, case.expected_output,
                )
                overall_passed = all(r.passed for r in eval_results)

                results.append(RegressionResult(
                    test_id=case.id,
                    input_data=case.input_data,
                    expected=case.expected_output,
                    actual=actual,
                    eval_results=eval_results,
                    overall_passed=overall_passed,
                ))
            except Exception as e:
                logger.error("回归测试用例 %s 失败: %s", case.id, e)
                results.append(RegressionResult(
                    test_id=case.id,
                    input_data=case.input_data,
                    expected=case.expected_output,
                    actual=f"ERROR: {e}",
                    eval_results=[],
                    overall_passed=False,
                ))
        return results

    def is_acceptable(self, results: List[RegressionResult]) -> bool:
        """检查回归测试是否通过"""
        if not results:
            return True

        pass_rate = sum(1 for r in results if r.overall_passed) / len(results)
        return pass_rate >= self._threshold

    def report(self, results: List[RegressionResult]) -> Dict[str, Any]:
        """生成回归测试报告"""
        total = len(results)
        passed = sum(1 for r in results if r.overall_passed)
        failed = total - passed
        pass_rate = passed / total if total > 0 else 0.0

        return {
            "total_tests": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": round(pass_rate, 2),
            "threshold": self._threshold,
            "acceptable": self.is_acceptable(results),
            "failures": [
                {
                    "test_id": r.test_id,
                    "input": r.input_data[:100],
                    "expected": r.expected[:100],
                    "actual": r.actual[:100],
                }
                for r in results if not r.overall_passed
            ],
        }
