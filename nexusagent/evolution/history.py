"""
NexusAgent v4.0+ — Config History 配置版本历史管理

职责:
    1. 保存每个配置维度的历史版本（最近 50 个）
    2. 支持回滚到任意历史版本
    3. 提供版本差异对比

存储结构:
    ~/.nexusagent/evolution/history/
        prompt/
            20250602_143000_xxxxxxxx.json
            20250602_150000_xxxxxxxx.json
        tool_map/
            ...
        budget/
            ...
        routing/
            ...
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nexus.evolution.history")


@dataclass
class ConfigVersion:
    """配置版本记录"""
    version_id: str
    dimension: str
    config: Dict[str, Any]
    timestamp: float
    description: str = ""
    proposal_id: Optional[str] = None
    deployed_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_id": self.version_id,
            "dimension": self.dimension,
            "config": self.config,
            "timestamp": self.timestamp,
            "description": self.description,
            "proposal_id": self.proposal_id,
            "deployed_by": self.deployed_by,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConfigVersion":
        return cls(**{
            k: v for k, v in data.items()
            if k in {f.name for f in cls.__dataclass_fields__.values()}
        })


class ConfigHistory:
    """
    配置版本历史管理器

    Usage:
        history = ConfigHistory("~/.nexusagent/evolution")
        history.save("prompt", current_prompt_config, description="优化系统提示词")
        versions = history.list("prompt")
        history.rollback("prompt", versions[0].version_id)
    """

    MAX_VERSIONS = 50  # 每个维度保留的最大版本数

    def __init__(self, base_dir: str):
        self._base = Path(base_dir) / "history"
        self._base.mkdir(parents=True, exist_ok=True)
        self._save_counter = 0  # 用于防止同一毫秒内的 version_id 冲突

    def _dim_dir(self, dimension: str) -> Path:
        """获取维度的存储目录"""
        d = self._base / dimension
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save(
        self,
        dimension: str,
        config: Dict[str, Any],
        description: str = "",
        proposal_id: Optional[str] = None,
        deployed_by: Optional[str] = None,
    ) -> ConfigVersion:
        """
        保存配置版本

        Returns:
            ConfigVersion: 保存的版本记录
        """
        self._save_counter += 1
        version_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time() * 1000) % 1000000:06d}_{self._save_counter:04d}"
        version = ConfigVersion(
            version_id=version_id,
            dimension=dimension,
            config=dict(config),
            timestamp=time.time(),
            description=description,
            proposal_id=proposal_id,
            deployed_by=deployed_by,
        )

        dim_dir = self._dim_dir(dimension)
        filepath = dim_dir / f"{version_id}.json"
        filepath.write_text(json.dumps(version.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

        # 清理旧版本
        self._cleanup_old_versions(dimension)

        logger.info("配置已保存: %s/%s (%s)", dimension, version_id, description)
        return version

    def load(self, dimension: str, version_id: str) -> Optional[ConfigVersion]:
        """加载指定版本"""
        filepath = self._dim_dir(dimension) / f"{version_id}.json"
        if not filepath.exists():
            return None
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            return ConfigVersion.from_dict(data)
        except Exception as e:
            logger.warning("加载配置版本失败 %s/%s: %s", dimension, version_id, e)
            return None

    def list(self, dimension: str, limit: int = 50) -> List[ConfigVersion]:
        """列出维度的所有版本（按时间倒序）"""
        dim_dir = self._dim_dir(dimension)
        versions: List[ConfigVersion] = []

        for filepath in sorted(dim_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(filepath.read_text(encoding="utf-8"))
                versions.append(ConfigVersion.from_dict(data))
            except Exception as e:
                logger.debug("跳过损坏的版本文件 %s: %s", filepath, e)

        return versions[:limit]

    def get_current(self, dimension: str) -> Optional[ConfigVersion]:
        """获取当前最新版本"""
        versions = self.list(dimension, limit=1)
        return versions[0] if versions else None

    def rollback(self, dimension: str, version_id: str) -> Optional[ConfigVersion]:
        """
        回滚到指定版本

        实际行为: 将旧版本的配置复制为新版本（保留回滚记录）
        """
        old = self.load(dimension, version_id)
        if old is None:
            logger.error("回滚失败: 版本 %s/%s 不存在", dimension, version_id)
            return None

        # 保存为新版本（标记为回滚）
        new_version = self.save(
            dimension=dimension,
            config=old.config,
            description=f"回滚到版本 {version_id}",
            proposal_id=old.proposal_id,
        )
        logger.warning("配置已回滚: %s → %s", version_id, new_version.version_id)
        return new_version

    def diff(self, dimension: str, version_a: str, version_b: str) -> Dict[str, Any]:
        """
        比较两个版本的差异

        Returns:
            {"added": {...}, "removed": {...}, "changed": {...}}
        """
        va = self.load(dimension, version_a)
        vb = self.load(dimension, version_b)

        if va is None or vb is None:
            return {"error": "版本不存在"}

        def _deep_diff(a: Any, b: Any, path: str = "") -> Dict[str, Any]:
            result: Dict[str, Any] = {"added": {}, "removed": {}, "changed": {}}
            if isinstance(a, dict) and isinstance(b, dict):
                for key in set(a.keys()) | set(b.keys()):
                    new_path = f"{path}.{key}" if path else key
                    if key not in a:
                        result["added"][new_path] = b[key]
                    elif key not in b:
                        result["removed"][new_path] = a[key]
                    elif a[key] != b[key]:
                        sub = _deep_diff(a[key], b[key], new_path)
                        result["added"].update(sub["added"])
                        result["removed"].update(sub["removed"])
                        result["changed"].update(sub["changed"])
            elif a != b:
                result["changed"][path] = {"from": a, "to": b}
            return result

        return _deep_diff(va.config, vb.config)

    def delete_dimension(self, dimension: str) -> bool:
        """删除整个维度的历史"""
        dim_dir = self._base / dimension
        if dim_dir.exists() and dim_dir.is_dir():
            shutil.rmtree(dim_dir)
            logger.info("已删除维度历史: %s", dimension)
            return True
        return False

    def _cleanup_old_versions(self, dimension: str) -> int:
        """清理超出保留限制的旧版本"""
        dim_dir = self._dim_dir(dimension)
        files = sorted(dim_dir.glob("*.json"), reverse=True)
        if len(files) <= self.MAX_VERSIONS:
            return 0

        to_delete = files[self.MAX_VERSIONS:]
        deleted = 0
        for f in to_delete:
            try:
                f.unlink()
                deleted += 1
            except Exception as e:
                logger.warning("删除旧版本失败 %s: %s", f, e)

        if deleted:
            logger.debug("清理 %s 旧版本: %d 个", dimension, deleted)
        return deleted

    def get_stats(self) -> Dict[str, Any]:
        """获取历史统计"""
        stats = {}
        for dim_dir in self._base.iterdir():
            if dim_dir.is_dir():
                files = list(dim_dir.glob("*.json"))
                stats[dim_dir.name] = len(files)
        return stats
