"""Testes do doc_pipeline — Pro desambiguador + fallback."""
from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("GCP_PROJECT", "test-project")


class TestDocDetect:

    def test_detect_pdf(self):
        from pipelines.doc_pipeline import detect
        assert detect("leia o pdf") is True

    def test_detect_docx(self):
        from pipelines.doc_pipeline import detect
        assert detect("arquivo docx") is True

    def test_detect_ata(self):
        from pipelines.doc_pipeline import detect
        assert detect("ata da reuniao") is True

    def test_detect_documento(self):
        from pipelines.doc_pipeline import detect
        assert detect("leia o documento") is True

    def test_detect_memorizar(self):
        from pipelines.doc_pipeline import detect
        assert detect("memorize esse contrato") is True

    def test_detect_salvar(self):
        from pipelines.doc_pipeline import detect
        assert detect("salve isso no drive") is True

    def test_negative_calendar(self):
        from pipelines.doc_pipeline import detect
        assert detect("minha agenda") is False

    def test_negative_email(self):
        from pipelines.doc_pipeline import detect
        assert detect("meus emails") is False

    def test_negative_conversa(self):
        from pipelines.doc_pipeline import detect
        assert detect("oi tudo bem") is False


class TestDisambiguateKeywords:
    """Fast path: keywords explicitas → decisao sem chamar Pro."""

    @pytest.mark.asyncio
    async def test_rag_keyword_base_de_conhecimento(self):
        from pipelines.doc_pipeline import _disambiguate_rag_vs_drive

        result = await _disambiguate_rag_vs_drive(
            "quais documentos voce tem na sua base de conhecimento"
        )
        assert result == "rag"

    @pytest.mark.asyncio
    async def test_rag_keyword_memorizou(self):
        from pipelines.doc_pipeline import _disambiguate_rag_vs_drive

        result = await _disambiguate_rag_vs_drive(
            "voce memorizou alguma coisa sobre LGPD?"
        )
        assert result == "rag"

    @pytest.mark.asyncio
    async def test_rag_keyword_indexado(self):
        from pipelines.doc_pipeline import _disambiguate_rag_vs_drive

        result = await _disambiguate_rag_vs_drive(
            "documentos indexados no vector"
        )
        assert result == "rag"

    @pytest.mark.asyncio
    async def test_rag_keyword_seus_documentos(self):
        from pipelines.doc_pipeline import _disambiguate_rag_vs_drive

        result = await _disambiguate_rag_vs_drive(
            "meus documentos salvos"
        )
        assert result == "rag"

    @pytest.mark.asyncio
    async def test_drive_keyword_meu_drive(self):
        from pipelines.doc_pipeline import _disambiguate_rag_vs_drive

        result = await _disambiguate_rag_vs_drive(
            "liste os arquivos do meu drive"
        )
        assert result == "drive"

    @pytest.mark.asyncio
    async def test_drive_keyword_dentro_do_drive(self):
        from pipelines.doc_pipeline import _disambiguate_rag_vs_drive

        result = await _disambiguate_rag_vs_drive(
            "dentro do drive tem uma pasta"
        )
        assert result == "drive"

    @pytest.mark.asyncio
    async def test_drive_keyword_upload(self):
        from pipelines.doc_pipeline import _disambiguate_rag_vs_drive

        result = await _disambiguate_rag_vs_drive(
            "faca upload do arquivo"
        )
        assert result == "drive"


class TestDisambiguatePro:
    """DeepSeek V4 Pro — apenas quando keywords ambíguas."""

    @pytest.mark.asyncio
    async def test_pro_returns_rag_for_ambiguous_query(self):
        mock_response = type("Resp", (), {"content": "RAG"})()
        from pipelines.doc_pipeline import _disambiguate_rag_vs_drive

        with patch("langchain_openai.ChatOpenAI") as mock_llm:
            mock_llm.return_value.invoke.return_value = mock_response
            with patch("os.getenv", return_value="fake-key"):
                result = await _disambiguate_rag_vs_drive(
                    "leia o documento sobre editais"
                )
        assert result == "rag"

    @pytest.mark.asyncio
    async def test_pro_returns_drive_for_ambiguous_query(self):
        mock_response = type("Resp", (), {"content": "DRIVE"})()
        from pipelines.doc_pipeline import _disambiguate_rag_vs_drive

        with patch("langchain_openai.ChatOpenAI") as mock_llm:
            mock_llm.return_value.invoke.return_value = mock_response
            with patch("os.getenv", return_value="fake-key"):
                result = await _disambiguate_rag_vs_drive(
                    "leia o documento do cliente"
                )
        assert result == "drive"

    @pytest.mark.asyncio
    async def test_pro_unavailable_returns_clarify(self):
        from pipelines.doc_pipeline import _disambiguate_rag_vs_drive

        with patch("langchain_openai.ChatOpenAI") as mock_llm:
            mock_llm.side_effect = Exception("API down")
            result = await _disambiguate_rag_vs_drive(
                "leia o documento"
            )
        assert result == "clarify"

    @pytest.mark.asyncio
    async def test_pro_no_api_key_returns_clarify(self):
        from pipelines.doc_pipeline import _disambiguate_rag_vs_drive

        with patch("os.getenv", return_value=""):
            result = await _disambiguate_rag_vs_drive(
                "leia o documento"
            )
        assert result == "clarify"


