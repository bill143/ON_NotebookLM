"""Unit tests for the DEV_AUTO_LOGIN development bypass in get_current_user."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.exceptions import AuthError
from src.infra.nexus_vault_keys import DEV_TENANT_ID, DEV_USER_ID, get_current_user


def _settings(dev_auto_login: bool, is_production: bool) -> MagicMock:
    s = MagicMock()
    s.dev_auto_login = dev_auto_login
    s.is_production = is_production
    return s


class TestDevAutoLogin:
    @pytest.mark.asyncio
    async def test_no_header_without_flag_still_rejected(self):
        with patch(
            "src.infra.nexus_vault_keys.get_settings",
            return_value=_settings(dev_auto_login=False, is_production=False),
        ):
            with pytest.raises(AuthError):
                await get_current_user(authorization=None)

    @pytest.mark.asyncio
    async def test_flag_enables_dev_identity_in_development(self):
        with patch(
            "src.infra.nexus_vault_keys.get_settings",
            return_value=_settings(dev_auto_login=True, is_production=False),
        ):
            ctx = await get_current_user(authorization=None)

        assert ctx.user_id == DEV_USER_ID
        assert ctx.tenant_id == DEV_TENANT_ID
        assert ctx.is_admin

    @pytest.mark.asyncio
    async def test_flag_is_ignored_in_production(self):
        with patch(
            "src.infra.nexus_vault_keys.get_settings",
            return_value=_settings(dev_auto_login=True, is_production=True),
        ):
            with pytest.raises(AuthError):
                await get_current_user(authorization=None)

    def test_production_settings_reject_the_flag(self):
        from src.config import Settings

        with pytest.raises(ValueError, match="DEV_AUTO_LOGIN"):
            Settings(
                environment="production",
                dev_auto_login=True,
                jwt_secret="x" * 48,
                csrf_secret="x" * 48,
                encryption_key="x" * 48,
            )
