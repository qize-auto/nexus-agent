"""
Tests for {{module_name}}

运行: pytest templates/module/tests/test_module.py -v
"""

import pytest

from ..{{module_name}}_spec import {{ModuleName}}Spec


class Test{{ModuleName}}Spec:
    def test_module_metadata(self):
        spec = {{ModuleName}}Spec()
        assert spec.name == "{{module_name}}"
        assert spec.version == "0.1.0"
        assert spec.provides_tools is True

    def test_health_check(self):
        spec = {{ModuleName}}Spec()
        health = spec.health_check()
        assert "status" in health
        assert health["status"] in ("healthy", "unknown")

    def test_lifecycle(self):
        spec = {{ModuleName}}Spec()
        assert spec.state.name == "UNLOADED"
        assert spec.on_load() is True
        assert spec.on_initialize() is True

    @pytest.mark.asyncio
    async def test_handler(self):
        from ..handlers import example_handler
        result = await example_handler("test query")
        assert "test query" in result
