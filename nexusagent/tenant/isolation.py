"""
NexusAgent v4.0 — 租户资源隔离

设计参考:
- Dify 多租户: PostgreSQL schema + tenant_id 行级隔离
- K8s 多租户: Namespace + RBAC + ResourceQuota
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger("nexus.tenant.isolation")


@dataclass
class TenantQuota:
    """租户资源配额"""
    max_agents: int = 10
    max_memory_mb: int = 500
    max_requests_per_min: int = 100
    max_concurrent_tasks: int = 5


class TenantRegistry:
    """租户注册表 — 管理所有租户的配额和状态"""

    def __init__(self):
        self._quotas: Dict[str, TenantQuota] = {}
        self._counters: Dict[str, Dict[str, int]] = {}
        self._lock = asyncio.Lock()

    async def register(self, tenant_id: str, quota: Optional[TenantQuota] = None) -> None:
        """注册租户"""
        async with self._lock:
            self._quotas[tenant_id] = quota or TenantQuota()
            self._counters[tenant_id] = {
                "agents": 0,
                "requests": 0,
                "tasks": 0,
            }
        logger.info("租户注册: %s", tenant_id)

    async def get_quota(self, tenant_id: str) -> TenantQuota:
        async with self._lock:
            return self._quotas.get(tenant_id, TenantQuota())

    async def check_and_increment(self, tenant_id: str, resource: str, delta: int = 1) -> bool:
        """
        检查配额并增加计数

        Returns:
            True if within quota, False if exceeded
        """
        async with self._lock:
            quota = self._quotas.get(tenant_id)
            if not quota:
                return True
            counter = self._counters.setdefault(tenant_id, {})
            current = counter.get(resource, 0)
            limit = getattr(quota, f"max_{resource}", 99999)
            if current + delta > limit:
                logger.warning("租户 %s 资源 %s 超出配额: %d/%d", tenant_id, resource, current, limit)
                return False
            counter[resource] = current + delta
            return True

    async def decrement(self, tenant_id: str, resource: str, delta: int = 1) -> None:
        async with self._lock:
            counter = self._counters.get(tenant_id, {})
            counter[resource] = max(0, counter.get(resource, 0) - delta)

    async def reset_counters(self, tenant_id: str) -> None:
        async with self._lock:
            self._counters[tenant_id] = {k: 0 for k in ["agents", "requests", "tasks"]}


# 全局注册表实例
_registry = TenantRegistry()


async def get_registry() -> TenantRegistry:
    return _registry
