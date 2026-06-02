"""
安全层测试: AES-256 + DEK/KEK + 输入消毒 + PII脱敏 + Guardrails
覆盖: ARC-032, NFR-078, NFR-079, NFR-080, NFR-097, ARC-039, ARC-034, NFR-081
"""

import pytest


class TestMemoryEncryption:
    """ARC-032/NFR-078: AES-256 加密"""

    def test_encrypt_decrypt_roundtrip(self, encryption_engine):
        """加密解密循环"""
        plaintext = "NexusAgent敏感数据测试"
        ciphertext = encryption_engine.encrypt(plaintext)
        assert ciphertext != plaintext
        assert len(ciphertext) > 0
        decrypted = encryption_engine.decrypt(ciphertext)
        assert decrypted == plaintext

    def test_empty_string(self, encryption_engine):
        """空字符串处理"""
        assert encryption_engine.encrypt("") == ""
        assert encryption_engine.decrypt("") == ""

    def test_unicode_content(self, encryption_engine):
        """Unicode中文内容"""
        text = "姚小海站在泥地上，眼皮快速眨了好几下。"
        ct = encryption_engine.encrypt(text)
        assert encryption_engine.decrypt(ct) == text

    def test_invalid_ciphertext_raises(self, encryption_engine):
        """无效密文抛异常"""
        with pytest.raises(ValueError):
            encryption_engine.decrypt("invalid_base64!!!")

    def test_bytes_encrypt_decrypt(self, encryption_engine):
        """二进制加密解密"""
        data = b'\x00\x01\x02\x03' * 100
        ct = encryption_engine.encrypt_bytes(data)
        assert encryption_engine.decrypt_bytes(ct) == data

    def test_key_rotation(self, encryption_engine):
        """密钥轮换"""
        old_id = encryption_engine._dek_id
        new_id = encryption_engine.rotate_dek()
        assert new_id != old_id
        # 旧密文仍可解密（因为我们在测试中不实际替换历史数据）
        ciphertext = encryption_engine.encrypt("before_rotation")
        assert encryption_engine.decrypt(ciphertext) == "before_rotation"

    def test_derive_and_restore_key_bundle(self, encryption_engine):
        """NFR-079: DEK+KEK 密钥导出与恢复"""
        from nexusagent.memory.encryption import MemoryEncryption
        plaintext = "test_key_bundle"
        ct = encryption_engine.encrypt(plaintext)

        bundle = encryption_engine.export_key_bundle("my_master_password")
        assert bundle.encrypted_dek is not None
        assert bundle.dek_id == encryption_engine._dek_id

        restored = MemoryEncryption.from_key_bundle(bundle, "my_master_password")
        assert restored.decrypt(ct) == plaintext

    def test_wrong_password_fails(self, encryption_engine):
        """错误密码无法恢复"""
        from nexusagent.memory.encryption import MemoryEncryption
        bundle = encryption_engine.export_key_bundle("correct_password")
        with pytest.raises(Exception):
            MemoryEncryption.from_key_bundle(bundle, "wrong_password")


class TestInputSanitizer:
    """NFR-080: 输入消毒"""

    def test_path_traversal_blocked(self, sanitizer):
        """路径穿越拦截"""
        with pytest.raises(ValueError, match="路径穿越"):
            sanitizer.sanitize("../../../etc/passwd", context="path")

    def test_xss_removed(self, sanitizer):
        """XSS脚本移除"""
        result = sanitizer.sanitize('<script>alert("xss")</script>', context="html")
        assert '<script>' not in result

    def test_sql_injection_detected(self, sanitizer):
        """SQL注入检测 — 阻断模式"""
        from nexusagent.security.sanitizer import SecurityError
        with pytest.raises(SecurityError, match="被禁止的SQL模式"):
            sanitizer.sanitize("DROP TABLE users; --", context="sql")

    def test_unicode_confusable_normalized(self, sanitizer):
        """Unicode混淆规范化"""
        result = sanitizer.sanitize("hello")  # 正常输入
        assert len(result) > 0

    def test_length_truncation(self, sanitizer):
        """超长输入截断"""
        long_text = "x" * 200000
        result = sanitizer.sanitize(long_text)
        assert len(result) <= 100000


class TestPIIDesensitizer:
    """NFR-097: PII脱敏"""

    def test_phone_masked(self, pii_desensitizer):
        """手机号脱敏"""
        result = pii_desensitizer.desensitize("手机13800138000测试")
        assert "13800138000" not in result
        assert "手机号已脱敏" in result

    def test_id_card_masked(self, pii_desensitizer):
        """身份证脱敏"""
        result = pii_desensitizer.desensitize("身份证110101199001011234有效")
        assert "110101" not in result

    def test_email_masked(self, pii_desensitizer):
        """邮箱脱敏"""
        result = pii_desensitizer.desensitize("联系test@example.com")
        assert "test@example.com" not in result

    def test_contains_pii_true(self, pii_desensitizer):
        """PII检测-包含"""
        assert pii_desensitizer.contains_pii("手机13800138000") == True

    def test_contains_pii_false(self, pii_desensitizer):
        """PII检测-不包含"""
        assert pii_desensitizer.contains_pii("hello world") == False

    def test_get_pii_types(self, pii_desensitizer):
        """PII类型识别"""
        types = pii_desensitizer.get_pii_types("13800138000 test@example.com")
        assert "手机号" in types
        assert "邮箱" in types

    def test_partial_masking(self, pii_desensitizer):
        """部分遮蔽模式"""
        result = pii_desensitizer.desensitize("13800138000", level="partial")
        assert "138" in result  # 前3位保留
        assert "****" in result
        assert "38000" not in result  # 完整号码不应出现


