"""
NexusAgent v4.0+ — File Operations Tool Tests
覆盖: read, read_binary, write, list, move, delete
"""

import base64
import os
import tempfile

import pytest

from nexusagent.tools.file_ops import (
    FileReadTool,
    FileReadBinaryTool,
    FileWriteTool,
    FileListTool,
    FileMoveTool,
    FileDeleteTool,
    _sanitize_path,
)


class TestSanitizePath:
    def test_safe_relative_path(self):
        result = _sanitize_path("tests")
        assert result is not None

    def test_traversal_blocked(self):
        result = _sanitize_path("../../etc/passwd")
        assert result is None

    def test_absolute_outside_blocked(self):
        result = _sanitize_path("/etc/passwd")
        assert result is None


class TestFileReadTool:
    @pytest.mark.asyncio
    async def test_read_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        os.chdir(tmp_path)
        tool = FileReadTool()
        result = await tool.invoke("test.txt")
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_read_nonexistent(self, tmp_path):
        os.chdir(tmp_path)
        tool = FileReadTool()
        result = await tool.invoke("missing.txt")
        assert "[ERROR]" in result
        assert "不存在" in result

    @pytest.mark.asyncio
    async def test_read_unsafe_path(self, tmp_path):
        os.chdir(tmp_path)
        tool = FileReadTool()
        result = await tool.invoke("../../etc/passwd")
        assert "[ERROR]" in result

    @pytest.mark.asyncio
    async def test_read_with_limit(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("1234567890", encoding="utf-8")
        os.chdir(tmp_path)
        tool = FileReadTool()
        result = await tool.invoke("test.txt", limit=5)
        assert result == "12345"


class TestFileReadBinaryTool:
    @pytest.mark.asyncio
    async def test_read_binary(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00\x01\x02\x03")
        os.chdir(tmp_path)
        tool = FileReadBinaryTool()
        result = await tool.invoke("data.bin")
        assert result == base64.b64encode(b"\x00\x01\x02\x03").decode("ascii")

    @pytest.mark.asyncio
    async def test_read_binary_nonexistent(self, tmp_path):
        os.chdir(tmp_path)
        tool = FileReadBinaryTool()
        result = await tool.invoke("missing.bin")
        assert "[ERROR]" in result


class TestFileWriteTool:
    @pytest.mark.asyncio
    async def test_write_new_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "1")
        os.chdir(tmp_path)
        tool = FileWriteTool()
        result = await tool.invoke("new.txt", "content here")
        assert "[OK]" in result
        assert (tmp_path / "new.txt").read_text(encoding="utf-8") == "content here"

    @pytest.mark.asyncio
    async def test_write_disabled_by_default(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "0")
        os.chdir(tmp_path)
        tool = FileWriteTool()
        result = await tool.invoke("new.txt", "content")
        assert "[ERROR]" in result
        assert "禁用" in result

    @pytest.mark.asyncio
    async def test_write_append(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "1")
        os.chdir(tmp_path)
        (tmp_path / "existing.txt").write_text("hello ", encoding="utf-8")
        tool = FileWriteTool()
        result = await tool.invoke("existing.txt", "world", append=True)
        assert "[OK]" in result
        assert (tmp_path / "existing.txt").read_text(encoding="utf-8") == "hello world"


class TestFileListTool:
    @pytest.mark.asyncio
    async def test_list_directory(self, tmp_path):
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "b.txt").write_text("b", encoding="utf-8")
        os.mkdir(tmp_path / "subdir")
        os.chdir(tmp_path)
        tool = FileListTool()
        result = await tool.invoke(".")
        assert "a.txt" in result
        assert "b.txt" in result
        assert "subdir" in result

    @pytest.mark.asyncio
    async def test_list_recursive(self, tmp_path):
        os.mkdir(tmp_path / "sub")
        (tmp_path / "sub" / "nested.txt").write_text("x", encoding="utf-8")
        os.chdir(tmp_path)
        tool = FileListTool()
        result = await tool.invoke(".", recursive=True)
        assert "nested.txt" in result

    @pytest.mark.asyncio
    async def test_list_empty(self, tmp_path):
        os.chdir(tmp_path)
        tool = FileListTool()
        result = await tool.invoke(".")
        assert "空目录" in result or result == "(空目录)"


class TestFileMoveTool:
    @pytest.mark.asyncio
    async def test_move_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "1")
        (tmp_path / "old.txt").write_text("data", encoding="utf-8")
        os.chdir(tmp_path)
        tool = FileMoveTool()
        result = await tool.invoke("old.txt", "new.txt")
        assert "[OK]" in result
        assert not (tmp_path / "old.txt").exists()
        assert (tmp_path / "new.txt").read_text(encoding="utf-8") == "data"

    @pytest.mark.asyncio
    async def test_move_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "0")
        os.chdir(tmp_path)
        tool = FileMoveTool()
        result = await tool.invoke("a", "b")
        assert "[ERROR]" in result


class TestFileDeleteTool:
    @pytest.mark.asyncio
    async def test_delete_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "1")
        (tmp_path / "del.txt").write_text("x", encoding="utf-8")
        os.chdir(tmp_path)
        tool = FileDeleteTool()
        result = await tool.invoke("del.txt")
        assert "[OK]" in result
        assert not (tmp_path / "del.txt").exists()

    @pytest.mark.asyncio
    async def test_delete_directory_recursive(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "1")
        os.mkdir(tmp_path / "dir")
        (tmp_path / "dir" / "f.txt").write_text("x", encoding="utf-8")
        os.chdir(tmp_path)
        tool = FileDeleteTool()
        result = await tool.invoke("dir", recursive=True)
        assert "[OK]" in result
        assert not (tmp_path / "dir").exists()

    @pytest.mark.asyncio
    async def test_delete_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "0")
        os.chdir(tmp_path)
        tool = FileDeleteTool()
        result = await tool.invoke("x.txt")
        assert "[ERROR]" in result


class TestToolSpecs:
    def test_file_read_spec(self):
        spec = FileReadTool().to_tool_spec()
        assert spec["name"] == "file.read"
        assert "path" in spec["input_schema"]["properties"]

    def test_file_write_spec(self):
        spec = FileWriteTool().to_tool_spec()
        assert spec["name"] == "file.write"
        assert "content" in spec["input_schema"]["properties"]

    def test_file_list_spec(self):
        spec = FileListTool().to_tool_spec()
        assert spec["name"] == "file.list"

    def test_file_move_spec(self):
        spec = FileMoveTool().to_tool_spec()
        assert spec["name"] == "file.move"

    def test_file_delete_spec(self):
        spec = FileDeleteTool().to_tool_spec()
        assert spec["name"] == "file.delete"

    def test_file_read_binary_spec(self):
        spec = FileReadBinaryTool().to_tool_spec()
        assert spec["name"] == "file.read_binary"
