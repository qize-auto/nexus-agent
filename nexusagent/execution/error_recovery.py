"""
NexusAgent v4.0+ — Error Recovery Engine 错误自我纠正引擎

工具失败后自动切换替代方案、修正参数。

设计原则:
    1. 同一次 ReAct 迭代内完成替代，不消耗额外 LLM 调用
    2. 替代结果标注 [recovered]，让 LLM 知晓是降级结果
    3. 单次迭代最多 1 次替代，防止无限递归

Usage:
    from nexusagent.execution.error_recovery import ErrorRecoveryEngine
    recovery = ErrorRecoveryEngine(tool_registry)
    alt = recovery.recover("browser.visit", error_msg, {"url": "..."})
    if alt:
        result = await alt.execute()
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("nexus.execution.recovery")


@dataclass
class RecoveryAction:
    """替代动作描述"""
    tool_name: str
    arguments: Dict[str, Any]
    reason: str

    async def execute(self, registry) -> str:
        """执行替代工具"""
        tool = registry.get(self.tool_name)
        if tool is None:
            return f"[recovery failed] 替代工具 {self.tool_name} 未注册"
        try:
            result = await tool.invoke(**self.arguments)
            return f"[recovered via {self.tool_name}] {result}"
        except Exception as e:
            return f"[recovery failed] {self.tool_name} 也失败了: {e}"


class ErrorRecoveryEngine:
    """
    错误自我纠正引擎

    支持两种恢复策略:
    1. 工具替代: browser.visit 失败 → search.web
    2. 参数修正: file.read 路径错误 → 修正为安全路径
    """

    # ── 工具替代映射 ──
    # key: 失败工具名, value: (替代工具名, 参数转换函数)
    _TOOL_ALTERNATIVES: Dict[str, List[tuple]] = {
        "browser.visit": [
            # 访问网页失败 → 搜索同一域名关键词
            (
                "search.web",
                lambda args, err: {
                    "query": _extract_domain_keyword(args.get("url", "")),
                    "categories": "general",
                },
            ),
        ],
        "file.read": [
            # 文件不存在 → 列出所在目录
            (
                "file.list",
                lambda args, err: {
                    "path": os.path.dirname(args.get("path", ".")) or ".",
                    "recursive": False,
                },
            ),
        ],
        "search.web": [
            # 搜索无结果 → 如果有 URL 则直接访问
            (
                "browser.visit",
                lambda args, err: {
                    "url": _guess_url_from_query(args.get("query", "")),
                    "extract_text": True,
                } if _looks_like_url(args.get("query", "")) else None,
            ),
        ],
        "rag.retrieve": [
            # 知识库无结果 → 网上搜索补充
            (
                "search.web",
                lambda args, err: {
                    "query": args.get("query", ""),
                    "categories": "general",
                },
            ),
        ],
    }

    # ── 参数修正规则 ──
    # key: 工具名, value: (错误模式检查, 修正函数)
    _PARAM_FIXERS: Dict[str, List[tuple]] = {
        "file.read": [
            # 路径包含 .. 或不安全 → 修正为项目根目录
            (
                lambda err: "路径不安全" in err or "超出项目范围" in err,
                lambda args: {
                    **args,
                    "path": os.path.basename(args.get("path", "")) or ".",
                },
            ),
        ],
        "search.web": [
            # 查询太短 → 扩展
            (
                lambda err: True,  # 总是检查
                lambda args: {
                    **args,
                    "query": _expand_short_query(args.get("query", "")),
                } if len(args.get("query", "")) < 3 else args,
            ),
        ],
    }

    def __init__(self, tool_registry: Optional[Any] = None):
        self._registry = tool_registry

    def recover(
        self,
        tool_name: str,
        error_msg: str,
        arguments: Dict[str, Any],
    ) -> Optional[RecoveryAction]:
        """
        尝试生成恢复动作

        Returns:
            RecoveryAction 或 None（无可行替代）
        """
        # 1. 先尝试参数修正
        fixed = self._try_fix_params(tool_name, error_msg, arguments)
        if fixed is not None:
            return RecoveryAction(
                tool_name=tool_name,
                arguments=fixed,
                reason="参数修正",
            )

        # 2. 尝试工具替代
        alternatives = self._TOOL_ALTERNATIVES.get(tool_name, [])
        for alt_tool, arg_transform in alternatives:
            try:
                new_args = arg_transform(arguments, error_msg)
                if new_args is not None:
                    return RecoveryAction(
                        tool_name=alt_tool,
                        arguments=new_args,
                        reason=f"{tool_name} 失败，降级到 {alt_tool}",
                    )
            except Exception as e:
                logger.debug("替代方案生成失败: %s", e)
                continue

        return None

    def _try_fix_params(
        self,
        tool_name: str,
        error_msg: str,
        arguments: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """尝试修正参数"""
        fixers = self._PARAM_FIXERS.get(tool_name, [])
        for check, fix in fixers:
            try:
                if check(error_msg):
                    fixed = fix(arguments)
                    if fixed != arguments:
                        logger.info("参数修正: %s %s → %s", tool_name, arguments, fixed)
                        return fixed
            except Exception:
                continue
        return None

    def can_recover(self, tool_name: str, error_msg: str) -> bool:
        """快速检查是否有可能恢复"""
        if tool_name in self._PARAM_FIXERS:
            return True
        if tool_name in self._TOOL_ALTERNATIVES:
            return True
        return False


# ── 辅助函数 ──

def _extract_domain_keyword(url: str) -> str:
    """从 URL 中提取域名关键词用于搜索"""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        host = parsed.hostname or url
        # 去掉 www. 和顶级域名
        parts = host.replace("www.", "").split(".")
        if len(parts) > 1:
            return parts[0]
        return host
    except Exception:
        return url


def _looks_like_url(text: str) -> bool:
    """判断文本是否像 URL"""
    return text.startswith(("http://", "https://", "www."))


def _guess_url_from_query(query: str) -> str:
    """从查询词中猜测 URL"""
    if query.startswith("http"):
        return query
    if query.startswith("www."):
        return "https://" + query
    return "https://" + query


def _expand_short_query(query: str) -> str:
    """扩展短查询词"""
    expansions = {
        "py": "Python programming language",
        "js": "JavaScript programming",
        "go": "Go programming language Golang",
        "ai": "artificial intelligence",
        "llm": "large language model",
    }
    q = query.strip().lower()
    return expansions.get(q, query + " tutorial")
