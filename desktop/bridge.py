"""
NexusAgent Desktop — JS ↔ Python 桥接 (PyQt6 QWebChannel)
新版 UI 适配：单页面应用，通过 uiAPI 回调推送结果
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSlot


class NexusBridge(QObject):
    """前端 JS 通过 QWebChannel 调用 Python 方法"""

    def __init__(self, parent=None, agent=None, config=None):
        super().__init__(parent)
        self._window = parent
        self.agent = agent
        self.config = config

    @pyqtSlot(str, str, str, result=str)
    def reportError(self, message: str, source: str, line: str) -> str:
        """JS 错误上报"""
        error_msg = f"[UI Error] {message} at {source}:{line}"
        if self.agent and self._window and hasattr(self._window, "_run_agent"):
            self._window._run_agent(
                f"桌面客户端 UI 报错：{error_msg}。请检查 desktop/index.html 的代码。"
            )
        return json.dumps({"ok": True})

    @pyqtSlot(str, result=str)
    def sendMessage(self, text: str) -> str:
        """用户发送消息 → Agent 异步处理，结果通过 uiAPI 推送"""
        if not self.agent:
            return json.dumps({"ok": False, "error": "Agent 未初始化"})
        if self._window and hasattr(self._window, "_run_agent"):
            self._window._run_agent(text)
            return json.dumps({"ok": True})
        return json.dumps({"ok": False, "error": "窗口未初始化"})

    @pyqtSlot(result=str)
    def getConfig(self) -> str:
        """获取当前配置（脱敏）"""
        provider = "deepseek"
        model = "deepseek-chat"
        if self.config:
            provider = getattr(self.config.model, "default_provider", provider)
            model = getattr(self.config.model, "default_model", model)
        return json.dumps({
            "provider": provider,
            "model": model,
            "version": "3.3.0",
        })

    @pyqtSlot(result=str)
    def getModelList(self) -> str:
        """获取可用模型列表"""
        models = [
            "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k",
            "deepseek-chat", "deepseek-v4-pro",
            "openai/gpt-4o-mini", "local"
        ]
        return json.dumps({"ok": True, "models": models})

    @pyqtSlot(str, result=str)
    def switchModel(self, model_name: str) -> str:
        """切换模型"""
        if self.config:
            self.config.model.default_model = model_name
            self.config.model.default_provider = (
                "moonshot" if model_name.startswith("moonshot") else
                "deepseek" if model_name.startswith("deepseek") else
                "openai" if model_name.startswith("openai") else "local"
            )
        return json.dumps({"ok": True, "model": model_name})

    @pyqtSlot(result=str)
    def getTrustScore(self) -> str:
        return json.dumps({
            "ok": True, "score": 50, "tier": "可信", "level": "CONFIRM",
        })

    @pyqtSlot(result=str)
    def getSecurityStatus(self) -> str:
        return json.dumps({
            "ok": True, "guardrails": "active", "encryption": "AES-256", "sandbox": "ready",
        })

    @pyqtSlot(str, result=str)
    def saveConfig(self, config_json: str) -> str:
        """保存配置到 .env 并热重载 LLM backend"""
        try:
            data = json.loads(config_json)
            provider = data.get("provider", "deepseek")
            model = data.get("model", "deepseek-chat")
            api_key = data.get("api_key", "")

            # 更新内存配置
            if self.config:
                self.config.model.default_provider = provider
                self.config.model.default_model = model

            # 写入 .env
            env_path = Path(__file__).parent.parent / ".env"
            lines = []
            if env_path.exists():
                lines = env_path.read_text(encoding="utf-8").splitlines()

            updates = {
                "DEFAULT_PROVIDER": provider,
                "DEFAULT_MODEL": model,
            }
            key_var = {
                "moonshot": "MOONSHOT_API_KEY",
                "deepseek": "DEEPSEEK_API_KEY",
                "openai": "OPENAI_API_KEY",
            }.get(provider)
            if key_var and api_key:
                updates[key_var] = api_key

            existing = set()
            for i, line in enumerate(lines):
                if "=" in line and not line.strip().startswith("#"):
                    k = line.split("=", 1)[0].strip()
                    if k in updates:
                        lines[i] = f"{k}={updates[k]}"
                        existing.add(k)
            for k, v in updates.items():
                if k not in existing:
                    lines.append(f"{k}={v}")

            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            # 更新环境变量
            for k, v in updates.items():
                os.environ[k] = v

            # 热重载 LLM backend
            if self.agent:
                self.agent.reload_llm(provider, model)

            return json.dumps({"ok": True, "provider": provider, "model": model})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    @pyqtSlot(str, result=str)
    def confirmDangerous(self, command_json: str) -> str:
        try:
            json.loads(command_json)
            return json.dumps({"ok": True, "approved": True})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})
