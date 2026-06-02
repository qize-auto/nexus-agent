"""
NexusAgent v4.0+ — API Client Tool

HTTP 请求工具，支持 GET/POST/PUT/DELETE/ PATCH。

P1 能力:
- api.request: 发送 HTTP 请求并返回响应
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("nexus.tools.api_client")


# SSRF 防护: 禁止访问内网/本地地址
_FORBIDDEN_HOSTS = {
    "localhost", "127.0.0.1", "0.0.0.0", "::1",
}
_FORBIDDEN_PREFIXES = ("10.", "172.16.", "172.17.", "172.18.", "172.19.",
                       "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
                       "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
                       "172.30.", "172.31.", "192.168.", "169.254.")


def _is_safe_url(url: str) -> bool:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host in _FORBIDDEN_HOSTS:
        return False
    if any(host.startswith(p) for p in _FORBIDDEN_PREFIXES):
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    return True


class APIRequestTool:
    """HTTP API 请求工具"""

    async def invoke(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: str = "",
        timeout: float = 30.0,
    ) -> str:
        if not _is_safe_url(url):
            return f"[ERROR] URL 不安全或被禁止访问: {url}"

        try:
            import aiohttp
        except ImportError:
            return "[ERROR] aiohttp 未安装，无法发送 HTTP 请求"

        try:
            async with aiohttp.ClientSession() as session:
                kwargs: Dict[str, Any] = {"timeout": aiohttp.ClientTimeout(total=timeout)}
                if headers:
                    kwargs["headers"] = headers

                # 自动解析 JSON body
                data = None
                if body:
                    try:
                        data = json.loads(body)
                        kwargs["json"] = data
                    except json.JSONDecodeError:
                        kwargs["data"] = body

                async with session.request(method.upper(), url, **kwargs) as resp:
                    text = await resp.text()
                    # 截断过长响应
                    if len(text) > 50 * 1024:
                        text = text[:50 * 1024] + "\n...[truncated]"
                    result = (
                        f"Status: {resp.status} {resp.reason}\n"
                        f"Headers: {dict(resp.headers)}\n"
                        f"--- Body ---\n{text}"
                    )
                    return result
        except Exception as e:
            return f"[ERROR] 请求失败: {e}"

    def to_tool_spec(self) -> Dict[str, Any]:
        return {
            "name": "api.request",
            "description": "发送 HTTP 请求。支持 GET/POST/PUT/DELETE/PATCH。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "请求 URL"},
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"], "default": "GET"},
                    "headers": {"type": "object", "description": "请求头（JSON 对象）"},
                    "body": {"type": "string", "default": "", "description": "请求体（字符串或 JSON）"},
                    "timeout": {"type": "number", "default": 30, "description": "超时秒数"},
                },
                "required": ["url"],
            },
        }
