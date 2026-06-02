"""
NexusAgent v4.0+ — Code Editing Tool Tests
覆盖: search_replace, insert, delete
"""

import os
import pytest

from nexusagent.tools.code_edit import (
    CodeSearchReplaceTool,
    CodeInsertTool,
    CodeDeleteTool,
)


class TestCodeSearchReplaceTool:
    @pytest.mark.asyncio
    async def test_replace_single(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "1")
        f = tmp_path / "test.py"
        f.write_text("hello world\nfoo bar\n", encoding="utf-8")
        os.chdir(tmp_path)
        tool = CodeSearchReplaceTool()
        result = await tool.invoke("test.py", "foo", "baz")
        assert "[OK]" in result
        assert f.read_text(encoding="utf-8") == "hello world\nbaz bar\n"

    @pytest.mark.asyncio
    async def test_replace_all(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "1")
        f = tmp_path / "test.py"
        f.write_text("a a a\n", encoding="utf-8")
        os.chdir(tmp_path)
        tool = CodeSearchReplaceTool()
        result = await tool.invoke("test.py", "a", "b", replace_all=True)
        assert "[OK]" in result
        assert f.read_text(encoding="utf-8") == "b b b\n"

    @pytest.mark.asyncio
    async def test_replace_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "1")
        f = tmp_path / "test.py"
        f.write_text("hello\n", encoding="utf-8")
        os.chdir(tmp_path)
        tool = CodeSearchReplaceTool()
        result = await tool.invoke("test.py", "missing", "x")
        assert "[ERROR]" in result
        assert "未找到" in result

    @pytest.mark.asyncio
    async def test_replace_multiple_no_all(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "1")
        f = tmp_path / "test.py"
        f.write_text("a a\n", encoding="utf-8")
        os.chdir(tmp_path)
        tool = CodeSearchReplaceTool()
        result = await tool.invoke("test.py", "a", "b")
        assert "[ERROR]" in result

    @pytest.mark.asyncio
    async def test_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "0")
        os.chdir(tmp_path)
        tool = CodeSearchReplaceTool()
        result = await tool.invoke("x.py", "a", "b")
        assert "[ERROR]" in result


class TestCodeInsertTool:
    @pytest.mark.asyncio
    async def test_insert_at_line(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "1")
        f = tmp_path / "test.py"
        f.write_text("line1\nline2\n", encoding="utf-8")
        os.chdir(tmp_path)
        tool = CodeInsertTool()
        result = await tool.invoke("test.py", "INSERTED", line=2)
        assert "[OK]" in result
        text = f.read_text(encoding="utf-8")
        assert "INSERTED" in text

    @pytest.mark.asyncio
    async def test_insert_after_text(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "1")
        f = tmp_path / "test.py"
        f.write_text("def foo():\n    pass\n", encoding="utf-8")
        os.chdir(tmp_path)
        tool = CodeInsertTool()
        result = await tool.invoke("test.py", "    new_line", after_text="def foo()")
        assert "[OK]" in result
        text = f.read_text(encoding="utf-8")
        assert "new_line" in text

    @pytest.mark.asyncio
    async def test_insert_after_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "1")
        f = tmp_path / "test.py"
        f.write_text("abc\n", encoding="utf-8")
        os.chdir(tmp_path)
        tool = CodeInsertTool()
        result = await tool.invoke("test.py", "x", after_text="missing")
        assert "[ERROR]" in result


class TestCodeDeleteTool:
    @pytest.mark.asyncio
    async def test_delete_single_line(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "1")
        f = tmp_path / "test.py"
        f.write_text("line1\nline2\nline3\n", encoding="utf-8")
        os.chdir(tmp_path)
        tool = CodeDeleteTool()
        result = await tool.invoke("test.py", start_line=2, end_line=2)
        assert "[OK]" in result
        assert f.read_text(encoding="utf-8") == "line1\nline3\n"

    @pytest.mark.asyncio
    async def test_delete_range(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "1")
        f = tmp_path / "test.py"
        f.write_text("a\nb\nc\nd\n", encoding="utf-8")
        os.chdir(tmp_path)
        tool = CodeDeleteTool()
        result = await tool.invoke("test.py", start_line=2, end_line=3)
        assert "[OK]" in result
        assert f.read_text(encoding="utf-8") == "a\nd\n"

    @pytest.mark.asyncio
    async def test_delete_invalid_range(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "1")
        f = tmp_path / "test.py"
        f.write_text("a\n", encoding="utf-8")
        os.chdir(tmp_path)
        tool = CodeDeleteTool()
        result = await tool.invoke("test.py", start_line=10)
        assert "[ERROR]" in result


class TestToolSpecs:
    def test_search_replace_spec(self):
        spec = CodeSearchReplaceTool().to_tool_spec()
        assert spec["name"] == "code.search_replace"

    def test_insert_spec(self):
        spec = CodeInsertTool().to_tool_spec()
        assert spec["name"] == "code.insert"

    def test_delete_spec(self):
        spec = CodeDeleteTool().to_tool_spec()
        assert spec["name"] == "code.delete"
