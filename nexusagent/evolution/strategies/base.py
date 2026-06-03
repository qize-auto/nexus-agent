"""
NexusAgent v4.0+ — Evolution Strategy Base Class

所有进化策略的抽象基类。

子类需要实现:
    1. analyze() — 分析性能数据，生成进化建议
    2. apply() — 应用配置变更到文件系统
    3. load_config() / save_config() — 读写配置文件
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

from nexusagent.evolution.config import EvolutionProposal, BenchmarkMetrics
from nexusagent.utils.ulid import generate_ulid

logger = logging.getLogger("nexus.evolution.strategy")


class EvolutionStrategy(ABC):
    """
    进化策略基类

    Attributes:
        dimension: 策略对应的配置维度 (prompt | tool_map | budget | routing)
        config_dir: 配置文件目录
    """

    dimension: str = ""

    def __init__(self, config_dir: Optional[str] = None):
        self._config_dir = Path(config_dir) if config_dir else None

    @abstractmethod
    def analyze(
        self,
        metrics: BenchmarkMetrics,
        current_config: Dict[str, Any],
    ) -> List[EvolutionProposal]:
        """
        分析性能数据，生成进化建议

        Args:
            metrics: 当前性能指标
            current_config: 当前配置

        Returns:
            进化建议列表（空列表表示无建议）
        """

    @abstractmethod
    def apply(self, proposal: EvolutionProposal) -> bool:
        """
        应用配置变更

        Args:
            proposal: 已批准的进化建议

        Returns:
            是否成功应用
        """

    def load_config(self) -> Dict[str, Any]:
        """从文件加载当前配置"""
        if self._config_dir is None:
            return {}
        filepath = self._config_dir / f"{self.dimension}.yaml"
        if not filepath.exists():
            return {}
        try:
            import yaml
            with open(filepath, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning("加载配置失败 %s: %s", filepath, e)
            return {}

    def save_config(self, config: Dict[str, Any]) -> bool:
        """保存配置到文件"""
        if self._config_dir is None:
            return False
        filepath = self._config_dir / f"{self.dimension}.yaml"
        try:
            import yaml
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                yaml.dump(config, f, allow_unicode=True, sort_keys=False)
            return True
        except Exception as e:
            logger.warning("保存配置失败 %s: %s", filepath, e)
            return False

    def _create_proposal(
        self,
        description: str,
        current: Dict[str, Any],
        proposed: Dict[str, Any],
        rationale: str,
        confidence: float,
        expected_impact: Optional[Dict[str, float]] = None,
    ) -> EvolutionProposal:
        """辅助方法：创建标准化的 EvolutionProposal"""
        import time
        return EvolutionProposal(
            id=generate_ulid(),
            dimension=self.dimension,
            description=description,
            current_config=dict(current),
            proposed_config=dict(proposed),
            rationale=rationale,
            confidence=confidence,
            expected_impact=expected_impact or {},
            created_at=time.time(),
        )

    def _safe_yaml_read(self, filepath: Path) -> Dict[str, Any]:
        """安全读取 YAML 文件"""
        if not filepath.exists():
            return {}
        try:
            import yaml
            with open(filepath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.debug("YAML 读取失败 %s: %s", filepath, e)
            return {}

    def _safe_yaml_write(self, filepath: Path, data: Dict[str, Any]) -> bool:
        """安全写入 YAML 文件"""
        try:
            import yaml
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, sort_keys=False)
            return True
        except Exception as e:
            logger.warning("YAML 写入失败 %s: %s", filepath, e)
            return False
