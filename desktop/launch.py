"""
NexusAgent Desktop — 启动入口
参照: x-agent (PySide6 + QWebEngineView 架构)

用法:
    python -m nexusagent.desktop.launch
    # 或
    nexus-desktop
"""

from __future__ import annotations

import sys
import asyncio
import logging
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from nexusagent.main import NexusAgent
from nexusagent.config.settings import get_config, load_project_env
from nexusagent.desktop.main_window import NexusMainWindow


def main():
    """桌面客户端入口"""
    # 加载项目 .env
    project_root = Path(__file__).parent.parent.parent
    load_project_env(project_root)

    # Windows 高分屏适配
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("NexusAgent Desktop")
    app.setApplicationVersion("3.3.0")

    # 初始化 Agent
    config = get_config()

    async def init_agent():
        agent = NexusAgent(config)
        await agent.initialize()
        return agent

    loop = asyncio.new_event_loop()
    agent = loop.run_until_complete(init_agent())
    loop.close()

    # 创建主窗口
    window = NexusMainWindow(agent=agent, config=config)
    window.show()

    # 事件循环
    exit_code = app.exec()

    # 清理
    loop2 = asyncio.new_event_loop()
    loop2.run_until_complete(agent.shutdown())
    loop2.close()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
