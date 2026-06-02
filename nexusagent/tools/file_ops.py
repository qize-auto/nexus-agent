"""
NexusAgent v4.0+ — File Operations Tool Suite

提供完整的文件读写、目录浏览、文件管理能力。
所有路径操作均受路径遍历保护，限制在项目根目录内。

P0 能力:
- file.read: 读取文本文件
- file.read_binary: 读取二进制文件 (base64)
- file.write: 创建/覆盖文件
- file.list: 列出目录内容
- file.move: 移动/重命名文件
- file.delete: 删除文件
"""

from __future__ import annotations

import base64
import logging
import os
import shutil
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from nexusagent.utils.cross_platform import CrossPlatformPath

logger = logging.getLogger("nexus.tools.file_ops")


# ── 安全配置 ──
_MAX_READ_SIZE = 1024 * 1024  # 1MB
_MAX_BINARY_SIZE = 5 * 1024 * 1024  # 5MB


def _get_project_root() -> str:
    return os.path.realpath(os.getcwd())


def _sanitize_path(path: str) -> Optional[str]:
    """路径遍历防护: 确保解析后的路径在项目根目录范围内"""
    if not path:
        return None
    root = _get_project_root()
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
            "文件写入/修改/删除已被禁用。"
            "设置 NEXUS_ALLOW_FILE_OPS=1 以启用（仅限受信任环境）。"
        )
    return None


# ═══════════════════════════════════════════════════════════════
# file.read
# ═══════════════════════════════════════════════════════════════

class FileReadTool:
    """读取文本文件内容"""

    async def invoke(self, path: str, offset: int = 0, limit: int = 0) -> str:
        safe = _sanitize_path(path)
        if safe is None:
            return f"[ERROR] 路径不安全或超出项目范围: {path}"
        if not os.path.isfile(safe):
            return f"[ERROR] 文件不存在: {path}"
        try:
            with open(safe, "r", encoding="utf-8", errors="replace") as f:
                if offset > 0:
                    f.seek(offset)
                content = f.read(_MAX_READ_SIZE) if limit == 0 else f.read(limit)
                return content
        except Exception as e:
            return f"[ERROR] 读取失败: {e}"

    def to_tool_spec(self) -> Dict[str, Any]:
        return {
            "name": "file.read",
            "description": "读取指定文本文件的内容。支持偏移和长度限制。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径（相对项目根目录或绝对路径）"},
                    "offset": {"type": "integer", "default": 0, "description": "起始字符偏移"},
                    "limit": {"type": "integer", "default": 0, "description": "最大读取字符数（0=不限制）"},
                },
                "required": ["path"],
            },
        }


# ═══════════════════════════════════════════════════════════════
# file.read_binary
# ═══════════════════════════════════════════════════════════════

class FileReadBinaryTool:
    """读取二进制文件并返回 base64"""

    async def invoke(self, path: str) -> str:
        safe = _sanitize_path(path)
        if safe is None:
            return f"[ERROR] 路径不安全或超出项目范围: {path}"
        if not os.path.isfile(safe):
            return f"[ERROR] 文件不存在: {path}"
        try:
            size = os.path.getsize(safe)
            if size > _MAX_BINARY_SIZE:
                return f"[ERROR] 文件过大 ({size} bytes)，上限 {_MAX_BINARY_SIZE} bytes"
            with open(safe, "rb") as f:
                data = f.read()
            return base64.b64encode(data).decode("ascii")
        except Exception as e:
            return f"[ERROR] 读取失败: {e}"

    def to_tool_spec(self) -> Dict[str, Any]:
        return {
            "name": "file.read_binary",
            "description": "读取二进制文件并返回 base64 编码内容。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                },
                "required": ["path"],
            },
        }


# ═══════════════════════════════════════════════════════════════
# file.write
# ═══════════════════════════════════════════════════════════════

class FileWriteTool:
    """创建或覆盖文件"""

    async def invoke(self, path: str, content: str, append: bool = False) -> str:
        blocked = _check_write_allowed()
        if blocked:
            return f"[ERROR] {blocked}"
        safe = _sanitize_path(path)
        if safe is None:
            return f"[ERROR] 路径不安全或超出项目范围: {path}"
        try:
            os.makedirs(os.path.dirname(safe), exist_ok=True)
            mode = "a" if append else "w"
            with open(safe, mode, encoding="utf-8") as f:
                f.write(content)
            action = "追加" if append else "写入"
            return f"[OK] {action} {len(content)} 字符到 {path}"
        except Exception as e:
            return f"[ERROR] 写入失败: {e}"

    def to_tool_spec(self) -> Dict[str, Any]:
        return {
            "name": "file.write",
            "description": "创建新文件或覆盖/追加现有文件内容。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "content": {"type": "string", "description": "要写入的内容"},
                    "append": {"type": "boolean", "default": False, "description": "是否追加模式"},
                },
                "required": ["path", "content"],
            },
        }


