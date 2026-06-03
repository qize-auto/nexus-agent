"""
Tests for nexusagent.core.bootstrap — Module Bootstrap
"""

import pytest

from nexusagent.core.registry import ModuleRegistry, ModuleState
from nexusagent.core.bootstrap import (
    bootstrap_modules,
    get_module_catalog,
    get_builtin_tool_modules,
    _DeclarativeModuleSpec,
)


class TestBootstrapModules:
    def test_register_all_modules(self):
        """所有核心模块应正确注册"""
        registry = ModuleRegistry()
        results = bootstrap_modules(registry)

        # 检查注册结果
        assert len(results) > 30, f"预期注册 >30 个模块，实际 {len(results)}"
        assert all(results.values()), "所有模块应注册成功"

        # 检查关键模块存在
        key_modules = [
            "tools.search.web",
            "tools.document.convert",
            "tools.rag.retrieve",
            "memory.hybrid",
            "memory.vector_store",
            "execution.react_engine",
            "execution.error_recovery",
            "security.guardrails",
            "cognition.dream_engine",
            "orchestration.orchestrator",
        ]
        for name in key_modules:
            assert registry.get(name) is not None, f"模块 {name} 未注册"

    def test_module_dependencies(self):
        """模块依赖关系应正确声明"""
        registry = ModuleRegistry()
        bootstrap_modules(registry)

        # rag.retrieve 依赖 vector_store
        rag = registry.get("tools.rag.retrieve")
        assert rag is not None
        assert "memory.vector_store" in rag.dependencies

        # hybrid 依赖 store 和 vector_store
        hybrid = registry.get("memory.hybrid")
        assert hybrid is not None
        assert "memory.store" in hybrid.dependencies
        assert "memory.vector_store" in hybrid.dependencies

        # dream_engine 依赖 hybrid
        dream = registry.get("cognition.dream_engine")
        assert dream is not None
        assert "memory.hybrid" in dream.dependencies

    def test_module_capabilities(self):
        """模块能力声明应正确"""
        registry = ModuleRegistry()
        bootstrap_modules(registry)

        # 工具模块
        search = registry.get("tools.search.web")
        assert search.provides_tools is True
        assert search.provides_skills is False

        # 记忆模块
        hybrid = registry.get("memory.hybrid")
        assert hybrid.provides_memory is True

        # 执行模块
        recovery = registry.get("execution.error_recovery")
        assert recovery.provides_skills is True

        # 适配模块
        adapter = registry.get("interface.adapter")
        assert adapter.provides_adapters is True

    def test_capability_index(self):
        """能力索引应正确构建"""
        registry = ModuleRegistry()
        bootstrap_modules(registry)

        tools = registry.get_by_capability("tools")
        assert len(tools) > 5, f"预期 >5 个工具模块，实际 {len(tools)}"

        memory = registry.get_by_capability("memory")
        assert len(memory) > 3, f"预期 >3 个记忆模块，实际 {len(memory)}"

        skills = registry.get_by_capability("skills")
        assert len(skills) > 10, f"预期 >10 个技能模块，实际 {len(skills)}"

    def test_tag_index(self):
        """标签索引应正确构建"""
        registry = ModuleRegistry()
        bootstrap_modules(registry)

        search_modules = registry.get_by_tag("search")
        assert len(search_modules) >= 1

        security_modules = registry.get_by_tag("security")
        assert len(security_modules) >= 3

    def test_tool_registry_module(self):
        """ToolRegistry 本身应作为模块注册"""
        registry = ModuleRegistry()
        bootstrap_modules(registry)

        tr = registry.get("tools.registry")
        assert tr is not None
        assert tr.provides_tools is True

    def test_initialize_all(self):
        """批量初始化应成功"""
        registry = ModuleRegistry()
        bootstrap_modules(registry)
        # 先加载（load 会自动调用 initialize）
        load_results = registry.load_all()
        assert all(load_results.values()), f"加载失败: {[k for k, v in load_results.items() if not v]}"

        # 所有模块状态应为 RUNNING
        for item in registry.list_modules():
            name = item["name"]
            spec = registry.get(name)
            assert spec.state == ModuleState.RUNNING, f"模块 {name} 状态异常: {spec.state}"

    def test_health_check_all(self):
        """健康检查应返回所有模块状态"""
        registry = ModuleRegistry()
        bootstrap_modules(registry)
        registry.load_all()

        health = registry.health_check_all()
        assert len(health) > 30

        # 所有模块至少应报告状态
        for name, status in health.items():
            assert "status" in status
            # 声明式模块有 module_path，但 tools.registry 是自定义的
            if name != "tools.registry":
                assert "module_path" in status
                assert "import_ok" in status


