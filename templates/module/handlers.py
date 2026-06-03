"""
handlers.py — {{module_name}} 的业务逻辑

将核心功能实现放在此文件中，保持 module_spec.py 只负责元数据和生命周期。
"""

from __future__ import annotations


async def example_handler(query: str) -> str:
    """
    示例处理函数

    Args:
        query: 输入查询

    Returns:
        处理结果
    """
    return f"{{module_name}} processed: {query}"
