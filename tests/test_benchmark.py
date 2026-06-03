"""
Tests for nexusagent.benchmark — Benchmark runner and report
"""

import pytest

from nexusagent.benchmark.runner import (
    BenchmarkRunner,
    BenchmarkCase,
    ProviderBenchmark,
    BenchmarkRun,
)
from nexusagent.benchmark.report import BenchmarkReport


class TestBenchmarkRun:
    def test_to_dict(self):
        bench = ProviderBenchmark(provider="deepseek", model="deepseek-chat")
        bench.runs = [
            BenchmarkRun(success=True, latency_ms=100, first_token_ms=50, total_tokens=300, prompt_tokens=50, completion_tokens=250),
            BenchmarkRun(success=True, latency_ms=200, first_token_ms=80, total_tokens=400, prompt_tokens=50, completion_tokens=350),
            BenchmarkRun(success=False, latency_ms=50, first_token_ms=0, total_tokens=0, prompt_tokens=0, completion_tokens=0, error="timeout"),
        ]
        d = bench.to_dict()
        assert d["provider"] == "deepseek"
        assert d["model"] == "deepseek-chat"
        assert d["success_rate"] == pytest.approx(66.7, 0.1)
        assert d["avg_latency_ms"] == 150.0
        assert d["total_runs"] == 3
        assert d["successful_runs"] == 2

    def test_empty_runs(self):
        bench = ProviderBenchmark(provider="test", model="test-model")
        d = bench.to_dict()
        assert d["success_rate"] == 0.0
        assert d["avg_latency_ms"] == 0.0


class TestBenchmarkRunner:
    @pytest.mark.asyncio
    async def test_dry_run(self):
        runner = BenchmarkRunner()
        result = await runner.run_provider("deepseek", "deepseek-chat", runs=2, dry_run=True)
        assert result.provider == "deepseek"
        assert result.model == "deepseek-chat"
        assert len(result.runs) == 6  # 3 test cases * 2 runs
        assert all(r.success for r in result.runs)

    @pytest.mark.asyncio
    async def test_run_all_dry_run(self):
        runner = BenchmarkRunner()
        results = await runner.run_all(
            providers=[("deepseek", "deepseek-chat")],
            runs=1,
            dry_run=True,
        )
        assert len(results) == 1
        assert results[0].provider == "deepseek"


class TestBenchmarkReport:
    def test_to_markdown(self):
        bench1 = ProviderBenchmark(provider="a", model="m1")
        bench1.runs = [BenchmarkRun(success=True, latency_ms=100, first_token_ms=50, total_tokens=300, prompt_tokens=50, completion_tokens=250) for _ in range(5)]
        bench2 = ProviderBenchmark(provider="b", model="m2")
        bench2.runs = [BenchmarkRun(success=True, latency_ms=200, first_token_ms=100, total_tokens=200, prompt_tokens=50, completion_tokens=150) for _ in range(5)]

        report = BenchmarkReport([bench1, bench2])
        md = report.to_markdown()
        assert "# NexusAgent 基准测试报告" in md
        assert "a" in md
        assert "b" in md
        assert "综合排名" in md

    def test_to_json(self):
        bench = ProviderBenchmark(provider="test", model="model")
        bench.runs = [BenchmarkRun(success=True, latency_ms=100, first_token_ms=50, total_tokens=300, prompt_tokens=50, completion_tokens=250)]
        report = BenchmarkReport([bench])
        json_str = report.to_json()
        assert '"provider": "test"' in json_str

    def test_to_csv(self):
        bench = ProviderBenchmark(provider="test", model="model")
        bench.runs = [BenchmarkRun(success=True, latency_ms=100, first_token_ms=50, total_tokens=300, prompt_tokens=50, completion_tokens=250)]
        report = BenchmarkReport([bench])
        csv = report.to_csv()
        assert "provider,model" in csv
        assert "test" in csv

    def test_empty_report(self):
        report = BenchmarkReport([])
        assert "暂无数据" in report.to_markdown()

    def test_recommend(self):
        bench1 = ProviderBenchmark(provider="fast", model="m1")
        bench1.runs = [BenchmarkRun(success=True, latency_ms=50, first_token_ms=20, total_tokens=300, prompt_tokens=50, completion_tokens=250)] * 3
        bench2 = ProviderBenchmark(provider="slow", model="m2")
        bench2.runs = [BenchmarkRun(success=True, latency_ms=500, first_token_ms=200, total_tokens=300, prompt_tokens=50, completion_tokens=250)] * 3

        report = BenchmarkReport([bench1, bench2])
        rec = report.recommend()
        assert "fast/m1" in rec["best_overall"]
        assert "fast/m1" in rec["lowest_latency"]
