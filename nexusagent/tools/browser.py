"""
NexusAgent v4.0+ — 浏览器自动化工具

设计参考:
- OpenAI Computer Use: https://platform.openai.com/docs/guides/computer-use
  "Screenshot + click + keyboard input"
- Browser-use: https://github.com/browser-use/browser-use
  "Make websites accessible for AI agents"

职责:
    提供网页浏览、内容抓取、截图、点击、填表能力
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nexus.tools.browser")


@dataclass
class BrowserResult:
    """浏览器操作结果"""
    url: str
    title: str = ""
    content: str = ""  # 纯文本内容
    links: List[Dict[str, str]] = None
    success: bool = True
    error: str = ""

    def __post_init__(self):
        if self.links is None:
            self.links = []


class BrowserTool:
    """
    浏览器自动化工具

    Usage:
        browser = BrowserTool()
        result = await browser.visit("https://example.com")
        print(result.content)
    """

    def __init__(self):
        self._playwright_available = self._check_playwright()

    def _check_playwright(self) -> bool:
        try:
            import playwright  # noqa: F401
            return True
        except ImportError:
            logger.warning("playwright 未安装，BrowserTool 降级为 requests 模式")
            return False

    _FORBIDDEN_SCHEMES = {"file", "ftp", "data", "javascript", "vbscript"}
    _FORBIDDEN_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "169.254."}

    def _is_safe_url(self, url: str) -> bool:
        """SSRF 防护: 校验 URL scheme 和 host"""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        host = parsed.hostname or ""
        if any(host.startswith(h) or host == h for h in self._FORBIDDEN_HOSTS):
            return False
        return True

    async def visit(self, url: str, extract_text: bool = True) -> BrowserResult:
        """访问网页并提取内容"""
        if not self._is_safe_url(url):
            return BrowserResult(url=url, success=False, error="URL 不安全或被禁止访问")
        if self._playwright_available:
            return await self._visit_with_playwright(url, extract_text)
        return await self._visit_with_requests(url)

    async def _visit_with_playwright(self, url: str, extract_text: bool) -> BrowserResult:
        browser = None
        try:
            from playwright.async_api import async_playwright

            p = await async_playwright().start()
            try:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, timeout=30000)

                title = await page.title()
                content = ""
                if extract_text:
                    # 提取可见文本
                    content = await page.evaluate("""
                        () => document.body.innerText.substring(0, 8000)
                    """)

                # 提取链接
                links = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('a[href]'))
                        .slice(0, 20)
                        .map(a => ({text: a.innerText.trim(), href: a.href}))
                """)

                return BrowserResult(
                    url=url, title=title, content=content,
                    links=links, success=True,
                )
            finally:
                if browser:
                    await browser.close()
                await p.stop()
        except Exception as e:
            logger.error("Playwright 访问失败: %s", e)
            return BrowserResult(url=url, success=False, error=str(e))

    async def _visit_with_requests(self, url: str) -> BrowserResult:
        """降级：使用 HTTP 请求获取内容"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as resp:
                    html = await resp.text()
                    # 简单文本提取
                    import re
                    text = re.sub(r"<[^>]+>", " ", html)
                    text = re.sub(r"\s+", " ", text).strip()[:8000]
                    return BrowserResult(url=url, content=text, success=True)
        except Exception as e:
            return BrowserResult(url=url, success=False, error=str(e))

    async def search(self, query: str, engine: str = "duckduckgo") -> List[BrowserResult]:
        """搜索并返回结果"""
        try:
            from duckduckgo_search import DDGS
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=5):
                    results.append(BrowserResult(
                        url=r["href"],
                        title=r.get("title", ""),
                        content=r.get("body", ""),
                        success=True,
                    ))
            return results
        except ImportError:
            logger.warning("duckduckgo-search 未安装")
            return []
        except Exception as e:
            logger.error("搜索失败: %s", e)
            return []

    def to_tool_spec(self) -> Dict[str, Any]:
        """返回 ToolSpec 兼容描述"""
        return {
            "name": "browser.visit",
            "description": "访问指定 URL 并提取网页内容。支持网页浏览、内容抓取。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要访问的 URL"},
                    "extract_text": {"type": "boolean", "default": True},
                },
                "required": ["url"],
            },
        }
