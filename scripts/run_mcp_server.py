#!/usr/bin/env python3
"""
NexusAgent MCP Server 启动脚本

Usage:
    python scripts/run_mcp_server.py

将 ToolRegistry 中所有已注册工具通过 MCP 协议暴露，
支持 Cursor / Claude Desktop / Windsurf 等编辑器直接调用。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 确保项目根目录在 PYTHONPATH
project_root = Path(__file__).parent.parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nexusagent.tools.registry import get_registry
from nexusagent.tools.mcp_server import MCPServer


async def main() -> int:
    registry = get_registry()
    registry.discover_builtin_tools()

    tools = registry.list_tools()
    print(f"🔌 NexusAgent MCP Server")
    print(f"   项目根目录: {project_root}")
    print(f"   暴露工具数: {len(tools)}")
    for t in tools[:5]:
        print(f"     • {t['name']}: {t['description'][:60]}")
    if len(tools) > 5:
        print(f"     ... 等共 {len(tools)} 个工具")
    print()

    server = MCPServer(registry)
    try:
        await server.run()
    except KeyboardInterrupt:
        print("\n👋 MCP Server 已停止")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
