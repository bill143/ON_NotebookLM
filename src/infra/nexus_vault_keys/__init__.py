"""
Nexus Vault Keys — Feature 7: Security, Authentication & Credential Management
Source: Repo #6 (Supabase SSR), Repo #5 (CSRF), Repo #7 (credential model)

Provides:
- JWT token validation and session management
- API key encryption/decryption (AES-256-GCM)
- CSRF protection
- Tenant context extraction from auth tokens
- Rate limiting middleware
"""

from __future__ import annotations

import base64
import hashlib
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Header
from loguru import logger

from src.config import get_settings
from src.exceptions import AuthError, ForbiddenError, RateLimitError, TenantIsolationError

# ── Credential Encryption (AES-256-GCM + Argon2id KDF) ──────

_ARGON2_TIME_COST = 3
_ARGON2_MEMORY_COST = 65536  # 64 MB
_ARGON2_PARALLELISM = 1
_ARGON2_HASH_LEN = 32
_ARGON2_SALT_LEN = 16


def _derive_key_argon2(passphrase: bytes, salt: bytes) -> bytes:
    """Derive a 32-byte AES key from passphrase + salt using Argon2id."""
    from argon2.low_level import Type, hash_secret_raw

    return hash_secret_raw(
        secret=passphrase,
        salt=salt,
        time_cost=_ARGON2_TIME_COST,
        memory_cost=_ARGON2_MEMORY_COST,
        parallelism=_ARGON2_PARALLELISM,
        hash_len=_ARGON2_HASH_LEN,
        type=Type.ID,
    )


def _get_encryption_key_legacy() -> bytes:
    """Legacy SHA-256 key derivation for pre-migration credentials."""
    settings = get_settings()
    return hashlib.sha256(settings.encryption_key.encode()).digest()


def encrypt_credential(plaintext: str, *, salt: bytes | None = None) -> tuple[str, bytes]:
    """
    Encrypt an API key using AES-256-GCM with Argon2id-derived key.

    Returns (ciphertext_b64, salt). Caller must persist the salt
    alongside the ciphertext (ai_credentials.argon2_salt column).
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    settings = get_settings()
    if salt is None:
        salt = os.urandom(_ARGON2_SALT_LEN)

    key = _derive_key_argon2(settings.encryption_key.encode(), salt)
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)

    combined = nonce + ciphertext
    return base64.b64encode(combined).decode(), salt


def decrypt_credential(encrypted: str, *, salt: bytes | None = None) -> str:
    """
    Decrypt a stored API key.

    If *salt* is provided, Argon2id KDF is used.
    If *salt* is None, falls back to legacy SHA-256 derivation so
    pre-migration credentials remain readable until re-encrypted.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    settings = get_settings()

    if salt is not None:
        key = _derive_key_argon2(settings.encryption_key.encode(), salt)
    else:
        key = _get_encryption_key_legacy()

    combined = base64.b64decode(encrypted)
    nonce = combined[:12]
    ciphertext = combined[12:]

    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode()


# ── JWT Token Management ─────────────────────────────────────


def create_access_token(
    user_id: str,
    tenant_id: str,
    roles: list[str],
    *,
    expires_minutes: int | None = None,
) -> str:
    """Create a JWT access token."""
    from jose import jwt

    settings = get_settings()
    expires = expires_minutes or settings.jwt_expiry_minutes

    payload = {
        "sub": user_id,
        "tid": tenant_id,
        "roles": roles,
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=expires),
        "iss": "nexus-notebook-11",
    }

    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_token(token: str) -> dict[str, Any]:
    """Verify and decode a JWT token."""
    from jose import JWTError, jwt

    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer="nexus-notebook-11",
        )
        return payload
    except JWTError as e:
        raise AuthError(f"Invalid token: {e}") from e


# ── Auth Context ─────────────────────────────────────────────


class AuthContext:
    """Authenticated user context extracted from a verified token."""

    def __init__(
        self,
        user_id: str,
        tenant_id: str,
        roles: list[str],
        email: str | None = None,
    ) -> None:
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.roles = roles
        self.email = email

    @classmethod
    def from_token(cls, token: str) -> AuthContext:
        """Create AuthContext from a JWT token."""
        payload = verify_token(token)
        return cls(
            user_id=payload["sub"],
            tenant_id=payload["tid"],
            roles=payload.get("roles", ["member"]),
        )

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles or "owner" in self.roles

    def require_role(self, role: str) -> None:
        """Raise ForbiddenError if user doesn't have the required role."""
        if role not in self.roles and "owner" not in self.roles:
            raise ForbiddenError(f"Requires '{role}' role")

    def require_tenant(self, tenant_id: str) -> None:
        """Raise TenantIsolationError if tenant doesn't match."""
        if self.tenant_id != tenant_id:
            logger.critical(
                "TENANT ISOLATION VIOLATION",
                user_id=self.user_id,
                expected_tenant=self.tenant_id,
                attempted_tenant=tenant_id,
            )
            raise TenantIsolationError("Cross-tenant access denied")


