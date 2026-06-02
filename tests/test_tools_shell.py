"""
NexusAgent v4.0+ — Shell Execution Tool Tests
覆盖: execute, timeout, disabled, dangerous patterns
"""

import os
import pytest

from nexusagent.tools.shell import ShellExecuteTool


class TestShellExecuteTool:
    @pytest.mark.asyncio
    async def test_disabled_by_default(self, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_SHELL", "0")
        tool = ShellExecuteTool()
        result = await tool.invoke("echo hello")
        assert "[ERROR]" in result
        assert "禁用" in result

    @pytest.mark.asyncio
    async def test_simple_echo(self, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_SHELL", "1")
        tool = ShellExecuteTool()
        result = await tool.invoke("echo hello")
        assert "[EXIT 0]" in result
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_stderr_capture(self, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_SHELL", "1")
        tool = ShellExecuteTool()
        result = await tool.invoke('python -c "import sys; sys.stderr.write(\'error\\n\')"')
        assert "[EXIT 0]" in result
        assert "error" in result

    @pytest.mark.asyncio
    async def test_nonzero_exit(self, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_SHELL", "1")
        tool = ShellExecuteTool()
        result = await tool.invoke('python -c "import sys; sys.exit(1)"')
        assert "[EXIT 1]" in result

    @pytest.mark.asyncio
    async def test_timeout(self, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_SHELL", "1")
        tool = ShellExecuteTool()
        result = await tool.invoke('python -c "import time; time.sleep(5)"', timeout=0.5)
        assert "[ERROR]" in result
        assert "超时" in result

    @pytest.mark.asyncio
    async def test_dangerous_pattern_blocked(self, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_SHELL", "1")
        tool = ShellExecuteTool()
        result = await tool.invoke("rm -rf /")
        assert "[ERROR]" in result
        assert "安全拦截" in result

    @pytest.mark.asyncio
    async def test_command_not_found(self, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_SHELL", "1")
        tool = ShellExecuteTool()
        result = await tool.invoke("nonexistent_command_xyz_123")
        assert "[ERROR]" in result
        assert "未找到" in result

    def test_to_tool_spec(self):
        spec = ShellExecuteTool().to_tool_spec()
        assert spec["name"] == "shell.execute"
        assert "command" in spec["input_schema"]["properties"]
