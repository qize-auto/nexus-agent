"""
NexusAgent v4.0+ — 跨平台路径抽象层

设计参考:
- Hermes Agent Issue #36200: MSYS/WSL/Cygwin 路径 phantom C:\\c\\ tree
- Python pathlib 跨平台最佳实践

职责:
    1. 自动识别 WSL/MSYS/Cygwin/原生 Windows 路径格式
    2. 统一转换为平台原生路径
    3. 防止路径遍历（已在 layer.py 中实现，此处补充路径格式转换）

Usage:
    from nexusagent.utils.cross_platform import CrossPlatformPath
    cpp = CrossPlatformPath()
    native = cpp.resolve("/c/dev/x")  # Windows → C:\\dev\\x
"""

from __future__ import annotations

import logging
import os
import posixpath
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Optional

logger = logging.getLogger("nexus.utils.cross_platform")


class CrossPlatformPath:
    """
    跨平台路径解析器

    支持的输入格式:
        - 原生 Windows: C:\\dev\\x, C:/dev/x
        - WSL: /mnt/c/dev/x
        - MSYS/Git Bash: /c/dev/x
        - Cygwin: /cygdrive/c/dev/x
        - POSIX: /home/user/x
    """

    # MSYS/Git Bash 风格: /c/dev/x → C:\\dev\\x
    _MSYS_DRIVE_RE = re.compile(r"^/([a-zA-Z])(?:/|$)")
    # Cygwin 风格: /cygdrive/c/dev/x → C:\\dev\\x
    _CYGWIN_DRIVE_RE = re.compile(r"^/cygdrive/([a-zA-Z])(?:/|$)")
    # WSL 风格: /mnt/c/dev/x → C:\\dev\\x
    _WSL_DRIVE_RE = re.compile(r"^/mnt/([a-zA-Z])(?:/|$)")

    def __init__(self):
        self._is_windows = os.name == "nt"
        self._env = self._detect_env()

    def _detect_env(self) -> str:
        """检测当前运行环境"""
        if os.name == "nt":
            return "native_windows"
        if "WSL_DISTRO_NAME" in os.environ or "WSLENV" in os.environ:
            return "wsl"
        if "MSYSTEM" in os.environ:
            return "msys"
        if "CYGWIN" in os.environ:
            return "cygwin"
        return "posix"

    def resolve(self, path: str) -> str:
        """
        将任意路径格式转换为当前平台的原生路径

        Args:
            path: 任意格式的路径字符串

        Returns:
            str: 当前平台的原生路径
        """
        if not path:
            return path

        # 1. 检测并转换 POSIX 风格的 Windows 驱动器路径
        converted = self._convert_posix_drive(path)
        if converted != path:
            path = converted

        # 2. 使用 pathlib 规范化
        try:
            p = Path(path)
            # 如果路径存在，返回绝对路径
            if p.exists():
                return str(p.resolve())
            # Windows 上避免对纯 POSIX 路径进行 normpath 转换
            if os.name == "nt" and path.startswith("/") and not path.startswith("//"):
                # 检查是否是纯 POSIX 路径（无驱动器）
                if len(path) < 2 or path[1] != ":":
                    return path
            # 否则返回规范化后的路径
            return os.path.normpath(path)
        except Exception:
            # 极端情况下回退到原始路径
            return path

    def _convert_posix_drive(self, path: str) -> str:
        """将 POSIX 风格的 Windows 驱动器路径转换为原生格式"""
        # 尝试 Cygwin 格式
        m = self._CYGWIN_DRIVE_RE.match(path)
        if m:
            drive = m.group(1).upper()
            rest = path[m.end() - 1:]  # 包含开头的 /
            if rest == "/":
                rest = ""
            return f"{drive}:{rest}"

        # 尝试 WSL 格式
        m = self._WSL_DRIVE_RE.match(path)
        if m:
            drive = m.group(1).upper()
            rest = path[m.end() - 1:]
            if rest == "/":
                rest = ""
            return f"{drive}:{rest}"

        # 尝试 MSYS/Git Bash 格式
        m = self._MSYS_DRIVE_RE.match(path)
        if m:
            drive = m.group(1).upper()
            rest = path[m.end() - 1:]
            if rest == "/":
                rest = ""
            return f"{drive}:{rest}"

        return path

    def to_posix(self, path: str) -> str:
        """将路径统一转换为 POSIX 格式（用于跨平台存储）"""
        resolved = self.resolve(path)
        if self._is_windows:
            # C:\\dev\\x → /c/dev/x
            if len(resolved) >= 2 and resolved[1] == ":":
                drive = resolved[0].lower()
                rest = resolved[2:].replace("\\", "/")
                return f"/{drive}{rest}"
        return resolved.replace("\\", "/")

    def is_safe(self, path: str, root: str) -> bool:
        """
        检查路径是否在允许的根目录范围内

        Args:
            path: 要检查的路径
            root: 允许的根目录

        Returns:
            bool: 是否安全
        """
        try:
            # 统一使用 POSIX 格式进行比较，避免 Windows 路径语义干扰
            resolved = self.to_posix(path)
            resolved_root = self.to_posix(root)

            # 使用 posixpath.normpath 规范化路径（处理 .. 和 .）
            resolved_norm = posixpath.normpath(resolved)
            resolved_root_norm = posixpath.normpath(resolved_root)

            # 安全检查: 路径必须以 root 为前缀
            if resolved_norm == resolved_root_norm:
                return True
            if resolved_norm.startswith(resolved_root_norm + "/"):
                return True
            return False
        except Exception as e:
            logger.warning("路径安全检查失败: %s", e)
            return False


def resolve_path(path: str) -> str:
    """快捷函数: 解析任意路径为当前平台原生格式"""
    return CrossPlatformPath().resolve(path)