class TestDocRun:
    """run() — detect → disambiguate → route."""

    def _payload(self, text="leia o documento sobre LGPD"):
        return {
            "instance": "jennifer",
            "phone": "+5511966830020",
            "text": text,
            "sender_name": "Vinicius",
            "extra": {"remote_jid": "5511966830020@s.whatsapp.net"},
        }

    @pytest.mark.asyncio
    async def test_run_rag_path(self):
        from pipelines.doc_pipeline import run

        with patch(
            "pipelines.doc_pipeline._disambiguate_rag_vs_drive",
            new_callable=AsyncMock,
            return_value="rag",
        ):
            with patch(
                "pipelines.doc_pipeline._run_rag",
                new_callable=AsyncMock,
                return_value={
                    "reply": "Encontrado: Lei 13.709...",
                    "delay_ms": 0,
                    "presence": "composing",
                    "metadata": {"count": 1},
                },
            ):
                result = await run(
                    self._payload("documentos sobre LGPD na base de conhecimento")
                )
        assert "LGPD" in result["reply"].upper() or "Encontrado" in result["reply"]

    @pytest.mark.asyncio
    async def test_run_drive_path(self):
        from pipelines.doc_pipeline import run

        with patch(
            "pipelines.doc_pipeline._disambiguate_rag_vs_drive",
            new_callable=AsyncMock,
            return_value="drive",
        ):
            with patch(
                "pipelines.doc_pipeline._run_drive",
                new_callable=AsyncMock,
                return_value={
                    "reply": "Arquivos no Drive: ata.pdf",
                    "delay_ms": 500,
                    "presence": "composing",
                    "metadata": {"agent_id": "manager-drive"},
                },
            ):
                result = await run(
                    self._payload("liste os arquivos do drive")
                )
        assert "Drive" in result.get("reply", "") or "ata" in result.get("reply", "")

    @pytest.mark.asyncio
    async def test_run_clarify_path(self):
        from pipelines.doc_pipeline import run

        with patch(
            "pipelines.doc_pipeline._disambiguate_rag_vs_drive",
            new_callable=AsyncMock,
            return_value="clarify",
        ):
            result = await run(self._payload())
        assert result["metadata"]["needs_clarification"] is True
        assert "base de conhecimento" in result["reply"].lower()

    @pytest.mark.asyncio
    async def test_run_rag_path_error(self):
        from pipelines.doc_pipeline import _run_rag

        with patch(
            "agent_orchestration.knowledge_retriever.retrieve",
            side_effect=Exception("Firestore down"),
        ):
            result = await _run_rag(self._payload())
        assert "nao consegui" in result["reply"].lower()

    @pytest.mark.asyncio
    async def test_run_drive_guard_deny(self):
        from pipelines.doc_pipeline import _run_drive

        with patch(
            "pipelines._guard.check_google_access",
            new_callable=AsyncMock,
            return_value={"verdict": "deny", "reason": "not_owner"},
        ):
            result = await _run_drive(self._payload())
        assert result["metadata"]["blocked"] is True

    @pytest.mark.asyncio
    async def test_isolamento_rag_nunca_retorna_drive_url(self):
        from pipelines.doc_pipeline import _run_rag

        with patch(
            "agent_orchestration.knowledge_retriever.retrieve",
            new_callable=AsyncMock,
            return_value={
                "results": [
                    {"source": "lei-13709.pdf", "text": "Lei Geral de Protecao de Dados", "score": 0.9}
                ],
                "decision": "rag",
                "scope": "private",
                "count": 1,
            },
        ):
            result = await _run_rag(self._payload())
        reply = result["reply"].lower()
        assert "drive.google.com" not in reply
        assert "vector" not in reply

    @pytest.mark.asyncio
    async def test_isolamento_drive_nunca_retorna_vector(self):
        from pipelines.doc_pipeline import _run_drive

        with patch(
            "pipelines._guard.check_google_access",
            new_callable=AsyncMock,
            return_value={"verdict": "allow"},
        ):
            with patch("pipelines._ack.send_ack", new_callable=AsyncMock):
                with patch("pipelines._prefetch.prefetch_for_agent", new_callable=AsyncMock, return_value=None):
                    with patch(
                        "pipelines._executor.run_agent",
                        new_callable=AsyncMock,
                        return_value={
                            "reply": "Seus arquivos no Drive: ata.pdf, relatorio.docx",
                            "delay_ms": 500,
                            "presence": "composing",
                            "metadata": {"agent_id": "manager-drive"},
                        },
                    ):
                        result = await _run_drive(self._payload())
        reply = result["reply"].lower()
        assert "firestore" not in reply
        assert "vector" not in reply
        assert "embedding" not in reply

    @pytest.mark.asyncio
    async def test_detect_then_run_rag_route(self):
        """Integration: detect() True → run() → disambiguate → RAG."""
        from pipelines.doc_pipeline import detect, run

        assert detect("documentos sobre LGPD na base de conhecimento") is True

        with patch(
            "pipelines.doc_pipeline._disambiguate_rag_vs_drive",
            new_callable=AsyncMock,
            return_value="rag",
        ):
            with patch(
                "pipelines.doc_pipeline._run_rag",
                new_callable=AsyncMock,
                return_value={
                    "reply": "Resultados da base de conhecimento...",
                    "delay_ms": 0,
                    "presence": "composing",
                    "metadata": {"count": 3},
                },
            ):
                result = await run(
                    self._payload("documentos sobre LGPD na base de conhecimento")
                )
        assert "Resultados" in result["reply"]
        assert result["metadata"]["count"] == 3
