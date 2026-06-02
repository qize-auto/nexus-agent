"""
跨平台路径抽象层测试

覆盖 Hermes Agent Issue #36200 的所有已知问题场景:
- MSYS/Git Bash: /c/dev/x -> C:\\dev\\x
- WSL: /mnt/c/dev/x -> C:\\dev\\x
- Cygwin: /cygdrive/c/dev/x -> C:\\dev\\x
- 原生 Windows: C:/dev/x -> C:\\dev\\x
- 路径遍历防护
"""

import os
import sys

import pytest

from nexusagent.utils.cross_platform import CrossPlatformPath, resolve_path


class TestCrossPlatformPath:
    """跨平台路径解析测试"""

    def test_msys_path_conversion(self):
        """MSYS/Git Bash 风格路径: /c/dev/x -> C:\\dev\\x"""
        cpp = CrossPlatformPath()
        result = cpp.resolve("/c/dev/x")
        if os.name == "nt":
            assert result.lower().replace("\\", "/") == "c:/dev/x"
        else:
            # POSIX 系统上保留原始路径
            assert result == "/c/dev/x"

    def test_wsl_path_conversion(self):
        """WSL 风格路径: /mnt/c/dev/x -> C:\\dev\\x"""
        cpp = CrossPlatformPath()
        result = cpp.resolve("/mnt/c/dev/x")
        if os.name == "nt":
            assert result.lower().replace("\\", "/") == "c:/dev/x"
        else:
            assert result == "/mnt/c/dev/x"

    def test_cygwin_path_conversion(self):
        """Cygwin 风格路径: /cygdrive/c/dev/x -> C:\\dev\\x"""
        cpp = CrossPlatformPath()
        result = cpp.resolve("/cygdrive/c/dev/x")
        if os.name == "nt":
            assert result.lower().replace("\\", "/") == "c:/dev/x"
        else:
            assert result == "/cygdrive/c/dev/x"

    def test_native_windows_forward_slash(self):
        """原生 Windows 正斜杠路径: C:/dev/x -> C:\\dev\\x"""
        cpp = CrossPlatformPath()
        result = cpp.resolve("C:/dev/x")
        if os.name == "nt":
            assert result.lower().replace("\\", "/") == "c:/dev/x"

    def test_posix_path_unchanged(self):
        """纯 POSIX 路径应不变"""
        cpp = CrossPlatformPath()
        result = cpp.resolve("/home/user/project")
        assert result == "/home/user/project"

    def test_empty_path(self):
        """空路径应返回空"""
        cpp = CrossPlatformPath()
        assert cpp.resolve("") == ""

    def test_relative_path(self):
        """相对路径应保留"""
        cpp = CrossPlatformPath()
        result = cpp.resolve("./relative/path")
        assert "relative" in result
        assert "path" in result

    def test_to_posix_conversion(self):
        """to_posix 应统一转换为 POSIX 格式"""
        cpp = CrossPlatformPath()
        result = cpp.to_posix("C:\\dev\\x")
        assert result == "/c/dev/x"

    def test_is_safe_within_root(self):
        """安全路径检查: 在根目录内"""
        cpp = CrossPlatformPath()
        assert cpp.is_safe("/home/user/docs", "/home/user") is True

    def test_is_safe_traversal_blocked(self):
        """安全路径检查: 路径遍历应被阻止"""
        cpp = CrossPlatformPath()
        assert cpp.is_safe("/home/user/../../../etc/passwd", "/home/user") is False

    def test_is_safe_different_drive(self):
        """安全路径检查: 不同驱动器应被阻止 (Windows)"""
        cpp = CrossPlatformPath()
        if os.name == "nt":
            assert cpp.is_safe("D:\\other", "C:\\root") is False

    def test_resolve_path_function(self):
        """快捷函数测试"""
        result = resolve_path("/c/dev/x")
        assert result is not None

    def test_hermes_issue_36200_scenario(self):
        """
        复现 Hermes Agent Issue #36200:
        MSYS/WSL/Cygwin 路径在 Windows 上导致 phantom C:\\c\\ tree
        """
        cpp = CrossPlatformPath()
        # 这是 Hermes 报告中的核心问题场景
        test_cases = [
            "/c/dev/x",           # MSYS
            "/mnt/c/dev/x",       # WSL
            "/cygdrive/c/dev/x",  # Cygwin
        ]
        for case in test_cases:
            result = cpp.resolve(case)
            # 关键断言: 结果中不应出现 "C:\\c\\" 或 "C:/c/" 这种模式
            assert "c:/c/" not in result.lower().replace("\\", "/")
            assert "/c/c/" not in result.lower().replace("\\", "/")
