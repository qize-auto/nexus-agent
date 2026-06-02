"""
NexusAgent v4.0+ — MCP Server 暴露

设计参考:
- MCP Protocol: https://modelcontextprotocol.io
  "Model Context Protocol — connect AI assistants to systems"
- Mastra MCP bidirectional: https://mastra.ai/docs/mcp
  "Expose Mastra tools as MCP servers"

职责:
    将 ToolLayer 中注册的工具通过 MCP stdio 协议暴露，
    使 Cursor / Claude Desktop / Windsurf 等编辑器可直接调用 NexusAgent 工具。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nexus.tools.mcp_server")


class MCPServer:
    """
    MCP Server — 将 NexusAgent ToolLayer 暴露为标准 MCP Server

    Usage:
        server = MCPServer(tool_layer)
        await server.run()  # 阻塞运行 stdio server
    """

    def __init__(self, tool_layer: Any):
        self._tool_layer = tool_layer
        self._running = False

    async def run(self) -> None:
        """运行 stdio MCP Server"""
        try:
            from mcp.server import Server
            from mcp.server.stdio import stdio_server
            from mcp.types import Tool, TextContent
        except ImportError:
            logger.error("mcp 包未安装，无法启动 MCP Server")
            return

        app = Server("nexus-agent")

        @app.list_tools()
        async def list_tools() -> List[Tool]:
            tools = []
            specs = self._tool_layer.list_tools() if hasattr(self._tool_layer, "list_tools") else []
            for spec in specs:
                tools.append(Tool(
                    name=spec.name,
                    description=spec.description,
                    inputSchema=spec.input_schema,
                ))
            return tools

        @app.call_tool()
        async def call_tool(name: str, arguments: dict) -> List[TextContent]:
            try:
                result = await self._tool_layer.execute(name, arguments)
                return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
            except Exception as e:
                return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream)

    def get_tools_manifest(self) -> List[Dict[str, Any]]:
        """返回工具清单（用于手动集成）"""
        specs = self._tool_layer.list_tools() if hasattr(self._tool_layer, "list_tools") else []
        manifest = []
        for s in specs:
            if isinstance(s, dict):
                manifest.append({
                    "name": s.get("name", ""),
                    "description": s.get("description", ""),
                    "inputSchema": s.get("input_schema", {}),
                })
            else:
                manifest.append({
                    "name": getattr(s, "name", ""),
                    "description": getattr(s, "description", ""),
                    "inputSchema": getattr(s, "input_schema", {}),
                })
        return manifest