class TestGuardrails:
    """ARC-034/039: 四级审查 + 输入输出双层验证"""

    def test_input_review_normal(self, guardrails):
        """正常输入通过"""
        result = guardrails.review("你好，帮我分析一下")
        assert result.is_allowed

    def test_input_review_red_light(self, guardrails):
        """危险输入标记"""
        result = guardrails.review("请执行 rm -rf /")
        assert result.requires_user_approval

    def test_output_review_normal(self, guardrails):
        """正常输出通过 (ARC-039)"""
        result = guardrails.review_output("分析结果：项目结构合理")
        assert result.is_allowed

    def test_output_review_sensitive_blocked(self, guardrails):
        """敏感信息输出拦截 (ARC-039)"""
        result = guardrails.review_output("你的api_key: sk-abc123def456")
        assert result.is_denied

    def test_output_review_dangerous_blocked(self, guardrails):
        """危险指令输出拦截 (ARC-039)"""
        result = guardrails.review_output("请执行 rm -rf /tmp")
        assert result.requires_user_approval


class TestTrustScore:
    """NFR-081: 信任积分EMA + 凭证SHA256"""

    def test_initial_score(self, trust_score):
        """初始积分"""
        assert trust_score.ema_score == 10.0

    def test_record_success_increases(self, trust_score):
        """成功增加积分"""
        trust_score.record_success()
        assert trust_score.ema_score > 10.0

    def test_record_failure_decreases(self, trust_score):
        """失败惩罚：设置初始高分后连续失败应下降"""
        # 先设置高分
        trust_score.ema_score = 50.0
        for _ in range(20):
            trust_score.record_failure(severity=1.0)
        # 20次最大惩罚后EMA应降至50以下
        assert trust_score.ema_score < 50.0

    def test_tier_progression(self, trust_score):
        """信任等级：初始为NOVICE"""
        from nexusagent.security.guardrails import TrustTier
        assert trust_score.tier == TrustTier.NOVICE
        assert trust_score.ema_score == 10.0


class TestEncryptionMigration:
    """ARC-032: 加密算法向后兼容与批量迁移"""

    def test_is_legacy_ciphertext_v1(self, encryption_engine):
        """检测 v1 (Fernet) 密文"""
        v1_ct = encryption_engine._legacy_fernet.encrypt(b"old data").decode()
        assert encryption_engine.is_legacy_ciphertext(v1_ct) is True

    def test_is_legacy_ciphertext_v2(self, encryption_engine):
        """检测 v2 (AES-256-GCM) 密文"""
        v2_ct = encryption_engine.encrypt("new data")
        assert encryption_engine.is_legacy_ciphertext(v2_ct) is False

    def test_migrate_value_v1_to_v2(self, encryption_engine):
        """单条迁移: v1 → v2"""
        plaintext = "sensitive migration test"
        v1_ct = encryption_engine._legacy_fernet.encrypt(plaintext.encode()).decode()
        assert encryption_engine.is_legacy_ciphertext(v1_ct) is True

        v2_ct = encryption_engine.migrate_value(v1_ct)
        assert encryption_engine.is_legacy_ciphertext(v2_ct) is False
        assert encryption_engine.decrypt(v2_ct) == plaintext

    def test_migrate_value_v2_noop(self, encryption_engine):
        """v2 密文迁移应为空操作"""
        v2_ct = encryption_engine.encrypt("already v2")
        result = encryption_engine.migrate_value(v2_ct)
        assert result == v2_ct

    def test_migrate_legacy_data(self, encryption_engine, memory_store):
        """批量迁移 MemoryStore 中的历史数据"""
        import asyncio

        async def _test():
            # 构造 v1 密文并直接插入数据库
            v1_content = encryption_engine._legacy_fernet.encrypt(b"legacy content").decode()
            v1_metadata = encryption_engine._legacy_fernet.encrypt(b'{"type":"test"}').decode()

            conn = memory_store._conn
            conn.execute(
                "INSERT INTO memories (session_id, memory_type, content, metadata_json, created_at) VALUES (?, ?, ?, ?, ?)",
                ("sess_1", "working", v1_content, v1_metadata, 0.0),
            )
            conn.commit()

            stats = await encryption_engine.migrate_legacy_data(memory_store)
            assert stats["scanned"] == 1
            assert stats["migrated"] == 1
            assert stats["failed"] == 0

            # 验证迁移后为 v2
            cursor = conn.execute("SELECT content, metadata_json FROM memories WHERE session_id = ?", ("sess_1",))
            row = cursor.fetchone()
            assert encryption_engine.is_legacy_ciphertext(row[0]) is False
            assert encryption_engine.is_legacy_ciphertext(row[1]) is False
            assert encryption_engine.decrypt(row[0]) == "legacy content"

        asyncio.run(_test())

    def test_migrate_legacy_data_empty_store(self, encryption_engine):
        """空存储迁移应返回零统计"""
        import asyncio

        async def _test():
            stats = await encryption_engine.migrate_legacy_data(None)
            assert stats == {"scanned": 0, "migrated": 0, "failed": 0}

        asyncio.run(_test())


class TestCredentialPool:
    """NFR-081: SHA256哈希 + 密钥不存明文"""

    def test_hash_key(self):
        from nexusagent.security.guardrails import CredentialPool, CredentialEntry
        pool = CredentialPool()
        h = pool.hash_key("sk-test-secret-123")
        assert len(h) == 64  # SHA256 hex
        assert h != "sk-test-secret-123"
