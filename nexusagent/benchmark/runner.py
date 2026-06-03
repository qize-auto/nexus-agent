"""
NexusAgent v4.0+ — 性能基准测试引擎

量化各 LLM Provider 的延迟、token 消耗、成功率。

Usage:
    runner = BenchmarkRunner()
    result = await runner.run_provider("deepseek", "deepseek-chat", runs=5)
    print(result.to_markdown())
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class BenchmarkCase:
    """单个测试用例"""
    name: str
    messages: List[Dict[str, str]]
    expected_keywords: List[str] = field(default_factory=list)


@dataclass
class BenchmarkRun:
    """单次运行结果"""
    success: bool
    latency_ms: float
    first_token_ms: float
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    error: str = ""
    response_preview: str = ""


@dataclass
class ProviderBenchmark:
    """单个 Provider 的基准测试结果"""
    provider: str
    model: str
    runs: List[BenchmarkRun] = field(default_factory=list)
    test_cases: List[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if not self.runs:
            return 0.0
        return sum(1 for r in self.runs if r.success) / len(self.runs)

    @property
    def avg_latency_ms(self) -> float:
        ok = [r.latency_ms for r in self.runs if r.success]
        return sum(ok) / len(ok) if ok else 0.0

    @property
    def p99_latency_ms(self) -> float:
        ok = sorted(r.latency_ms for r in self.runs if r.success)
        if not ok:
            return 0.0
        idx = int(len(ok) * 0.99)
        return ok[min(idx, len(ok) - 1)]

    @property
    def avg_first_token_ms(self) -> float:
        ok = [r.first_token_ms for r in self.runs if r.success and r.first_token_ms > 0]
        return sum(ok) / len(ok) if ok else 0.0

    @property
    def avg_tokens_per_run(self) -> float:
        ok = [r.total_tokens for r in self.runs if r.success]
        return sum(ok) / len(ok) if ok else 0.0

    @property
    def tokens_per_second(self) -> float:
        ok = [r for r in self.runs if r.success and r.latency_ms > 0]
        if not ok:
            return 0.0
        total_tokens = sum(r.completion_tokens for r in ok)
        total_secs = sum(r.latency_ms for r in ok) / 1000
        return total_tokens / total_secs if total_secs > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "success_rate": round(self.success_rate * 100, 1),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "p99_latency_ms": round(self.p99_latency_ms, 1),
            "avg_first_token_ms": round(self.avg_first_token_ms, 1),
            "avg_tokens_per_run": round(self.avg_tokens_per_run, 1),
            "tokens_per_second": round(self.tokens_per_second, 1),
            "total_runs": len(self.runs),
            "successful_runs": sum(1 for r in self.runs if r.success),
        }


# 标准测试用例
DEFAULT_TEST_CASES: List[BenchmarkCase] = [
    BenchmarkCase(
        name="简单问答",
        messages=[
            {"role": "system", "content": "你是一个 helpful assistant。"},
            {"role": "user", "content": "1+1等于多少？请只用中文回答。"},
        ],
        expected_keywords=["2", "两"],
    ),
    BenchmarkCase(
        name="中文长文本生成",
        messages=[
            {"role": "system", "content": "你是一个 helpful assistant。"},
            {"role": "user", "content": "请用中文写一段200字左右的介绍，主题是'Python asyncio 异步编程'。"},
        ],
        expected_keywords=["asyncio", "异步", "Python"],
    ),
    BenchmarkCase(
        name="代码生成",
        messages=[
            {"role": "system", "content": "你是一个 helpful assistant。"},
            {"role": "user", "content": "写一个 Python 函数，接受一个列表，返回列表中的最大数和最小数。只输出代码，不要解释。"},
        ],
        expected_keywords=["def", "return", "max", "min"],
    ),
]


class BenchmarkRunner:
    """
    基准测试运行器

    Usage:
        runner = BenchmarkRunner()
        result = await runner.run_provider("deepseek", "deepseek-chat")
    """

    def __init__(self, test_cases: Optional[List[BenchmarkCase]] = None):
        self._test_cases = test_cases or DEFAULT_TEST_CASES

    async def run_provider(
        self,
        provider: str,
        model: str,
        runs: int = 3,
        api_key: Optional[str] = None,
        dry_run: bool = False,
    ) -> ProviderBenchmark:
        """
        测试单个 provider

        Args:
            provider: provider 名称
            model: 模型名称
            runs: 每个测试用例运行次数
            api_key: 可选 API key（默认从环境变量读取）
            dry_run: 如果为 True，不调用真实 API，使用 mock 数据
        """
        result = ProviderBenchmark(provider=provider, model=model)

        if dry_run:
            for _ in range(runs * len(self._test_cases)):
                result.runs.append(BenchmarkRun(
                    success=True,
                    latency_ms=500.0,
                    first_token_ms=120.0,
                    total_tokens=300,
                    prompt_tokens=50,
                    completion_tokens=250,
                    response_preview="[dry-run mock response]",
                ))
            result.test_cases = [tc.name for tc in self._test_cases]
            return result

        from nexusagent.models.unified_backend import UnifiedLLMBackend
        backend = UnifiedLLMBackend(provider=provider, model=model, api_key=api_key)

        for tc in self._test_cases:
            result.test_cases.append(tc.name)
            for _ in range(runs):
                run = await self._run_single(backend, tc)
                result.runs.append(run)
                # 两次运行之间间隔 1 秒，避免触发 rate limit
                await asyncio.sleep(1.0)

        return result

    async def _run_single(self, backend, test_case: BenchmarkCase) -> BenchmarkRun:
        """执行单次测试"""
        start = time.perf_counter()
        first_token_time: Optional[float] = None
        response_text = ""

        try:
            # 尝试流式获取 first_token 延迟
            if hasattr(backend, "complete_stream"):
                async for chunk in backend.complete_stream(test_case.messages):
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    response_text += chunk
            else:
                response = await backend.complete(test_case.messages)
                response_text = response.get("content", "")
                first_token_time = time.perf_counter()

            end = time.perf_counter()
            latency_ms = (end - start) * 1000
            ft_ms = (first_token_time - start) * 1000 if first_token_time else latency_ms

            # 估算 token 数（实际 provider 可能不返回 usage）
            total_tokens = len(response_text) // 2  # 粗略估算

            return BenchmarkRun(
                success=True,
                latency_ms=latency_ms,
                first_token_ms=ft_ms,
                total_tokens=total_tokens,
                prompt_tokens=sum(len(m["content"]) for m in test_case.messages) // 2,
                completion_tokens=total_tokens,
                response_preview=response_text[:100],
            )
        except Exception as e:
            end = time.perf_counter()
            return BenchmarkRun(
                success=False,
                latency_ms=(end - start) * 1000,
                first_token_ms=0.0,
                total_tokens=0,
                prompt_tokens=0,
                completion_tokens=0,
                error=str(e),
            )

    async def run_all(
        self,
        providers: Optional[List[tuple]] = None,
        runs: int = 3,
        dry_run: bool = False,
    ) -> List[ProviderBenchmark]:
        """
        批量测试多个 provider

        Args:
            providers: [(provider_name, model_name), ...]
            runs: 每个用例运行次数
            dry_run: 是否使用 mock 数据
        """
        if providers is None:
            providers = [
                ("deepseek", "deepseek-chat"),
                ("moonshot", "moonshot-v1-8k"),
                ("openai", "gpt-4o-mini"),
                ("ollama", "llama3.2"),
            ]

        results: List[ProviderBenchmark] = []
        for provider, model in providers:
            try:
                bench = await self.run_provider(provider, model, runs=runs, dry_run=dry_run)
                results.append(bench)
            except Exception as e:
                print(f"Provider {provider}/{model} 测试失败: {e}")
        return results
