"""
NexusAgent v4.0+ — 基准测试报告生成器

Usage:
    from nexusagent.benchmark.report import BenchmarkReport
    report = BenchmarkReport(results)
    print(report.to_markdown())
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from nexusagent.benchmark.runner import ProviderBenchmark


@dataclass
class BenchmarkReport:
    """基准测试报告"""
    results: List[ProviderBenchmark] = field(default_factory=list)

    def to_json(self, indent: int = 2) -> str:
        """导出 JSON 格式"""
        return json.dumps(
            [r.to_dict() for r in self.results],
            indent=indent,
            ensure_ascii=False,
        )

    def to_csv(self) -> str:
        """导出 CSV 格式"""
        lines = [
            "provider,model,success_rate,avg_latency_ms,p99_latency_ms,avg_first_token_ms,avg_tokens_per_run,tokens_per_second,total_runs"
        ]
        for r in self.results:
            d = r.to_dict()
            lines.append(
                f"{d['provider']},{d['model']},{d['success_rate']}%,"
                f"{d['avg_latency_ms']},{d['p99_latency_ms']},"
                f"{d['avg_first_token_ms']},{d['avg_tokens_per_run']},"
                f"{d['tokens_per_second']},{d['total_runs']}"
            )
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """导出 Markdown 格式报告"""
        if not self.results:
            return "# NexusAgent 基准测试报告\n\n暂无数据。"

        lines = [
            "# NexusAgent 基准测试报告",
            "",
            f"测试 Provider 数: {len(self.results)}",
            f"总运行次数: {sum(len(r.runs) for r in self.results)}",
            "",
            "## 综合排名",
            "",
            "| 排名 | Provider | 模型 | 成功率 | 平均延迟 | P99延迟 | 首Token | 吞吐(tokens/s) | 综合评分 |",
            "|------|----------|------|--------|----------|---------|---------|----------------|----------|",
        ]

        # 计算综合评分（成功率*0.4 + 延迟倒数*0.3 + 吞吐*0.3）
        scored = []
        for r in self.results:
            d = r.to_dict()
            # 标准化: 成功率 0-100, 延迟 0-100（越低越好）, 吞吐 0-100
            latency_score = max(0, 100 - d["avg_latency_ms"] / 10)
            throughput_score = min(100, d["tokens_per_second"] / 2)
            composite = d["success_rate"] * 0.4 + latency_score * 0.3 + throughput_score * 0.3
            scored.append((composite, d, r))

        scored.sort(key=lambda x: x[0], reverse=True)

        for rank, (score, d, r) in enumerate(scored, 1):
            lines.append(
                f"| {rank} | {d['provider']} | {d['model']} | "
                f"{d['success_rate']}% | {d['avg_latency_ms']:.0f}ms | "
                f"{d['p99_latency_ms']:.0f}ms | {d['avg_first_token_ms']:.0f}ms | "
                f"{d['tokens_per_second']:.1f} | {score:.1f} |"
            )

        # 详细数据
        lines.extend([
            "",
            "## 详细数据",
            "",
            "| Provider | 模型 | 成功率 | 平均延迟 | P99延迟 | 首Token | 平均Tokens | 吞吐 | 运行次数 |",
            "|----------|------|--------|----------|---------|---------|------------|------|----------|",
        ])
        for r in self.results:
            d = r.to_dict()
            lines.append(
                f"| {d['provider']} | {d['model']} | {d['success_rate']}% | "
                f"{d['avg_latency_ms']:.0f}ms | {d['p99_latency_ms']:.0f}ms | "
                f"{d['avg_first_token_ms']:.0f}ms | {d['avg_tokens_per_run']:.0f} | "
                f"{d['tokens_per_second']:.1f} | {d['total_runs']} |"
            )

        # 推荐配置
        lines.extend([
            "",
            "## 推荐配置",
            "",
        ])
        if scored:
            best = scored[0][2]
            lines.append(
                f"- **最佳综合性能**: `{best.provider}/{best.model}` "
                f"(成功率 {best.success_rate*100:.0f}%, 延迟 {best.avg_latency_ms:.0f}ms)"
            )
            # 最低延迟
            lowest_latency = min(self.results, key=lambda r: r.avg_latency_ms if r.avg_latency_ms > 0 else float('inf'))
            lines.append(
                f"- **最低延迟**: `{lowest_latency.provider}/{lowest_latency.model}` "
                f"({lowest_latency.avg_latency_ms:.0f}ms)"
            )
            # 最高吞吐
            highest_tps = max(self.results, key=lambda r: r.tokens_per_second)
            lines.append(
                f"- **最高吞吐**: `{highest_tps.provider}/{highest_tps.model}` "
                f"({highest_tps.tokens_per_second:.1f} tokens/s)"
            )

        lines.append("")
        return "\n".join(lines)

    def recommend(self) -> Dict[str, str]:
        """根据测试结果推荐最佳配置"""
        if not self.results:
            return {}

        best_overall = max(self.results, key=lambda r: r.success_rate)
        lowest_latency = min(
            (r for r in self.results if r.avg_latency_ms > 0),
            key=lambda r: r.avg_latency_ms,
            default=None,
        )
        highest_tps = max(self.results, key=lambda r: r.tokens_per_second)

        return {
            "best_overall": f"{best_overall.provider}/{best_overall.model}",
            "lowest_latency": f"{lowest_latency.provider}/{lowest_latency.model}" if lowest_latency else "N/A",
            "highest_throughput": f"{highest_tps.provider}/{highest_tps.model}",
        }
