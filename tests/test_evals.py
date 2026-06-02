"""
Phase 3 — 评估框架 + 回归测试套件测试
"""

import asyncio
import json
from pathlib import Path

import pytest

from nexusagent.evals.framework import (
    EvalRunner,
    EvalResult,
    ExactMatchEvaluator,
    ContainsEvaluator,
    ModelGradedEvaluator,
)
from nexusagent.evals.regression import RegressionSuite, RegressionTestCase


# ── Helpers ───────────────────────────────────────────────────────

class _FakeLLM:
    def __init__(self, score=85):
        self._score = score

    async def complete(self, messages, temperature=0.7):
        return {"content": f"{self._score}|理由测试"}


# ── ExactMatchEvaluator ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_exact_match_pass():
    ev = ExactMatchEvaluator()
    r = await ev.evaluate("hello", "hello", "hello")
    assert r.score == 1.0
    assert r.passed is True
    assert r.evaluator == "exact_match"


@pytest.mark.asyncio
async def test_exact_match_fail():
    ev = ExactMatchEvaluator()
    r = await ev.evaluate("hello", "world", "hello")
    assert r.score == 0.0
    assert r.passed is False


@pytest.mark.asyncio
async def test_exact_match_no_expected():
    ev = ExactMatchEvaluator()
    r = await ev.evaluate("hello", "hello", None)
    assert r.score == 0.0
    assert r.passed is False
    assert "无期望输出" in r.reason


@pytest.mark.asyncio
async def test_exact_match_strip():
    ev = ExactMatchEvaluator()
    r = await ev.evaluate("x", "  hello  ", "hello")
    assert r.score == 1.0
    assert r.passed is True


# ── ContainsEvaluator ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_contains_all_found():
    ev = ContainsEvaluator(["hello", "world"])
    r = await ev.evaluate("x", "hello world", None)
    assert r.score == 1.0
    assert r.passed is True


@pytest.mark.asyncio
async def test_contains_partial():
    ev = ContainsEvaluator(["hello", "world", "foo"])
    r = await ev.evaluate("x", "hello world", None)
    assert r.score == pytest.approx(2 / 3, 0.01)
    assert r.passed is False


@pytest.mark.asyncio
async def test_contains_case_insensitive():
    ev = ContainsEvaluator(["Hello"])
    r = await ev.evaluate("x", "HELLO there", None)
    assert r.score == 1.0
    assert r.passed is True


@pytest.mark.asyncio
async def test_contains_empty():
    ev = ContainsEvaluator([])
    r = await ev.evaluate("x", "anything", None)
    assert r.score == 1.0
    assert r.passed is True


@pytest.mark.asyncio
async def test_contains_none():
    ev = ContainsEvaluator()
    r = await ev.evaluate("x", "anything", None)
    assert r.score == 1.0


# ── ModelGradedEvaluator ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_model_graded_success():
    ev = ModelGradedEvaluator(_FakeLLM(85))
    r = await ev.evaluate("input", "output", "expected")
    assert r.score == 0.85
    assert r.passed is True
    assert "理由测试" in r.reason


@pytest.mark.asyncio
async def test_model_graded_low_score():
    ev = ModelGradedEvaluator(_FakeLLM(60))
    r = await ev.evaluate("input", "output", "expected")
    assert r.score == 0.60
    assert r.passed is False


@pytest.mark.asyncio
async def test_model_graded_no_llm():
    ev = ModelGradedEvaluator(None)
    r = await ev.evaluate("input", "output", "expected")
    assert r.score == 0.0
    assert r.passed is False
    assert "LLM 不可用" in r.reason


@pytest.mark.asyncio
async def test_model_graded_exception():
    class _BadLLM:
        async def complete(self, messages, temperature=0.7):
            raise RuntimeError("boom")

    ev = ModelGradedEvaluator(_BadLLM())
    r = await ev.evaluate("input", "output", "expected")
    assert r.score == 0.0
    assert r.passed is False
    assert "boom" in r.reason


# ── EvalRunner ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_runner_single_evaluator():
    runner = EvalRunner()
    runner.add_evaluator(ExactMatchEvaluator())
    results = await runner.run("in", "out", "out")
    assert len(results) == 1
    assert results[0].passed is True


