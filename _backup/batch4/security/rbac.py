"""
NexusAgent v4.0+ — RBAC 权限控制

设计参考:
- Mastra Enterprise RBAC: https://mastra.ai/docs/rbac
  "Fine-grained permissions per tool and per tenant"
- AWS IAM Policy model

支持:
    - per-tool 权限: 用户/租户可调用哪些工具
    - per-tenant 隔离: 租户间权限完全隔离
    - 默认拒绝: 未显式允许 = 拒绝
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("nexus.security.rbac")


@dataclass
class Permission:
    """权限定义"""
    resource: str       # 资源名，如 "tool.browser" 或 "tool.*"
    action: str         # 动作: invoke | read | write | admin
    effect: str = "allow"  # allow | deny


@dataclass
class Role:
    """角色定义"""
    name: str
    permissions: List[Permission] = field(default_factory=list)


@dataclass
class Policy:
    """策略 — 绑定到用户或租户"""
    subject_id: str     # user_id 或 tenant_id
    subject_type: str   # user | tenant
    permissions: List[Permission] = field(default_factory=list)
    roles: List[str] = field(default_factory=list)


class RBACEngine:
    """
    RBAC 引擎

    Usage:
        rbac = RBACEngine()
        rbac.add_policy("tenant_a", "tenant", [Permission("tool.browser", "invoke")])
        rbac.add_policy("user_1", "user", [Permission("tool.code_interpreter", "invoke")])

        if rbac.can_invoke("tenant_a", "user_1", "tool.browser"):
            tool.execute(...)
    """

    def __init__(self):
        self._roles: Dict[str, Role] = {}
        self._policies: Dict[str, Policy] = {}  # key = "{type}:{id}"
        self._default_deny = True

        # 预定义角色
        self._roles["admin"] = Role("admin", [Permission("*", "*", "allow")])
        self._roles["analyst"] = Role("analyst", [
            Permission("tool.browser", "invoke"),
            Permission("tool.search", "invoke"),
            Permission("tool.code_interpreter", "invoke"),
        ])
        self._roles["viewer"] = Role("viewer", [
            Permission("tool.search", "invoke"),
        ])

    def add_role(self, role: Role) -> None:
        self._roles[role.name] = role

    def add_policy(self, subject_id: str, subject_type: str, permissions: List[Permission], roles: Optional[List[str]] = None) -> None:
        key = f"{subject_type}:{subject_id}"
        self._policies[key] = Policy(
            subject_id=subject_id,
            subject_type=subject_type,
            permissions=permissions,
            roles=roles or [],
        )

    def can_invoke(self, tenant_id: str, user_id: str, tool_name: str) -> bool:
        """
        检查是否允许调用工具

        评估顺序:
        1. 租户级策略
        2. 用户级策略
        3. 角色权限
        4. 默认拒绝
        """
        # 收集所有相关权限
        all_perms: List[Permission] = []

        # 租户策略
        tenant_key = f"tenant:{tenant_id}"
        tenant_policy = self._policies.get(tenant_key)
        if tenant_policy:
            all_perms.extend(tenant_policy.permissions)
            for role_name in tenant_policy.roles:
                role = self._roles.get(role_name)
                if role:
                    all_perms.extend(role.permissions)

        # 用户策略
        user_key = f"user:{user_id}"
        user_policy = self._policies.get(user_key)
        if user_policy:
            all_perms.extend(user_policy.permissions)
            for role_name in user_policy.roles:
                role = self._roles.get(role_name)
                if role:
                    all_perms.extend(role.permissions)

        # 评估权限
        return self._evaluate(all_perms, tool_name)

    def _evaluate(self, permissions: List[Permission], tool_name: str) -> bool:
        """评估权限列表对特定工具的决定"""
        # 先检查 deny
        for perm in permissions:
            if perm.effect == "deny" and self._match(perm.resource, tool_name):
                return False

        # 再检查 allow
        for perm in permissions:
            if perm.effect == "allow" and self._match(perm.resource, tool_name):
                return True

        # 默认
        return not self._default_deny

    @staticmethod
    def _match(pattern: str, value: str) -> bool:
        """支持通配符匹配"""
        if pattern == "*" or pattern == value:
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return value.startswith(prefix + ".")
        return False

    def get_allowed_tools(self, tenant_id: str, user_id: str) -> Set[str]:
        """获取用户允许调用的工具列表（用于 LLM 工具选择）"""
        # 简化实现：返回所有可能被允许的工具前缀
        # 实际生产环境应查询注册表
        return set()


# 全局 RBAC 实例
_rbac = RBACEngine()


def get_rbac() -> RBACEngine:
    return _rbac
