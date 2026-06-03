"""
NexusAgent v4.0+ — SearXNG 聚合搜索工具

本地优先的搜索能力，无需商业搜索 API Key。
依赖: SearXNG 实例（可通过 Docker 本地运行）

Usage:
    tool = SearXNGTool()
    result = await tool.search("Python asyncio")
    print(result.to_markdown())
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nexus.tools.search")


@dataclass
class SearchResultItem:
    """单条搜索结果"""
    title: str
    url: str
    content: str = ""
    engine: str = ""
    score: float = 0.0


@dataclass
class SearchResult:
    """搜索结果集合"""
    query: str
    items: List[SearchResultItem] = field(default_factory=list)
    total: int = 0
    error: Optional[str] = None

    def to_markdown(self, max_items: int = 10) -> str:
        """转换为 Markdown 格式供 LLM 阅读"""
        if self.error:
            return f"搜索出错: {self.error}"
        if not self.items:
            return f"未找到与「{self.query}」相关的结果。"
        lines = [f"## 搜索结果: {self.query}", ""]
        for i, item in enumerate(self.items[:max_items], 1):
            lines.append(f"{i}. **{item.title}**")
            lines.append(f"   - 链接: {item.url}")
            if item.content:
                snippet = item.content.replace("\n", " ")[:300]
                lines.append(f"   - 摘要: {snippet}")
            lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "total": self.total,
            "items": [
                {
                    "title": i.title,
                    "url": i.url,
                    "content": i.content,
                    "engine": i.engine,
                    "score": i.score,
                }
                for i in self.items
            ],
            "error": self.error,
        }


class SearXNGTool:
    """
    SearXNG 聚合搜索工具

    配置:
        SEARXNG_HOST — SearXNG 实例地址（默认 http://localhost:8081）
    """

    def __init__(self, host: Optional[str] = None):
        self._host = (host or os.environ.get("SEARXNG_HOST", "http://localhost:8081")).rstrip("/")

    async def search(
        self,
        query: str,
        categories: str = "general",
        language: str = "zh-CN",
        max_results: int = 10,
    ) -> SearchResult:
        """
        执行搜索查询

        Args:
            query: 搜索关键词
            categories: 搜索分类 (general/images/news/science/it)
            language: 语言代码
            max_results: 最大返回条数
        """
        if not query or not query.strip():
            return SearchResult(query="", error="搜索关键词不能为空")

        try:
            import aiohttp
        except ImportError:
            return SearchResult(
                query=query,
                error="aiohttp 未安装，无法执行网络搜索。请安装: pip install aiohttp",
            )

        params = {
            "q": query.strip(),
            "format": "json",
            "categories": categories,
            "language": language,
        }

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self._host}/search", params=params) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.warning("SearXNG 返回非 200: %s %s", resp.status, text[:200])
                        return SearchResult(
                            query=query,
                            error=f"SearXNG 返回 HTTP {resp.status}。请检查 SearXNG 服务是否运行 ({self._host})",
                        )
                    data = await resp.json()
        except aiohttp.ClientConnectorError as e:
            logger.warning("无法连接 SearXNG: %s", e)
            return SearchResult(
                query=query,
                error=f"无法连接 SearXNG ({self._host})。请确认服务已启动: docker compose up searxng",
            )
        except Exception as e:
            logger.warning("SearXNG 查询失败: %s", e)
            return SearchResult(query=query, error=f"搜索请求失败: {e}")

        items: List[SearchResultItem] = []
        for raw in data.get("results", [])[:max_results]:
            items.append(
                SearchResultItem(
                    title=raw.get("title", ""),
                    url=raw.get("url", ""),
                    content=raw.get("content", ""),
                    engine=raw.get("engine", ""),
                    score=raw.get("score", 0.0),
                )
            )

        return SearchResult(
            query=query,
            items=items,
            total=data.get("number_of_results", len(items)),
        )

    # ── ToolSpec 兼容 ──

    async def invoke(self, query: str, categories: str = "general", language: str = "zh-CN", max_results: int = 10) -> str:
        """供 ToolRegistry 调用的统一接口，返回 Markdown 文本"""
        result = await self.search(query, categories, language, max_results)
        return result.to_markdown()

    def to_tool_spec(self) -> Dict[str, Any]:
        return {
            "name": "search.web",
            "description": (
                "使用 SearXNG 聚合搜索引擎查询网络信息。"
                "支持普通网页、图片、新闻、IT技术等多种分类。"
                "当用户询问实时信息、新闻、技术文档、事实核查时优先使用此工具。"
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词",
                    },
                    "categories": {
                        "type": "string",
                        "default": "general",
                        "description": "搜索分类: general(通用), images(图片), news(新闻), science(科学), it(IT技术)",
                    },
                    "language": {
                        "type": "string",
                        "default": "zh-CN",
                        "description": "语言代码，如 zh-CN, en-US",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 10,
                        "description": "最大返回结果数 (1-20)",
                    },
                },
                "required": ["query"],
            },
        }
