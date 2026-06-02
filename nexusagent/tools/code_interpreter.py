"""
NexusAgent v4.0+ — 代码解释器工具

设计参考:
- OpenAI Code Interpreter: 沙箱 Python 执行 + 数据分析 + 图表生成
- E2B Code Interpreter: https://e2b.dev/docs/code-interpreter

职责:
    在沙箱中安全执行 Python/R 代码，支持数据分析、图表生成、文件处理
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nexus.tools.code_interpreter")


@dataclass
class CodeResult:
    """代码执行结果"""
    code: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    images: List[str] = field(default_factory=list)  # base64 编码的图片
    files: Dict[str, str] = field(default_factory=dict)  # 生成的文件
    success: bool = True
    error: str = ""
    execution_time_ms: float = 0.0


class CodeInterpreterTool:
    """
    代码解释器工具

    Usage:
        ci = CodeInterpreterTool()
        result = await ci.execute("import pandas as pd; df = pd.DataFrame({'a': [1,2,3]}); print(df)")
    """

    def __init__(self, sandbox: Optional[Any] = None):
        self._sandbox = sandbox
        self._e2b_available = self._check_e2b()

    def _check_e2b(self) -> bool:
        try:
            import e2b  # noqa: F401
            return True
        except ImportError:
            return False

    async def execute(self, code: str, language: str = "python", files: Optional[Dict[str, str]] = None) -> CodeResult:
        """执行代码"""
        if self._sandbox and hasattr(self._sandbox, "execute_code"):
            return await self._execute_in_sandbox(code, language, files)
        return await self._execute_locally(code, language)

    async def _execute_in_sandbox(self, code: str, language: str, files: Optional[Dict[str, str]]) -> CodeResult:
        from nexusagent.security.e2b_sandbox import E2BSandbox, SandboxResult

        if not isinstance(self._sandbox, E2BSandbox):
            self._sandbox = E2BSandbox()

        report = await self._sandbox.execute_code(code, language=language, files=files, timeout=60)

        return CodeResult(
            code=code,
            stdout=report.stdout,
            stderr=report.stderr,
            exit_code=report.exit_code,
            success=report.result == SandboxResult.PASSED,
            error="; ".join(report.security_events) if report.security_events else "",
            execution_time_ms=report.duration_ms,
        )

    # 危险代码模式黑名单（阻止常见 RCE/信息泄露手段）
    _DANGEROUS_PATTERNS = [
        "__import__", "import os", "import subprocess", "import sys",
        "eval(", "exec(", "compile(", "open(",
        "subprocess", "os.system", "os.popen", "os.spawn",
        "shutil", "socket", "urllib", "requests",
    ]

    def _scan_code(self, code: str) -> Optional[str]:
        """静态扫描代码中的危险模式"""
        for pattern in self._DANGEROUS_PATTERNS:
            if pattern in code:
                return f"检测到危险模式: {pattern}"
        return None

    async def _execute_locally(self, code: str, language: str) -> CodeResult:
        """本地执行（降级，不推荐用于生产）

        安全准则:
            - 默认禁止本地执行，需设置 NEXUS_ALLOW_LOCAL_EXECUTION=1
            - 执行前进行静态危险代码扫描
            - 超时后强制 kill 子进程
        """
        import asyncio
        import subprocess
        import tempfile
        import time
        import os

        if not os.getenv("NEXUS_ALLOW_LOCAL_EXECUTION"):
            return CodeResult(
                code=code, success=False,
                error="本地执行已被禁用。设置 NEXUS_ALLOW_LOCAL_EXECUTION=1 以启用（仅限开发环境）。",
            )

        if language != "python":
            return CodeResult(code=code, success=False, error="本地模式仅支持 Python")

        danger = self._scan_code(code)
        if danger:
            return CodeResult(code=code, success=False, error=f"安全拦截: {danger}")

        start = time.time()
        path = ""
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                path = f.name

            proc = await asyncio.create_subprocess_exec(
                "python", path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            return CodeResult(
                code=code,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                exit_code=proc.returncode or 0,
                success=proc.returncode == 0,
                execution_time_ms=(time.time() - start) * 1000,
            )
        except asyncio.TimeoutError:
            if proc:
                proc.kill()
                # 等待僵尸进程回收
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
            return CodeResult(code=code, success=False, error="执行超时", execution_time_ms=(time.time() - start) * 1000)
        except Exception as e:
            return CodeResult(code=code, success=False, error=str(e))
        finally:
            if path:
                try:
                    os.unlink(path)
                except Exception as e:
                    logger.debug("临时文件清理失败: %s", e)

    def to_tool_spec(self) -> Dict[str, Any]:
        return {
            "name": "code_interpreter.execute",
            "description": "在沙箱中执行 Python 代码。支持数据分析、图表生成、文件处理。预装 pandas, matplotlib, numpy。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "要执行的 Python 代码"},
                    "language": {"type": "string", "enum": ["python"], "default": "python"},
                },
                "required": ["code"],
            },
        }
