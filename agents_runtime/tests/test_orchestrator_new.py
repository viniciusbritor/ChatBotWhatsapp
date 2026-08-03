"""Testes do novo orchestrator — Tier 1 + Tier 2 + multi-intent."""
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


class TestTier2Routing:

    def _payload(self, text="qual minha agenda?"):
        return {
            "instance": "jennifer", "phone": "+5511966830020",
            "text": text, "sender_name": "Vinicius",
            "extra": {"remote_jid": "5511966830020@s.whatsapp.net"},
        }

    @pytest.mark.asyncio
    async def test_single_calendar_match(self):
        from orchestrator import orchestrate

        with patch("pipelines.calendar_pipeline.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {"reply": "Agenda: reuniao as 15h", "delay_ms": 500,
                                     "presence": "composing", "metadata": {"agent_id": "manager-calendar"}}
            with patch("pipelines.email_pipeline.detect", return_value=False):
                with patch("pipelines.doc_pipeline.detect", return_value=False):
                    with patch("pipelines.jennifer_pipeline.run", new_callable=AsyncMock):
                        result = await orchestrate(self._payload())
        assert "reuniao" in result["reply"].lower()

    @pytest.mark.asyncio
    async def test_single_email_match(self):
        from orchestrator import orchestrate

        with patch("pipelines.email_pipeline.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {"reply": "Voce tem 3 emails.", "delay_ms": 500,
                                     "presence": "composing", "metadata": {"agent_id": "manager-email"}}
            with patch("pipelines.calendar_pipeline.detect", return_value=False):
                with patch("pipelines.doc_pipeline.detect", return_value=False):
                    with patch("pipelines.jennifer_pipeline.run", new_callable=AsyncMock):
                        result = await orchestrate(self._payload("meus emails"))
        assert "email" in result["reply"].lower()

    @pytest.mark.asyncio
    async def test_double_match_parallel(self):
        from orchestrator import orchestrate

        async def cal_run(p): return {"reply": "Reuniao as 15h", "delay_ms": 500,
                                       "presence": "composing", "metadata": {}}
        async def eml_run(p): return {"reply": "3 emails nao lidos", "delay_ms": 300,
                                       "presence": "composing", "metadata": {}}

        with patch("pipelines.calendar_pipeline.detect", return_value=True):
            with patch("pipelines.calendar_pipeline.run", new=cal_run):
                with patch("pipelines.email_pipeline.detect", return_value=True):
                    with patch("pipelines.email_pipeline.run", new=eml_run):
                        with patch("pipelines.doc_pipeline.detect", return_value=False):
                            with patch("pipelines.jennifer_pipeline.run", new_callable=AsyncMock):
                                with patch("orchestrator._detect_web", return_value=False):
                                    result = await orchestrate(self._payload())
        assert "---" in result["reply"]
        assert result["metadata"]["multi_intent"] is True
        assert result["metadata"]["pipelines"] == 2

    @pytest.mark.asyncio
    async def test_no_match_fallback_jennifer(self):
        from orchestrator import orchestrate

        with patch("pipelines.jennifer_pipeline.run", new_callable=AsyncMock) as mock_jen:
            mock_jen.return_value = {"reply": "Oi! Como posso ajudar?", "delay_ms": 500,
                                     "presence": "composing", "metadata": {"agent_id": "jennifer"}}
            with patch("pipelines.calendar_pipeline.detect", return_value=False):
                with patch("pipelines.email_pipeline.detect", return_value=False):
                    with patch("pipelines.doc_pipeline.detect", return_value=False):
                        with patch("orchestrator._detect_web", return_value=False):
                            with patch("orchestrator._setup_nickname_consent", new_callable=AsyncMock):
                                result = await orchestrate(self._payload("oi tudo bem?"))
        assert result["metadata"]["agent_id"] == "jennifer"

    @pytest.mark.asyncio
    async def test_morality_blocks_calendar(self):
        """Tier 1 morality deve bloquear antes de chegar no Tier 2 calendar."""
        from orchestrator import orchestrate

        with patch("pipelines.calendar_pipeline.run", new_callable=AsyncMock) as mock_cal:
            mock_cal.return_value = {"reply": "Agenda...", "delay_ms": 500, "presence": "composing", "metadata": {}}
            result = await orchestrate(self._payload("sua puta agenda"))
        assert not mock_cal.called, "Calendar nao deveria ser chamado com insulto"

    @pytest.mark.asyncio
    async def test_runtime_blocks_calendar(self):
        """Tier 1 runtime deve bloquear antes de Tier 2."""
        from orchestrator import orchestrate

        with patch("pipelines.calendar_pipeline.run", new_callable=AsyncMock) as mock_cal:
            with patch("orchestrator._handle_runtime_status", new_callable=AsyncMock) as mock_rt:
                mock_rt.return_value = {"reply": "Agentes ativos: 5", "delay_ms": 0, "presence": "composing",
                                        "metadata": {"agent_id": "runtime-status"}}
                result = await orchestrate(self._payload("quantos agentes estao ativos e agenda"))
        assert not mock_cal.called


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
                with patch("pipelines.doc_pipeline.detect", return_value=False):
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
