"""
Tests for nexusagent.core.registry — Module Registry
"""

import pytest

from nexusagent.core.registry import (
    ModuleRegistry,
    ModuleSpec,
    ModuleState,
    SimpleModuleSpec,
    get_module_registry,
)


class MockModule(ModuleSpec):
    name = "mock.test"
    version = "1.0.0"
    description = "A mock module for testing"
    provides_tools = True

    def __init__(self):
        super().__init__()
        self.loaded = False
        self.initialized = False
        self.unloaded = False

    def on_load(self) -> bool:
        self.loaded = True
        return True

    def on_initialize(self) -> bool:
        self.initialized = True
        return True

    def on_unload(self) -> None:
        self.unloaded = True


class FailingModule(ModuleSpec):
    name = "failing.test"
    version = "1.0.0"

    def on_load(self) -> bool:
        return False


class TestModuleSpec:
    def test_default_state(self):
        spec = MockModule()
        assert spec.state == ModuleState.UNLOADED
        assert not spec.is_running

    def test_to_dict(self):
        spec = MockModule()
        d = spec.to_dict()
        assert d["name"] == "mock.test"
        assert d["version"] == "1.0.0"
        assert d["capabilities"]["tools"] is True
        assert d["capabilities"]["skills"] is False

    def test_health_check(self):
        spec = MockModule()
        health = spec.health_check()
        assert health["status"] in ("healthy", "unknown")
        assert health["state"] == "UNLOADED"

    def test_lifecycle_hooks(self):
        spec = MockModule()
        assert spec.on_load() is True
        assert spec.on_initialize() is True
        spec.on_unload()
        assert spec.loaded
        assert spec.initialized
        assert spec.unloaded


class TestModuleRegistry:
    def test_register_and_get(self):
        registry = ModuleRegistry()
        spec = MockModule()
        assert registry.register(spec) is True
        assert registry.get("mock.test") is spec

    def test_register_duplicate(self):
        registry = ModuleRegistry()
        registry.register(MockModule())
        assert registry.register(MockModule()) is False

    def test_register_no_name(self):
        registry = ModuleRegistry()
        bad = ModuleSpec()
        bad.name = ""
        assert registry.register(bad) is False

    def test_unregister(self):
        registry = ModuleRegistry()
        registry.register(MockModule())
        assert registry.unregister("mock.test") is True
        assert registry.get("mock.test") is None

    def test_load_and_initialize(self):
        registry = ModuleRegistry()
        spec = MockModule()
        registry.register(spec)
        assert registry.load("mock.test") is True
        assert spec.state == ModuleState.RUNNING
        assert registry.initialize("mock.test") is True
        assert spec.is_running

    def test_load_failure(self):
        registry = ModuleRegistry()
        spec = FailingModule()
        registry.register(spec)
        assert registry.load("failing.test") is False
        assert spec.state == ModuleState.FAILED

    def test_list_modules(self):
        registry = ModuleRegistry()
        registry.register(MockModule())
        modules = registry.list_modules()
        assert len(modules) == 1
        assert modules[0]["name"] == "mock.test"

    def test_list_by_capability(self):
        registry = ModuleRegistry()
        registry.register(MockModule())
        tools = registry.list_modules(capability="tools")
        assert len(tools) == 1
        skills = registry.list_modules(capability="skills")
        assert len(skills) == 0

    def test_search(self):
        registry = ModuleRegistry()
        registry.register(MockModule())
        results = registry.search("mock")
        assert len(results) == 1
        results = registry.search("nonexistent")
        assert len(results) == 0

    def test_dependency_resolution(self):
        registry = ModuleRegistry()

        class DepModule(ModuleSpec):
            name = "dep.child"
            dependencies = ["dep.parent"]

        class ParentModule(ModuleSpec):
            name = "dep.parent"

        registry.register(DepModule())
        registry.register(ParentModule())
        order = registry._resolve_dependencies()
        assert order.index("dep.parent") < order.index("dep.child")

    def test_circular_dependency(self):
        registry = ModuleRegistry()

        class A(ModuleSpec):
            name = "circular.a"
            dependencies = ["circular.b"]

        class B(ModuleSpec):
            name = "circular.b"
            dependencies = ["circular.a"]

        registry.register(A())
        registry.register(B())
        with pytest.raises(ValueError, match="循环依赖"):
            registry._resolve_dependencies()

    def test_health_check_all(self):
        registry = ModuleRegistry()
        registry.register(MockModule())
        health = registry.health_check_all()
        assert "mock.test" in health

    def test_stats(self):
        registry = ModuleRegistry()
        registry.register(MockModule())
        stats = registry.get_stats()
        assert stats["total_modules"] == 1
        assert stats["by_capability"]["tools"] == 1

    def test_load_all_and_initialize_all(self):
        registry = ModuleRegistry()
        registry.register(MockModule())
        load_results = registry.load_all()
        assert load_results["mock.test"] is True
        init_results = registry.initialize_all()
        assert init_results["mock.test"] is True

    def test_unload_all(self):
        registry = ModuleRegistry()
        spec = MockModule()
        registry.register(spec)
        registry.load("mock.test")
        registry.initialize("mock.test")
        registry.unload_all()
        assert spec.unloaded


class TestSimpleModuleSpec:
    def test_from_tool_instance(self):
        class FakeTool:
            def to_tool_spec(self):
                return {"name": "fake.tool", "description": "A fake tool"}

        spec = SimpleModuleSpec(FakeTool(), source="builtin")
        assert spec.name == "fake.tool"
        assert spec.description == "A fake tool"
        assert spec.provides_tools is True

    def test_health_check(self):
        class FakeTool:
            def to_tool_spec(self):
                return {"name": "fake.tool"}

        spec = SimpleModuleSpec(FakeTool())
        health = spec.health_check()
        assert health["status"] == "healthy"


class TestGlobalRegistry:
    def test_get_module_registry_singleton(self):
        r1 = get_module_registry()
        r2 = get_module_registry()
        assert r1 is r2
