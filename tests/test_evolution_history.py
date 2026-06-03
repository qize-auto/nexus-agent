"""
Tests for nexusagent.evolution.history — Config History
"""

import json
import tempfile
from pathlib import Path

import pytest

from nexusagent.evolution.history import ConfigHistory, ConfigVersion


class TestConfigHistory:
    @pytest.fixture
    def history(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield ConfigHistory(tmp)

    def test_save_and_load(self, history):
        version = history.save(
            dimension="prompt",
            config={"system_prompt": "hello"},
            description="初始配置",
        )
        assert version.dimension == "prompt"
        assert version.config == {"system_prompt": "hello"}

        loaded = history.load("prompt", version.version_id)
        assert loaded is not None
        assert loaded.config == {"system_prompt": "hello"}

    def test_list_versions(self, history):
        history.save("prompt", {"v": 1}, "版本1")
        history.save("prompt", {"v": 2}, "版本2")
        history.save("prompt", {"v": 3}, "版本3")

        versions = history.list("prompt")
        assert len(versions) == 3
        # 倒序
        assert versions[0].config == {"v": 3}
        assert versions[1].config == {"v": 2}
        assert versions[2].config == {"v": 1}

    def test_get_current(self, history):
        history.save("prompt", {"v": 1}, "版本1")
        history.save("prompt", {"v": 2}, "版本2")

        current = history.get_current("prompt")
        assert current is not None
        assert current.config == {"v": 2}

    def test_rollback(self, history):
        v1 = history.save("prompt", {"v": 1}, "版本1")
        history.save("prompt", {"v": 2}, "版本2")

        rolled = history.rollback("prompt", v1.version_id)
        assert rolled is not None

        current = history.get_current("prompt")
        assert current is not None
        assert current.config == {"v": 1}
        assert "回滚" in current.description

    def test_rollback_nonexistent(self, history):
        result = history.rollback("prompt", "nonexistent")
        assert result is None

    def test_diff(self, history):
        v1 = history.save("prompt", {"a": 1, "b": 2}, "版本1")
        v2 = history.save("prompt", {"a": 1, "b": 3, "c": 4}, "版本2")

        diff = history.diff("prompt", v1.version_id, v2.version_id)
        assert "changed" in diff
        assert "added" in diff
        assert "removed" in diff

    def test_delete_dimension(self, history):
        history.save("prompt", {"v": 1}, "版本1")
        assert history.delete_dimension("prompt") is True
        assert history.list("prompt") == []
        assert history.delete_dimension("nonexistent") is False

    def test_cleanup_old_versions(self, history):
        # 保存超过 50 个版本
        for i in range(55):
            history.save("prompt", {"v": i}, f"版本{i}")

        versions = history.list("prompt")
        assert len(versions) <= 50

    def test_get_stats(self, history):
        history.save("prompt", {"v": 1}, "版本1")
        history.save("tool_map", {"v": 1}, "版本1")

        stats = history.get_stats()
        assert stats["prompt"] == 1
        assert stats["tool_map"] == 1

    def test_invalid_version_file_ignored(self, history):
        dim_dir = history._dim_dir("prompt")
        bad_file = dim_dir / "bad.json"
        bad_file.write_text("not json", encoding="utf-8")

        versions = history.list("prompt")
        assert versions == []


class TestConfigVersion:
    def test_to_dict(self):
        v = ConfigVersion(
            version_id="v1",
            dimension="prompt",
            config={"a": 1},
            timestamp=123.0,
            description="测试",
        )
        d = v.to_dict()
        assert d["version_id"] == "v1"
        assert d["config"] == {"a": 1}

    def test_from_dict(self):
        d = {
            "version_id": "v2",
            "dimension": "budget",
            "config": {"b": 2},
            "timestamp": 456.0,
            "description": "测试2",
        }
        v = ConfigVersion.from_dict(d)
        assert v.version_id == "v2"
        assert v.config == {"b": 2}
