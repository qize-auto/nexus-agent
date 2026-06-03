"""
NexusAgent v4.0+ — Tool Mapping Strategy

错误恢复工具映射优化策略：
    1. 分析 ErrorRecovery 触发频率和成功率
    2. 识别高频失败但无替代方案的工具
    3. 建议新增/修改替代工具映射
    4. 输出 YAML 配置文件

进化维度: tool_map
配置文件: evolution/configs/tool_alternatives.yaml
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from nexusagent.evolution.config import EvolutionProposal, BenchmarkMetrics
from nexusagent.evolution.strategies.base import EvolutionStrategy

logger = logging.getLogger("nexus.evolution.strategy.tool_map")


class ToolMappingStrategy(EvolutionStrategy):
    """
    工具映射优化策略

    分析错误恢复数据，优化替代工具映射：
        - recovery_attempts 高但 recovery_success_rate 低 → 需要更好的替代方案
        - tool_success_rate 低 → 某些工具经常失败，需要备用方案
    """

    dimension = "tool_map"

    # 内置的替代工具映射建议库
    _SUGGESTED_ALTERNATIVES: Dict[str, List[Dict[str, Any]]] = {
        "browser.visit": [
            {"tool": "search.web", "condition": "domain_unreachable", "arg_transform": "extract_domain_keyword"},
        ],
        "file.read": [
            {"tool": "file.list", "condition": "file_not_found", "arg_transform": "dirname_fallback"},
            {"tool": "document.convert", "condition": "unsupported_format", "arg_transform": "passthrough"},
        ],
        "search.web": [
            {"tool": "browser.visit", "condition": "looks_like_url", "arg_transform": "query_to_url"},
        ],
        "rag.retrieve": [
            {"tool": "search.web", "condition": "no_results", "arg_transform": "passthrough"},
        ],
        "shell.exec": [
            {"tool": "file.list", "condition": "command_not_found", "arg_transform": "directory_only"},
        ],
        "database.query": [
            {"tool": "file.read", "condition": "connection_failed", "arg_transform": "fallback_to_sqlite"},
        ],
    }

    def analyze(
        self,
        metrics: BenchmarkMetrics,
        current_config: Dict[str, Any],
    ) -> List[EvolutionProposal]:
        """分析性能数据，生成工具映射优化建议"""
        proposals: List[EvolutionProposal] = []

        current_map = current_config.get("tool_alternatives", {})

        # 检查是否需要新增替代方案
        if metrics.recovery_attempts > 5 and metrics.recovery_success_rate < 0.5:
            # 恢复尝试多但成功率低 → 需要更好的映射
            missing = self._find_missing_alternatives(current_map)
            if missing:
                new_map = self._merge_alternatives(current_map, missing)
                proposal = self._create_proposal(
                    description=f"新增 {len(missing)} 个工具替代映射",
                    current={"tool_alternatives": current_map},
                    proposed={"tool_alternatives": new_map},
                    rationale=(
                        f"错误恢复尝试 {metrics.recovery_attempts} 次，"
                        f"成功率仅 {metrics.recovery_success_rate:.1%}。"
                        f"新增替代映射可提高恢复成功率。"
                    ),
                    confidence=min(0.6 + (1 - metrics.recovery_success_rate) * 0.3, 0.9),
                    expected_impact={
                        "recovery_success_rate": (0.7 - metrics.recovery_success_rate) * 0.5,
                        "success_rate": 0.05,
                    },
                )
                proposals.append(proposal)
                logger.info("生成工具映射优化建议: %s (missing=%d)", proposal.id, len(missing))

        # 检查是否需要调整参数修正规则
        if metrics.success_rate < 0.85:
            param_fixes = self._suggest_param_fixes(current_config.get("param_fixers", {}))
            if param_fixes:
                new_fixers = dict(current_config.get("param_fixers", {}))
                new_fixers.update(param_fixes)
                proposal = self._create_proposal(
                    description=f"新增 {len(param_fixes)} 个参数修正规则",
                    current={"param_fixers": current_config.get("param_fixers", {})},
                    proposed={"param_fixers": new_fixers},
                    rationale=f"成功率 {metrics.success_rate:.1%} 偏低，添加参数修正可减少失败。",
                    confidence=0.65,
                    expected_impact={
                        "success_rate": 0.03,
                        "recovery_success_rate": 0.05,
                    },
                )
                proposals.append(proposal)

        return proposals

    def apply(self, proposal: EvolutionProposal) -> bool:
        """应用工具映射配置变更"""
        proposed = proposal.proposed_config
        if not proposed:
            return False

        if self._config_dir:
            filepath = self._config_dir / "tool_alternatives.yaml"
            current = self._safe_yaml_read(filepath)
            current.update(proposed)
            return self._safe_yaml_write(filepath, current)
        return False

    def _find_missing_alternatives(self, current_map: Dict[str, Any]) -> Dict[str, Any]:
        """找出当前映射中缺失的替代方案"""
        missing: Dict[str, Any] = {}
        for tool_name, alternatives in self._SUGGESTED_ALTERNATIVES.items():
            existing = current_map.get(tool_name, [])
            existing_tools = {a.get("tool") for a in existing}
            for alt in alternatives:
                if alt["tool"] not in existing_tools:
                    missing.setdefault(tool_name, []).append(alt)
        return missing

    def _merge_alternatives(
        self,
        current: Dict[str, Any],
        additions: Dict[str, Any],
    ) -> Dict[str, Any]:
        """合并现有映射和新增映射"""
        merged = dict(current)
        for tool_name, alts in additions.items():
            merged.setdefault(tool_name, [])
            merged[tool_name] = list(merged[tool_name]) + list(alts)
        return merged

    def _suggest_param_fixes(self, current_fixers: Dict[str, Any]) -> Dict[str, Any]:
        """建议新增参数修正规则"""
        suggested: Dict[str, Any] = {
            "search.web": [
                {
                    "condition": "query_too_short",
                    "description": "查询词少于 3 个字符时扩展",
                },
            ],
            "file.read": [
                {
                    "condition": "path_traversal",
                    "description": "路径包含 .. 时修正为 basename",
                },
            ],
        }
        # 过滤已存在的
        result: Dict[str, Any] = {}
        for tool, rules in suggested.items():
            if tool not in current_fixers:
                result[tool] = rules
        return result
