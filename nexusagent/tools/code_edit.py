"""
NexusAgent v4.0+ — Code Editing Tool Suite

提供精确的代码修改能力：搜索替换、插入行、删除行。
所有修改操作均受路径遍历保护，且需 NEXUS_ALLOW_FILE_OPS=1。

P0 能力:
- code.search_replace: 文件中搜索并替换文本
- code.insert: 在指定位置插入行
- code.delete: 删除指定行范围
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from nexusagent.utils.cross_platform import CrossPlatformPath

logger = logging.getLogger("nexus.tools.code_edit")


def _sanitize_path(path: str) -> Optional[str]:
    if not path:
        return None
    root = os.path.realpath(os.getcwd())
    cpp = CrossPlatformPath()
    if os.path.isabs(path):
        full = os.path.realpath(path)
    else:
        full = os.path.realpath(os.path.join(root, path))
    if not cpp.is_safe(full, root):
        return None
    return full


def _check_write_allowed() -> Optional[str]:
    if os.getenv("NEXUS_ALLOW_FILE_OPS", "0") != "1":
        return (
            "代码编辑已被禁用。"
            "设置 NEXUS_ALLOW_FILE_OPS=1 以启用（仅限受信任环境）。"
        )
    return None


# ═══════════════════════════════════════════════════════════════
# code.search_replace
# ═══════════════════════════════════════════════════════════════

class CodeSearchReplaceTool:
    """在文件中搜索并替换文本"""

    async def invoke(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> str:
        blocked = _check_write_allowed()
        if blocked:
            return f"[ERROR] {blocked}"
        safe = _sanitize_path(path)
        if safe is None:
            return f"[ERROR] 路径不安全: {path}"
        if not os.path.isfile(safe):
            return f"[ERROR] 文件不存在: {path}"
        try:
            with open(safe, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            if old_string not in content:
                return f"[ERROR] 未找到匹配文本: {old_string[:80]}..."

            if replace_all:
                count = content.count(old_string)
                new_content = content.replace(old_string, new_string)
                message = f"[OK] 已替换 {count} 处匹配"
            else:
                if content.count(old_string) > 1:
                    return (
                        f"[ERROR] 找到 {content.count(old_string)} 处匹配，"
                        f"但 replace_all=false。请确保 old_string 唯一或设置 replace_all=true。"
                    )
                new_content = content.replace(old_string, new_string, 1)
                message = "[OK] 已替换 1 处匹配"

            with open(safe, "w", encoding="utf-8") as f:
                f.write(new_content)
            return message
        except Exception as e:
            return f"[ERROR] 替换失败: {e}"

    def to_tool_spec(self) -> Dict[str, Any]:
        return {
            "name": "code.search_replace",
            "description": "在文件中搜索 old_string 并替换为 new_string。支持单次或全部替换。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "old_string": {"type": "string", "description": "要搜索的文本（必须精确匹配）"},
                    "new_string": {"type": "string", "description": "替换后的文本"},
                    "replace_all": {"type": "boolean", "default": False, "description": "是否替换所有匹配"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        }


# ═══════════════════════════════════════════════════════════════
# code.insert
# ═══════════════════════════════════════════════════════════════

class CodeInsertTool:
    """在文件指定位置插入行"""

    async def invoke(
        self,
        path: str,
        content: str,
        line: int = 0,
        after_text: str = "",
    ) -> str:
        blocked = _check_write_allowed()
        if blocked:
            return f"[ERROR] {blocked}"
        safe = _sanitize_path(path)
        if safe is None:
            return f"[ERROR] 路径不安全: {path}"
        if not os.path.isfile(safe):
            return f"[ERROR] 文件不存在: {path}"
        try:
            with open(safe, "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()

            if after_text:
                # 在匹配文本所在行之后插入
                inserted = False
                for i, existing in enumerate(lines):
                    if after_text in existing:
                        lines.insert(i + 1, content)
                        inserted = True
                        break
                if not inserted:
                    return f"[ERROR] 未找到匹配行: {after_text[:80]}..."
                message = f"[OK] 已在匹配行后插入"
            else:
                # 在指定行号处插入（1-based）
                idx = max(0, min(line - 1, len(lines)))
                lines.insert(idx, content)
                message = f"[OK] 已在第 {idx + 1} 行插入"

            with open(safe, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            return message
        except Exception as e:
            return f"[ERROR] 插入失败: {e}"

    def to_tool_spec(self) -> Dict[str, Any]:
        return {
            "name": "code.insert",
            "description": "在文件指定位置插入一行或多行内容。可通过 line 指定行号，或通过 after_text 在匹配行后插入。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "content": {"type": "string", "description": "要插入的内容"},
                    "line": {"type": "integer", "default": 0, "description": "插入位置的行号（1-based，0=末尾）"},
                    "after_text": {"type": "string", "default": "", "description": "在包含此文本的行后插入"},
                },
                "required": ["path", "content"],
            },
        }


# ═══════════════════════════════════════════════════════════════
# code.delete
# ═══════════════════════════════════════════════════════════════

class CodeDeleteTool:
    """删除文件中的指定行范围"""

    async def invoke(
        self,
        path: str,
        start_line: int,
        end_line: int = 0,
    ) -> str:
        blocked = _check_write_allowed()
        if blocked:
            return f"[ERROR] {blocked}"
        safe = _sanitize_path(path)
        if safe is None:
            return f"[ERROR] 路径不安全: {path}"
        if not os.path.isfile(safe):
            return f"[ERROR] 文件不存在: {path}"
        try:
            with open(safe, "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()

            if end_line == 0:
                end_line = start_line

            # 转换为 0-based 索引
            start_idx = max(1, start_line) - 1
            end_idx = min(len(lines), end_line)

            if start_idx >= len(lines) or start_idx >= end_idx:
                return f"[ERROR] 无效的行范围: {start_line}-{end_line} (文件共 {len(lines)} 行)"

            deleted = lines[start_idx:end_idx]
            remaining = lines[:start_idx] + lines[end_idx:]

            with open(safe, "w", encoding="utf-8") as f:
                f.write("\n".join(remaining) + "\n")

            return f"[OK] 已删除第 {start_line}-{end_line} 行 ({len(deleted)} 行)"
        except Exception as e:
            return f"[ERROR] 删除失败: {e}"

    def to_tool_spec(self) -> Dict[str, Any]:
        return {
            "name": "code.delete",
            "description": "删除文件中指定范围的行（1-based，含首尾）。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "start_line": {"type": "integer", "description": "起始行号（1-based）"},
                    "end_line": {"type": "integer", "default": 0, "description": "结束行号（0=与start_line相同）"},
                },
                "required": ["path", "start_line"],
            },
        }
