"""
NexusAgent v4.0+ — 诊断工具 (nexus doctor)

设计参考:
- Hermes Agent `hermes doctor`: 覆盖 50+ 检查项，排查效率提升 10x
- CowAgent Web console 诊断面板

职责:
    检查环境、配置、依赖、API key、目录权限等，输出诊断报告

Usage:
    python -m nexusagent.cli.doctor
"""

from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class CheckResult:
    """单个检查项结果"""
    name: str
    status: str  # PASS | WARN | FAIL | SKIP
    message: str = ""
    suggestion: str = ""


class NexusDoctor:
    """
    NexusAgent 诊断器

    检查类别:
        1. 环境: Python 版本、操作系统
        2. 依赖: 核心包安装状态
        3. 配置: .env 文件、API key
        4. 目录: 项目根目录、数据目录权限
        5. 网络: API 后端连通性
        6. 安全: 主密钥配置
    """

    _REQUIRED_PACKAGES = [
        "aiohttp",
        "pydantic",
        "cryptography",
        "yaml",
    ]

    _OPTIONAL_PACKAGES = [
        "sqlite_vec",
        "playwright",
        "duckduckgo_search",
    ]

    def __init__(self):
        self._results: List[CheckResult] = []

    def run_all(self) -> List[CheckResult]:
        """运行所有检查"""
        self._results = []
        self._check_environment()
        self._check_dependencies()
        self._check_configuration()
        self._check_directories()
        self._check_network()
        self._check_security()
        return self._results

    def _add(self, name: str, status: str, message: str = "", suggestion: str = "") -> None:
        self._results.append(CheckResult(name, status, message, suggestion))

    def _check_environment(self) -> None:
        """检查运行环境"""
        # Python 版本
        py_version = sys.version_info
        if py_version >= (3, 10):
            self._add("Python 版本", "PASS", f"Python {py_version.major}.{py_version.minor}.{py_version.micro}")
        else:
            self._add("Python 版本", "FAIL", f"Python {py_version.major}.{py_version.minor}", "需要 Python 3.10+")

        # 操作系统
        import platform
        os_name = platform.system()
        self._add("操作系统", "PASS", f"{os_name} {platform.release()}")

        # 事件循环策略
        if sys.platform == "win32":
            self._add("Windows 事件循环", "WARN", "Windows 默认使用 SelectorEventLoop", "建议使用 ProactorEventLoop: asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())")
        else:
            self._add("事件循环", "PASS", "使用默认事件循环策略")

    def _check_dependencies(self) -> None:
        """检查依赖包"""
        for pkg in self._REQUIRED_PACKAGES:
            try:
                importlib.import_module(pkg)
                self._add(f"依赖: {pkg}", "PASS")
            except ImportError:
                self._add(f"依赖: {pkg}", "FAIL", f"{pkg} 未安装", f"pip install {pkg}")

        for pkg in self._OPTIONAL_PACKAGES:
            try:
                importlib.import_module(pkg)
                self._add(f"可选依赖: {pkg}", "PASS")
            except ImportError:
                self._add(f"可选依赖: {pkg}", "WARN", f"{pkg} 未安装", f"pip install {pkg} (如需此功能)")

    def _check_configuration(self) -> None:
        """检查配置"""
        # .env 文件
        env_file = Path(".env")
        if env_file.exists():
            self._add(".env 文件", "PASS", f"找到 {env_file.absolute()}")
        else:
            self._add(".env 文件", "WARN", "未找到 .env 文件", "复制 .env.example 到 .env 并填写配置")

        # API Key
        for key_name in ["DEEPSEEK_API_KEY", "MOONSHOT_API_KEY", "KIMI_API_KEY", "OPENAI_API_KEY"]:
            value = os.getenv(key_name, "")
            if value:
                masked = value[:4] + "****" + value[-4:] if len(value) > 8 else "****"
                self._add(f"API Key: {key_name}", "PASS", f"已配置 ({masked})")
            else:
                self._add(f"API Key: {key_name}", "WARN", "未配置", f"在 .env 中设置 {key_name}")

    def _check_directories(self) -> None:
        """检查目录权限"""
        from nexusagent.config.settings import PROJECT_ROOT
        if PROJECT_ROOT.exists():
            if os.access(PROJECT_ROOT, os.W_OK):
                self._add("项目目录", "PASS", f"{PROJECT_ROOT} 可写")
            else:
                self._add("项目目录", "FAIL", f"{PROJECT_ROOT} 不可写", "检查目录权限")
        else:
            self._add("项目目录", "WARN", f"{PROJECT_ROOT} 不存在", "运行应用时会自动创建")

    def _check_network(self) -> None:
        """检查网络连通性"""
        import asyncio

        async def _check():
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession() as session:
                # DeepSeek
                try:
                    async with session.get("https://api.deepseek.com/v1", timeout=timeout):
                        self._add("网络: DeepSeek API", "PASS", "可连通")
                except Exception as e:
                    self._add("网络: DeepSeek API", "WARN", f"无法连通: {e}", "检查网络连接或代理设置")
                # Moonshot / Kimi
                try:
                    async with session.get("https://api.moonshot.cn/v1", timeout=timeout):
                        self._add("网络: Moonshot API", "PASS", "可连通")
                except Exception as e:
                    self._add("网络: Moonshot API", "WARN", f"无法连通: {e}", "检查网络连接或代理设置")

        try:
            asyncio.run(_check())
        except Exception as e:
            self._add("网络检查", "SKIP", f"检查失败: {e}")

    def _check_security(self) -> None:
        """检查安全配置"""
        master_key = os.getenv("NEXUS_MASTER_KEY", "")
        if master_key:
            try:
                import base64
                decoded = base64.b64decode(master_key)
                if len(decoded) >= 32:
                    self._add("安全: NEXUS_MASTER_KEY", "PASS", f"已配置 ({len(decoded)} 字节)")
                else:
                    self._add("安全: NEXUS_MASTER_KEY", "FAIL", f"密钥长度不足: {len(decoded)} 字节", "生成 32+ 字节密钥")
            except Exception:
                self._add("安全: NEXUS_MASTER_KEY", "FAIL", "格式错误", "应为 base64 编码的 32+ 字节密钥")
        else:
            self._add("安全: NEXUS_MASTER_KEY", "FAIL", "未配置", "设置 NEXUS_MASTER_KEY 环境变量")

    def report(self) -> Dict[str, Any]:
        """生成诊断报告"""
        if not self._results:
            self.run_all()

        total = len(self._results)
        passed = sum(1 for r in self._results if r.status == "PASS")
        warnings = sum(1 for r in self._results if r.status == "WARN")
        failed = sum(1 for r in self._results if r.status == "FAIL")
        skipped = sum(1 for r in self._results if r.status == "SKIP")

        return {
            "summary": {
                "total": total,
                "pass": passed,
                "warn": warnings,
                "fail": failed,
                "skip": skipped,
                "healthy": failed == 0,
            },
            "checks": [
                {"name": r.name, "status": r.status, "message": r.message, "suggestion": r.suggestion}
                for r in self._results
            ],
        }

    def print_report(self) -> None:
        """打印诊断报告到控制台"""
        report = self.report()
        summary = report["summary"]

        print("=" * 60)
        print("  NexusAgent 诊断报告")
        print("=" * 60)
        print(f"  总计: {summary['total']} 项")
        print(f"  ✅ 通过: {summary['pass']}")
        print(f"  ⚠️  警告: {summary['warn']}")
        print(f"  ❌ 失败: {summary['fail']}")
        print(f"  ⏭️  跳过: {summary['skip']}")
        print("-" * 60)

        for check in report["checks"]:
            icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌", "SKIP": "⏭️"}.get(check["status"], "?")
            print(f"  {icon} [{check['status']}] {check['name']}")
            if check["message"]:
                print(f"      {check['message']}")
            if check["suggestion"]:
                print(f"      💡 {check['suggestion']}")

        print("=" * 60)
        if summary["healthy"]:
            print("  🎉 环境健康，可以开始使用 NexusAgent!")
        else:
            print(f"  ⚠️  发现 {summary['fail']} 个问题，请根据建议修复后重试")
        print("=" * 60)


def main():
    """CLI 入口"""
    doctor = NexusDoctor()
    doctor.print_report()
    report = doctor.report()
    sys.exit(0 if report["summary"]["healthy"] else 1)


if __name__ == "__main__":
    main()
