"""
NexusAgent v4.0+ — Archive Tool (Placeholder / Basic)

提供压缩/解压能力（zip/tar.gz）。
P2 级别，基础实现，完整功能可后续扩展。

安全模型:
- 所有路径受项目根目录限制
- 解压时禁止覆盖绝对路径（zip slip 防护）
- 需 NEXUS_ALLOW_FILE_OPS=1 才能创建/修改压缩包
"""

from __future__ import annotations

import logging
import os
import shutil
import tarfile
import zipfile
from typing import Any, Dict, Optional

from nexusagent.utils.cross_platform import CrossPlatformPath

logger = logging.getLogger("nexus.tools.archive")


def _sanitize_path(path: str) -> Optional[str]:
    if not path:
        return None
    root = os.path.realpath(os.getcwd())
    cpp = CrossPlatformPath()
    if os.path.isabs(path):
        full = os.path.realpath(path)
    else:
        full = os.path.realpath(os.path.join(root, path))
    if not cpp.is_safe(full, root):
        return None
    return full


def _check_write_allowed() -> Optional[str]:
    if os.getenv("NEXUS_ALLOW_FILE_OPS", "0") != "1":
        return (
            "归档操作已被禁用。"
            "设置 NEXUS_ALLOW_FILE_OPS=1 以启用（仅限受信任环境）。"
        )
    return None


class ArchiveTool:
    """压缩/解压工具"""

    async def invoke(
        self,
        operation: str,  # "zip" | "unzip" | "tar" | "untar"
        source: str,
        destination: str,
    ) -> str:
        blocked = _check_write_allowed()
        if blocked:
            return f"[ERROR] {blocked}"
        safe_src = _sanitize_path(source)
        safe_dst = _sanitize_path(destination)
        if safe_src is None:
            return f"[ERROR] 源路径不安全: {source}"
        if safe_dst is None:
            return f"[ERROR] 目标路径不安全: {destination}"

        try:
            if operation == "zip":
                return self._do_zip(safe_src, safe_dst)
            elif operation == "unzip":
                return self._do_unzip(safe_src, safe_dst)
            elif operation == "tar":
                return self._do_tar(safe_src, safe_dst)
            elif operation == "untar":
                return self._do_untar(safe_src, safe_dst)
            return f"[ERROR] 不支持的操作: {operation} (支持: zip, unzip, tar, untar)"
        except Exception as e:
            return f"[ERROR] 归档操作失败: {e}"

    def _do_zip(self, src: str, dst: str) -> str:
        root_dir = os.path.dirname(src) if os.path.isfile(src) else src
        base_dir = os.path.basename(src) if os.path.isfile(src) else "."
        shutil.make_archive(dst.replace(".zip", ""), "zip", root_dir=root_dir, base_dir=base_dir)
        return f"[OK] 已创建压缩包: {dst}"

    def _do_unzip(self, src: str, dst: str) -> str:
        os.makedirs(dst, exist_ok=True)
        with zipfile.ZipFile(src, "r") as zf:
            # Zip Slip 防护
            for member in zf.namelist():
                member_path = os.path.join(dst, member)
                if not os.path.commonpath([os.path.realpath(member_path), os.path.realpath(dst)]) == os.path.realpath(dst):
                    return f"[ERROR] Zip Slip 攻击检测: {member}"
            zf.extractall(dst)
        return f"[OK] 已解压到: {dst}"

    def _do_tar(self, src: str, dst: str) -> str:
        mode = "w:gz" if dst.endswith(".gz") else "w"
        with tarfile.open(dst, mode) as tf:
            tf.add(src, arcname=os.path.basename(src))
        return f"[OK] 已创建 tar 包: {dst}"

    def _do_untar(self, src: str, dst: str) -> str:
        os.makedirs(dst, exist_ok=True)
        with tarfile.open(src, "r:*") as tf:
            # Tar Slip 防护
            for member in tf.getmembers():
                member_path = os.path.join(dst, member.name)
                if not os.path.commonpath([os.path.realpath(member_path), os.path.realpath(dst)]) == os.path.realpath(dst):
                    return f"[ERROR] Tar Slip 攻击检测: {member.name}"
            import sys
            if sys.version_info >= (3, 12):
                tf.extractall(dst, filter='data')
            else:
                tf.extractall(dst)
        return f"[OK] 已解压到: {dst}"

    def to_tool_spec(self) -> Dict[str, Any]:
        return {
            "name": "archive.pack_unpack",
            "description": "压缩或解压文件/目录。支持 zip 和 tar.gz 格式。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["zip", "unzip", "tar", "untar"], "description": "操作类型"},
                    "source": {"type": "string", "description": "源路径"},
                    "destination": {"type": "string", "description": "目标路径"},
                },
                "required": ["operation", "source", "destination"],
            },
        }
