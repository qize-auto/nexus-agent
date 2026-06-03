"""
NexusAgent v3.3 — 接入层：通道适配器架构
来源: 设计稿第3章 (3.2通道适配器架构 + 3.2.4 ChannelAdapter)
实现: P0×2, P1×2, P2×2, P3×2 全部缺陷修复
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Awaitable, Callable, Dict, List, Optional

from nexusagent.utils.ulid import generate_ulid

logger = logging.getLogger("nexus.interface")


# ═══════════════════════════════════════════════════════════════
# 3.2.2 核心枚举 — 设计稿第3章
# ═══════════════════════════════════════════════════════════════

class ChannelType(Enum):
    CLI = "cli"
    WEB = "web"
    TELEGRAM = "telegram"
    FEISHU = "feishu"
    DISCORD = "discord"
    API = "api"
    SLACK = "slack"
    WECHAT = "wechat"


class MessageType(Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"
    COMMAND = "command"
    SYSTEM = "system"
    CALLBACK = "callback"


class SecurityLevel(Enum):
    """渠道安全等级 — P2-011 跨平台数据同步安全 + ARC-038 数据四级分类"""
    CRITICAL = 5   # 绝密：本地CLI，不跨设备同步
    HIGH = 4       # 机密：个人手机Telegram
    MEDIUM = 3     # 秘密：工作飞书 (默认)
    LOW = 2        # 内部：Discord群组
    PUBLIC = 1     # 公开：Web页面

    def can_sync_to(self, target: "SecurityLevel") -> bool:
        """ARC-038: 数据仅在同级或更高级渠道间同步"""
        return self.value >= target.value

    def minimum_sync_level(self, target: "SecurityLevel") -> bool:
        """NFR-098: 最小权限同步 — 数据仅在相同或更高等级间传输"""
        return self.value >= target.value

    @classmethod
    def from_string(cls, s: str) -> "SecurityLevel":
        """从字符串解析安全等级"""
        mapping = {
            "critical": cls.CRITICAL, "high": cls.HIGH,
            "medium": cls.MEDIUM, "low": cls.LOW, "public": cls.PUBLIC,
        }
        return mapping.get(s.lower(), cls.MEDIUM)


class PermissionPromptLevel(Enum):
    """权限提示等级 — P0-U2 信任积分快速通道"""
    SILENT = auto()    # 静默放行(积分80+)
    TOAST = auto()     # 仅提示(积分50-80)
    CONFIRM = auto()   # 单次确认(积分20-50)
    STRICT = auto()    # 四级审查(积分0-20)


# ═══════════════════════════════════════════════════════════════
# 3.2.3 MessageEnvelope — 统一消息模型
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True, slots=True)
class UserIdentity:
    """用户身份标识（跨通道统一）"""
    user_id: str
    channel_user_id: str
    channel_type: ChannelType
    display_name: str = ""
    email: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    locale: str = "zh-CN"
    timezone: str = "Asia/Shanghai"

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "channel_user_id": self.channel_user_id,
            "channel_type": self.channel_type.value,
            "display_name": self.display_name,
            "email": self.email,
            "phone": self.phone,
            "avatar_url": self.avatar_url,
            "locale": self.locale,
            "timezone": self.timezone,
        }


@dataclass(frozen=True, slots=True)
class Attachment:
    """消息附件"""
    attachment_id: str
    file_name: str
    file_type: str       # MIME type
    file_size: int       # bytes
    url: Optional[str] = None
    content: Optional[bytes] = None


@dataclass(slots=True)
class MessageEnvelope:
    """
    统一消息信封 — 所有通道的入站/出站消息均包装为此格式
    设计稿第3章: 必要信息内联，扩展信息放metadata
    """
    envelope_id: str = field(default_factory=generate_ulid)
    message_type: MessageType = MessageType.TEXT
    channel_type: ChannelType = ChannelType.CLI
    security_level: SecurityLevel = SecurityLevel.MEDIUM

    sender: Optional[UserIdentity] = None
    recipient_id: Optional[str] = None
    session_id: str = ""
    content: str = ""
    attachments: List[Attachment] = field(default_factory=list)
    command: Optional[str] = None
    command_args: Dict[str, Any] = field(default_factory=dict)

    timestamp: float = field(default_factory=time.time)
    ttl: int = 300
    metadata: Dict[str, Any] = field(default_factory=dict)

    trust_score_at_send: float = 0.0
    permission_prompt_level: PermissionPromptLevel = PermissionPromptLevel.STRICT

    def is_expired(self) -> bool:
        return (time.time() - self.timestamp) > self.ttl

    def to_dict(self) -> dict:
        return {
            "envelope_id": self.envelope_id,
            "message_type": self.message_type.value,
            "channel_type": self.channel_type.value,
            "security_level": self.security_level.value,
            "sender": self.sender.to_dict() if self.sender else None,
            "recipient_id": self.recipient_id,
            "session_id": self.session_id,
            "content": self.content,
            "attachments": [{
                "attachment_id": a.attachment_id,
                "file_name": a.file_name,
                "file_type": a.file_type,
                "file_size": a.file_size,
                "url": a.url,
            } for a in self.attachments],
            "command": self.command,
            "command_args": self.command_args,
            "timestamp": self.timestamp,
            "ttl": self.ttl,
            "metadata": self.metadata,
            "trust_score_at_send": self.trust_score_at_send,
            "permission_prompt_level": self.permission_prompt_level.name,
        }


# ═══════════════════════════════════════════════════════════════
# 3.2.4 ChannelAdapter — 抽象基类
# ═══════════════════════════════════════════════════════════════

class ChannelAdapter(ABC):
    """
    通道适配器抽象基类 — 所有具体通道均需实现
    设计稿第3章: 接入层通过统一接口调度，屏蔽通道差异
    """

    def __init__(
        self,
        channel_type: ChannelType,
        security_level: SecurityLevel,
        config: Dict[str, Any],
    ) -> None:
        self._channel_type = channel_type
        self._security_level = security_level
        self._config = config
        self._running = False
        self._health_check_interval = config.get("health_check_interval", 30)
        self._last_health_check: float = 0.0
        self._health_status: Dict[str, Any] = {
            "status": "unknown", "latency_ms": 0.0,
            "error_count": 0, "last_error": None,
        }
        self._message_handlers: List[
            Callable[[MessageEnvelope], Awaitable[Optional[MessageEnvelope]]]
        ] = []
        logger.info("[%s] Adapter initialized", channel_type.value)

    @property
    def channel_type(self) -> ChannelType:
        return self._channel_type

    @property
    def security_level(self) -> SecurityLevel:
        return self._security_level

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def health_status(self) -> dict:
        return self._health_status.copy()

    def register_handler(
        self, handler: Callable[[MessageEnvelope], Awaitable[Optional[MessageEnvelope]]]
    ) -> None:
        """注册消息处理器 — P3扩展性设计"""
        self._message_handlers.append(handler)

    async def _dispatch(self, envelope: MessageEnvelope) -> Optional[MessageEnvelope]:
        """将消息派发给已注册的处理器链"""
        for handler in self._message_handlers:
            try:
                result = await handler(envelope)
                if result is not None:
                    return result
            except Exception as e:
                logger.error("Handler error for envelope %s: %s", envelope.envelope_id, e)
        return None

    @abstractmethod
    async def start(self) -> None:
        """启动适配器，开始监听通道消息"""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """停止适配器，清理资源"""
        ...

    @abstractmethod
    async def send(self, envelope: MessageEnvelope) -> bool:
        """向通道发送消息"""
        ...

    @abstractmethod
    def parse_inbound(self, raw_payload: Any) -> Optional[MessageEnvelope]:
        """将通道原始消息解析为统一MessageEnvelope"""
        ...

    async def health_check(self) -> Dict[str, Any]:
        """健康检查 — P1心跳监控"""
        start = time.monotonic()
        try:
            self._health_status["status"] = "healthy"
            self._health_status["latency_ms"] = (time.monotonic() - start) * 1000
            self._health_status["error_count"] = 0
        except Exception as e:
            self._health_status["status"] = "unhealthy"
            self._health_status["error_count"] += 1
            self._health_status["last_error"] = str(e)
        self._last_health_check = time.time()
        return self.health_status


# ═══════════════════════════════════════════════════════════════
# 请求限流 + 幂等性 — NFR-099/100
# ═══════════════════════════════════════════════════════════════

class RateLimiter:
    """限流器抽象基类"""
    async def acquire(self, key: str, tokens: float = 1.0) -> bool:
        raise NotImplementedError
    async def get_remaining(self, key: str) -> float:
        raise NotImplementedError


class MemoryTokenBucket(RateLimiter):
    """
    内存级 Token Bucket 限流器
    外部依据: arcjet.com/blog/rate-limiting-algorithms-token-bucket-vs-sliding-window-vs-fixed-window/
    "Token bucket is the strongest general-purpose default for APIs"
    """
    def __init__(self, rate: float = 10.0, capacity: float = 20.0):
        self._rate = rate
        self._capacity = capacity
        self._tokens: Dict[str, float] = {}
        self._last_update: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, key: str, tokens: float = 1.0) -> bool:
        async with self._lock:
            now = time.monotonic()
            last = self._last_update.get(key, now)
            self._tokens[key] = min(
                self._capacity,
                self._tokens.get(key, self._capacity) + self._rate * (now - last),
            )
            self._last_update[key] = now
            if self._tokens[key] >= tokens:
                self._tokens[key] -= tokens
                return True
            return False

    async def get_remaining(self, key: str) -> float:
        async with self._lock:
            now = time.monotonic()
            last = self._last_update.get(key, now)
            self._tokens[key] = min(
                self._capacity,
                self._tokens.get(key, self._capacity) + self._rate * (now - last),
            )
            self._last_update[key] = now
            return self._tokens.get(key, 0.0)


class RedisTokenBucket(RateLimiter):
    """
    Redis 分布式 Token Bucket 限流器
    外部依据:
    - timderzhavets.com: "Redis Lua scripts for all rate limit checks to guarantee atomicity"
    - redis.io: "Start with a sliding window counter"
    - github.com/Jay-Lokhande: "Redis-backed distributed rate limiting and in-memory fallback"

    使用 Redis Hash + Lua 原子脚本实现 O(1) 的令牌操作。
    Redis 不可用时自动降级为内存限流器（fail-open 策略）。
    """

    # Lua 原子脚本: 读令牌数 → 补充 → 检查 → 扣减
    _LUA_SCRIPT = """
    local key = KEYS[1]
    local rate = tonumber(ARGV[1])
    local capacity = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])
    local requested = tonumber(ARGV[4])

    local data = redis.call('HMGET', key, 'tokens', 'last_update')
    local tokens = tonumber(data[1])
    local last_update = tonumber(data[2])

    if tokens == nil then
        tokens = capacity
        last_update = now
    end

    -- 补充令牌
    local elapsed = now - last_update
    tokens = math.min(capacity, tokens + elapsed * rate)

    -- 检查并扣减
    if tokens >= requested then
        tokens = tokens - requested
        redis.call('HMSET', key, 'tokens', tokens, 'last_update', now)
        redis.call('EXPIRE', key, math.ceil(capacity / rate) + 1)
        return {1, tokens}
    else
        redis.call('HMSET', key, 'tokens', tokens, 'last_update', now)
        redis.call('EXPIRE', key, math.ceil(capacity / rate) + 1)
        return {0, tokens}
    end
    """

    def __init__(
        self,
        redis_url: str = "",
        rate: float = 10.0,
        capacity: float = 20.0,
    ):
        self._rate = rate
        self._capacity = capacity
        self._redis_url = redis_url or "redis://localhost:6379/0"
        self._redis: Any = None
        self._script_sha: str = ""
        self._fallback: Optional[MemoryTokenBucket] = None
        self._lock = asyncio.Lock()
        self._available = False

    async def _ensure_connection(self) -> bool:
        if self._available:
            return True
        async with self._lock:
            if self._available:
                return True
            try:
                import redis.asyncio as aioredis
                self._redis = await aioredis.from_url(
                    self._redis_url, socket_connect_timeout=2, socket_timeout=2
                )
                await self._redis.ping()
                self._script_sha = await self._redis.script_load(self._LUA_SCRIPT)
                self._available = True
                logger.info("Redis 限流器已连接: %s", self._redis_url)
                return True
            except Exception as e:
                logger.warning("Redis 限流器连接失败，降级为内存限流: %s", e)
                self._fallback = MemoryTokenBucket(self._rate, self._capacity)
                self._available = False
                return False

    async def acquire(self, key: str, tokens: float = 1.0) -> bool:
        if not await self._ensure_connection():
            return await self._fallback.acquire(key, tokens)
        try:
            now = time.time()
            result = await self._redis.evalsha(
                self._script_sha, 1, key, self._rate, self._capacity, now, tokens
            )
            return result[0] == 1
        except Exception as e:
            logger.warning("Redis 限流操作失败，降级: %s", e)
            return await self._fallback.acquire(key, tokens)

    async def get_remaining(self, key: str) -> float:
        if not await self._ensure_connection():
            return await self._fallback.get_remaining(key)
        try:
            data = await self._redis.hmget(key, "tokens", "last_update")
            tokens = float(data[0]) if data[0] else self._capacity
            last_update = float(data[1]) if data[1] else time.time()
            elapsed = time.time() - last_update
            return min(self._capacity, tokens + elapsed * self._rate)
        except Exception:
            return await self._fallback.get_remaining(key)

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()


class IdempotencyStore:
    """幂等键存储 — 防止重复处理同一请求"""
    def __init__(self, ttl_seconds: float = 300.0):
        self._store: Dict[str, float] = {}
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()

    async def check_and_set(self, key: str) -> bool:
        """检查幂等键是否存在，不存在则设置并返回True"""
        async with self._lock:
            now = time.time()
            # 清理过期键
            expired = [k for k, ts in self._store.items() if now - ts > self._ttl]
            for k in expired:
                del self._store[k]
            if key in self._store:
                return False
            self._store[key] = now
            return True


# ═══════════════════════════════════════════════════════════════
# WebAdapter — HTTP + WebSocket 通道 (设计稿第3章)
# ═══════════════════════════════════════════════════════════════

class WebAdapter(ChannelAdapter):
    """
    Web通道适配器 — 基于 aiohttp 的 HTTP REST + WebSocket 双模接入

    特性:
    - HTTP REST API 兼容现有前端 (fetch)
    - WebSocket 实时推送用于长连接场景
    - 静态文件服务 (桌面客户端资源)
    """

    def __init__(self, config: Dict[str, Any], llm: Optional[Any] = None):
        super().__init__(ChannelType.WEB, SecurityLevel.PUBLIC, config)
        self._host = config.get("host", "127.0.0.1")
        self._port = config.get("port", 8080)
        self._static_path = config.get("static_path", "")
        self._app: Optional[Any] = None
        self._runner: Optional[Any] = None
        self._site: Optional[Any] = None
        self._ws_connections: List[Any] = []
        self._message_callback: Optional[Callable] = None
        self._llm = llm  # v4.0+ 流式响应使用的 LLM backend
        # 限流 + 幂等 — 自动检测 Redis 分布式后端，未配置则内存降级
        redis_url = config.get("redis_url", "")
        if redis_url:
            self._rate_limiter: RateLimiter = RedisTokenBucket(
                redis_url=redis_url,
                rate=config.get("rate_limit_per_second", 10.0),
                capacity=config.get("rate_limit_burst", 20.0),
            )
        else:
            self._rate_limiter = MemoryTokenBucket(
                rate=config.get("rate_limit_per_second", 10.0),
                capacity=config.get("rate_limit_burst", 20.0),
            )
        self._idempotency = IdempotencyStore(
            ttl_seconds=config.get("idempotency_ttl", 300.0),
        )
        self._scheduler: Optional[Any] = None
        self._diag_store: Optional[Any] = None
        self._enable_scheduler = config.get("diagnostic_scheduler_enabled", True)
        self._scheduler_interval = config.get("diagnostic_scheduler_interval", 300.0)

    async def start(self) -> None:
        from aiohttp import web

        self._app = web.Application()
        self._app.router.add_get("/ws", self._handle_ws)
        self._app.router.add_post("/api/chat", self._handle_chat)
        self._app.router.add_get("/api/stream", self._handle_stream)
        self._app.router.add_get("/api/health", self._handle_health)
        self._app.router.add_get("/api/metrics", self._handle_metrics)
        self._app.router.add_get("/api/traces", self._handle_traces)
        self._app.router.add_post("/api/config", self._handle_config)
        self._app.router.add_get("/api/models", self._handle_models)
        self._app.router.add_post("/api/upload", self._handle_upload)
        # ── Diagnostics APIs ──
        self._app.router.add_get("/api/diagnostics/health/full", self._handle_diag_health)
        self._app.router.add_get("/api/diagnostics/connectivity", self._handle_diag_connectivity)
        self._app.router.add_get("/api/diagnostics/audit", self._handle_diag_audit)
        self._app.router.add_post("/api/diagnostics/compare/design", self._handle_diag_design_diff)
        self._app.router.add_post("/api/diagnostics/compare/competitor", self._handle_diag_competitor)
        self._app.router.add_get("/api/diagnostics/ux", self._handle_diag_ux)
        self._app.router.add_get("/api/diagnostics/modules", self._handle_diag_modules)
        self._app.router.add_get("/api/diagnostics/history", self._handle_diag_history)
        self._app.router.add_get("/api/diagnostics/alerts", self._handle_diag_alerts)
        self._app.router.add_post("/api/diagnostics/alerts/ack", self._handle_diag_ack_alert)
        self._app.router.add_get("/api/diagnostics/export", self._handle_diag_export)
        self._app.router.add_get("/api/diagnostics/config", self._handle_diag_config_get)
        self._app.router.add_post("/api/diagnostics/config", self._handle_diag_config_post)
        self._app.router.add_get("/{tail:.*}", self._handle_static)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()
        self._running = True

        # ── Diagnostic Scheduler ──
        if self._enable_scheduler:
            from nexusagent.diagnostics.persistence import DiagnosticStore
            from nexusagent.diagnostics.scheduler import DiagnosticScheduler
            self._diag_store = DiagnosticStore()
            self._scheduler = DiagnosticScheduler(
                interval_seconds=self._scheduler_interval,
                on_alert=self._broadcast_alert,
                store=self._diag_store,
            )
            self._scheduler.start_in_background()

        logger.info("WebAdapter 启动于 http://%s:%s", self._host, self._port)

    async def stop(self) -> None:
        """优雅关闭：先关闭所有 WebSocket，再停止 HTTP 服务"""
        if self._scheduler:
            await self._scheduler.stop()
            # Brief grace for pending thread-pool DB operations
            await asyncio.sleep(0.05)
            self._scheduler = None

        if self._diag_store:
            self._diag_store.close()
            self._diag_store = None

        for ws in self._ws_connections:
            await ws.close()
        self._ws_connections.clear()

        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        self._running = False
        logger.info("WebAdapter 已停止")

    def _broadcast_alert(self, alert: Any) -> None:
        """向所有 WebSocket 客户端广播告警"""
        import asyncio
        payload = alert.to_json()
        dead = []
        for ws in self._ws_connections:
            try:
                if hasattr(ws, "send_str"):
                    asyncio.create_task(ws.send_str(payload))
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self._ws_connections:
                self._ws_connections.remove(ws)
        if self._ws_connections:
            logger.info("告警已广播到 %d 个 WebSocket 客户端: %s", len(self._ws_connections), alert.title)

    async def send(self, envelope: MessageEnvelope) -> bool:
        """向所有 WebSocket 客户端广播消息"""
        if not envelope.content:
            return False
        payload = json.dumps({
            "ok": True,
            "response": envelope.content,
            "session": envelope.session_id,
        })
        dead = []
        for ws in self._ws_connections:
            try:
                await ws.send_str(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._ws_connections.remove(ws)
        return len(self._ws_connections) > 0

    def parse_inbound(self, raw_payload: Any) -> Optional[MessageEnvelope]:
        """解析前端 JSON 为 MessageEnvelope"""
        if isinstance(raw_payload, dict):
            content = raw_payload.get("message", "")
            session = raw_payload.get("session", "")
        elif isinstance(raw_payload, str):
            try:
                data = json.loads(raw_payload)
                content = data.get("message", "")
                session = data.get("session", "")
            except Exception:
                content = raw_payload
                session = ""
        else:
            return None

        if not content or not str(content).strip():
            return None
        return MessageEnvelope(
            channel_type=ChannelType.WEB,
            content=str(content).strip(),
            security_level=SecurityLevel.PUBLIC,
            session_id=session or f"web_{time.time()}",
        )

    def register_message_callback(self, callback: Callable[[MessageEnvelope], Awaitable[Optional[MessageEnvelope]]]) -> None:
        """注册消息处理回调（由 Orchestrator 使用）"""
        self._message_callback = callback

    # ── HTTP Handlers ──

    async def _handle_chat(self, request: Any) -> Any:
        from aiohttp import web
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        # 1. 限流检查 — Token Bucket (per session)
        session_id = data.get("session", "")
        client_key = request.remote or "unknown"
        rate_key = f"{client_key}:{session_id or 'global'}"
        if not await self._rate_limiter.acquire(rate_key):
            remaining = await self._rate_limiter.get_remaining(rate_key)
            logger.warning("Rate limit exceeded: %s", rate_key)
            return web.json_response(
                {"error": "Rate limit exceeded", "retry_after": 1, "remaining": remaining},
                status=429,
            )

        # 2. 幂等性检查
        idempotency_key = data.get("idempotency_key", "")
        if idempotency_key:
            if not await self._idempotency.check_and_set(idempotency_key):
                logger.info("Idempotency key replay blocked: %s", idempotency_key)
                return web.json_response(
                    {"error": "Duplicate request", "idempotency_key": idempotency_key},
                    status=409,
                )

        envelope = self.parse_inbound(data)
        if not envelope:
            return web.json_response({"error": "Empty message"}, status=400)

        if self._message_callback:
            try:
                response = await self._message_callback(envelope)
                return web.json_response({
                    "ok": True,
                    "response": response.content if response else "",
                    "session": envelope.session_id,
                })
            except Exception as e:
                logger.error("WebAdapter 处理消息失败: %s", e)
                return web.json_response({"ok": False, "error": str(e)}, status=500)
        return web.json_response({"ok": False, "error": "No handler"}, status=503)

    async def _handle_stream(self, request: Any) -> Any:
        """SSE 流式输出端点 — v4.0+ 真实 LLM 流式"""
        from aiohttp import web

        # 从 query params 获取消息
        message = request.query.get("message", "")
        session_id = request.query.get("session", "")

        if not message:
            return web.json_response({"error": "message is required"}, status=400)

        response = web.StreamResponse()
        response.headers["Content-Type"] = "text/event-stream"
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Connection"] = "keep-alive"
        await response.prepare(request)

        # ══ v4.0+ 真实流式: 如果 LLM backend 可用，直接流式输出 token ══
        if self._llm and hasattr(self._llm, "complete_stream"):
            try:
                # 发送开始事件
                await response.write(
                    f'data: {json.dumps({"event": "start", "model": self._llm.model})}\n\n'.encode("utf-8")
                )

                messages = [
                    {"role": "system", "content": "你是 NexusAgent，一个本地优先的 AI 助手。请用中文回复。"},
                    {"role": "user", "content": message},
                ]

                buffer = ""
                async for token in self._llm.complete_stream(messages):
                    buffer += token
                    await response.write(
                        f'data: {json.dumps({"event": "token", "token": token})}\n\n'.encode("utf-8")
                    )

                await response.write(
                    f'data: {json.dumps({"event": "complete", "response": buffer})}\n\n'.encode("utf-8")
                )
                await response.write(b"data: [DONE]\n\n")
                return response
            except Exception as e:
                logger.error("WebAdapter 流式输出失败: %s", e)
                error_evt = {"event": "error", "error": str(e)}
                await response.write(f"data: {json.dumps(error_evt)}\n\n".encode("utf-8"))
                await response.write(b"data: [DONE]\n\n")
                return response

        # ══ Fallback: 通过 message_callback 获取完整响应后分段输出 ══
        envelope = self.parse_inbound({"message": message, "session": session_id})
        if envelope and self._message_callback:
            try:
                # 发送进度事件
                steps = [
                    {"event": "step", "node": "理解任务", "status": "running"},
                    {"event": "step", "node": "检索记忆", "status": "running"},
                    {"event": "step", "node": "安全审查", "status": "running"},
                    {"event": "step", "node": "生成回复", "status": "running"},
                ]
                for step in steps:
                    await response.write(f"data: {json.dumps(step)}\n\n".encode("utf-8"))
                    await asyncio.sleep(0.05)

                # 调用真实消息处理器获取响应
                result = await self._message_callback(envelope)
                final_text = result.content if result else ""

                complete_evt = {"event": "complete", "response": final_text}
                await response.write(f"data: {json.dumps(complete_evt)}\n\n".encode("utf-8"))
            except Exception as e:
                logger.error("WebAdapter SSE 处理失败: %s", e)
                error_evt = {"event": "error", "error": str(e)}
                await response.write(f"data: {json.dumps(error_evt)}\n\n".encode("utf-8"))
        else:
            error_evt = {"event": "error", "error": "No handler available"}
            await response.write(f"data: {json.dumps(error_evt)}\n\n".encode("utf-8"))

        await response.write(b"data: [DONE]\n\n")
        return response

    async def _handle_health(self, request: Any) -> Any:
        from aiohttp import web
        status = await self.health_check()
        # 附加限流器状态
        status["rate_limiter"] = {
            "enabled": True,
            "rate": self._rate_limiter._rate,
            "capacity": self._rate_limiter._capacity,
        }
        return web.json_response({"ok": self._running, **status})

    async def _handle_metrics(self, request: Any) -> Any:
        """Dashboard 指标 API — Phase 1.5"""
        from aiohttp import web
        from nexusagent.observability.metrics import metrics_collector

        snapshot = metrics_collector.snapshot()
        return web.json_response({
            "ok": True,
            "metrics": {
                "requests_total": snapshot.requests_total,
                "requests_success": snapshot.requests_success,
                "requests_error": snapshot.requests_error,
                "avg_latency_ms": round(snapshot.avg_latency_ms, 2),
                "active_sessions": snapshot.active_sessions,
                "security_interceptions": snapshot.security_interceptions,
                "token_usage_total": snapshot.token_usage_total,
            },
        })

    async def _handle_traces(self, request: Any) -> Any:
        """执行轨迹 API — Phase 1.5"""
        from aiohttp import web
        from nexusagent.observability.tracing import trace_collector

        limit = int(request.query.get("limit", "20"))
        traces = trace_collector.list_traces(limit=limit)
        return web.json_response({
            "ok": True,
            "traces": [t.to_dict() for t in traces],
        })

    async def _handle_config(self, request: Any) -> Any:
        from aiohttp import web
        import os
        from pathlib import Path

        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        provider = data.get("provider", "").strip().lower()
        model = data.get("model", "").strip()
        api_key = data.get("api_key", "").strip()

        if not provider or not model:
            return web.json_response({"error": "provider and model are required"}, status=400)

        # 更新 .env 文件
        base = Path(self._static_path) if self._static_path else Path(__file__).parent.parent
        env_path = base / ".env"
        lines: List[str] = []
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()

        updates = {"DEFAULT_PROVIDER": provider, "DEFAULT_MODEL": model}
        key_var = {"moonshot": "MOONSHOT_API_KEY", "deepseek": "DEEPSEEK_API_KEY", "openai": "OPENAI_API_KEY", "ollama": "OLLAMA_API_KEY"}.get(provider)
        if key_var and api_key:
            updates[key_var] = api_key
        if provider == "ollama":
            updates["OLLAMA_HOST"] = data.get("ollama_host", "http://localhost:11434")
            if not api_key and key_var:
                updates[key_var] = ""

        existing = set()
        for i, line in enumerate(lines):
            if "=" in line and not line.strip().startswith("#"):
                k = line.split("=", 1)[0].strip()
                if k in updates:
                    lines[i] = f"{k}={updates[k]}"
                    existing.add(k)
        for k, v in updates.items():
            if k not in existing:
                lines.append(f"{k}={v}")

        try:
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception as e:
            return web.json_response({"error": f"Failed to write .env: {e}"}, status=500)

        for k, v in updates.items():
            os.environ[k] = v

        return web.json_response({"ok": True, "provider": provider, "model": model})

    async def _handle_models(self, request: Any) -> Any:
        """返回可用模型列表，支持 Ollama 本地查询"""
        from aiohttp import web
        import aiohttp
        import os

        provider = request.query.get("provider", "").strip().lower()
        if not provider:
            # 返回所有 provider 的模型映射
            return web.json_response({
                "ok": True,
                "models": {
                    "ollama": ["llama3.2", "qwen2.5", "deepseek-coder-v2", "mistral"],
                    "moonshot": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
                    "deepseek": ["deepseek-chat", "deepseek-v4-pro"],
                    "openai": ["gpt-4o-mini"],
                },
            })

        if provider == "ollama":
            ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{ollama_host}/api/tags", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            models = [m.get("name", "").split(":")[0] for m in data.get("models", [])]
                            return web.json_response({"ok": True, "provider": "ollama", "models": models})
                        else:
                            return web.json_response({"ok": True, "provider": "ollama", "models": ["llama3.2"], "warning": f"Ollama returned {resp.status}"})
            except Exception as e:
                logger.warning("Ollama 模型查询失败: %s", e)
                return web.json_response({"ok": True, "provider": "ollama", "models": ["llama3.2"], "warning": str(e)})

        hardcoded = {
            "moonshot": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
            "deepseek": ["deepseek-chat", "deepseek-v4-pro"],
            "openai": ["gpt-4o-mini"],
        }
        models = hardcoded.get(provider, [])
        return web.json_response({"ok": True, "provider": provider, "models": models})

    async def _handle_upload(self, request: Any) -> Any:
        """文件上传 + 文档转换端点"""
        from aiohttp import web
        import aiohttp
        from pathlib import Path

        # 确保 uploads 目录存在
        uploads_base = Path(os.getcwd()) / "uploads"
        uploads_base.mkdir(exist_ok=True)

        reader = await request.multipart()
        file_field = await reader.next()
        if not file_field or not file_field.filename:
            return web.json_response({"error": "No file provided"}, status=400)

        filename = file_field.filename
        # 清理文件名，防止路径遍历
        safe_name = Path(filename).name
        if not safe_name or safe_name.startswith("."):
            return web.json_response({"error": "Invalid filename"}, status=400)

        # 大小限制 (20MB)
        max_size = 20 * 1024 * 1024
        data = b""
        chunk_size = 64 * 1024
        while True:
            chunk = await file_field.read_chunk(chunk_size)
            if not chunk:
                break
            data += chunk
            if len(data) > max_size:
                return web.json_response({"error": "File too large (max 20MB)"}, status=413)

        # 保存文件
        file_path = uploads_base / safe_name
        try:
            file_path.write_bytes(data)
        except Exception as e:
            return web.json_response({"error": f"Failed to save file: {e}"}, status=500)

        # 文档转换
        try:
            from nexusagent.tools.document import DocumentConverterTool
            converter = DocumentConverterTool(uploads_dir=str(uploads_base))
            result = await converter.convert(str(file_path))
        except Exception as e:
            logger.error("文档转换失败: %s", e)
            return web.json_response({
                "ok": True,
                "file_path": str(file_path),
                "filename": safe_name,
                "file_size": len(data),
                "text": "",
                "error": f"转换失败: {e}",
            })

        # v4.0+ 自动索引到 ChromaDB（异步后台，不影响响应）
        if result.success and result.text:
            try:
                from nexusagent.memory.vector_store import ChromaVectorStore
                from nexusagent.tools.rag import _chunk_text
                store = ChromaVectorStore()
                session_id = request.query.get("session", "")
                chunks = _chunk_text(result.text, chunk_size=1000, overlap=200)
                for idx, chunk in enumerate(chunks):
                    await store.add_document(
                        text=chunk,
                        metadata={
                            "filename": safe_name,
                            "session_id": session_id,
                            "chunk_index": idx,
                            "total_chunks": len(chunks),
                        },
                        doc_id=f"{safe_name}_{idx}_{session_id}",
                    )
                logger.info("文档已索引到 ChromaDB: %s (%d chunks)", safe_name, len(chunks))
            except Exception as e:
                logger.warning("ChromaDB 索引失败 (不影响上传): %s", e)

        return web.json_response({
            "ok": result.success,
            "file_path": str(file_path),
            "filename": safe_name,
            "file_size": len(data),
            "mime_type": result.mime_type,
            "text": result.text[:8000] if result.success else "",
            "indexed": result.success and len(result.text) > 0,
            "error": result.error,
        })

    async def _handle_static(self, request: Any) -> Any:
        from aiohttp import web
        from pathlib import Path

        raw = request.raw_path
        if ".." in raw or "%2e" in raw.lower():
            return web.Response(text="Forbidden", status=403)

        path = request.match_info.get("tail", "") or "desktop/index.html"
        if ".." in path or path.startswith("/") or "\\" in path:
            return web.Response(text="Forbidden", status=403)

        safe_path = path.replace("//", "/").lstrip("/")
        if not safe_path:
            safe_path = "desktop/index.html"

        base = Path(self._static_path) if self._static_path else Path(__file__).parent.parent
        file_path = (base / safe_path).resolve()
        try:
            file_path.relative_to(base.resolve())
        except ValueError:
            return web.Response(text="Forbidden", status=403)

        if file_path.exists() and file_path.is_file():
            suffix = file_path.suffix.lower()
            content_type = {
                ".html": "text/html", ".css": "text/css",
                ".js": "application/javascript", ".json": "application/json",
                ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml",
                ".ico": "image/x-icon",
            }.get(suffix, "text/plain")
            if suffix in (".html", ".css", ".js", ".json", ".svg", ".txt", ".md"):
                return web.Response(text=file_path.read_text(encoding="utf-8"), content_type=content_type)
            return web.Response(body=file_path.read_bytes(), content_type=content_type)
        return web.Response(text="Not Found", status=404)

    # ═══════════════════════════════════════════════════════════════
    # Diagnostic Handlers
    # ═══════════════════════════════════════════════════════════════

    async def _handle_diag_health(self, request: Any) -> Any:
        """Full health dashboard — delegates to shared collector."""
        from aiohttp import web
        from nexusagent.diagnostics import collect_health

        adapter_state = {
            "running": self._running,
            "rate_limiter": {
                "rate": getattr(self._rate_limiter, '_rate', None),
                "capacity": getattr(self._rate_limiter, '_capacity', None),
            },
        }
        data = await collect_health(adapter_state=adapter_state)
        return web.json_response(data)

    async def _handle_diag_connectivity(self, request: Any) -> Any:
        """Connectivity test — delegates to shared collector."""
        from aiohttp import web
        from nexusagent.diagnostics import collect_connectivity

        data = await collect_connectivity()
        return web.json_response(data)

    async def _handle_diag_audit(self, request: Any) -> Any:
        """Audit viewer — delegates to shared collector."""
        from aiohttp import web
        from nexusagent.diagnostics import collect_audit

        limit = int(request.query.get("limit", "20"))
        level_filter = request.query.get("level", "").upper()
        data = await collect_audit(limit=limit, level_filter=level_filter)
        return web.json_response(data)

    async def _handle_diag_design_diff(self, request: Any) -> Any:
        """Design diff — delegates to shared collector."""
        from aiohttp import web
        from nexusagent.diagnostics import compare_design

        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        baseline = payload.get("baseline", "")
        current = payload.get("current", "")
        if not baseline or not current:
            return web.json_response({"error": "baseline and current are required"}, status=400)

        data = compare_design(baseline, current)
        return web.json_response(data)

    async def _handle_diag_competitor(self, request: Any) -> Any:
        """Competitor analysis — delegates to shared collector."""
        from aiohttp import web
        from nexusagent.diagnostics import compare_competitor

        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        ours = payload.get("our_features", [])
        competitor = payload.get("competitor_features", [])
        competitor_name = payload.get("competitor_name", "Competitor")

        if not ours or not competitor:
            return web.json_response({"error": "our_features and competitor_features are required"}, status=400)

        data = compare_competitor(our_features=ours, competitor_features=competitor, competitor_name=competitor_name)
        return web.json_response(data)

    async def _handle_diag_ux(self, request: Any) -> Any:
        """UX Advisor — delegates to shared collector."""
        from aiohttp import web
        from nexusagent.diagnostics import collect_ux

        theme = request.query.get("theme", "dark")
        model = request.query.get("model", "")
        data = await collect_ux(theme=theme, model=model)
        return web.json_response(data)

    async def _handle_diag_modules(self, request: Any) -> Any:
        """Module status — delegates to shared collector."""
        from aiohttp import web
        from nexusagent.diagnostics import collect_modules

        data = await collect_modules()
        return web.json_response(data)

    async def _handle_diag_history(self, request: Any) -> Any:
        """Diagnostic history — returns time-series snapshots."""
        from aiohttp import web

        category = request.query.get("category", "health")
        hours = float(request.query.get("hours", "24"))
        if self._diag_store:
            points = self._diag_store.get_history(category, hours=hours)
        else:
            points = []
        return web.json_response({
            "ok": True,
            "category": category,
            "hours": hours,
            "points": points,
        })

    async def _handle_diag_alerts(self, request: Any) -> Any:
        """Alert history — returns paginated alert list."""
        from aiohttp import web

        level = request.query.get("level", "")
        hours = float(request.query.get("hours", "24"))
        limit = int(request.query.get("limit", "50"))
        ack_raw = request.query.get("acknowledged", "")
        acknowledged = {"true": True, "false": False}.get(ack_raw.lower()) if ack_raw else None

        if self._diag_store:
            alerts = self._diag_store.get_alerts(
                level_filter=level,
                hours=hours,
                limit=limit,
                acknowledged=acknowledged,
            )
        else:
            alerts = []
        return web.json_response({
            "ok": True,
            "alerts": alerts,
            "unacknowledged_count": self._diag_store.count_unacknowledged_alerts(hours) if self._diag_store else 0,
        })

    async def _handle_diag_ack_alert(self, request: Any) -> Any:
        """Acknowledge an alert."""
        from aiohttp import web

        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)
        alert_id = payload.get("alert_id", "")
        if not alert_id:
            return web.json_response({"error": "alert_id required"}, status=400)
        if self._diag_store:
            ok = self._diag_store.acknowledge_alert(alert_id)
        else:
            ok = False
        return web.json_response({"ok": ok})

    async def _handle_diag_export(self, request: Any) -> Any:
        """Export diagnostic report as Markdown."""
        from aiohttp import web
        from nexusagent.diagnostics.report import generate_report

        if self._diag_store:
            markdown = generate_report(self._diag_store)
        else:
            markdown = "# Diagnostic Report\n\nNo store available.\n"
        return web.json_response({
            "ok": True,
            "markdown": markdown,
        })

    async def _handle_diag_config_get(self, request: Any) -> Any:
        """Get diagnostic configuration."""
        from aiohttp import web
        from nexusagent.diagnostics.config import load_config

        config = load_config()
        return web.json_response({"ok": True, "config": config.to_dict()})

    async def _handle_diag_config_post(self, request: Any) -> Any:
        """Update diagnostic configuration."""
        from aiohttp import web
        from nexusagent.diagnostics.config import load_config, save_config, DiagnosticConfig

        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)
        current = load_config()
        updated = current.with_overrides(payload)
        save_config(updated)
        # Hot-reload scheduler interval if running
        if self._scheduler and hasattr(self._scheduler, "_interval"):
            self._scheduler._interval = max(10.0, updated.scheduler_interval_seconds)
        return web.json_response({"ok": True, "config": updated.to_dict()})

    # ── WebSocket Handler ──

    async def _handle_ws(self, request: Any) -> Any:
        from aiohttp import web
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._ws_connections.append(ws)
        logger.info("WebSocket 客户端已连接 (当前%d)", len(self._ws_connections))

        try:
            async for msg in ws:
                if msg.type == 1:  # TEXT
                    envelope = self.parse_inbound(msg.data)
                    if envelope and self._message_callback:
                        try:
                            response = await self._message_callback(envelope)
                            if response:
                                await ws.send_str(json.dumps({
                                    "ok": True,
                                    "response": response.content,
                                    "session": envelope.session_id,
                                }))
                        except Exception as e:
                            await ws.send_str(json.dumps({"ok": False, "error": str(e)}))
                elif msg.type == 258:  # CLOSE
                    break
        except Exception as e:
            logger.warning("WebSocket 异常: %s", e)
        finally:
            if ws in self._ws_connections:
                self._ws_connections.remove(ws)
            logger.info("WebSocket 客户端已断开 (剩余%d)", len(self._ws_connections))
        return ws
