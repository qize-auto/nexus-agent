"""
NexusAgent v3.3 — ULID生成器
"""

import time
import os
import hashlib


def generate_ulid() -> str:
    """生成ULID格式的唯一标识符"""
    timestamp = int(time.time() * 1000)
    random_bytes = os.urandom(10)
    random_hex = random_bytes.hex()
    return f"{timestamp:013x}{random_hex}"[:26]


__all__ = ["generate_ulid"]
