"""
NexusAgent v3.3 — 统一配置管理
来源: 设计稿第4章编排层(4.10零配置设计) + 第10章模型策略
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv

# 项目根目录（惰性初始化，不在导入时创建）
PROJECT_ROOT = Path(os.getenv("NEXUS_HOME", Path.home() / ".nexusagent"))


def _ensure_dirs() -> None:
    """确保必要目录存在 — 仅在需要时调用，避免模块导入副作用"""
    PROJECT_ROOT.mkdir(parents=True, exist_ok=True)


def load_project_env(path: Path) -> None:
    """显式加载项目根目录的 .env 文件（覆盖系统级 dotenv）"""
    env_file = path / ".env"
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()


@dataclass
class BudgetConfig:
    """三层成本预算 — 设计稿第10章"""
    monthly_limit_usd: float = 100.0
    daily_limit_usd: float = 5.0
    per_task_limit_usd: float = 10.0
    deliberation_hard_cap_usd: float = 2.0


@dataclass
class ReActConfig:
    """ReAct引擎配置 — 设计稿第5章"""
    max_iterations: int = 25
    max_tokens: int = 8000
    max_time_seconds: float = 120.0
    circuit_breaker_errors: int = 3


@dataclass
class CacheConfig:
    """语义缓存配置 — 设计稿第5章(CacheEvolution)"""
    enabled: bool = True
    target_hit_rate: float = 0.75
    max_entries: int = 10000
    ttl_seconds: int = 3600
    similarity_threshold: float = 0.85


@dataclass
class SecurityConfig:
    """安全配置 — 设计稿第8章"""
    encryption_key_path: str = ""
    audit_log_retention_days: int = 90
    trust_score_alpha: float = 0.3
    guardrails_level: str = "full"
    # ARC-038: 数据四级分类默认配置
    data_classification_default: str = "MEDIUM"
    # NFR-096: 数据收集默认关闭
    telemetry_enabled: bool = False
    analytics_enabled: bool = False
    crash_reporting: bool = False


@dataclass
class MemoryConfig:
    """记忆层配置 — 设计稿第7章"""
    db_path: str = ""
    vector_dimension: int = 1536
    checkpoint_interval: int = 5
    auto_compact_threshold: int = 1000

    def __post_init__(self):
        if not self.db_path:
            _ensure_dirs()
            self.db_path = str(PROJECT_ROOT / "nexus.db")


@dataclass
class ModelConfig:
    """模型路由配置 — 设计稿第10章 / Model routing configuration

    支持 Provider 列表 (按 region 分组):
      国内 domestic: deepseek, moonshot, kimi, qwen, wenxin, glm, xiaomi
      国际 international: openai, anthropic, google, azure, groq, together
    """
    # 默认 Provider 和模型
    default_provider: str = "deepseek"
    default_model: str = "deepseek-chat"

    # Fallback 链: 格式 "provider/model" 或纯模型名
    fallback_chain: list[str] = field(default_factory=lambda: [
        "deepseek/deepseek-chat",
        "ollama/llama3.2",
        "moonshot/moonshot-v1-8k",
        "deepseek/deepseek-v4-pro",
        "openai/gpt-4o-mini",
        "local",
    ])

    # Provider 预热配置: provider_name -> {model, api_key_env, base_url}
    # 留空则使用 ProviderRegistry 内置默认值
    providers: Dict[str, Dict[str, str]] = field(default_factory=dict)

    # 场景专用模型路由 (格式 "provider/model")
    privacy_model: str = "local"
    complex_model: str = "anthropic/claude-3-5-sonnet-20241022"
    long_context_model: str = "deepseek/deepseek-v4-pro"
    coding_model: str = "deepseek/deepseek-chat"
    fast_model: str = "openai/gpt-4o-mini"


@dataclass
class StrictModeConfig:
    """严谨执行模式配置 — 设计稿第9章"""
    # 模式切换: "auto"(自动检测), "strict"(强制严谨), "chat"(强制对话)
    mode: str = "auto"
    # 最大澄清轮数
    max_clarify_rounds: int = 3
    # 最大重试次数
    max_retry_attempts: int = 3
    # 是否启用 LLM 增强意图分析
    llm_enhanced_analysis: bool = True
    # 是否启用 5 Expert 研讨
    enable_deliberation: bool = True
    # 验证失败时是否自动重试
    auto_retry_on_failure: bool = True


@dataclass
class ChannelConfig:
    """通道配置 — 设计稿第3章"""
    enabled_channels: list[str] = field(default_factory=lambda: ["cli"])
    cli: Dict[str, Any] = field(default_factory=dict)
    telegram: Dict[str, Any] = field(default_factory=dict)
    discord: Dict[str, Any] = field(default_factory=dict)
    feishu: Dict[str, Any] = field(default_factory=dict)
    web: Dict[str, Any] = field(default_factory=dict)
    api: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AppConfig:
    """应用总配置"""
    debug: bool = False
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    react: ReActConfig = field(default_factory=ReActConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    channels: ChannelConfig = field(default_factory=ChannelConfig)
    strict: StrictModeConfig = field(default_factory=StrictModeConfig)

    @classmethod
    def from_yaml(cls, path: Optional[str] = None) -> AppConfig:
        """从YAML文件加载配置 — 设计稿4.10零配置原则"""
        if path is None:
            path = os.getenv("NEXUS_CONFIG", str(PROJECT_ROOT / "config.yaml"))

        data: Dict[str, Any] = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = yaml.safe_load(f)
                    if isinstance(loaded, dict):
                        data = loaded
            except Exception as e:
                logging.getLogger("nexus.config").warning("配置加载失败 %s: %s", path, e)

        # 环境变量覆盖 — 零配置原则
        data.setdefault("debug", os.getenv("NEXUS_DEBUG", "false").lower() == "true")

        def _safe_subconfig(klass, key):
            """安全构建子配置，忽略未知字段"""
            raw = data.get(key, {})
            if not isinstance(raw, dict):
                raw = {}
            known = {f.name for f in klass.__dataclass_fields__.values()}
            filtered = {k: v for k, v in raw.items() if k in known}
            return klass(**filtered)

        return cls(
            debug=data.get("debug", False),
            budget=_safe_subconfig(BudgetConfig, "budget"),
            react=_safe_subconfig(ReActConfig, "react"),
            cache=_safe_subconfig(CacheConfig, "cache"),
            security=_safe_subconfig(SecurityConfig, "security"),
            memory=_safe_subconfig(MemoryConfig, "memory"),
            model=_safe_subconfig(ModelConfig, "model"),
            channels=_safe_subconfig(ChannelConfig, "channels"),
            strict=_safe_subconfig(StrictModeConfig, "strict"),
        )


# 全局单例
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """获取全局配置单例"""
    global _config
    if _config is None:
        load_project_env(Path(__file__).parent.parent)
        _ensure_dirs()
        _config = AppConfig.from_yaml()
    return _config


def reload_config(path: Optional[str] = None) -> AppConfig:
    """重新加载配置（热更新）"""
    global _config
    _ensure_dirs()
    _config = AppConfig.from_yaml(path)
    return _config
