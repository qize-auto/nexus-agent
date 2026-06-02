"""
NexusAgent Diagnostic Configuration — 诊断系统配置管理

Usage:
    from nexusagent.diagnostics.config import load_config, save_config
    cfg = load_config()
    cfg.scheduler_interval_seconds = 60
    save_config(cfg)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("nexus.diagnostics.config")

DEFAULT_CONFIG_PATH = Path.home() / ".nexusagent" / "diagnostics_config.json"


@dataclass
class DiagnosticConfig:
    """诊断系统配置"""

    scheduler_interval_seconds: float = 300.0
    alert_dedup_seconds: float = 600.0
    latency_warning_ms: float = 5000.0
    latency_critical_ms: float = 10000.0
    error_rate_warning: float = 5.0
    error_rate_critical: float = 10.0
    history_keep_days: int = 30
    alerts_keep_days: int = 90

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def with_overrides(self, overrides: Dict[str, Any]) -> "DiagnosticConfig":
        """应用部分覆盖，返回新实例"""
        data = self.to_dict()
        for key, value in overrides.items():
            if key in data and value is not None:
                data[key] = type(data[key])(value) if type(data[key]) is not type(value) else value
        return DiagnosticConfig(**data)


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> DiagnosticConfig:
    """加载配置，文件不存在则返回默认值"""
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            return DiagnosticConfig().with_overrides(raw)
        except Exception as e:
            logger.warning("配置加载失败，使用默认值: %s", e)
    return DiagnosticConfig()


def save_config(config: DiagnosticConfig, path: Path = DEFAULT_CONFIG_PATH) -> None:
    """保存配置到文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning("配置保存失败: %s", e)
