"""
NexusAgent Web Server — 基于 WebAdapter 的统一接入层
启动后打开 http://localhost:8080
"""

import sys
import os
import asyncio
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
# REMOVED: sys.path.insert hack no longer needed after package structure fix

from nexusagent.config.settings import load_project_env
load_project_env(PROJECT_ROOT)

from nexusagent.main import NexusAgent
from nexusagent.interface.adapter import (
    WebAdapter, MessageEnvelope,
)

# 全局 Agent 实例
_agent: NexusAgent | None = None


async def _handle_message(envelope: MessageEnvelope) -> MessageEnvelope | None:
    """WebAdapter 消息回调 — 委托给 Agent 处理"""
    global _agent
    if _agent is None:
        return None
    response = await _agent.process_message(
        user_id="web_user",
        message=envelope.content,
        session_id=envelope.session_id,
    )
    return MessageEnvelope(
        channel_type=envelope.channel_type,
        content=response,
        security_level=envelope.security_level,
        session_id=envelope.session_id,
    )


async def init_agent():
    global _agent
    _agent = NexusAgent()
    await _agent.initialize()
    print("Agent initialized")


async def main():
    await init_agent()

    adapter = WebAdapter(
        config={
            "host": "127.0.0.1",
            "port": 8080,
            "static_path": str(PROJECT_ROOT / "web_ui"),
        },
        llm=_agent.current_llm if _agent else None,
    )
    adapter.register_message_callback(_handle_message)
    await adapter.start()

    print()
    print("=" * 50)
    print("  NexusAgent Web Server")
    print("  http://localhost:8080")
    print("=" * 50)

    try:
        while adapter.is_running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await adapter.stop()
        if _agent:
            await _agent.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
