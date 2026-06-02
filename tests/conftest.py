"""
NexusAgent v3.3 — 测试配置
"""

import sys
import os
import pytest
import tempfile
from pathlib import Path

# 确保项目根目录在 path 中
# REMOVED: sys.path.insert hack no longer needed after package structure fix

# 安全准则: 为测试环境提供固定的主密钥，避免每次生成不同密钥导致测试不稳定
# 注意: 这是测试专用密钥，生产环境必须使用独立强密钥
if not os.getenv("NEXUS_MASTER_KEY"):
    os.environ["NEXUS_MASTER_KEY"] = "dGVzdC1rZXktZm9yLW5leHVzYWdlbnQtb25seS0xMjM0NTY3OA=="


@pytest.fixture
def temp_db():
    """临时数据库"""
    db_path = tempfile.mktemp(suffix='.db')
    yield db_path
    try:
        os.unlink(db_path)
    except Exception:
        pass


@pytest.fixture
def encryption_engine():
    """加密引擎"""
    from nexusagent.memory.encryption import MemoryEncryption
    return MemoryEncryption()


@pytest.fixture
def guardrails():
    """安全审查引擎"""
    from nexusagent.security.guardrails import GuardrailsEngine
    return GuardrailsEngine()


@pytest.fixture
def sanitizer():
    """输入消毒器"""
    from nexusagent.security.sanitizer import InputSanitizer
    return InputSanitizer()


@pytest.fixture
def pii_desensitizer():
    """PII脱敏器"""
    from nexusagent.security.sanitizer import PIIDesensitizer
    return PIIDesensitizer()


@pytest.fixture
def tool_layer():
    """工具层"""
    from nexusagent.tools.layer import ToolLayer
    return ToolLayer()


@pytest.fixture
def memory_store(temp_db):
    """记忆存储"""
    from nexusagent.memory.store import MemoryStore
    store = MemoryStore(temp_db)
    yield store
    store.close()


@pytest.fixture
def trust_score():
    """信任积分"""
    from nexusagent.security.guardrails import TrustScore
    return TrustScore(user_id="test_user")
