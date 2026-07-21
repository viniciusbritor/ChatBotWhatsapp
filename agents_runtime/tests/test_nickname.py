"""Tests for nickname tool."""
import pytest
from unittest.mock import patch, mock_open


class TestNormalizeName:
    def test_basic(self):
        from tools.nickname import _normalize_name
        assert _normalize_name("vinicius") == "Vinicius"
        assert _normalize_name("VINICIUS") == "Vinicius"
        assert _normalize_name("  vinicius  ") == "Vinicius"


class TestLookup:
    @pytest.mark.asyncio
    async def test_lookup_builtin_hit(self):
        from tools import nickname
        nickname._builtin_dict = None

        with patch("builtins.open", mock_open(read_data='{"Vinicius": ["Vini", "Vinicinho"]}')):
            result = await nickname.lookup("Vinicius")
        assert result["source"] == "builtin"
        assert "Vini" in result["nicknames"]

    @pytest.mark.asyncio
    async def test_lookup_no_match(self):
        from tools import nickname
        nickname._builtin_dict = None

        with patch("builtins.open", mock_open(read_data='{"Vinicius": ["Vini"]}')):
            with patch("os.getenv", return_value=""):
                result = await nickname.lookup("NomeInexistente")
        assert result["source"] == "none"
        assert result["nicknames"] == []


class TestSetConsent:
    @pytest.mark.asyncio
    async def test_set_consent_no_firestore(self):
        from tools import nickname
        nickname._builtin_dict = None

        with patch("os.getenv", return_value=""):
            result = await nickname.set_consent(
                "+5511999999999", "Vinicius", "Vini", accepted=True
            )
        assert result["phone"] == "+5511999999999"
        assert result["accepted"] is True
        assert result["nickname"] == "Vini"


class TestGetPreferredName:
    @pytest.mark.asyncio
    async def test_get_preferred_name_no_firestore(self):
        from tools import nickname
        nickname._builtin_dict = None

        with patch("os.getenv", return_value=""):
            result = await nickname.get_preferred_name("+5511999999999")
        assert result is None
