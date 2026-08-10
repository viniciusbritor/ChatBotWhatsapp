"""Testes do onboarding — vinculo email do Portal ao telefone WhatsApp."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestLinkEmail:
    @pytest.mark.asyncio
    async def test_link_email_success(self):
        from tools.onboarding import link_email

        db = MagicMock()
        with patch("tools.onboarding._get_firestore", return_value=db):
            result = await link_email(phone="5511777777777", email="ana@company.com")
        assert result["linked"] is True
        assert result["email"] == "ana@company.com"
        doc = db.collection.return_value.document.return_value
        doc.set.assert_called_once()
        data = doc.set.call_args[0][0]
        assert data["email"] == "ana@company.com"
        assert data["phone"] == "5511777777777"

    @pytest.mark.asyncio
    async def test_link_email_lowercases(self):
        from tools.onboarding import link_email

        db = MagicMock()
        with patch("tools.onboarding._get_firestore", return_value=db):
            result = await link_email(phone="5511777777777", email="Ana@Company.COM")
        assert result["linked"] is True
        assert result["email"] == "ana@company.com"

    @pytest.mark.asyncio
    async def test_link_email_requires_both(self):
        from tools.onboarding import link_email

        assert (await link_email(phone="", email="a@b.com"))["error"] == "phone_and_email_required"
        assert (await link_email(phone="5511777777777", email=""))["error"] == "phone_and_email_required"

    @pytest.mark.asyncio
    async def test_link_email_rejects_invalid_email(self):
        from tools.onboarding import link_email

        result = await link_email(phone="5511777777777", email="not-an-email")
        assert result["error"] == "invalid_email"

    @pytest.mark.asyncio
    async def test_link_email_firestore_unavailable(self):
        from tools.onboarding import link_email

        with patch("tools.onboarding._get_firestore", return_value=None):
            result = await link_email(phone="5511777777777", email="ana@company.com")
        assert result["error"] == "firestore_unavailable"

    def test_tool_registered(self):
        from tool_registry import get_tool

        fn = get_tool("onboarding.link_email")
        assert fn is not None
        assert callable(fn)
