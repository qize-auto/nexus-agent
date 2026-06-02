"""
NexusAgent v3.3 — 多渠道适配器实现
补全: 设计稿第3章多渠道接入 (Telegram / Discord / Feishu)

外部调研依据:
- python-telegram-bot: 28K+ stars, v20+ fully asyncio native
  https://python-telegram-bot.org/
- discord.py: v2+ 活跃维护, 最大社区
  https://discordpy.readthedocs.io/
- Feishu/Lark: WebHook 接入最轻量，无需完整 SDK
  https://open.feishu.cn/document/ukTMukTMukTM/ucTM5YjL3ETO24yNxkjN

实现策略:
- 所有适配器均继承 ChannelAdapter
- 可选依赖：未安装库时优雅降级（import try/except）
- Telegram: python-telegram-bot ApplicationBuilder 长轮询
- Discord: discord.py Client + on_message 事件
- Feishu: aiohttp WebHook 推送 + 签名校验
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, List, Optional

from nexusagent.interface.adapter import (
    ChannelAdapter, ChannelType, MessageEnvelope, MessageType,
    SecurityLevel, UserIdentity,
)

logger = logging.getLogger("nexus.interface.multi_channel")


# ═══════════════════════════════════════════════════════════════
# Telegram Adapter
# ═══════════════════════════════════════════════════════════════

class TelegramAdapter(ChannelAdapter):
    """Telegram Bot 适配器 — 基于 python-telegram-bot v20+"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(ChannelType.TELEGRAM, SecurityLevel.HIGH, config)
        self._token = config.get("token", "")
        self._app: Optional[Any] = None
        self._pending: asyncio.Queue = asyncio.Queue()
        self._ptb_available = False

    async def start(self) -> None:
        try:
            from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
            self._ptb_available = True
        except ImportError:
            logger.error("python-telegram-bot 未安装: pip install python-telegram-bot")
            self._running = False
            return

        if not self._token:
            logger.error("Telegram token 未配置")
            self._running = False
            return

        self._app = ApplicationBuilder().token(self._token).build()
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message))
        self._app.add_handler(CommandHandler("start", self._on_start))

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        self._running = True
        logger.info("TelegramAdapter 已启动")

    async def stop(self) -> None:
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        self._running = False
        logger.info("TelegramAdapter 已停止")

    async def send(self, envelope: MessageEnvelope) -> bool:
        if not self._app or not envelope.recipient_id:
            return False
        try:
            await self._app.bot.send_message(
                chat_id=envelope.recipient_id,
                text=envelope.content[:4000],
            )
            return True
        except Exception as e:
            logger.error("Telegram 发送失败: %s", e)
            return False

    def parse_inbound(self, raw_payload: Any) -> Optional[MessageEnvelope]:
        if isinstance(raw_payload, dict):
            return MessageEnvelope(
                channel_type=ChannelType.TELEGRAM,
                content=raw_payload.get("text", ""),
                session_id=str(raw_payload.get("chat_id", "")),
                sender=UserIdentity(
                    user_id=str(raw_payload.get("user_id", "")),
                    channel_user_id=str(raw_payload.get("user_id", "")),
                    channel_type=ChannelType.TELEGRAM,
                    display_name=raw_payload.get("username", ""),
                ),
            )
        return None

    async def _on_message(self, update: Any, context: Any) -> None:
        msg = update.effective_message
        if not msg or not msg.text:
            return
        envelope = MessageEnvelope(
            channel_type=ChannelType.TELEGRAM,
            content=msg.text,
            session_id=str(msg.chat_id),
            sender=UserIdentity(
                user_id=str(msg.from_user.id),
                channel_user_id=str(msg.from_user.id),
                channel_type=ChannelType.TELEGRAM,
                display_name=msg.from_user.username or msg.from_user.full_name,
            ),
            recipient_id=str(msg.chat_id),
        )
        response = await self._dispatch(envelope)
        if response and response.content:
            await msg.reply_text(response.content[:4000])

    async def _on_start(self, update: Any, context: Any) -> None:
        await update.message.reply_text("NexusAgent 已连接。发送消息即可开始对话。")


# ═══════════════════════════════════════════════════════════════
# Discord Adapter
# ═══════════════════════════════════════════════════════════════

