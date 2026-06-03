"""
{{module_name}}_spec.py — 模块规格定义

这是 NexusAgent 模块的核心文件。你需要:
1. 填写模块元数据（name, version, description, author）
2. 声明依赖（dependencies）
3. 实现生命周期钩子（on_load, on_initialize, on_unload）
4. 实现健康检查（health_check）
"""

from __future__ import annotations

from typing import Any, Dict

from nexusagent.core.registry import ModuleSpec


class {{ModuleName}}Spec(ModuleSpec):
    """
    {{module_description}}
    """

    # ── 元数据 ──
    name = "{{module_name}}"
    version = "0.1.0"
    description = "{{module_description}}"
    author = "{{author}}"
    tags = ["{{tag1}}", "{{tag2}}"]

    # ── 依赖 ──
    # 列出此模块依赖的其他 NexusAgent 模块名
    dependencies: list[str] = []
    # optional_dependencies: list[str] = ["some_optional_module"]

    # ── 能力声明 ──
    provides_tools = True   # 如果提供工具，设为 True
    provides_skills = False
    provides_adapters = False
    provides_memory = False

    # ── 内部状态 ──
    def __init__(self):
        super().__init__()
        self._config: Dict[str, Any] = {}

    # ── 生命周期钩子 ──

    def on_load(self) -> bool:
        """加载时调用 — 读取配置、导入依赖"""
        # TODO: 实现加载逻辑
        return True

    def on_initialize(self) -> bool:
        """初始化时调用 — 创建资源、建立连接"""
        # TODO: 实现初始化逻辑
        return True

    def on_unload(self) -> None:
        """卸载时调用 — 释放资源"""
        # TODO: 实现清理逻辑
        pass

    # ── 健康检查 ──

    def health_check(self) -> Dict[str, Any]:
        """返回模块健康状态"""
        base = super().health_check()
        base["details"] = {
            # TODO: 添加自定义健康指标
            "custom_metric": "ok",
        }
        return base

    # ── 业务方法 ──

    # TODO: 实现模块的核心功能方法
    # async def my_handler(self, input_data: str) -> str:
    #     return f"Processed: {input_data}"
