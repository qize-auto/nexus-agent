"""
NexusAgent v4.0+ — Archive Tool Tests
覆盖: zip, unzip, tar, untar
"""

import os
import pytest

from nexusagent.tools.archive import ArchiveTool


class TestArchiveTool:
    @pytest.mark.asyncio
    async def test_zip_and_unzip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "1")
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("hello", encoding="utf-8")
        dst_zip = tmp_path / "archive.zip"
        extract_dir = tmp_path / "extracted"
        os.chdir(tmp_path)

        tool = ArchiveTool()
        result = await tool.invoke("zip", str(src), str(dst_zip))
        assert "[OK]" in result

        result2 = await tool.invoke("unzip", str(dst_zip), str(extract_dir))
        assert "[OK]" in result2
        assert (extract_dir / "a.txt").read_text(encoding="utf-8") == "hello"

    @pytest.mark.asyncio
    async def test_tar_and_untar(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "1")
        src = tmp_path / "src"
        src.mkdir()
        (src / "b.txt").write_text("world", encoding="utf-8")
        dst_tar = tmp_path / "archive.tar.gz"
        extract_dir = tmp_path / "extracted"
        os.chdir(tmp_path)

        tool = ArchiveTool()
        result = await tool.invoke("tar", str(src), str(dst_tar))
        assert "[OK]" in result

        result2 = await tool.invoke("untar", str(dst_tar), str(extract_dir))
        assert "[OK]" in result2
        # tar preserves directory structure: src/b.txt
        assert (extract_dir / "src" / "b.txt").read_text(encoding="utf-8") == "world"

    @pytest.mark.asyncio
    async def test_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "0")
        os.chdir(tmp_path)
        tool = ArchiveTool()
        result = await tool.invoke("zip", "a", "b")
        assert "[ERROR]" in result

    def test_to_tool_spec(self):
        spec = ArchiveTool().to_tool_spec()
        assert spec["name"] == "archive.pack_unpack"