@pytest.mark.asyncio
async def test_runner_multiple_evaluators():
    runner = EvalRunner()
    runner.add_evaluator(ExactMatchEvaluator())
    runner.add_evaluator(ContainsEvaluator(["ok"]))
    results = await runner.run("in", "ok", "ok")
    assert len(results) == 2
    assert all(r.passed for r in results)


@pytest.mark.asyncio
async def test_runner_exception_in_evaluator():
    class _BadEval(ExactMatchEvaluator):
        @property
        def name(self):
            return "bad"

        async def evaluate(self, input_data, output, expected=None):
            raise RuntimeError("eval error")

    runner = EvalRunner()
    runner.add_evaluator(_BadEval())
    results = await runner.run("in", "out", "out")
    assert len(results) == 1
    assert results[0].passed is False
    assert "eval error" in results[0].reason


@pytest.mark.asyncio
async def test_runner_summary():
    runner = EvalRunner()
    runner.add_evaluator(ExactMatchEvaluator())
    results = await runner.run("in", "out", "out")
    summary = runner.summary(results)
    assert summary["total"] == 1
    assert summary["passed"] == 1
    assert summary["failed"] == 0
    assert summary["avg_score"] == 1.0


@pytest.mark.asyncio
async def test_runner_summary_empty():
    runner = EvalRunner()
    summary = runner.summary([])
    assert summary["total"] == 0
    assert summary["avg_score"] == 0.0


# ── RegressionSuite ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_regression_suite_from_json(tmp_path):
    data = [
        {"id": "t1", "input": "hello", "expected": "hi", "tags": ["greeting"]},
    ]
    p = tmp_path / "regression.json"
    p.write_text(json.dumps(data))
    suite = RegressionSuite.from_json(str(p))
    assert len(suite._test_cases) == 1
    assert suite._test_cases[0].id == "t1"


@pytest.mark.asyncio
async def test_regression_suite_run_pass():
    cases = [RegressionTestCase(id="t1", input_data="hello", expected_output="hello")]
    suite = RegressionSuite(cases)
    suite._eval_runner.add_evaluator(ExactMatchEvaluator())

    async def agent_fn(inp):
        return inp

    results = await suite.run(agent_fn)
    assert len(results) == 1
    assert results[0].overall_passed is True


@pytest.mark.asyncio
async def test_regression_suite_run_fail():
    cases = [RegressionTestCase(id="t1", input_data="hello", expected_output="world")]
    suite = RegressionSuite(cases)
    suite._eval_runner.add_evaluator(ExactMatchEvaluator())

    async def agent_fn(inp):
        return "hello"

    results = await suite.run(agent_fn)
    assert results[0].overall_passed is False


@pytest.mark.asyncio
async def test_regression_suite_run_exception():
    cases = [RegressionTestCase(id="t1", input_data="x", expected_output="y")]
    suite = RegressionSuite(cases)

    async def agent_fn(inp):
        raise RuntimeError("agent boom")

    results = await suite.run(agent_fn)
    assert results[0].overall_passed is False
    assert "agent boom" in results[0].actual


@pytest.mark.asyncio
async def test_regression_suite_acceptable():
    cases = [
        RegressionTestCase(id="t1", input_data="a", expected_output="a"),
        RegressionTestCase(id="t2", input_data="b", expected_output="b"),
    ]
    suite = RegressionSuite(cases, threshold=0.5)

    async def agent_fn(inp):
        return inp if inp == "a" else "wrong"

    results = await suite.run(agent_fn)
    assert suite.is_acceptable(results) is True  # 50% >= threshold 0.5


@pytest.mark.asyncio
async def test_regression_suite_not_acceptable():
    cases = [
        RegressionTestCase(id="t1", input_data="a", expected_output="a"),
        RegressionTestCase(id="t2", input_data="b", expected_output="b"),
    ]
    suite = RegressionSuite(cases, threshold=0.8)

    async def agent_fn(inp):
        return "wrong"

    results = await suite.run(agent_fn)
    assert suite.is_acceptable(results) is False


@pytest.mark.asyncio
async def test_regression_suite_report():
    cases = [RegressionTestCase(id="t1", input_data="a", expected_output="b")]
    suite = RegressionSuite(cases)

    async def agent_fn(inp):
        return "a"

    results = await suite.run(agent_fn)
    report = suite.report(results)
    assert report["total_tests"] == 1
    assert report["passed"] == 0
    assert report["failed"] == 1
    assert report["acceptable"] is False
    assert len(report["failures"]) == 1
