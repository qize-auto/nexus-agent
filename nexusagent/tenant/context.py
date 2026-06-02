"""
NexusAgent v4.0 — 租户上下文管理

多租户数据隔离的核心：每个请求携带 TenantContext，
所有数据库操作自动过滤 tenant_id。
"""

from __future__ import annotations

import contextvars
import logging
from dataclasses import dataclass
from typing import Optional

from nexusagent.interface.adapter import SecurityLevel

logger = logging.getLogger("nexus.tenant.context")

# 全局 ContextVar — 在当前 asyncio Task 中传递租户信息
_current_tenant: contextvars.ContextVar[Optional["TenantContext"]] = contextvars.ContextVar(
    "current_tenant", default=None
)


@dataclass(frozen=True)
class TenantContext:
    """租户上下文 — 贯穿请求生命周期"""
    tenant_id: str
    user_id: str = ""
    security_level: SecurityLevel = SecurityLevel.MEDIUM
    display_name: str = ""

    @property
    def is_default(self) -> bool:
        return self.tenant_id == "default"


class TenantContextManager:
    """租户上下文管理器"""

    @staticmethod
    def get_current() -> TenantContext:
        """获取当前租户上下文（默认租户兜底）"""
        ctx = _current_tenant.get()
        if ctx is None:
            return TenantContext(tenant_id="default")
        return ctx

    @staticmethod
    def set_current(ctx: TenantContext) -> None:
        """设置当前租户上下文"""
        _current_tenant.set(ctx)
        logger.debug("租户上下文切换: tenant_id=%s", ctx.tenant_id)

    @staticmethod
    def reset() -> None:
        """重置为默认租户"""
        _current_tenant.set(TenantContext(tenant_id="default"))


# 快捷函数
def get_tenant_id() -> str:
    return TenantContextManager.get_current().tenant_id
