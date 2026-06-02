"""
NexusAgent Desktop — 启动器
首选 Electron 方案；若 Node.js 不可用则回退到 PyQt6 备用方案。
"""

import sys
import os
import asyncio
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger("nexus.desktop")

PROJECT_ROOT = Path(__file__).parent.resolve()
# 确保 nexusagent 包的父目录在 PYTHONPATH 中，以便 Python 能正确导入 nexusagent 包
# REMOVED: sys.path.insert hack no longer needed after package structure fix

from nexusagent.config.settings import load_project_env
load_project_env(PROJECT_ROOT)


def _has_npm() -> bool:
    """检查系统是否安装了 npm / node"""
    for cmd in (["npm.cmd", "npm"] if sys.platform == "win32" else ["npm"]):
        try:
            subprocess.run([cmd, "--version"], capture_output=True, timeout=5, check=True)
            return True
        except Exception as e:
            logger.debug("npm检测命令 %s 失败: %s", cmd, e)
    return False


def _has_electron_deps() -> bool:
    """检查 node_modules 是否存在"""
    return (PROJECT_ROOT / "node_modules" / "electron").exists()


def _launch_electron() -> int:
    """启动 Electron 桌面客户端"""
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    # 如果没有 node_modules，尝试自动安装
    if not _has_electron_deps():
        print("[Desktop] 正在安装 Electron 依赖（首次运行）…")
        try:
            subprocess.run(
                [npm, "install"],
                cwd=PROJECT_ROOT,
                check=True,
                timeout=300,
            )
        except subprocess.CalledProcessError as e:
            print(f"[Desktop] npm install 失败: {e}")
            return -1
        except subprocess.TimeoutExpired:
            print("[Desktop] npm install 超时")
            return -1

    print("[Desktop] 启动 Electron 桌面客户端…")
    try:
        result = subprocess.run(
            [npm, "start"],
            cwd=PROJECT_ROOT,
            check=False,
        )
        return result.returncode
    except KeyboardInterrupt:
        return 0


def _launch_pyqt6_fallback() -> int:
    """回退到 PyQt6 桌面客户端（legacy）"""
    print("[Desktop] Node.js 不可用，回退到 PyQt6 方案…")
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
    except ImportError as e:
        print(f"[Desktop] PyQt6 未安装: {e}")
        print("[Desktop] 请执行: pip install PyQt6 PyQt6-WebEngine")
        return 1

    from nexusagent.main import NexusAgent
    from nexusagent.config.settings import get_config
    from nexusagent.desktop.main_window import NexusMainWindow

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("NexusAgent Desktop")
    app.setApplicationVersion("3.3.0")

    config = get_config()

    loop = asyncio.new_event_loop()
    async def init_agent():
        agent = NexusAgent(config)
        await agent.initialize()
        return agent
    agent = loop.run_until_complete(init_agent())
    loop.close()

    window = NexusMainWindow(agent=agent, config=config)
    window.show()

    exit_code = app.exec()

    loop2 = asyncio.new_event_loop()
    loop2.run_until_complete(agent.shutdown())
    loop2.close()

    return exit_code


def main() -> int:
    if _has_npm():
        rc = _launch_electron()
        if rc == 0:
            return 0
        print("[Desktop] Electron 启动失败，尝试回退…")
    return _launch_pyqt6_fallback()


if __name__ == "__main__":
    sys.exit(main())
