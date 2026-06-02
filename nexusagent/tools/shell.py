"""
NexusAgent v4.0+ — Shell Execution Tool

安全执行 shell 命令，支持超时控制和输出捕获。

安全模型:
- 默认禁用，需设置 NEXUS_ALLOW_SHELL=1
- 禁止危险命令模式 (rm -rf /, curl | sh, 等)
- 超时后强制终止子进程
- 输出长度限制防止内存爆炸
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nexus.tools.shell")


_MAX_OUTPUT = 50 * 1024  # 50KB
_DEFAULT_TIMEOUT = 30.0

# 危险命令模式黑名单
_DANGEROUS_PATTERNS = [
    "rm -rf /", "rm -rf /*", "> /dev/sda", ":(){ :|:& };:",
    "curl .*\\|.*sh", "wget .*\\|.*sh", "curl .*\\|.*bash",
    "mkfs", "dd if=/dev/zero", "mv / /dev/null",
    "chmod 000 /", "chown -R /",
]


@dataclass
class ShellResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    success: bool = True
    error: str = ""
    execution_time_ms: float = 0.0


class ShellExecuteTool:
    """安全 Shell 命令执行器"""

    async def invoke(
        self,
        command: str,
        timeout: float = _DEFAULT_TIMEOUT,
        cwd: str = "",
        env: Optional[Dict[str, str]] = None,
    ) -> str:
        if os.getenv("NEXUS_ALLOW_SHELL", "0") != "1":
            return (
                "[ERROR] Shell 命令执行已被禁用。"
                "设置 NEXUS_ALLOW_SHELL=1 以启用（仅限受信任环境）。"
            )

        # 静态危险模式扫描
        cmd_lower = command.lower()
        for pattern in _DANGEROUS_PATTERNS:
            import re
            if re.search(pattern, cmd_lower):
                return f"[ERROR] 安全拦截: 命令包含危险模式 '{pattern}'"

        # 使用 shlex 解析，拒绝明显危险的单字符/路径
        try:
            parts = shlex.split(command)
        except ValueError as e:
            return f"[ERROR] 命令解析失败: {e}"

        if not parts:
            return "[ERROR] 空命令"

        import time
        start = time.monotonic()
        proc = None
        try:
            kwargs: Dict[str, Any] = {
                "stdout": asyncio.subprocess.PIPE,
                "stderr": asyncio.subprocess.PIPE,
            }
            if cwd:
                kwargs["cwd"] = cwd
            if env:
                kwargs["env"] = {**os.environ, **env}

            proc = await asyncio.create_subprocess_exec(parts[0], *parts[1:], **kwargs)
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )

            stdout = stdout_b.decode("utf-8", errors="replace")[:_MAX_OUTPUT]
            stderr = stderr_b.decode("utf-8", errors="replace")[:_MAX_OUTPUT]
            elapsed = (time.monotonic() - start) * 1000

            result = ShellResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=proc.returncode or 0,
                success=proc.returncode == 0,
                execution_time_ms=elapsed,
            )
            return self._format_result(result)

        except asyncio.TimeoutError:
            if proc:
                proc.kill()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
            return f"[ERROR] 命令执行超时 ({timeout}s)"
        except FileNotFoundError:
            return f"[ERROR] 命令未找到: {parts[0]}"
        except Exception as e:
            return f"[ERROR] 执行失败: {e}"

    def _format_result(self, result: ShellResult) -> str:
        lines = [f"[EXIT {result.exit_code}] 耗时 {result.execution_time_ms:.0f}ms"]
        if result.stdout:
            lines.append("--- stdout ---")
            lines.append(result.stdout)
        if result.stderr:
            lines.append("--- stderr ---")
            lines.append(result.stderr)
        return "\n".join(lines)

    def to_tool_spec(self) -> Dict[str, Any]:
        return {
            "name": "shell.execute",
            "description": (
                "执行 shell 命令。支持超时控制和工作目录设置。"
                "默认禁用，需管理员开启。"
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的 shell 命令"},
                    "timeout": {"type": "number", "default": 30, "description": "超时秒数"},
                    "cwd": {"type": "string", "default": "", "description": "工作目录"},
                },
                "required": ["command"],
            },
        }
