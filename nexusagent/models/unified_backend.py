"""
NexusAgent v0.1.0 — Unified LLM Backend

统一大模型接入层，支持国内/国外所有主流 LLM Provider。

设计原则:
    1. OpenAI-compatible first: 90%+ 的模型都支持 OpenAI 兼容接口
    2. litellm as primary: 使用 litellm 统一调用，省去维护各厂商 SDK
    3. aiohttp as fallback: litellm 不可用时降级到原生 HTTP
    4. Provider registry pattern: 新增模型只需注册配置，无需写新类

支持的 Provider / 支持的提供商:
    🇨🇳 国内 Domestic:
        - deepseek      (DeepSeek-V3, DeepSeek-R1)
        - moonshot      (Moonshot v1 系列, Kimi K2.6)
        - qwen          (阿里云通义千问 Qwen-Max/Plus/Turbo)
        - wenxin        (百度文心一言 Ernie-Bot)
        - glm           (智谱 GLM-4/3-Turbo)
        - xiaomi        (小米大模型 Mi-LLM)

    🌍 国外 International:
        - openai        (GPT-4o, o1, o3-mini, GPT-4-Turbo)
        - anthropic     (Claude 3.5 Sonnet, Claude 3 Opus, Claude 3 Haiku)
        - google        (Gemini 1.5 Pro, Gemini 1.5 Flash)
        - azure         (Azure OpenAI GPT-4o)
        - groq          (Llama 3, Mixtral via Groq)
        - together      (开源模型托管)

Usage:
    backend = UnifiedLLMBackend(provider="deepseek", model="deepseek-chat")
    result = await backend.complete(messages=[...])
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional

from nexusagent.utils.retry import exponential_backoff

logger = logging.getLogger("nexus.models.unified")


# ═══════════════════════════════════════════════════════════════
# Provider Registry / 提供商注册表
# ═══════════════════════════════════════════════════════════════

@dataclass
class ProviderConfig:
    """LLM Provider 配置模板"""
    name: str                          # 内部标识名
    display_name: str                  # 显示名称
    base_url: str                      # API Base URL
    api_key_env: str                   # 环境变量名
    default_model: str                 # 默认模型
    model_prefix: str = ""             # litellm model 前缀 (如 "openai/", "anthropic/")
    supports_tools: bool = True        # 是否支持 function calling
    supports_streaming: bool = True    # 是否支持流式输出
    max_tokens_default: int = 4096     # 默认 max_tokens
    cost_per_1k_prompt: float = 0.0    # 提示成本 (USD/1K tokens)
    cost_per_1k_completion: float = 0.0  # 补全成本 (USD/1K tokens)
    region: str = "global"             # "domestic" | "international"


# Provider alias 映射 — 不同品牌名指向同一底层 provider
_PROVIDER_ALIASES: Dict[str, str] = {
    "kimi": "moonshot",  # Kimi 品牌渠道 → Moonshot 内部统一处理
}


def _resolve_provider(name: str) -> str:
    """解析 provider 名称，支持 alias"""
    return _PROVIDER_ALIASES.get(name.lower(), name.lower())


# 内置 Provider 配置表 — 新增 Provider 只需在此添加一行
_BUILTIN_PROVIDERS: Dict[str, ProviderConfig] = {
    # ── 国内 Domestic ──
    "deepseek": ProviderConfig(
        name="deepseek",
        display_name="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
        default_model="deepseek-chat",
        cost_per_1k_prompt=0.00014,
        cost_per_1k_completion=0.00028,
        region="domestic",
    ),
    "moonshot": ProviderConfig(
        name="moonshot",
        display_name="Moonshot (Kimi)",
        base_url="https://api.moonshot.cn/v1",
        api_key_env="MOONSHOT_API_KEY",
        default_model="moonshot-v1-8k",
        cost_per_1k_prompt=0.012,
        cost_per_1k_completion=0.012,
        region="domestic",
    ),
    "kimi": ProviderConfig(
        name="kimi",
        display_name="Kimi (Moonshot)",
        base_url="https://api.moonshot.cn/v1",
        api_key_env="KIMI_API_KEY",
        default_model="kimi-k2.6",
        cost_per_1k_prompt=0.012,
        cost_per_1k_completion=0.012,
        region="domestic",
    ),
    "ollama": ProviderConfig(
        name="ollama",
        display_name="Ollama (Local)",
        base_url="http://localhost:11434/v1",
        api_key_env="OLLAMA_API_KEY",
        default_model="llama3.2",
        cost_per_1k_prompt=0.0,
        cost_per_1k_completion=0.0,
        region="local",
    ),
    "qwen": ProviderConfig(
        name="qwen",
        display_name="通义千问 (Qwen)",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY",
        default_model="qwen-max",
        cost_per_1k_prompt=0.0035,
        cost_per_1k_completion=0.007,
        region="domestic",
    ),
    "wenxin": ProviderConfig(
        name="wenxin",
        display_name="文心一言 (Ernie)",
        base_url="https://qianfan.baidubce.com/v2",
        api_key_env="QIANFAN_API_KEY",
        default_model="ernie-bot",
        supports_tools=False,
        region="domestic",
    ),
    "glm": ProviderConfig(
        name="glm",
        display_name="智谱 GLM",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key_env="ZHIPU_API_KEY",
        default_model="glm-4",
        cost_per_1k_prompt=0.001,
        cost_per_1k_completion=0.001,
        region="domestic",
    ),
    "xiaomi": ProviderConfig(
        name="xiaomi",
        display_name="小米大模型 (Mi-LLM)",
        base_url="https://api.xiaomi.ai/v1",
        api_key_env="XIAOMI_API_KEY",
        default_model="mi-llm-pro",
        region="domestic",
    ),
    # ── 国外 International ──
    "openai": ProviderConfig(
        name="openai",
        display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        default_model="gpt-4o-mini",
        model_prefix="openai/",
        cost_per_1k_prompt=0.00015,
        cost_per_1k_completion=0.0006,
        region="international",
    ),
    "anthropic": ProviderConfig(
        name="anthropic",
        display_name="Anthropic Claude",
        base_url="https://api.anthropic.com/v1",
        api_key_env="ANTHROPIC_API_KEY",
        default_model="claude-3-5-sonnet-20241022",
        model_prefix="anthropic/",
        cost_per_1k_prompt=0.003,
        cost_per_1k_completion=0.015,
        region="international",
    ),
    "google": ProviderConfig(
        name="google",
        display_name="Google Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key_env="GOOGLE_API_KEY",
        default_model="gemini-1.5-pro",
        model_prefix="gemini/",
        region="international",
    ),
    "azure": ProviderConfig(
        name="azure",
        display_name="Azure OpenAI",
        base_url="",  # 用户必须自行配置，如 https://xxx.openai.azure.com/
        api_key_env="AZURE_OPENAI_API_KEY",
        default_model="azure/gpt-4o",
        model_prefix="azure/",
        region="international",
    ),
    "groq": ProviderConfig(
        name="groq",
        display_name="Groq",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        default_model="llama-3.3-70b-versatile",
        cost_per_1k_prompt=0.00059,
        cost_per_1k_completion=0.00079,
        region="international",
    ),
    "together": ProviderConfig(
        name="together",
        display_name="Together AI",
        base_url="https://api.together.xyz/v1",
        api_key_env="TOGETHER_API_KEY",
        default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        region="international",
    ),
}


class ProviderRegistry:
    """
    Provider 注册中心 — 支持动态注册新 Provider。
    用户可以通过代码或配置文件扩展支持的模型列表。
    """

    _instance: Optional[ProviderRegistry] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._providers: Dict[str, ProviderConfig] = dict(_BUILTIN_PROVIDERS)
        return cls._instance

    def register(self, config: ProviderConfig) -> None:
        """动态注册新 Provider"""
        self._providers[config.name.lower()] = config
        logger.info("Registered new provider: %s", config.name)

    def get(self, name: str) -> Optional[ProviderConfig]:
        """获取 Provider 配置"""
        return self._providers.get(name.lower())

    def list_providers(self, region: Optional[str] = None) -> List[ProviderConfig]:
        """列出所有 Provider，可按 region 过滤"""
        providers = list(self._providers.values())
        if region:
            providers = [p for p in providers if p.region == region]
        return providers

    def list_models(self, provider_name: Optional[str] = None) -> List[str]:
        """列出所有默认模型"""
        if provider_name:
            cfg = self.get(provider_name)
            return [cfg.default_model] if cfg else []
        return [p.default_model for p in self._providers.values()]

    def is_supported(self, provider: str) -> bool:
        return provider.lower() in self._providers


# 全局单例
provider_registry = ProviderRegistry()


# ═══════════════════════════════════════════════════════════════
# Unified LLM Backend / 统一大模型后端
# ═══════════════════════════════════════════════════════════════

class UnifiedLLMBackend:
    """
    统一 LLM 后端 — 一个类支持所有 Provider。

    调用优先级:
        1. litellm (如果安装) — 自动处理所有 OpenAI 兼容接口
        2. openai SDK (如果安装) — 作为 litellm 的替代
        3. 原生 aiohttp — 最后保底
    """

    def __init__(
        self,
        provider: str,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        timeout: float = 60.0,
    ):
        """
        Args:
            provider: Provider 名称，如 "deepseek", "openai", "kimi"
            model: 模型名称，如 "deepseek-chat", "gpt-4o"
            api_key: API 密钥，留空则从环境变量读取
            base_url: 自定义 API Base URL
            temperature: 默认温度
            timeout: 请求超时（秒）
        """
        self._provider_name = _resolve_provider(provider)
        self._config = provider_registry.get(self._provider_name)

        if self._config is None:
            logger.warning(
                "Unknown provider '%s'; falling back to generic OpenAI-compatible mode. "
                "Please register it via ProviderRegistry.register()",
                provider,
            )
            self._config = ProviderConfig(
                name=provider,
                display_name=provider,
                base_url=base_url or "",
                api_key_env=f"{provider.upper()}_API_KEY",
                default_model=model or "unknown",
            )

        self._model = model or self._config.default_model

        # 读取 API Key；对 moonshot/kimi 两套独立 Key 体系做交叉回退
        _key = api_key or os.getenv(self._config.api_key_env, "")
        if not _key and self._provider_name in ("moonshot", "kimi"):
            _alt_env = "KIMI_API_KEY" if self._provider_name == "moonshot" else "MOONSHOT_API_KEY"
            _key = os.getenv(_alt_env, "")
            if _key:
                logger.info(
                    "Provider '%s' 未配置 %s，已回退使用 %s",
                    self._provider_name,
                    self._config.api_key_env,
                    _alt_env,
                )
        self._api_key = _key

        self._base_url = base_url or self._config.base_url
        self._temperature = temperature
        self._timeout = timeout
        self._session: Any = None

        # 缓存调用策略
        self._strategy = self._detect_strategy()

    def _detect_strategy(self) -> str:
        """检测最佳调用策略"""
        try:
            import litellm  # noqa: F401
            return "litellm"
        except ImportError:
            pass
        try:
            import openai  # noqa: F401
            return "openai"
        except ImportError:
            pass
        return "aiohttp"

    # ── 连接池管理 ──

    async def _get_session(self):
        if self._session is None:
            import aiohttp
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    # ── 核心调用 ──

    async def complete(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        统一 completion 接口。

        Returns:
            {
                "content": str,
                "tool_calls": List[Dict],
                "usage": {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int},
                "_model_used": str,
                "_provider": str,
            }
        """
        temp = temperature if temperature is not None else self._temperature
        max_tok = max_tokens if max_tokens is not None else self._config.max_tokens_default

        if self._strategy == "litellm":
            return await self._complete_litellm(messages, tools, temp, max_tok)
        elif self._strategy == "openai":
            return await self._complete_openai_sdk(messages, tools, temp, max_tok)
        else:
            return await self._complete_aiohttp(messages, tools, temp, max_tok)

    async def complete_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """
        流式 completion 接口 — 逐 token 返回文本
        使用 openai SDK stream 模式（兼容所有 OpenAI-compatible API）
        """
        temp = temperature if temperature is not None else self._temperature
        max_tok = max_tokens if max_tokens is not None else self._config.max_tokens_default

        try:
            import openai
        except ImportError:
            yield "[NexusAgent] openai SDK not installed. pip install openai"
            return

        client = openai.AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url or None,
            timeout=self._timeout,
        )

        kwargs: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temp,
            "max_tokens": max_tok,
            "stream": True,
        }

        try:
            stream = await client.chat.completions.create(**kwargs)
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        except Exception as e:
            logger.warning("stream error for %s: %s", self._provider_name, e)
            yield f"\n[Stream Error: {e}]"
        finally:
            await client.close()

    # ── litellm 策略 ──

    async def _complete_litellm(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]],
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        import litellm

        # litellm 模型名格式: "provider/model" 或 "model"
        litellm_model = f"{self._config.model_prefix}{self._model}".lstrip("/")
        if not self._config.model_prefix:
            litellm_model = self._model

        # 特殊处理 Azure
        if self._provider_name == "azure":
            litellm_model = self._model  # azure 模型名已包含 azure/ 前缀

        kwargs: Dict[str, Any] = {
            "model": litellm_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "api_key": self._api_key,
            "base_url": self._base_url or None,
            "timeout": self._timeout,
        }
        if tools and self._config.supports_tools:
            kwargs["tools"] = tools

        try:
            response = await litellm.acompletion(**kwargs)
            choice = response.choices[0]
            msg = choice.message

            # 提取 tool_calls
            tool_calls = []
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append({
                        "id": getattr(tc, "id", ""),
                        "name": tc.function.name if hasattr(tc, "function") else "",
                        "arguments": tc.function.arguments if hasattr(tc, "function") else "",
                    })

            usage = response.usage
            return {
                "content": msg.content or "",
                "tool_calls": tool_calls,
                "usage": {
                    "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                    "completion_tokens": getattr(usage, "completion_tokens", 0),
                    "total_tokens": getattr(usage, "total_tokens", 0),
                },
                "_model_used": self._model,
                "_provider": self._provider_name,
            }
        except Exception as e:
            logger.warning("litellm error for %s: %s", self._provider_name, e)
            # 降级到 aiohttp
            return await self._complete_aiohttp(messages, tools, temperature, max_tokens)

    # ── openai SDK 策略 ──

    async def _complete_openai_sdk(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]],
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        import openai

        client = openai.AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url or None,
            timeout=self._timeout,
        )

        kwargs: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools and self._config.supports_tools:
            kwargs["tools"] = [{"type": "function", "function": t} for t in tools]

        try:
            response = await client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            msg = choice.message

            tool_calls = []
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    })

            usage = response.usage
            return {
                "content": msg.content or "",
                "tool_calls": tool_calls,
                "usage": {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                },
                "_model_used": self._model,
                "_provider": self._provider_name,
            }
        except Exception as e:
            logger.warning("openai SDK error for %s: %s", self._provider_name, e)
            return await self._complete_aiohttp(messages, tools, temperature, max_tokens)
        finally:
            await client.close()

    # ── aiohttp 保底策略 ──

    @exponential_backoff(max_retries=3, base_delay=1.0, retryable_exceptions=(Exception,))
    async def _complete_aiohttp(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]],
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        try:
            import aiohttp
        except ImportError:
            return self._fallback(messages, "aiohttp not installed. pip install aiohttp")

        if not self._base_url:
            return self._fallback(messages, f"No base_url configured for provider '{self._provider_name}'")

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools and self._config.supports_tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]

        try:
            session = await self._get_session()
            async with session.post(
                f"{self._base_url}/chat/completions",
                json=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as resp:
                data = await resp.json()
                if "choices" in data:
                    choice = data["choices"][0]
                    msg = choice.get("message", {})
                    return {
                        "content": msg.get("content", ""),
                        "tool_calls": msg.get("tool_calls", []),
                        "usage": data.get("usage", {}),
                        "_model_used": self._model,
                        "_provider": self._provider_name,
                    }
                error_msg = data.get("error", {}).get("message", str(data)[:200])
                return self._fallback(messages, f"API Error: {error_msg}")
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            logger.warning("aiohttp error for %s: %s", self._provider_name, e)
            return self._fallback(messages, str(e))

    def _fallback(self, messages: List[Dict[str, str]], error: str = "") -> Dict[str, Any]:
        last = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last = m.get("content", "")[:100]
                break
        reason = error or "Unknown error"
        return {
            "content": (
                f"[NexusAgent] {self._config.display_name} API call failed: {reason}\n"
                f"Please check: 1) pip install litellm  2) API key in .env ({self._config.api_key_env})"
            ),
            "tool_calls": [],
            "usage": {"total_tokens": 0},
            "_model_used": self._model,
            "_provider": self._provider_name,
        }

    # ── 属性暴露 ──

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return self._provider_name

    @property
    def cost_per_1k_prompt(self) -> float:
        return self._config.cost_per_1k_prompt

    @property
    def cost_per_1k_completion(self) -> float:
        return self._config.cost_per_1k_completion