class TestModuleCatalog:
    def test_catalog_structure(self):
        """模块目录结构应正确"""
        catalog = get_module_catalog()
        assert len(catalog) > 30

        for item in catalog:
            assert "name" in item
            assert "description" in item
            assert "dependencies" in item
            assert "capabilities" in item
            assert "tags" in item

            # capabilities 应有四个维度
            caps = item["capabilities"]
            assert "tools" in caps
            assert "skills" in caps
            assert "adapters" in caps
            assert "memory" in caps

    def test_builtin_tool_modules(self):
        """内置工具模块列表应正确"""
        modules = get_builtin_tool_modules()
        assert len(modules) > 5

        # 验证关键工具模块存在
        assert "nexusagent.tools.search" in modules
        assert "nexusagent.tools.document" in modules
        assert "nexusagent.tools.rag" in modules
        assert "nexusagent.tools.browser" in modules


class TestDeclarativeModuleSpec:
    def test_on_load_import_check(self):
        """on_load 应检查模块可导入性"""
        spec = _DeclarativeModuleSpec(
            name="test.ok",
            module_path="nexusagent.tools.search",  # 确保可导入
        )
        assert spec.on_load() is True
        assert spec._import_ok is True

    def test_on_load_bad_module(self):
        """on_load 对不存在的模块应返回 False"""
        spec = _DeclarativeModuleSpec(
            name="test.bad",
            module_path="nexusagent.nonexistent.module_xyz",
        )
        assert spec.on_load() is False
        assert spec._import_ok is False

    def test_on_initialize_noop(self):
        """声明式模块的 on_initialize 应返回 True（不创建实例）"""
        spec = _DeclarativeModuleSpec(
            name="test.noop",
            module_path="nexusagent.tools.search",
        )
        assert spec.on_initialize() is True

    def test_health_check_with_import(self):
        """健康检查应反映导入状态"""
        spec = _DeclarativeModuleSpec(
            name="test.health",
            module_path="nexusagent.tools.search",
        )
        spec.on_load()
        health = spec.health_check()
        assert health["status"] == "healthy"
        assert health["import_ok"] is True

    def test_health_check_without_import(self):
        """未加载时的健康检查"""
        spec = _DeclarativeModuleSpec(
            name="test.noimport",
            module_path="nexusagent.tools.search",
        )
        health = spec.health_check()
        assert health["status"] == "degraded"
        assert health["import_ok"] is False

    def test_custom_health_checker(self):
        """自定义健康检查器"""
        spec = _DeclarativeModuleSpec(
            name="test.custom",
            module_path="nexusagent.tools.search",
            health_checker=lambda: {"custom_metric": 42},
        )
        spec.on_load()
        health = spec.health_check()
        assert health["custom_metric"] == 42

    def test_to_dict(self):
        """序列化应包含所有元数据"""
        spec = _DeclarativeModuleSpec(
            name="test.dict",
            module_path="nexusagent.tools.search",
            description="测试描述",
            version="2.0.0",
            dependencies=["dep1", "dep2"],
            provides_tools=True,
            tags=["test", "demo"],
        )
        d = spec.to_dict()
        assert d["name"] == "test.dict"
        assert d["description"] == "测试描述"
        assert d["version"] == "2.0.0"
        assert d["dependencies"] == ["dep1", "dep2"]
        assert d["capabilities"]["tools"] is True
        assert d["tags"] == ["test", "demo"]


class TestIntegrationWithNexusAgent:
    @pytest.mark.asyncio
    async def test_nexusagent_initializes_registry(self):
        """NexusAgent 初始化后应包含 ModuleRegistry"""
        from nexusagent.main import NexusAgent
        from nexusagent.config.settings import AppConfig

        config = AppConfig()
        agent = NexusAgent(config)
        await agent.initialize()

        assert agent._module_registry is not None
        # 检查关键模块已注册
        assert agent._module_registry.get("tools.search.web") is not None
        assert agent._module_registry.get("memory.hybrid") is not None
        assert agent._module_registry.get("execution.react_engine") is not None

        # 健康检查
        health = agent._module_registry.health_check_all()
        assert len(health) > 30

    @pytest.mark.asyncio
    async def test_nexusagent_registry_health(self):
        """NexusAgent 的 ModuleRegistry 健康检查应通过"""
        from nexusagent.main import NexusAgent
        from nexusagent.config.settings import AppConfig

        config = AppConfig()
        agent = NexusAgent(config)
        await agent.initialize()

        health = agent._module_registry.health_check_all()
        # 所有已加载的模块应报告 healthy 或 degraded（未导入的会 degraded）
        for name, status in health.items():
            assert status["status"] in ("healthy", "degraded", "unknown")
