"""
NexusAgent v4.0+ — 文档转换工具

将各种文件格式转换为 Markdown，供 LLM 阅读和分析。
支持格式:
  - 文本类: .txt, .md, .py, .json, .csv, .yaml, .yml, .xml, .html
  - Office:  .pdf, .docx, .pptx, .xlsx (需 markitdown)
  - 图片:    .png, .jpg, .jpeg, .gif, .webp (可选 OCR)

路径安全: 限制在项目根目录 + uploads/ 子目录内
大小限制: 单文件 20MB

Usage:
    tool = DocumentConverterTool()
    result = await tool.convert("/path/to/file.pdf")
    print(result.text)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from nexusagent.tools.file_ops import _sanitize_path

logger = logging.getLogger("nexus.tools.document")

# ── 安全配置 ──
_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB

_TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst",
    ".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".go", ".rs", ".rb", ".php",
    ".json", ".csv", ".yaml", ".yml", ".xml", ".html", ".htm", ".css", ".sql",
    ".sh", ".bat", ".ps1", ".cmd",
    ".log", ".ini", ".conf", ".cfg", ".toml",
}

_OFFICE_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx"}

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}


@dataclass
class ConversionResult:
    """文档转换结果"""
    text: str
    file_path: str
    mime_type: str = ""
    file_size: int = 0
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "file_path": self.file_path,
            "mime_type": self.mime_type,
            "file_size": self.file_size,
            "error": self.error,
        }


class DocumentConverterTool:
    """
    文档转换工具 — 将文件转为 Markdown 文本
    """

    def __init__(self, uploads_dir: Optional[str] = None):
        self._uploads_dir = uploads_dir or os.path.join(os.getcwd(), "uploads")

    async def convert(self, file_path: str) -> ConversionResult:
        """
        将文件转换为 Markdown 文本

        Args:
            file_path: 文件路径（相对项目根目录或绝对路径）
        """
        # 路径安全校验
        safe = _sanitize_path(file_path)
        if safe is None:
            return ConversionResult(
                text="",
                file_path=file_path,
                error=f"路径不安全或超出项目范围: {file_path}",
            )
        if not os.path.isfile(safe):
            return ConversionResult(
                text="",
                file_path=file_path,
                error=f"文件不存在: {file_path}",
            )

        # 大小限制
        size = os.path.getsize(safe)
        if size > _MAX_FILE_SIZE:
            return ConversionResult(
                text="",
                file_path=file_path,
                file_size=size,
                error=f"文件过大 ({size / 1024 / 1024:.1f}MB)，上限 20MB",
            )

        ext = Path(safe).suffix.lower()

        try:
            if ext in _TEXT_EXTENSIONS:
                return await self._convert_text(safe, size)
            elif ext in _OFFICE_EXTENSIONS:
                return await self._convert_office(safe, size)
            elif ext in _IMAGE_EXTENSIONS:
                return await self._convert_image(safe, size)
            else:
                return ConversionResult(
                    text="",
                    file_path=file_path,
                    file_size=size,
                    error=f"不支持的文件格式: {ext}。支持: 文本、PDF、Office、图片",
                )
        except Exception as e:
            logger.error("文档转换失败 %s: %s", safe, e)
            return ConversionResult(
                text="",
                file_path=file_path,
                file_size=size,
                error=f"转换失败: {e}",
            )

    async def _convert_text(self, path: str, size: int) -> ConversionResult:
        """读取文本文件"""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return ConversionResult(
                text=content,
                file_path=path,
                mime_type="text/plain",
                file_size=size,
            )
        except Exception as e:
            return ConversionResult(
                text="",
                file_path=path,
                file_size=size,
                error=f"文本读取失败: {e}",
            )

    async def _convert_office(self, path: str, size: int) -> ConversionResult:
        """使用 markitdown 转换 Office/PDF 文件"""
        try:
            from markitdown import MarkItDown
        except ImportError:
            return ConversionResult(
                text="",
                file_path=path,
                file_size=size,
                error=(
                    "markitdown 未安装，无法转换 Office/PDF 文件。"
                    "请安装: pip install markitdown[all]"
                ),
            )

        try:
            md = MarkItDown()
            result = md.convert(path)
            return ConversionResult(
                text=result.text_content,
                file_path=path,
                mime_type="application/markdown",
                file_size=size,
            )
        except Exception as e:
            logger.warning("markitdown 转换失败 %s: %s", path, e)
            return ConversionResult(
                text="",
                file_path=path,
                file_size=size,
                error=f"markitdown 转换失败: {e}",
            )

    async def _convert_image(self, path: str, size: int) -> ConversionResult:
        """图片 OCR（可选）"""
        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            return ConversionResult(
                text="",
                file_path=path,
                file_size=size,
                error=(
                    "图片 OCR 需要 pytesseract 和 Pillow。"
                    "请安装: pip install pytesseract Pillow"
                ),
            )

        try:
            image = Image.open(path)
            text = pytesseract.image_to_string(image, lang="chi_sim+eng")
            return ConversionResult(
                text=text,
                file_path=path,
                mime_type="text/plain",
                file_size=size,
            )
        except Exception as e:
            return ConversionResult(
                text="",
                file_path=path,
                file_size=size,
                error=f"图片 OCR 失败: {e}",
            )

    def list_supported_formats(self) -> List[str]:
        """返回所有支持的文件扩展名"""
        return sorted(_TEXT_EXTENSIONS | _OFFICE_EXTENSIONS | _IMAGE_EXTENSIONS)

    # ── ToolSpec 兼容 ──

    async def invoke(self, file_path: str) -> str:
        """供 ToolRegistry 调用的统一接口"""
        result = await self.convert(file_path)
        if result.error:
            return f"[ERROR] {result.error}"
        header = f"<!-- 文件: {os.path.basename(result.file_path)} | 大小: {result.file_size} bytes -->\n\n"
        return header + result.text

    def to_tool_spec(self) -> Dict[str, Any]:
        formats = ", ".join(sorted(self.list_supported_formats()))
        return {
            "name": "document.convert",
            "description": (
                f"将文件转换为 Markdown 文本，供 LLM 阅读和分析。"
                f"支持格式: {formats}。"
                "当用户上传文件、要求阅读文档、提取 PDF 内容时使用此工具。"
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "文件路径（相对项目根目录或绝对路径）",
                    },
                },
                "required": ["file_path"],
            },
        }
