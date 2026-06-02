"""
NexusAgent v4.0+ — Database Tool Tests
覆盖: SELECT, INSERT, DDL blocking
"""

import os
import pytest

from nexusagent.tools.database import DatabaseTool


class TestDatabaseTool:
    @pytest.mark.asyncio
    async def test_select_query(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "1")
        db = tmp_path / "test.db"
        os.chdir(tmp_path)
        tool = DatabaseTool()
        # 先创建表和插入数据
        await tool.invoke(str(db), "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        await tool.invoke(str(db), "INSERT INTO users (name) VALUES ('Alice'), ('Bob')")
        result = await tool.invoke(str(db), "SELECT * FROM users")
        assert "Alice" in result
        assert "Bob" in result

    @pytest.mark.asyncio
    async def test_ddl_blocked(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "0")
        db = tmp_path / "test.db"
        os.chdir(tmp_path)
        tool = DatabaseTool()
        result = await tool.invoke(str(db), "DROP TABLE IF EXISTS x")
        assert "[ERROR]" in result
        assert "禁用" in result

    @pytest.mark.asyncio
    async def test_dml_write_blocked(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "0")
        db = tmp_path / "test.db"
        os.chdir(tmp_path)
        tool = DatabaseTool()
        result = await tool.invoke(str(db), "INSERT INTO x VALUES (1)")
        assert "[ERROR]" in result

    @pytest.mark.asyncio
    async def test_empty_result(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "1")
        db = tmp_path / "empty.db"
        os.chdir(tmp_path)
        tool = DatabaseTool()
        await tool.invoke(str(db), "CREATE TABLE t (id INT)")
        result = await tool.invoke(str(db), "SELECT * FROM t")
        assert "0 行" in result

    def test_to_tool_spec(self):
        spec = DatabaseTool().to_tool_spec()
        assert spec["name"] == "database.query"
