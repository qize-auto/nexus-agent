"""
Tests for nexusagent.tools.document — Document conversion tool
"""

import os
import tempfile

import pytest

from nexusagent.tools.document import DocumentConverterTool, ConversionResult

# 项目根目录，用于创建安全的测试文件
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_TMP_DIR = os.path.join(PROJECT_ROOT, "tests", "tmp")


def _tmp_path(filename: str) -> str:
    """返回项目根目录内的临时文件路径"""
    os.makedirs(TEST_TMP_DIR, exist_ok=True)
    return os.path.join(TEST_TMP_DIR, filename)


class TestDocumentConverterTool:
    def test_to_tool_spec(self):
        tool = DocumentConverterTool()
        spec = tool.to_tool_spec()
        assert spec["name"] == "document.convert"
        assert "Markdown" in spec["description"]
        assert "file_path" in spec["input_schema"]["properties"]

    def test_list_supported_formats(self):
        tool = DocumentConverterTool()
        formats = tool.list_supported_formats()
        assert ".txt" in formats
        assert ".pdf" in formats
        assert ".docx" in formats
        assert ".png" in formats

    @pytest.mark.asyncio
    async def test_convert_text_file(self):
        path = _tmp_path("test_doc.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("Hello, NexusAgent!\n第二行内容。")
        try:
            tool = DocumentConverterTool()
            result = await tool.convert(path)
            assert result.success
            assert "Hello, NexusAgent!" in result.text
            assert "第二行内容" in result.text
            assert result.mime_type == "text/plain"
        finally:
            if os.path.exists(path):
                os.unlink(path)

    @pytest.mark.asyncio
    async def test_convert_python_file(self):
        path = _tmp_path("test_doc.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write("def hello():\n    return 'world'\n")
        try:
            tool = DocumentConverterTool()
            result = await tool.convert(path)
            assert result.success
            assert "def hello():" in result.text
        finally:
            if os.path.exists(path):
                os.unlink(path)

    @pytest.mark.asyncio
    async def test_convert_nonexistent_file(self):
        tool = DocumentConverterTool()
        result = await tool.convert("/path/that/does/not/exist.txt")
        assert not result.success
        assert "路径不安全" in result.error or "文件不存在" in result.error

    @pytest.mark.asyncio
    async def test_convert_unsupported_format(self):
        path = _tmp_path("test_doc.xyz")
        with open(path, "w") as f:
            f.write("unknown format")
        try:
            tool = DocumentConverterTool()
            result = await tool.convert(path)
            assert not result.success
            assert "不支持的文件格式" in result.error
        finally:
            if os.path.exists(path):
                os.unlink(path)

    @pytest.mark.asyncio
    async def test_convert_large_file(self):
        path = _tmp_path("test_large.txt")
        with open(path, "w") as f:
            # 写入超过 20MB 的内容
            f.write("x" * (21 * 1024 * 1024))
        try:
            tool = DocumentConverterTool()
            result = await tool.convert(path)
            assert not result.success
            assert "文件过大" in result.error
        finally:
            if os.path.exists(path):
                os.unlink(path)

    @pytest.mark.asyncio
    async def test_convert_outside_project(self):
        tool = DocumentConverterTool()
        # 尝试访问系统路径（应该被 _sanitize_path 拒绝）
        result = await tool.convert("C:/Windows/System32/drivers/etc/hosts")
        assert not result.success
        assert "路径不安全" in result.error or "文件不存在" in result.error

    @pytest.mark.asyncio
    async def test_invoke_returns_text(self):
        path = _tmp_path("test_invoke.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("invoke test content")
        try:
            tool = DocumentConverterTool()
            text = await tool.invoke(path)
            assert "invoke test content" in text
            assert "<!-- 文件:" in text
        finally:
            if os.path.exists(path):
                os.unlink(path)

    @pytest.mark.asyncio
    async def test_convert_json_file(self):
        path = _tmp_path("test_doc.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"key": "value", "number": 42}')
        try:
            tool = DocumentConverterTool()
            result = await tool.convert(path)
            assert result.success
            assert '"key": "value"' in result.text
        finally:
            if os.path.exists(path):
                os.unlink(path)