class DiscordAdapter(ChannelAdapter):
    """Discord Bot 适配器 — 基于 discord.py v2+"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(ChannelType.DISCORD, SecurityLevel.LOW, config)
        self._token = config.get("token", "")
        self._client: Optional[Any] = None
        self._discord_available = False

    async def start(self) -> None:
        try:
            import discord
            self._discord_available = True
        except ImportError:
            logger.error("discord.py 未安装: pip install discord.py")
            self._running = False
            return

        if not self._token:
            logger.error("Discord token 未配置")
            self._running = False
            return

        import discord

        class _DiscordClient(discord.Client):
            def __init__(inner_self, adapter: "DiscordAdapter", **kwargs):
                super().__init__(**kwargs)
                inner_self._adapter = adapter

            async def on_ready(inner_self):
                logger.info("DiscordAdapter 已登录: %s", inner_self.user)

            async def on_message(inner_self, message: discord.Message):
                if message.author == inner_self.user:
                    return
                envelope = MessageEnvelope(
                    channel_type=ChannelType.DISCORD,
                    content=message.content,
                    session_id=str(message.channel.id),
                    sender=UserIdentity(
                        user_id=str(message.author.id),
                        channel_user_id=str(message.author.id),
                        channel_type=ChannelType.DISCORD,
                        display_name=message.author.display_name,
                    ),
                    recipient_id=str(message.channel.id),
                )
                response = await inner_self._adapter._dispatch(envelope)
                if response and response.content:
                    await message.channel.send(response.content[:2000])

        intents = discord.Intents.default()
        intents.message_content = True
        self._client = _DiscordClient(self, intents=intents)

        self._running = True
        # discord.Client.start 是阻塞的，需要在后台任务中运行
        asyncio.create_task(self._client.start(self._token))
        logger.info("DiscordAdapter 已启动")

    async def stop(self) -> None:
        if self._client:
            await self._client.close()
        self._running = False
        logger.info("DiscordAdapter 已停止")

    async def send(self, envelope: MessageEnvelope) -> bool:
        if not self._client or not envelope.recipient_id:
            return False
        try:
            channel = await self._client.fetch_channel(int(envelope.recipient_id))
            if channel:
                await channel.send(envelope.content[:2000])
                return True
        except Exception as e:
            logger.error("Discord 发送失败: %s", e)
        return False

    def parse_inbound(self, raw_payload: Any) -> Optional[MessageEnvelope]:
        if isinstance(raw_payload, dict):
            return MessageEnvelope(
                channel_type=ChannelType.DISCORD,
                content=raw_payload.get("content", ""),
                session_id=str(raw_payload.get("channel_id", "")),
                sender=UserIdentity(
                    user_id=str(raw_payload.get("author_id", "")),
                    channel_user_id=str(raw_payload.get("author_id", "")),
                    channel_type=ChannelType.DISCORD,
                    display_name=raw_payload.get("username", ""),
                ),
            )
        return None


# ═══════════════════════════════════════════════════════════════
# Feishu/Lark Adapter
# ═══════════════════════════════════════════════════════════════

class FeishuAdapter(ChannelAdapter):
    """飞书/ Lark WebHook 适配器 — 基于 aiohttp 轻量接入"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(ChannelType.FEISHU, SecurityLevel.MEDIUM, config)
        self._webhook_url = config.get("webhook_url", "")
        self._secret = config.get("secret", "")
        self._app_id = config.get("app_id", "")
        self._app_secret = config.get("app_secret", "")
        self._session: Optional[Any] = None

    def _gen_sign(self, timestamp: str) -> str:
        """飞书自定义机器人签名校验"""
        if not self._secret:
            return ""
        string_to_sign = f"{timestamp}\n{self._secret}"
        hmac_code = hmac.new(
            string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
        ).digest()
        return base64.b64encode(hmac_code).decode("utf-8")

    async def start(self) -> None:
        try:
            import aiohttp
            self._session = aiohttp.ClientSession()
        except ImportError:
            logger.error("aiohttp 未安装")
            self._running = False
            return
        self._running = True
        logger.info("FeishuAdapter 已启动 (webhook=%s)", bool(self._webhook_url))

    async def stop(self) -> None:
        if self._session:
            await self._session.close()
        self._running = False
        logger.info("FeishuAdapter 已停止")

    async def send(self, envelope: MessageEnvelope) -> bool:
        if not self._session or not self._webhook_url:
            return False
        timestamp = str(int(time.time()))
        payload = {
            "timestamp": timestamp,
            "sign": self._gen_sign(timestamp),
            "msg_type": "text",
            "content": {"text": envelope.content[:4000]},
        }
        try:
            async with self._session.post(self._webhook_url, json=payload) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error("Feishu 发送失败: %s", e)
            return False

    def parse_inbound(self, raw_payload: Any) -> Optional[MessageEnvelope]:
        if isinstance(raw_payload, dict):
            event = raw_payload.get("event", {})
            message = event.get("message", {})
            sender = event.get("sender", {})
            if message.get("message_type") == "text":
                content = json.loads(message.get("content", "{}"))
                return MessageEnvelope(
                    channel_type=ChannelType.FEISHU,
                    content=content.get("text", ""),
                    session_id=str(message.get("chat_id", "")),
                    sender=UserIdentity(
                        user_id=str(sender.get("sender_id", {}).get("user_id", "")),
                        channel_user_id=str(sender.get("sender_id", {}).get("user_id", "")),
                        channel_type=ChannelType.FEISHU,
                        display_name=sender.get("sender_id", {}).get("union_id", ""),
                    ),
                )
        return None
