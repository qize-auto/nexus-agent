"""
NexusAgent Desktop — 后台工作线程
参照: x-agent/gui/worker.py
"""

from __future__ import annotations

import asyncio
import logging
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger("nexus.desktop.worker")


class AgentWorker(QThread):
    """后台 Agent 工作线程，不阻塞 UI"""

    messageEmitted = pyqtSignal(str, object)   # (type, payload)
    turnFinished = pyqtSignal(object)           # result
    errorOccurred = pyqtSignal(str)             # error message

    def __init__(self, agent, user_input: str, session_id: str = ""):
        super().__init__()
        self._agent = agent
        self._input = user_input
        self._session_id = session_id or f"desktop_session"

    def run(self) -> None:
        """在线程中运行异步 Agent"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def _process():
                self.messageEmitted.emit("thinking", {"status": "started"})
                result = await self._agent.process_message(
                    user_id="desktop_user",
                    message=self._input,
                    session_id=self._session_id,
                )
                return result

            result = loop.run_until_complete(_process())
            loop.close()
            self.turnFinished.emit(result)

        except Exception as e:
            logger.error("Agent worker error: %s", e, exc_info=True)
            self.errorOccurred.emit(str(e))
