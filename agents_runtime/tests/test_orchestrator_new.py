"""Testes do novo orchestrator ÔÇö Tier 1 + Tier 2 + multi-intent."""
from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock




class TestTier1Handlers:

    def test_detect_intimacy(self):
        from orchestrator import _detect_intimacy
        assert _detect_intimacy("me chame de Joao") is True
        assert _detect_intimacy("meu apelido e Ze") is True
        assert _detect_intimacy("como devo te chamar") is True
        assert _detect_intimacy("qual minha agenda") is False

    def test_detect_runtime_status(self):
        from orchestrator import _detect_runtime_status
        assert _detect_runtime_status("quantos agentes estao ativos") is True
        assert _detect_runtime_status("status dos agentes") is True
        assert _detect_runtime_status("qual minha agenda") is False

    def test_detect_correction(self):
        from orchestrator import _detect_correction
        assert _detect_correction("na verdade meu nome e Vinicius") is True
        assert _detect_correction("errado, nao e assim") is True
        assert _detect_correction("qual minha agenda") is False

    def test_detect_morality(self):
        from orchestrator import _detect_morality
        assert _detect_morality("sua puta") is True
        assert _detect_morality("vai se foder") is True
        assert _detect_morality("qual minha agenda") is False

    def test_detect_web(self):
        from orchestrator import _detect_web
        assert _detect_web("pesquisar sobre LGPD") is True
        assert _detect_web("pesquise na web") is True
        assert _detect_web("https://example.com") is True
        assert _detect_web("qual minha agenda") is False


class TestAttachmentsAndCommands:
    def _payload(self, text="memorizar", extra=None):
        e = extra or {}
        return {
            "instance": "jennifer", "phone": "+5511966830020",
            "text": text, "sender_name": "Vinicius", "extra": e,
        }

    @pytest.mark.asyncio
    async def test_attachment_flag_triggers_handler(self):
        from orchestrator import orchestrate

        with patch("pipelines.calendar_pipeline.detect", return_value=False):
            with patch("pipelines.email_pipeline.detect", return_value=False):
                with patch("orchestrator._classify_intent_llm", return_value="conversa"):
                    with patch("orchestrator._detect_web", return_value=False):
                        with patch("orchestrator._handle_attachment", new_callable=AsyncMock) as mock_att:
                            mock_att.return_value = {"reply": "Arquivo indexado!", "delay_ms": 500,
                                                     "presence": "composing",
                                                     "metadata": {"attachment": "indexed"}}
                            with patch("pipelines.jennifer_pipeline.run", new_callable=AsyncMock):
                                result = await orchestrate(
                                    self._payload("pdf", {"has_document": True, "doc_mimetype": "application/pdf"})
                                )
        assert mock_att.called


