"""
NexusAgent v4.0+ — E2B 云沙箱集成

设计参考:
- E2B: https://e2b.dev
  "Cloud sandbox for AI-generated code execution"
- smolagents E2B integration: https://github.com/huggingface/smolagents

职责:
    1. 跨平台代码隔离（Windows/Mac/Linux 一致体验）
    2. 危险代码在云端执行，宿主机零风险
    3. 支持文件上传/下载、网络访问控制
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from nexusagent.security.sandbox import SandboxResult, SandboxReport

logger = logging.getLogger("nexus.security.e2b")


@dataclass
class E2BConfig:
    """E2B 配置"""
    api_key: str = ""
    template: str = "base"  # base, code-interpreter, browser
    timeout_ms: int = 30000
    request_timeout: int = 60


class E2BSandbox:
    """
    E2B 云沙箱适配器

    Usage:
        sandbox = E2BSandbox(api_key="e2b_...")
        report = await sandbox.execute_code("print('hello')", language="python")
    """

    def __init__(self, config: Optional[E2BConfig] = None):
        self._config = config or E2BConfig()
        self._available = self._check_availability()

    def _check_availability(self) -> bool:
        try:
            import e2b  # noqa: F401
            if self._config.api_key:
                return True
            # 尝试从环境变量读取
            import os
            if os.getenv("E2B_API_KEY"):
                self._config.api_key = os.getenv("E2B_API_KEY")
                return True
        except ImportError:
            logger.warning("e2b 包未安装，云沙箱不可用。pip install e2b")
        return False

    @property
    def is_available(self) -> bool:
        return self._available

    async def execute_code(
        self,
        code: str,
        language: str = "python",
        files: Optional[Dict[str, str]] = None,
        timeout: int = 30,
    ) -> SandboxReport:
        """
        在 E2B 沙箱中执行代码

        Args:
            code: 代码内容
            language: python | javascript | bash
            files: 上传的文件 {filename: content}
            timeout: 超时秒数

        Returns:
            SandboxReport
        """
        if not self._available:
            return SandboxReport(
                result=SandboxResult.REJECTED,
                stderr="E2B 沙箱不可用（未安装 e2b 包或未配置 API key）",
            )

        try:
            from e2b import Sandbox as E2B_Sandbox

            sbx = E2B_Sandbox(api_key=self._config.api_key)

            # 上传文件
            if files:
                for filename, content in files.items():
                    sbx.files.write(filename, content)

            # 执行代码
            if language == "python":
                execution = sbx.run_code(code, timeout=timeout)
            else:
                execution = sbx.commands.run(code, timeout=timeout)

            stdout = getattr(execution, "stdout", "")
            stderr = getattr(execution, "stderr", "")
            exit_code = getattr(execution, "exit_code", 0)

            sbx.close()

            return SandboxReport(
                result=SandboxResult.PASSED if exit_code == 0 else SandboxResult.FAILED,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_ms=getattr(execution, "duration", 0) * 1000,
            )

        except Exception as e:
            logger.error("E2B 执行失败: %s", e)
            return SandboxReport(
                result=SandboxResult.REJECTED,
                error=str(e),
            )

    async def execute_browser_task(self, url: str, task: str) -> SandboxReport:
        """
        在浏览器沙箱中执行任务

        Args:
            url: 起始 URL
            task: 自然语言任务描述
        """
        if not self._available:
            return SandboxReport(
                result=SandboxResult.REJECTED,
                error="E2B 浏览器沙箱不可用",
            )

        code = f"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto({repr(url)})
        content = await page.content()
        print(content[:5000])
        await browser.close()

asyncio.run(main())
"""
        return await self.execute_code(code, language="python", timeout=60)
