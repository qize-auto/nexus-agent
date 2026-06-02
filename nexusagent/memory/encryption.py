"""
NexusAgent v3.3 — 记忆层加密：AES-256-GCM + DEK/KEK双层密钥
补全: ARC-032, NFR-078, NFR-079
依赖: cryptography库

外部依据:
- pythonsheets.com/notes/security/python-crypto.html:
  "Always use authenticated encryption (AES-GCM, ChaCha20-Poly1305)"
- tools.zeyrovault.com/blog/aes-256-gcm-encryption-guide/:
  Python AESGCM high-level API 示例
"""

from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger("nexus.memory.encryption")


# ═══════════════════════════════════════════════════════════════
# NFR-079: DEK + KEK 双层密钥体系
# DEK (Data Encryption Key): 加密实际数据，定期轮换
# KEK (Key Encryption Key): 加密DEK，由用户主密码派生
# ═══════════════════════════════════════════════════════════════

@dataclass
class KeyBundle:
    """密钥包 — DEK由KEK加密存储"""
    encrypted_dek: bytes    # KEK加密后的DEK
    dek_id: str            # DEK标识符（用于轮换）
    salt: bytes            # PBKDF2盐值
    version: int = 2       # 密钥格式版本 (v2=AES-256-GCM)


class MemoryEncryption:
    """
    AES-256-GCM 内存加密引擎 — ARC-032, NFR-078

    架构:
        用户主密码 → PBKDF2 → KEK → 解密DEK → AES-256-GCM 加密/解密数据

    向后兼容:
        - v1 密文 (Fernet/AES-128-CBC) 仍可解密
        - v2 新密文使用 AES-256-GCM (nonce 前缀)
    """

    # 密文版本标记 (1字节前缀)
    _V1_FERNET = b"\x01"
    _V2_AESGCM = b"\x02"

    def __init__(self, master_key: Optional[bytes] = None):
        """
        Args:
            master_key: 32字节主密钥。如果为None，从环境变量NEXUS_MASTER_KEY读取
        """
        if master_key is None:
            master_key_b64 = os.getenv("NEXUS_MASTER_KEY", "")
            if master_key_b64:
                master_key = base64.b64decode(master_key_b64)
            else:
                # 安全准则: 禁止自动生成临时密钥，防止生产环境静默降级
                raise RuntimeError(
                    "NEXUS_MASTER_KEY 未设置。请设置环境变量: "
                    "export NEXUS_MASTER_KEY=$(python -c 'import base64,os;print(base64.b64encode(os.urandom(32)).decode())')"
                )

        # 安全准则: 禁止零字节填充（严重削弱密钥熵）
        if len(master_key) < 32:
            raise ValueError(
                f"主密钥长度不足: {len(master_key)} 字节, 要求至少 32 字节。"
                f"请生成强密钥: python -c 'import base64,os;print(base64.b64encode(os.urandom(32)).decode())'"
            )

        # KEK: 从主密钥派生 (32字节用于 AES-256)
        self._kek = master_key[:32]

        # DEK: 自动生成 256-bit (32字节)
        self._dek = os.urandom(32)
        self._dek_id = os.urandom(8).hex()

        # 向后兼容的 Fernet 实例（用于解密历史数据）
        self._legacy_fernet = Fernet(base64.urlsafe_b64encode(self._dek[:32].ljust(32, b"\x00")[:32]))

        logger.info("MemoryEncryption: AES-256-GCM 双层密钥就绪 (dek_id=%s)", self._dek_id)

    # ── 密钥管理 ──

    def derive_kek(self, master_password: str, salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
        """
        从用户密码派生KEK — NFR-079

        Args:
            master_password: 用户主密码
            salt: 盐值（None则自动生成）

        Returns:
            (kek, salt): 密钥加密密钥和使用的盐值
        """
        if salt is None:
            salt = os.urandom(16)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=600_000,  # OWASP 2025推荐
        )
        kek = kdf.derive(master_password.encode())
        return kek, salt

    def export_key_bundle(self, master_password: str) -> KeyBundle:
        """
        导出加密的密钥包 — NFR-079

        Args:
            master_password: 用户主密码

        Returns:
            KeyBundle: 可用于安全存储的密钥包
        """
        kek, salt = self.derive_kek(master_password)
        aesgcm = AESGCM(kek)
        nonce = os.urandom(12)
        encrypted_dek = aesgcm.encrypt(nonce, self._dek, None)
        # 存储格式: nonce (12) + ciphertext (+16 tag)
        payload = nonce + encrypted_dek
        return KeyBundle(
            encrypted_dek=payload,
            dek_id=self._dek_id,
            salt=salt,
            version=2,
        )

    @classmethod
    def from_key_bundle(cls, bundle: KeyBundle, master_password: str) -> "MemoryEncryption":
        """
        从密钥包恢复加密引擎 — NFR-079

        Args:
            bundle: 之前导出的密钥包
            master_password: 用户主密码

        Returns:
            MemoryEncryption: 恢复的加密引擎
        """
        instance = cls.__new__(cls)
        kek, _ = instance.derive_kek(master_password, bundle.salt)
        if bundle.version >= 2:
            nonce, ciphertext = bundle.encrypted_dek[:12], bundle.encrypted_dek[12:]
            aesgcm = AESGCM(kek)
            instance._dek = aesgcm.decrypt(nonce, ciphertext, None)
        else:
            kek_fernet = Fernet(base64.urlsafe_b64encode(kek))
            instance._dek = kek_fernet.decrypt(bundle.encrypted_dek)
        instance._dek_id = bundle.dek_id
        instance._kek = kek
        instance._legacy_fernet = Fernet(base64.urlsafe_b64encode(instance._dek[:32].ljust(32, b"\x00")[:32]))
        return instance

    # ── 数据加密/解密 — AES-256-GCM ──

    def encrypt(self, plaintext: str) -> str:
        """
        AES-256-GCM 加密字符串

        Args:
            plaintext: 明文

        Returns:
            str: Base64编码的密文 (版本标记 + nonce + ciphertext)
        """
        if not plaintext:
            return ""
        try:
            nonce = os.urandom(12)
            aesgcm = AESGCM(self._dek)
            ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
            # v2 格式: \x02 + nonce(12) + ciphertext(+tag)
            payload = self._V2_AESGCM + nonce + ciphertext
            return base64.urlsafe_b64encode(payload).decode("ascii")
        except Exception as e:
            logger.error("加密失败: %s", e)
            raise

    def decrypt(self, ciphertext_b64: str) -> str:
        """
        解密字符串 — 自动识别 v1(Fernet) 或 v2(AES-256-GCM)

        Args:
            ciphertext_b64: Base64编码的密文

        Returns:
            str: 明文
        """
        if not ciphertext_b64:
            return ""
        try:
            payload = base64.urlsafe_b64decode(ciphertext_b64.encode("ascii"))
            if not payload:
                return ""

            # 检测版本标记
            if payload.startswith(self._V2_AESGCM):
                # v2: AES-256-GCM
                _, nonce, ciphertext = payload[0], payload[1:13], payload[13:]
                aesgcm = AESGCM(self._dek)
                plaintext = aesgcm.decrypt(nonce, ciphertext, None)
                return plaintext.decode("utf-8")
            else:
                # 尝试 v1 Fernet 向后兼容
                # Fernet.decrypt() 接收 base64url 编码的 token，无需二次解码
                plaintext = self._legacy_fernet.decrypt(ciphertext_b64)
                return plaintext.decode("utf-8")
        except Exception as e:
            logger.error("解密失败: %s", e)
            raise ValueError(f"无法解密: {e}")

    def encrypt_bytes(self, data: bytes) -> bytes:
        """加密二进制数据 — v2 AES-256-GCM"""
        if not data:
            return b""
        nonce = os.urandom(12)
        aesgcm = AESGCM(self._dek)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return self._V2_AESGCM + nonce + ciphertext

    def decrypt_bytes(self, data: bytes) -> bytes:
        """解密二进制数据 — 自动识别版本"""
        if not data:
            return b""
        if data.startswith(self._V2_AESGCM):
            _, nonce, ciphertext = data[0], data[1:13], data[13:]
            aesgcm = AESGCM(self._dek)
            return aesgcm.decrypt(nonce, ciphertext, None)
        return self._legacy_fernet.decrypt(data)

    def rotate_dek(self) -> str:
        """
        轮换DEK — NFR-079密钥管理
        返回新的dek_id
        """
        old_dek_id = self._dek_id
        self._dek = os.urandom(32)
        self._dek_id = os.urandom(8).hex()
        logger.info("DEK轮换: %s → %s", old_dek_id, self._dek_id)
        return self._dek_id

    def is_legacy_ciphertext(self, ciphertext_b64: str) -> bool:
        """检测密文是否为 v1 (Fernet) 格式"""
        if not ciphertext_b64:
            return False
        try:
            payload = base64.urlsafe_b64decode(ciphertext_b64.encode("ascii"))
            return not payload.startswith(self._V2_AESGCM)
        except Exception:
            return False

    def migrate_value(self, ciphertext_b64: str) -> str:
        """
        单条数据迁移: v1(Fernet) → v2(AES-256-GCM)

        外部依据: cryptography.io 官方文档
        "Token rotation as offered by MultiFernet.rotate() is a best practice"
        这里将 rotate 概念扩展为算法升级: 解密旧格式 → 用新算法加密。

        Args:
            ciphertext_b64: 可能为 v1 或 v2 的密文

        Returns:
            str: v2 AES-256-GCM 密文（如果原已是 v2 则直接返回）
        """
        if not ciphertext_b64 or not self.is_legacy_ciphertext(ciphertext_b64):
            return ciphertext_b64
        # 解密旧格式
        plaintext = self.decrypt(ciphertext_b64)
        # 用新格式重新加密
        return self.encrypt(plaintext)

    async def migrate_legacy_data(self, memory_store: Any) -> Dict[str, Any]:
        """
        批量迁移 MemoryStore 中的 v1 密文到 v2

        生产级加固要求: 升级加密算法后，历史数据必须可自动迁移，
        而非让用户手动处理。

        Args:
            memory_store: MemoryStore 实例

        Returns:
            迁移统计 {"scanned": N, "migrated": N, "failed": N}
        """
        stats = {"scanned": 0, "migrated": 0, "failed": 0}
        if not memory_store or not hasattr(memory_store, "_conn"):
            logger.warning("migrate_legacy_data: 无效的 memory_store")
            return stats

        conn = memory_store._conn
        cursor = conn.execute(
            "SELECT id, content, metadata_json FROM memories WHERE content IS NOT NULL"
        )
        rows = cursor.fetchall()

        for row_id, content, metadata_json in rows:
            stats["scanned"] += 1
            try:
                new_content = self.migrate_value(content)
                new_metadata = self.migrate_value(metadata_json)
                if new_content != content or new_metadata != metadata_json:
                    conn.execute(
                        "UPDATE memories SET content = ?, metadata_json = ? WHERE id = ?",
                        (new_content, new_metadata, row_id),
                    )
                    stats["migrated"] += 1
            except Exception as e:
                stats["failed"] += 1
                logger.warning("迁移记录 %s 失败: %s", row_id, e)

        conn.commit()
        logger.info(
            "批量迁移完成: scanned=%d, migrated=%d, failed=%d",
            stats["scanned"], stats["migrated"], stats["failed"],
        )
        return stats
