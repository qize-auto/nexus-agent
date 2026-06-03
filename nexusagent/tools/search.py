"""
NexusAgent v4.0+ — SearXNG Aggregated Search Tool

Local-first search capability, no commercial search API key required.
Dependency: SearXNG instance (can run locally via Docker)

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
    """Single search result"""
    title: str
    url: str
    content: str = ""
    engine: str = ""
    score: float = 0.0


@dataclass
class SearchResult:
    """Collection of search results"""
    query: str
    items: List[SearchResultItem] = field(default_factory=list)
    total: int = 0
    error: Optional[str] = None

    def to_markdown(self, max_items: int = 10) -> str:
        """Convert to Markdown format for LLM consumption"""
        if self.error:
            return f"Search error: {self.error}"
        if not self.items:
            return f"No results found for \"{self.query}\"."
        lines = [f"## Search Results: {self.query}", ""]
        for i, item in enumerate(self.items[:max_items], 1):
            lines.append(f"{i}. **{item.title}**")
            lines.append(f"   - URL: {item.url}")
            if item.content:
                snippet = item.content.replace("\n", " ")[:300]
                lines.append(f"   - Snippet: {snippet}")
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
    SearXNG Aggregated Search Tool

    Config:
        SEARXNG_HOST — SearXNG instance URL (default http://localhost:8081)
    """

    def __init__(self, host: Optional[str] = None):
        self._host = (host or os.environ.get("SEARXNG_HOST", "http://localhost:8081")).rstrip("/")

    async def search(
        self,
        query: str,
        categories: str = "general",
        language: str = "en-US",
        max_results: int = 10,
    ) -> SearchResult:
        """
        Execute a search query

        Args:
            query: Search keywords
            categories: Search category (general/images/news/science/it)
            language: Language code
            max_results: Maximum results to return
        """
        if not query or not query.strip():
            return SearchResult(query="", error="Search query cannot be empty")

        try:
            import aiohttp
        except ImportError:
            return SearchResult(
                query=query,
                error="aiohttp is not installed. Install it: pip install aiohttp",
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
                        logger.warning("SearXNG returned non-200: %s %s", resp.status, text[:200])
                        return SearchResult(
                            query=query,
                            error=f"SearXNG returned HTTP {resp.status}. Check if SearXNG is running ({self._host})",
                        )
                    data = await resp.json()
        except aiohttp.ClientConnectorError as e:
            logger.warning("Cannot connect to SearXNG: %s", e)
            return SearchResult(
                query=query,
                error=f"Cannot connect to SearXNG ({self._host}). Ensure the service is running: docker compose up searxng",
            )
        except Exception as e:
            logger.warning("SearXNG query failed: %s", e)
            return SearchResult(query=query, error=f"Search request failed: {e}")

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

    # ── ToolSpec compatibility ──

    async def invoke(self, query: str, categories: str = "general", language: str = "en-US", max_results: int = 10) -> str:
        """Unified interface for ToolRegistry, returns Markdown text"""
        result = await self.search(query, categories, language, max_results)
        return result.to_markdown()

    def to_tool_spec(self) -> Dict[str, Any]:
        return {
            "name": "search.web",
            "description": (
                "Use SearXNG aggregated search engine to query web information. "
                "Supports general web pages, images, news, IT tech, and more. "
                "Prioritize this tool when the user asks about real-time info, news, "
                "technical docs, or fact-checking."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keywords",
                    },
                    "categories": {
                        "type": "string",
                        "default": "general",
                        "description": "Category: general, images, news, science, it",
                    },
                    "language": {
                        "type": "string",
                        "default": "en-US",
                        "description": "Language code, e.g. en-US, zh-CN",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 10,
                        "description": "Max results (1-20)",
                    },
                },
                "required": ["query"],
            },
        }
