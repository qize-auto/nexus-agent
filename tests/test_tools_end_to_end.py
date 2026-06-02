"""
NexusAgent v4.0+ — End-to-End Tool Chain Integration Test

验证完整工作流: 读取文件 → 修改代码 → 执行命令验证 → 保存结果
"""

import os
import pytest

from nexusagent.tools.file_ops import FileReadTool, FileWriteTool
from nexusagent.tools.code_edit import CodeSearchReplaceTool
from nexusagent.tools.shell import ShellExecuteTool
from nexusagent.tools.registry import ToolRegistry


class TestEndToEndToolChain:
    """端到端工具链测试"""

    @pytest.mark.asyncio
    async def test_full_workflow_read_edit_execute(self, tmp_path, monkeypatch):
        """
        完整工作流:
        1. 创建初始 Python 文件
        2. 读取文件内容
        3. 搜索替换修改代码
        4. 执行验证
        5. 保存结果到新文件
        """
        monkeypatch.setenv("NEXUS_ALLOW_FILE_OPS", "1")
        monkeypatch.setenv("NEXUS_ALLOW_SHELL", "1")
        os.chdir(tmp_path)

        # Step 1: 创建初始文件
        initial_code = (
            "def greet():\n"
            "    return 'hello'\n"
            "\n"
            "if __name__ == '__main__':\n"
            "    print(greet())\n"
        )
        (tmp_path / "greet.py").write_text(initial_code, encoding="utf-8")

        # Step 2: 读取文件
        read_tool = FileReadTool()
        content = await read_tool.invoke("greet.py")
        assert "def greet()" in content

        # Step 3: 修改代码 (搜索替换)
        edit_tool = CodeSearchReplaceTool()
        result = await edit_tool.invoke(
            "greet.py",
            old_string="    return 'hello'",
            new_string="    return 'hello world'",
        )
        assert "[OK]" in result

        # 验证修改
        updated = (tmp_path / "greet.py").read_text(encoding="utf-8")
        assert "hello world" in updated

        # Step 4: 执行验证
        shell_tool = ShellExecuteTool()
        py_path = str(tmp_path / "greet.py").replace("\\", "/")
        result = await shell_tool.invoke(f'python "{py_path}"')
        assert "[EXIT 0]" in result
        assert "hello world" in result

        # Step 5: 保存结果摘要
        write_tool = FileWriteTool()
        summary = f"Test passed. Output: hello world\nModified file: greet.py\n"
        result = await write_tool.invoke("result.txt", summary)
        assert "[OK]" in result
        assert (tmp_path / "result.txt").exists()

    @pytest.mark.asyncio
    async def test_registry_discovers_all_tools(self):
        """验证 ToolRegistry 能发现所有内置工具"""
        registry = ToolRegistry()
        count = registry.discover_builtin_tools()
        assert count >= 10  # browser + code_interpreter + layer + guard + 6 file_ops + shell + 3 code_edit + api + archive + database

        # 验证关键工具已注册
        required_tools = [
            "browser.visit",
            "code_interpreter.execute",
            "file.read",
            "file.write",
            "file.list",
            "file.move",
            "file.delete",
            "file.read_binary",
            "shell.execute",
            "code.search_replace",
            "code.insert",
            "code.delete",
            "api.request",
            "archive.pack_unpack",
            "database.query",
        ]
        for name in required_tools:
            tool = registry.get(name)
            assert tool is not None, f"工具未注册: {name}"
            assert tool.metadata.enabled, f"工具被禁用: {name}"

    @pytest.mark.asyncio
    async def test_tool_registry_describe_for_llm(self):
        """验证 ReActEngine 可以获取所有工具描述"""
        registry = ToolRegistry()
        registry.discover_builtin_tools()
        descriptions = registry.describe_tools()
        names = [d["name"] for d in descriptions]

        assert "file.read" in names
        assert "file.write" in names
        assert "shell.execute" in names
        assert "code.search_replace" in names

        # 验证每个描述都有 LLM 需要的结构
        for desc in descriptions:
            assert "name" in desc
            assert "description" in desc
            assert "parameters" in desc

    def test_registry_stats(self):
        """验证注册中心统计信息正确"""
        registry = ToolRegistry()
        registry.discover_builtin_tools()
        stats = registry.get_stats()
        assert stats["total"] >= 10
        assert stats["enabled"] >= 10
        assert "builtin" in stats["sources"]
