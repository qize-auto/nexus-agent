"""
Tests for nexusagent.evolution.strategies — Evolution Strategies
"""

import pytest

from nexusagent.evolution.config import BenchmarkMetrics
from nexusagent.evolution.strategies.prompt_opt import PromptOptimizationStrategy
from nexusagent.evolution.strategies.tool_map import ToolMappingStrategy
from nexusagent.evolution.strategies.budget_tune import BudgetTuningStrategy


class TestPromptOptimizationStrategy:
    @pytest.fixture
    def strategy(self, tmp_path):
        return PromptOptimizationStrategy(config_dir=str(tmp_path))

    def test_analyze_no_trigger(self, strategy):
        """指标良好时不应生成建议"""
        metrics = BenchmarkMetrics(
            success_rate=0.95,
            completeness_score=0.9,
            anti_compression_score=0.9,
            avg_latency_ms=500,
        )
        proposals = strategy.analyze(metrics, {})
        assert len(proposals) == 0

    def test_analyze_low_success(self, strategy):
        """成功率低时应生成建议"""
        metrics = BenchmarkMetrics(
            success_rate=0.7,
            completeness_score=0.9,
            anti_compression_score=0.9,
        )
        proposals = strategy.analyze(metrics, {})
        assert len(proposals) == 1
        assert proposals[0].dimension == "prompt"
        assert proposals[0].confidence > 0.5
        assert "low_success" in proposals[0].description

    def test_analyze_low_completeness(self, strategy):
        """完整性低时应生成建议"""
        metrics = BenchmarkMetrics(
            success_rate=0.9,
            completeness_score=0.6,
            anti_compression_score=0.9,
        )
        proposals = strategy.analyze(metrics, {})
        assert len(proposals) == 1
        assert "completeness" in proposals[0].description.lower() or "完整性" in proposals[0].description

    def test_analyze_multiple_triggers(self, strategy):
        """多个规则触发时只生成一个建议"""
        metrics = BenchmarkMetrics(
            success_rate=0.7,
            completeness_score=0.6,
            anti_compression_score=0.6,
            avg_latency_ms=4000,
        )
        proposals = strategy.analyze(metrics, {})
        assert len(proposals) == 1
        # 置信度应更高（因为触发了更多规则）
        assert proposals[0].confidence > 0.6

    def test_apply(self, strategy, tmp_path):
        """应用配置变更"""
        from nexusagent.evolution.config import EvolutionProposal
        proposal = EvolutionProposal(
            id="test",
            dimension="prompt",
            description="测试",
            current_config={},
            proposed_config={"system_prompt": "new prompt"},
            rationale="测试",
        )
        result = strategy.apply(proposal)
        assert result is True
        # 检查文件是否写入
        config_file = tmp_path / "prompt.yaml"
        assert config_file.exists()

    def test_load_default_prompt(self, strategy):
        """加载默认提示词"""
        prompt = strategy._load_default_prompt()
        assert "NexusAgent" in prompt


class TestToolMappingStrategy:
    @pytest.fixture
    def strategy(self, tmp_path):
        return ToolMappingStrategy(config_dir=str(tmp_path))

    def test_analyze_no_issue(self, strategy):
        """恢复数据良好时不应生成建议"""
        metrics = BenchmarkMetrics(
            recovery_attempts=2,
            recovery_success_rate=0.9,
            success_rate=0.95,
        )
        proposals = strategy.analyze(metrics, {})
        assert len(proposals) == 0

    def test_analyze_low_recovery_rate(self, strategy):
        """恢复成功率低时应生成建议"""
        metrics = BenchmarkMetrics(
            recovery_attempts=10,
            recovery_success_rate=0.3,
        )
        proposals = strategy.analyze(metrics, {"tool_alternatives": {}})
        assert len(proposals) >= 1
        assert proposals[0].dimension == "tool_map"

    def test_find_missing_alternatives(self, strategy):
        current = {"browser.visit": [{"tool": "search.web"}]}
        missing = strategy._find_missing_alternatives(current)
        # browser.visit 已有 search.web，不应出现在 missing 中
        assert "browser.visit" not in missing or all(
            m["tool"] != "search.web" for m in missing.get("browser.visit", [])
        )

    def test_apply(self, strategy, tmp_path):
        from nexusagent.evolution.config import EvolutionProposal
        proposal = EvolutionProposal(
            id="test",
            dimension="tool_map",
            description="测试",
            current_config={},
            proposed_config={"tool_alternatives": {"browser.visit": [{"tool": "search.web"}]}},
            rationale="测试",
        )
        result = strategy.apply(proposal)
        assert result is True


class TestBudgetTuningStrategy:
    @pytest.fixture
    def strategy(self, tmp_path):
        return BudgetTuningStrategy(config_dir=str(tmp_path))

    def test_analyze_no_change(self, strategy):
        """预算合理时不应生成建议"""
        metrics = BenchmarkMetrics(
            avg_tokens_per_request=4000,
            success_rate=0.85,  # 不触发条件2（需要 > 0.9）
            avg_latency_ms=1500,  # 不触发条件2（需要 < 1000）
            recovery_attempts=2,  # 不触发条件3（需要 > 10）
            avg_cost_usd=0.001,  # 不触发条件4（需要 > 0.005）
        )
        current = {
            "react_budget": {
                "max_iterations": {"default": 15},  # 不触发条件2（需要 > 15）
                "max_tokens": {"default": 8000},
                "max_time_seconds": {"default": 120.0},
            }
        }
        proposals = strategy.analyze(metrics, current)
        assert len(proposals) == 0

    def test_analyze_increase_tokens(self, strategy):
        """Token 使用接近上限时应建议增加"""
        metrics = BenchmarkMetrics(
            avg_tokens_per_request=7500,
            success_rate=0.95,
        )
        current = {
            "react_budget": {
                "max_tokens": {"default": 8000},
            }
        }
        proposals = strategy.analyze(metrics, current)
        assert len(proposals) == 1
        assert "max_tokens" in proposals[0].description

    def test_analyze_reduce_iterations(self, strategy):
        """延迟低且成功率高时应建议减少迭代次数"""
        metrics = BenchmarkMetrics(
            avg_latency_ms=500,
            success_rate=0.98,
            recovery_attempts=2,
        )
        current = {
            "react_budget": {
                "max_iterations": {"default": 25},
                "max_tokens": {"default": 8000},
                "max_time_seconds": {"default": 120.0},
            }
        }
        proposals = strategy.analyze(metrics, current)
        assert len(proposals) == 1
        # 应减少 max_iterations
        proposed = proposals[0].proposed_config["react_budget"]
        assert proposed["max_iterations"]["default"] < current["react_budget"]["max_iterations"]["default"]

    def test_apply(self, strategy, tmp_path):
        from nexusagent.evolution.config import EvolutionProposal
        proposal = EvolutionProposal(
            id="test",
            dimension="budget",
            description="测试",
            current_config={},
            proposed_config={"react_budget": {"max_iterations": {"default": 20}}},
            rationale="测试",
        )
        result = strategy.apply(proposal)
        assert result is True
