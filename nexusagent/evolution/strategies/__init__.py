"""
NexusAgent v4.0+ — Evolution Strategies

进化策略集合：
    - PromptOptimizationStrategy: 系统提示词优化
    - ToolMappingStrategy: 错误恢复工具映射优化
    - BudgetTuningStrategy: ReAct 预算参数调优

Usage:
    from nexusagent.evolution.strategies import (
        PromptOptimizationStrategy,
        ToolMappingStrategy,
        BudgetTuningStrategy,
    )
"""

from nexusagent.evolution.strategies.base import EvolutionStrategy
from nexusagent.evolution.strategies.prompt_opt import PromptOptimizationStrategy
from nexusagent.evolution.strategies.tool_map import ToolMappingStrategy
from nexusagent.evolution.strategies.budget_tune import BudgetTuningStrategy

__all__ = [
    "EvolutionStrategy",
    "PromptOptimizationStrategy",
    "ToolMappingStrategy",
    "BudgetTuningStrategy",
]