# ── CSRF Protection ──────────────────────────────────────────


def generate_csrf_token(session_id: str) -> str:
    """Generate a CSRF token tied to a session."""
    settings = get_settings()
    raw = f"{session_id}:{settings.csrf_secret}:{int(time.time() // 3600)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def verify_csrf_token(token: str, session_id: str) -> bool:
    """Verify a CSRF token."""
    expected = generate_csrf_token(session_id)
    return token == expected


# ── Rate Limiter (Redis-backed sliding window) ──────────────


class RateLimiter:
    """
    Redis-backed sliding window rate limiter.

    Uses a sorted set per key where each member is a request
    timestamp. This works correctly across multiple Uvicorn
    workers because all state lives in Redis, not in process
    memory.

    Falls back to permissive (allow-all) if Redis is unavailable
    so a transient cache outage never blocks every request.
    """

    _PREFIX = "nexus:rl:"

    def __init__(self) -> None:
        self._redis: Any = None
        self._init_attempted = False

    def _get_redis(self) -> Any:
        """Lazy-connect to Redis on first use."""
        if self._redis is not None:
            return self._redis
        if self._init_attempted:
            return None

        self._init_attempted = True
        try:
            import redis as redis_lib

            settings = get_settings()
            self._redis = redis_lib.Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            self._redis.ping()
            logger.debug("Rate limiter connected to Redis")
        except Exception as exc:
            logger.warning(
                "Rate limiter Redis unavailable — falling back to permissive mode",
                error=str(exc),
            )
            self._redis = None
        return self._redis

    def check(
        self,
        key: str,
        *,
        max_requests: int = 60,
        window_seconds: int = 60,
    ) -> None:
        """Check rate limit. Raises RateLimitError if exceeded."""
        conn = self._get_redis()
        if conn is None:
            return

        redis_key = f"{self._PREFIX}{key}"
        now = time.time()
        window_start = now - window_seconds
        member = f"{now}"

        try:
            pipe = conn.pipeline(transaction=True)
            pipe.zremrangebyscore(redis_key, "-inf", window_start)
            pipe.zcard(redis_key)
            pipe.zadd(redis_key, {member: now})
            pipe.expire(redis_key, window_seconds + 1)
            results = pipe.execute()

            current_count: int = results[1]

            if current_count >= max_requests:
                conn.zrem(redis_key, member)
                oldest = conn.zrange(redis_key, 0, 0, withscores=True)
                retry_after = 0.0
                if oldest:
                    retry_after = (oldest[0][1] + window_seconds) - now
                raise RateLimitError(
                    "Rate limit exceeded",
                    retry_after_seconds=max(0.0, retry_after),
                )
        except RateLimitError:
            raise
        except Exception as exc:
            logger.warning("Rate limiter error — allowing request", error=str(exc))

    def remaining(
        self,
        key: str,
        *,
        max_requests: int = 60,
        window_seconds: int = 60,
    ) -> int:
        """Return how many requests remain in the current window."""
        conn = self._get_redis()
        if conn is None:
            return max_requests

        redis_key = f"{self._PREFIX}{key}"
        now = time.time()
        window_start = now - window_seconds

        try:
            pipe = conn.pipeline(transaction=True)
            pipe.zremrangebyscore(redis_key, "-inf", window_start)
            pipe.zcard(redis_key)
            results = pipe.execute()
            return max(0, max_requests - results[1])
        except Exception:
            return max_requests

    def reset(self, key: str) -> None:
        """Clear the rate limit window for a key (admin use)."""
        conn = self._get_redis()
        if conn is None:
            return
        try:
            conn.delete(f"{self._PREFIX}{key}")
        except Exception as exc:
            logger.warning("Rate limiter reset failed", error=str(exc))


rate_limiter = RateLimiter()


# ── FastAPI Dependency ───────────────────────────────────────


async def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> AuthContext:
    """FastAPI dependency for extracting authenticated user."""
    if not authorization:
        raise AuthError("No authorization header")

    # Support both "Bearer <token>" and raw token
    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization[7:]

    return AuthContext.from_token(token)
