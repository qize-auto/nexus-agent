"""
{{module_name}} — NexusAgent 模块

使用说明:
    1. 修改 {{module_name}}_spec.py 中的元数据
    2. 在 handlers.py 中实现业务逻辑
    3. 运行 `nexus module register {{module_name}}` 注册模块
    4. 运行 `pytest tests/` 确保测试通过
"""

from .{{module_name}}_spec import {{ModuleName}}Spec

__all__ = ["{{ModuleName}}Spec"]
__version__ = "0.1.0"
