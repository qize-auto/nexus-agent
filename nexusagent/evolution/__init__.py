"""
NexusAgent v4.0+ — Self-Evolution System 自我进化系统

配置级进化框架：绝不修改 .py 文件，只进化 YAML/JSON 配置。

设计原则:
    1. HITL 人类在环: 所有进化操作需人类确认
    2. A/B 测试: 新旧配置并行对比，数据驱动决策
    3. 可回滚: 保留配置历史版本（最近 50 个）
    4. 可进化维度: 系统提示词、错误恢复策略、工具优先级、ReAct 预算、模型路由规则

Usage:
    from nexusagent.evolution.engine import EvolutionEngine
    from nexusagent.benchmark.runner import BenchmarkRunner

    engine = EvolutionEngine(
        config_dir=Path.home() / ".nexusagent" / "evolution",
        benchmark_runner=BenchmarkRunner(),
    )
    engine.register_strategy(PromptOptimizationStrategy())
    proposals = await engine.run_cycle()
"""

from nexusagent.evolution.config import EvolutionProposal, ABTestResult, ProposalStatus
from nexusagent.evolution.history import ConfigHistory
from nexusagent.evolution.hitl import HITLApprover
from nexusagent.evolution.ab_test import ABTestFramework
from nexusagent.evolution.strategies.base import EvolutionStrategy
from nexusagent.evolution.engine import EvolutionEngine

__all__ = [
    "EvolutionProposal",
    "ABTestResult",
    "ProposalStatus",
    "ConfigHistory",
    "HITLApprover",
    "ABTestFramework",
    "EvolutionStrategy",
    "EvolutionEngine",
]
