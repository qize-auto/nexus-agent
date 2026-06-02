"""
NexusAgent CLI — 命令行交互模式
用法: python run_cli.py
"""

import sys, os, asyncio
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
# REMOVED: sys.path.insert hack no longer needed after package structure fix

from nexusagent.config.settings import load_project_env
load_project_env(PROJECT_ROOT)

from nexusagent.main import NexusAgent


async def main():
    agent = NexusAgent()
    await agent.initialize()

    print()
    print("=" * 50)
    print("  NexusAgent v3.3 CLI")
    print("  DeepSeek API connected")
    print("  输入消息，输入 exit 退出")
    print("=" * 50)
    print()

    sid = "cli"
    while True:
        try:
            msg = input(">>> ").strip()
            if msg.lower() in ("exit", "quit", "q"):
                break
            if not msg:
                continue
            print("...", end="\r")
            r = await agent.process_message("cli_user", msg, sid)
            print(f"\n{r}\n")
        except KeyboardInterrupt:
            print("\n")
            break

    await agent.shutdown()
    print("再见")


if __name__ == "__main__":
    asyncio.run(main())