class TestAttachmentModeConfirmation:
    """F4d: usuario confirma 'memorizar' apos pergunta 'memorizar ou salvar?'."""

    def _payload(self, text="memorizar"):
        return {
            "instance": "jennifer",
            "phone": "+5511966830020",
            "text": text,
            "sender_name": "Vinicius",
            "extra": {"remote_jid": "5511966830020@s.whatsapp.net"},
        }

    def _pending_action(self):
        return {
            "action_type": "attachment_mode",
            "payload": {
                "attachment_payload": {
                    "instance": "jennifer",
                    "phone": "+5511966830020",
                    "message_id": "test-att-msg-001",
                    "sender_name": "Vinicius",
                    "extra": {
                        "has_document": True,
                        "doc_mimetype": "application/pdf",
                        "doc_file_name": "teste.pdf",
                        "remote_jid": "5511966830020@s.whatsapp.net",
                    },
                },
            },
        }

    @pytest.mark.asyncio
    async def test_memorizar_confirmation_calls_handler_with_is_attachment(self):
        """Quando o usuario responde 'memorizar', _handle_attachment
        deve ser chamado com is_attachment=True e is_save=True."""
        from orchestrator import orchestrate

        pending = self._pending_action()

        with patch("core.pending_actions.get_pending_action", new_callable=AsyncMock) as mock_get:
            with patch("core.pending_actions.consume_pending_action", new_callable=AsyncMock) as mock_consume:
                with patch("pipelines.calendar_pipeline.detect", return_value=False):
                    with patch("pipelines.email_pipeline.detect", return_value=False):
                        with patch("orchestrator._classify_intent_llm", return_value="conversa"):
                            with patch("orchestrator._detect_web", return_value=False):
                                with patch("orchestrator._handle_attachment", new_callable=AsyncMock) as mock_att:
                                    mock_att.return_value = {
                                        "reply": "Feito! Memorei 10 trechos.",
                                        "delay_ms": 500,
                                        "presence": "composing",
                                        "metadata": {"attachment": "rag_individual", "source_name": "teste.pdf"},
                                    }
                                    with patch("pipelines.jennifer_pipeline.run", new_callable=AsyncMock):
                                        mock_get.return_value = pending
                                        result = await orchestrate(self._payload("memorizar"))

        assert mock_get.called
        assert mock_consume.called
        assert mock_att.called
        call_kwargs = mock_att.call_args
        intent = call_kwargs[0][1]  # segundo arg posicional = intent
        assert intent["is_attachment"] is True
        assert intent["is_attachment_save"] is True
        assert intent["is_attachment_file"] is False
        assert result["reply"] == "Feito! Memorei 10 trechos."
        assert result["metadata"]["attachment"] == "rag_individual"

    @pytest.mark.asyncio
    async def test_salvar_confirmation_calls_handler_with_is_attachment(self):
        """Quando o usuario responde 'salvar', _handle_attachment
        deve ser chamado com is_attachment=True e is_file=True."""
        from orchestrator import orchestrate

        pending = self._pending_action()

        with patch("core.pending_actions.get_pending_action", new_callable=AsyncMock) as mock_get:
            with patch("core.pending_actions.consume_pending_action", new_callable=AsyncMock) as mock_consume:
                with patch("pipelines.calendar_pipeline.detect", return_value=False):
                    with patch("pipelines.email_pipeline.detect", return_value=False):
                        with patch("orchestrator._classify_intent_llm", return_value="conversa"):
                            with patch("orchestrator._detect_web", return_value=False):
                                with patch("orchestrator._handle_attachment", new_callable=AsyncMock) as mock_att:
                                    mock_att.return_value = {
                                        "reply": "Feito! Salvei no Drive.",
                                        "delay_ms": 500,
                                        "presence": "composing",
                                        "metadata": {"attachment": "drive_individual", "source_name": "teste.pdf"},
                                    }
                                    with patch("pipelines.jennifer_pipeline.run", new_callable=AsyncMock):
                                        mock_get.return_value = pending
                                        result = await orchestrate(self._payload("salvar"))

        assert mock_att.called
        call_kwargs = mock_att.call_args
        intent = call_kwargs[0][1]
        assert intent["is_attachment"] is True
        assert intent["is_attachment_save"] is False
        assert intent["is_attachment_file"] is True
        assert result["reply"] == "Feito! Salvei no Drive."


class TestIdempotency:
    def _payload(self):
        return {
            "instance": "jennifer", "phone": "+5511966830020",
            "text": "oi", "sender_name": "Vinicius",
            "extra": {"remote_jid": "5511966830020@s.whatsapp.net"},
            "message_id": "test-msg-id-001",
        }

    @pytest.mark.asyncio
    async def test_idempotency_cache_hit(self):
        import time
        from orchestrator import _response_cache, _idempotency_key, orchestrate, CACHE_TTL_SEC

        cache_key = _idempotency_key(self._payload())
        _response_cache[cache_key] = {"reply": "cached", "delay_ms": 0, "presence": "composing",
                                       "metadata": {}, "ts": int(time.time())}
        result = await orchestrate(self._payload())
        assert result["reply"] == "cached"
        assert result["metadata"]["cached"] is True
        del _response_cache[cache_key]