# ═══════════════════════════════════════════════════════════════
# file.list
# ═══════════════════════════════════════════════════════════════

@dataclass
class ListEntry:
    name: str
    type: str  # "file" | "directory"
    size: int = 0


class FileListTool:
    """列出目录内容"""

    async def invoke(self, path: str = ".", recursive: bool = False) -> str:
        safe = _sanitize_path(path)
        if safe is None:
            return f"[ERROR] 路径不安全或超出项目范围: {path}"
        if not os.path.isdir(safe):
            return f"[ERROR] 目录不存在: {path}"
        try:
            entries: List[str] = []
            if recursive:
                for root, dirs, files in os.walk(safe):
                    # 排除隐藏目录和 __pycache__
                    dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                    rel_root = os.path.relpath(root, _get_project_root())
                    for d in sorted(dirs):
                        entries.append(f"[DIR]  {os.path.join(rel_root, d)}")
                    for f in sorted(files):
                        if f.startswith("."):
                            continue
                        fp = os.path.join(root, f)
                        size = os.path.getsize(fp)
                        entries.append(f"[FILE] {os.path.join(rel_root, f)} ({size} bytes)")
            else:
                for entry in sorted(os.listdir(safe)):
                    if entry.startswith(".") or entry == "__pycache__":
                        continue
                    full = os.path.join(safe, entry)
                    if os.path.isdir(full):
                        entries.append(f"[DIR]  {entry}")
                    else:
                        size = os.path.getsize(full)
                        entries.append(f"[FILE] {entry} ({size} bytes)")
            return "\n".join(entries) if entries else "(空目录)"
        except Exception as e:
            return f"[ERROR] 列出目录失败: {e}"

    def to_tool_spec(self) -> Dict[str, Any]:
        return {
            "name": "file.list",
            "description": "列出指定目录的内容。支持递归列出子目录。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": ".", "description": "目录路径"},
                    "recursive": {"type": "boolean", "default": False, "description": "是否递归"},
                },
                "required": [],
            },
        }


# ═══════════════════════════════════════════════════════════════
# file.move
# ═══════════════════════════════════════════════════════════════

class FileMoveTool:
    """移动或重命名文件/目录"""

    async def invoke(self, source: str, destination: str) -> str:
        blocked = _check_write_allowed()
        if blocked:
            return f"[ERROR] {blocked}"
        safe_src = _sanitize_path(source)
        safe_dst = _sanitize_path(destination)
        if safe_src is None:
            return f"[ERROR] 源路径不安全: {source}"
        if safe_dst is None:
            return f"[ERROR] 目标路径不安全: {destination}"
        if not os.path.exists(safe_src):
            return f"[ERROR] 源不存在: {source}"
        try:
            os.makedirs(os.path.dirname(safe_dst), exist_ok=True)
            shutil.move(safe_src, safe_dst)
            return f"[OK] 已移动 {source} → {destination}"
        except Exception as e:
            return f"[ERROR] 移动失败: {e}"

    def to_tool_spec(self) -> Dict[str, Any]:
        return {
            "name": "file.move",
            "description": "移动或重命名文件/目录。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "源路径"},
                    "destination": {"type": "string", "description": "目标路径"},
                },
                "required": ["source", "destination"],
            },
        }


# ═══════════════════════════════════════════════════════════════
# file.delete
# ═══════════════════════════════════════════════════════════════

class FileDeleteTool:
    """删除文件或空目录"""

    async def invoke(self, path: str, recursive: bool = False) -> str:
        blocked = _check_write_allowed()
        if blocked:
            return f"[ERROR] {blocked}"
        safe = _sanitize_path(path)
        if safe is None:
            return f"[ERROR] 路径不安全: {path}"
        if not os.path.exists(safe):
            return f"[ERROR] 路径不存在: {path}"
        try:
            if os.path.isfile(safe):
                os.remove(safe)
                return f"[OK] 已删除文件: {path}"
            elif os.path.isdir(safe):
                if recursive:
                    shutil.rmtree(safe)
                    return f"[OK] 已递归删除目录: {path}"
                else:
                    os.rmdir(safe)
                    return f"[OK] 已删除空目录: {path}"
            return f"[ERROR] 未知类型: {path}"
        except Exception as e:
            return f"[ERROR] 删除失败: {e}"

    def to_tool_spec(self) -> Dict[str, Any]:
        return {
            "name": "file.delete",
            "description": "删除文件或目录。recursive=true 可删除非空目录。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要删除的路径"},
                    "recursive": {"type": "boolean", "default": False, "description": "是否递归删除目录"},
                },
                "required": ["path"],
            },
        }
