# 🧪 EXPERIMENTAL / 实验性模块
# 该模块尚未接入 NexusAgent 主执行流程（main.py / cli / orchestrator）。
# 功能完整且在测试中被引用，但 API 可能不稳定。
# This module is not yet wired into the main NexusAgent execution flow.
# Fully functional in isolation with test coverage, but APIs may change.
"""
NexusAgent v4.0+ — 评估框架

设计参考:
- Mastra Evals: https://mastra.ai/docs/evals
  "Model-graded, rule-based, and heuristic evaluators"
- OpenAI Evals: https://github.com/openai/evals

支持:
    - ModelGradedEval: LLM 作为评判者
    - ExactMatchEval: 精确匹配
    - SemanticSimilarityEval: 语义相似度
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nexus.evals")


@dataclass
class EvalResult:
    """评估结果"""
    score: float  # 0.0-1.0
    passed: bool
    evaluator: str
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseEvaluator(ABC):
    """评估器基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def evaluate(self, input_data: str, output: str, expected: Optional[str] = None) -> EvalResult:
        ...


class ExactMatchEvaluator(BaseEvaluator):
    """精确匹配评估器"""

    @property
    def name(self) -> str:
        return "exact_match"

    async def evaluate(self, input_data: str, output: str, expected: Optional[str] = None) -> EvalResult:
        if expected is None:
            return EvalResult(score=0.0, passed=False, evaluator=self.name, reason="无期望输出")
        match = output.strip() == expected.strip()
        return EvalResult(
            score=1.0 if match else 0.0,
            passed=match,
            evaluator=self.name,
            reason="完全匹配" if match else f"期望: {expected[:100]}, 实际: {output[:100]}",
        )


class ContainsEvaluator(BaseEvaluator):
    """包含匹配评估器"""

    def __init__(self, required_phrases: Optional[List[str]] = None):
        self._required = required_phrases or []

    @property
    def name(self) -> str:
        return "contains"

    async def evaluate(self, input_data: str, output: str, expected: Optional[str] = None) -> EvalResult:
        if not self._required:
            return EvalResult(score=1.0, passed=True, evaluator=self.name, reason="无必需短语")

        found = [p for p in self._required if p.lower() in output.lower()]
        score = len(found) / len(self._required)
        return EvalResult(
            score=score,
            passed=score >= 1.0,
            evaluator=self.name,
            reason=f"找到 {len(found)}/{len(self._required)} 个必需短语",
        )


class ModelGradedEvaluator(BaseEvaluator):
    """LLM 评分评估器"""

    _PROMPT_TEMPLATE = """请评估以下 AI 输出是否符合要求。

输入:
{input_data}

期望输出描述:
{expected}

实际输出:
{output}

请评分（0-100），并简要说明理由。格式: 分数|理由"""

    def __init__(self, llm_backend: Any):
        self._llm = llm_backend

    @property
    def name(self) -> str:
        return "model_graded"

    async def evaluate(self, input_data: str, output: str, expected: Optional[str] = None) -> EvalResult:
        if not self._llm:
            return EvalResult(score=0.0, passed=False, evaluator=self.name, reason="LLM 不可用")

        try:
            prompt = self._PROMPT_TEMPLATE.format(
                input_data=input_data[:500],
                expected=expected or "无特殊要求",
                output=output[:1000],
            )
            response = await self._llm.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            content = response.get("content", "")

            # 解析分数
            import re
            score_match = re.search(r"(\d+)", content)
            if score_match:
                score = int(score_match.group()) / 100.0
            else:
                score = 0.5

            # 解析理由
            reason = content.split("|")[-1].strip() if "|" in content else content[:200]

            return EvalResult(
                score=round(score, 2),
                passed=score >= 0.7,
                evaluator=self.name,
                reason=reason,
            )
        except Exception as e:
            logger.warning("模型评分失败: %s", e)
            return EvalResult(score=0.0, passed=False, evaluator=self.name, reason=str(e))


class EvalRunner:
    """
    评估运行器

    Usage:
        runner = EvalRunner()
        runner.add_evaluator(ExactMatchEvaluator())
        result = await runner.run("输入", "输出", "期望输出")
    """

    def __init__(self):
        self._evaluators: List[BaseEvaluator] = []

    def add_evaluator(self, evaluator: BaseEvaluator) -> None:
        self._evaluators.append(evaluator)

    async def run(
        self,
        input_data: str,
        output: str,
        expected: Optional[str] = None,
    ) -> List[EvalResult]:
        """运行所有评估器"""
        results = []
        for evaluator in self._evaluators:
            try:
                result = await evaluator.evaluate(input_data, output, expected)
                results.append(result)
            except Exception as e:
                logger.error("评估器 %s 失败: %s", evaluator.name, e)
                results.append(EvalResult(
                    score=0.0, passed=False,
                    evaluator=evaluator.name, reason=str(e),
                ))
        return results

    def summary(self, results: List[EvalResult]) -> Dict[str, Any]:
        """生成评估摘要"""
        if not results:
            return {"total": 0, "passed": 0, "failed": 0, "avg_score": 0.0}

        passed = sum(1 for r in results if r.passed)
        scores = [r.score for r in results]

        return {
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "avg_score": round(sum(scores) / len(scores), 2),
            "details": [
                {"evaluator": r.evaluator, "score": r.score, "passed": r.passed, "reason": r.reason}
                for r in results
            ],
        }
