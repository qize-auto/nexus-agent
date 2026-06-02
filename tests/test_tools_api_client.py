"""
NexusAgent v4.0+ — API Client Tool Tests
覆盖: request, SSRF blocking
"""

import pytest

from nexusagent.tools.api_client import APIRequestTool, _is_safe_url


class TestIsSafeUrl:
    def test_safe_http(self):
        assert _is_safe_url("http://example.com/api") is True

    def test_safe_https(self):
        assert _is_safe_url("https://example.com") is True

    def test_localhost_blocked(self):
        assert _is_safe_url("http://localhost:8080") is False

    def test_127_blocked(self):
        assert _is_safe_url("http://127.0.0.1") is False

    def test_private_ip_blocked(self):
        assert _is_safe_url("http://192.168.1.1") is False
        assert _is_safe_url("http://10.0.0.1") is False

    def test_file_scheme_blocked(self):
        assert _is_safe_url("file:///etc/passwd") is False


class TestAPIRequestTool:
    def test_to_tool_spec(self):
        spec = APIRequestTool().to_tool_spec()
        assert spec["name"] == "api.request"
        assert "url" in spec["input_schema"]["properties"]

    @pytest.mark.asyncio
    async def test_ssrf_blocked(self):
        tool = APIRequestTool()
        result = await tool.invoke("http://localhost/admin")
        assert "[ERROR]" in result
        assert "不安全" in result

    @pytest.mark.asyncio
    async def test_real_http_get(self):
        tool = APIRequestTool()
        result = await tool.invoke("https://httpbin.org/get")
        # 接受任何成功响应（外部服务可能临时不可用）
        assert "Status:" in result

    @pytest.mark.asyncio
    async def test_real_http_post_json(self):
        tool = APIRequestTool()
        result = await tool.invoke(
            "https://httpbin.org/post",
            method="POST",
            body='{"key": "value"}',
        )
        assert "Status:" in result
