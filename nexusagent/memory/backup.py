"""
NexusAgent v4.0+ — 记忆系统备份与恢复管理器

自动备份 SQLite DB + ChromaDB + uploads，支持定时清理。

Usage:
    from nexusagent.memory.backup import MemoryBackupManager
    mgr = MemoryBackupManager()
    mgr.backup()  # 创建备份
    mgr.restore("20250602_143000")  # 恢复备份
    mgr.auto_cleanup()  # 清理旧备份
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nexus.memory.backup")


@dataclass
class BackupInfo:
    """备份信息"""
    timestamp: str
    path: str
    size_bytes: int
    file_count: int
    created_at: float


class MemoryBackupManager:
    """
    记忆系统备份管理器

    备份内容:
        - SQLite 数据库 (nexus.db)
        - ChromaDB 向量存储 (chroma_db/)
        - 上传文件 (uploads/)
        - 用户画像数据库 (user_profiles.db 若独立)
    """

    def __init__(
        self,
        backup_dir: Optional[str] = None,
        data_dir: Optional[str] = None,
        max_backups: int = 7,
    ):
        self._backup_dir = Path(backup_dir or os.environ.get("NEXUS_BACKUP_DIR", "./backups"))
        self._data_dir = Path(data_dir or os.environ.get("NEXUS_HOME", "."))
        self._max_backups = max_backups
        self._backup_dir.mkdir(parents=True, exist_ok=True)

    def backup(self, label: str = "") -> BackupInfo:
        """
        创建备份

        Args:
            label: 可选标签，如 "before_upgrade"
        """
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        if label:
            timestamp = f"{timestamp}_{label}"

        backup_path = self._backup_dir / timestamp
        backup_path.mkdir(parents=True, exist_ok=True)

        files_backed = 0
        total_size = 0

        # 1. 备份 SQLite 数据库
        db_file = self._data_dir / "nexus.db"
        if db_file.exists():
            dest = backup_path / "nexus.db"
            # 使用 SQLite 的在线备份（不锁表）
            self._backup_sqlite(str(db_file), str(dest))
            size = dest.stat().st_size
            total_size += size
            files_backed += 1
            logger.info("SQLite 备份完成: %s (%d bytes)", dest, size)

        # 2. 备份 ChromaDB
        chroma_dir = self._data_dir / "chroma_db"
        if chroma_dir.exists():
            dest = backup_path / "chroma_db"
            count, size = self._copy_tree(chroma_dir, dest)
            total_size += size
            files_backed += count
            logger.info("ChromaDB 备份完成: %s (%d files, %d bytes)", dest, count, size)

        # 3. 备份 uploads
        uploads_dir = Path("uploads")
        if uploads_dir.exists():
            dest = backup_path / "uploads"
            count, size = self._copy_tree(uploads_dir, dest)
            total_size += size
            files_backed += count
            logger.info("Uploads 备份完成: %s (%d files, %d bytes)", dest, count, size)

        # 4. 备份配置文件
        for cfg in ["config.yaml", ".env"]:
            src = Path(cfg)
            if src.exists():
                shutil.copy2(src, backup_path / cfg)
                total_size += src.stat().st_size
                files_backed += 1

        # 写入备份元数据
        meta = {
            "timestamp": timestamp,
            "created_at": time.time(),
            "size_bytes": total_size,
            "file_count": files_backed,
            "label": label,
        }
        meta_path = backup_path / "backup_meta.json"
        import json
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        logger.info("备份创建完成: %s (总大小 %.1f MB, %d 文件)",
                    backup_path, total_size / 1024 / 1024, files_backed)

        return BackupInfo(
            timestamp=timestamp,
            path=str(backup_path),
            size_bytes=total_size,
            file_count=files_backed,
            created_at=time.time(),
        )

    def restore(self, timestamp: str) -> bool:
        """从备份恢复"""
        backup_path = self._backup_dir / timestamp
        if not backup_path.exists():
            logger.error("备份不存在: %s", backup_path)
            return False

        logger.warning("开始恢复备份: %s", timestamp)

        # 1. 恢复 SQLite
        db_backup = backup_path / "nexus.db"
        if db_backup.exists():
            dest = self._data_dir / "nexus.db"
            # 先备份当前数据库
            if dest.exists():
                shutil.copy2(dest, f"{dest}.restore_backup_{int(time.time())}")
            shutil.copy2(db_backup, dest)
            logger.info("SQLite 已恢复: %s", dest)

        # 2. 恢复 ChromaDB
        chroma_backup = backup_path / "chroma_db"
        if chroma_backup.exists():
            dest = self._data_dir / "chroma_db"
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(chroma_backup, dest)
            logger.info("ChromaDB 已恢复: %s", dest)

        # 3. 恢复 uploads
        uploads_backup = backup_path / "uploads"
        if uploads_backup.exists():
            dest = Path("uploads")
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(uploads_backup, dest)
            logger.info("Uploads 已恢复: %s", dest)

        logger.warning("备份恢复完成: %s", timestamp)
        return True

    def list_backups(self) -> List[BackupInfo]:
        """列出所有备份"""
        results: List[BackupInfo] = []
        if not self._backup_dir.exists():
            return results

        for entry in sorted(self._backup_dir.iterdir()):
            if not entry.is_dir():
                continue
            meta_file = entry / "backup_meta.json"
            if meta_file.exists():
                import json
                meta = json.loads(meta_file.read_text())
                results.append(BackupInfo(
                    timestamp=meta.get("timestamp", entry.name),
                    path=str(entry),
                    size_bytes=meta.get("size_bytes", 0),
                    file_count=meta.get("file_count", 0),
                    created_at=meta.get("created_at", 0),
                ))
            else:
                # 无元数据时估算
                size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
                count = sum(1 for _ in entry.rglob("*") if _.is_file())
                results.append(BackupInfo(
                    timestamp=entry.name,
                    path=str(entry),
                    size_bytes=size,
                    file_count=count,
                    created_at=entry.stat().st_mtime,
                ))

        return sorted(results, key=lambda b: b.created_at, reverse=True)

    def auto_cleanup(self, max_backups: Optional[int] = None) -> int:
        """
        自动清理旧备份

        Returns:
            删除的备份数量
        """
        max_b = max_backups or self._max_backups
        backups = self.list_backups()
        if len(backups) <= max_b:
            return 0

        to_delete = backups[max_b:]
        deleted = 0
        for b in to_delete:
            try:
                shutil.rmtree(b.path)
                logger.info("删除旧备份: %s", b.timestamp)
                deleted += 1
            except Exception as e:
                logger.warning("删除备份失败 %s: %s", b.path, e)
        return deleted

    def get_disk_usage(self) -> Dict[str, int]:
        """返回各数据目录的磁盘使用量（字节）"""
        result = {}
        for name, path in [
            ("nexus.db", self._data_dir / "nexus.db"),
            ("chroma_db", self._data_dir / "chroma_db"),
            ("uploads", Path("uploads")),
            ("backups", self._backup_dir),
        ]:
            if path.exists():
                if path.is_file():
                    result[name] = path.stat().st_size
                else:
                    result[name] = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            else:
                result[name] = 0
        return result

    # ── 内部方法 ──

    def _backup_sqlite(self, src: str, dest: str) -> None:
        """使用 SQLite 在线备份 API（不锁表）"""
        src_conn = None
        dest_conn = None
        try:
            src_conn = sqlite3.connect(src)
            dest_conn = sqlite3.connect(dest)
            with dest_conn:
                src_conn.backup(dest_conn)
        except Exception:
            # 在线备份失败时回退到文件复制
            shutil.copy2(src, dest)
        finally:
            if src_conn:
                src_conn.close()
            if dest_conn:
                dest_conn.close()

    def _copy_tree(self, src: Path, dest: Path) -> tuple:
        """复制目录树，返回 (文件数, 总字节数)"""
        if not src.exists():
            return 0, 0
        shutil.copytree(src, dest, dirs_exist_ok=True)
        files = [f for f in dest.rglob("*") if f.is_file()]
        total = sum(f.stat().st_size for f in files)
        return len(files), total
