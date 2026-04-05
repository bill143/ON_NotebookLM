"""Unit tests for nexus_vault_keys — encryption, JWT, auth, CSRF, rate limiting."""

from __future__ import annotations

import pytest

from src.exceptions import AuthError, ForbiddenError, TenantIsolationError
from src.infra.nexus_vault_keys import (
    AuthContext,
    _derive_key_argon2,
    _get_encryption_key_legacy,
    create_access_token,
    decrypt_credential,
    encrypt_credential,
    generate_csrf_token,
    verify_csrf_token,
    verify_token,
)


class TestArgon2KDF:
    def test_derive_key_produces_32_bytes(self):
        key = _derive_key_argon2(b"passphrase", b"a" * 16)
        assert len(key) == 32

    def test_derive_key_deterministic(self):
        salt = b"fixed-salt-value"
        k1 = _derive_key_argon2(b"pass", salt)
        k2 = _derive_key_argon2(b"pass", salt)
        assert k1 == k2

    def test_derive_key_different_salt_produces_different_key(self):
        k1 = _derive_key_argon2(b"pass", b"salt-aaaaaaaaaa01")
        k2 = _derive_key_argon2(b"pass", b"salt-bbbbbbbbbb02")
        assert k1 != k2

    def test_legacy_key_produces_32_bytes(self):
        key = _get_encryption_key_legacy()
        assert len(key) == 32


class TestEncryptDecrypt:
    def test_roundtrip_argon2(self):
        ciphertext, salt = encrypt_credential("my-api-key-123")
        plaintext = decrypt_credential(ciphertext, salt=salt)
        assert plaintext == "my-api-key-123"

    def test_different_salts_produce_different_ciphertext(self):
        ct1, s1 = encrypt_credential("same-key")
        ct2, s2 = encrypt_credential("same-key")
        assert ct1 != ct2
        assert s1 != s2

    def test_wrong_salt_fails(self):
        from cryptography.exceptions import InvalidTag

        ciphertext, _salt = encrypt_credential("secret")
        with pytest.raises(InvalidTag):
            decrypt_credential(ciphertext, salt=b"wrong-salt-12345")

    def test_legacy_fallback_when_no_salt(self):
        import base64
        import os

        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = _get_encryption_key_legacy()
        nonce = os.urandom(12)
        ct = AESGCM(key).encrypt(nonce, b"old-secret", None)
        encoded = base64.b64encode(nonce + ct).decode()

        result = decrypt_credential(encoded, salt=None)
        assert result == "old-secret"

    def test_encrypt_returns_tuple(self):
        result = encrypt_credential("test")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], bytes)
        assert len(result[1]) == 16


class TestJWT:
    def test_create_and_verify_token(self):
        token = create_access_token("user-1", "tenant-1", ["member"])
        payload = verify_token(token)
        assert payload["sub"] == "user-1"
        assert payload["tid"] == "tenant-1"
        assert "member" in payload["roles"]

    def test_verify_invalid_token_raises(self):
        with pytest.raises(AuthError):
            verify_token("not-a-valid-jwt")

    def test_token_contains_issuer(self):
        token = create_access_token("u", "t", ["member"])
        payload = verify_token(token)
        assert payload["iss"] == "nexus-notebook-11"


class TestAuthContext:
    def test_from_token(self):
        token = create_access_token("u1", "t1", ["member", "admin"])
        ctx = AuthContext.from_token(token)
        assert ctx.user_id == "u1"
        assert ctx.tenant_id == "t1"
        assert ctx.is_admin

    def test_require_role_passes(self):
        ctx = AuthContext("u", "t", ["admin"])
        ctx.require_role("admin")

    def test_require_role_fails(self):
        ctx = AuthContext("u", "t", ["member"])
        with pytest.raises(ForbiddenError):
            ctx.require_role("admin")

    def test_require_tenant_passes(self):
        ctx = AuthContext("u", "t1", ["member"])
        ctx.require_tenant("t1")

    def test_require_tenant_fails(self):
        ctx = AuthContext("u", "t1", ["member"])
        with pytest.raises(TenantIsolationError):
            ctx.require_tenant("t2")


class TestCSRF:
    def test_generate_and_verify(self):
        token = generate_csrf_token("session-abc")
        assert verify_csrf_token(token, "session-abc")

    def test_wrong_session_fails(self):
        token = generate_csrf_token("session-abc")
        assert not verify_csrf_token(token, "session-xyz")
