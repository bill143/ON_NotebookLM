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
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from loguru import logger

from src.config import get_settings
from src.exceptions import AuthError, ForbiddenError, RateLimitError, TenantIsolationError
from fastapi import Header


# ── Credential Encryption (AES-256-GCM) ─────────────────────

def _get_encryption_key() -> bytes:
    """Derive a 32-byte key from the configured encryption key."""
    settings = get_settings()
    key = settings.encryption_key.encode()
    return hashlib.sha256(key).digest()


def encrypt_credential(plaintext: str) -> str:
    """Encrypt an API key or secret for storage."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _get_encryption_key()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)

    # Store as base64: nonce + ciphertext
    combined = nonce + ciphertext
    return base64.b64encode(combined).decode()


def decrypt_credential(encrypted: str) -> str:
    """Decrypt a stored API key or secret."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _get_encryption_key()
    combined = base64.b64decode(encrypted)
    nonce = combined[:12]
    ciphertext = combined[12:]

    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode()


# ── JWT Token Management ─────────────────────────────────────

def create_access_token(
    user_id: str,
    tenant_id: str,
    roles: list[str],
    *,
    expires_minutes: Optional[int] = None,
) -> str:
    """Create a JWT access token."""
    from jose import jwt

    settings = get_settings()
    expires = expires_minutes or settings.jwt_expiry_minutes

    payload = {
        "sub": user_id,
        "tid": tenant_id,
        "roles": roles,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expires),
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
        raise AuthError(f"Invalid token: {e}")


# ── Auth Context ─────────────────────────────────────────────

class AuthContext:
    """Authenticated user context extracted from a verified token."""

    def __init__(
        self,
        user_id: str,
        tenant_id: str,
        roles: list[str],
        email: Optional[str] = None,
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


# ── Rate Limiter ─────────────────────────────────────────────

class RateLimiter:
    """
    In-memory rate limiter with sliding window.
    For production: replace with Redis-backed implementation.
    """

    def __init__(self) -> None:
        self._windows: dict[str, list[float]] = {}

    def check(
        self,
        key: str,
        *,
        max_requests: int = 60,
        window_seconds: int = 60,
    ) -> None:
        """Check rate limit. Raises RateLimitError if exceeded."""
        now = time.time()
        window_start = now - window_seconds

        if key not in self._windows:
            self._windows[key] = []

        # Clean old entries
        self._windows[key] = [t for t in self._windows[key] if t > window_start]

        if len(self._windows[key]) >= max_requests:
            retry_after = self._windows[key][0] - window_start + window_seconds
            raise RateLimitError(
                "Rate limit exceeded",
                retry_after_seconds=max(0, retry_after),
            )

        self._windows[key].append(now)


rate_limiter = RateLimiter()


# ── FastAPI Dependency ───────────────────────────────────────

async def get_current_user(authorization: str = Header("")) -> AuthContext:
    """FastAPI dependency for extracting authenticated user."""
    if not authorization:
        raise AuthError("No authorization header")

    # Support both "Bearer <token>" and raw token
    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization[7:]

    return AuthContext.from_token(token)
