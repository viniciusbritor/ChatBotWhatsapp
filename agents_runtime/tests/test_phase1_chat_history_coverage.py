"""Fase 1 — Cobertura 100% de indexacao no message-history.

Verifica que os 3 handlers TIER 1 (_handle_morality, _handle_correction,
_handle_intimacy) chamam _finalize_orchestration mesmo quando o agente
nao existe no Firestore.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

_BASE_PAYLOAD = {
    "instance": "jennifer",
    "phone": "+5511966830020",
    "text": "texto de teste",
    "sender_name": "Vinicius",
    "extra": {"remote_jid": "5511966830020@s.whatsapp.net"},
}


class TestPhase1Coverage:
    def _patch_finalize(self):
        finalize_mock = AsyncMock()
        finalize_mock.return_value = {"reply": "ok"}
        return finalize_mock

    @pytest.mark.asyncio
    async def test_morality_fallback_indexes(self):
        from orchestrator import _handle_morality

        finalize_mock = self._patch_finalize()
        with patch("orchestrator._finalize_orchestration", finalize_mock):
            with patch("orchestrator.get_agent", return_value=None):
                await _handle_morality(
                    _BASE_PAYLOAD, "texto agressivo", "Vinicius",
                    "cache_key_123", "jennifer", "+5511966830020",
                )
        finalize_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_correction_fallback_indexes(self):
        from orchestrator import _handle_correction

        finalize_mock = self._patch_finalize()
        with patch("orchestrator._finalize_orchestration", finalize_mock):
            with patch("orchestrator.get_agent", return_value=None):
                await _handle_correction(
                    _BASE_PAYLOAD, "na verdade meu nome e Joao",
                    "Vinicius", "cache_key_456",
                )
        finalize_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_intimacy_fallback_indexes(self):
        from orchestrator import _handle_intimacy

        finalize_mock = self._patch_finalize()
        with patch("orchestrator._finalize_orchestration", finalize_mock):
            with patch("orchestrator.get_agent", return_value=None):
                await _handle_intimacy(
                    _BASE_PAYLOAD, "me chame de Ze",
                    "Vinicius", "cache_key_789",
                    "Vinicius", "+5511966830020",
                )
        finalize_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_morality_fallback_blocks_message(self):
        from orchestrator import _handle_morality

        with patch("orchestrator.get_agent", return_value=None):
            result = await _handle_morality(
                _BASE_PAYLOAD, "texto agressivo", "Vinicius",
                "cache_key_abc", "jennifer", "+5511966830020",
            )
        assert "bloqueada" in result["reply"].lower()
        assert result["metadata"]["blocked"] is True

    @pytest.mark.asyncio
    async def test_correction_fallback_acknowledges(self):
        from orchestrator import _handle_correction

        with patch("orchestrator.get_agent", return_value=None):
            result = await _handle_correction(
                _BASE_PAYLOAD, "errado, nao e assim",
                "Vinicius", "cache_key_def",
            )
        assert "correcao" in result["reply"].lower()

    @pytest.mark.asyncio
    async def test_intimacy_fallback_greets(self):
        from orchestrator import _handle_intimacy

        with patch("orchestrator.get_agent", return_value=None):
            result = await _handle_intimacy(
                _BASE_PAYLOAD, "me chame de Ze",
                "Vinicius", "cache_key_ghi",
                "Vinicius", "+5511966830020",
            )
        assert "Vinicius" in result["reply"]

    @pytest.mark.asyncio
    async def test_morality_with_agent_still_indexes(self):
        from orchestrator import _handle_morality

        finalize_mock = self._patch_finalize()
        fake_agent = {"id": "agent-morality", "system_prompt": "bloqueie ofensas"}
        with patch("orchestrator._finalize_orchestration", finalize_mock):
            with patch("orchestrator.get_agent", return_value=fake_agent):
                with patch("orchestrator._execute_agent", new_callable=AsyncMock) as exec_mock:
                    exec_mock.return_value = {"reply": "bloqueado", "metadata": {}}
                    await _handle_morality(
                        _BASE_PAYLOAD, "texto agressivo", "Vinicius",
                        "cache_key_jkl", "jennifer", "+5511966830020",
                    )
        finalize_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_intimacy_with_agent_still_indexes(self):
        from orchestrator import _handle_intimacy

        finalize_mock = self._patch_finalize()
        fake_agent = {"id": "agent-intimacy", "system_prompt": "apelidos"}
        with patch("orchestrator._finalize_orchestration", finalize_mock):
            with patch("orchestrator.get_agent", return_value=fake_agent):
                with patch("orchestrator._execute_agent", new_callable=AsyncMock) as exec_mock:
                    exec_mock.return_value = {"reply": "pode me chamar de Ze", "metadata": {}}
                    await _handle_intimacy(
                        _BASE_PAYLOAD, "me chame de Ze",
                        "Vinicius", "cache_key_mno",
                        "Vinicius", "+5511966830020",
                    )
        finalize_mock.assert_called_once()
