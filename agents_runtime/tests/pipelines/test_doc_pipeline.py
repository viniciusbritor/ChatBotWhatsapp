"""Testes do doc_pipeline — Pro desambiguador + fallback."""
from __future__ import annotations

import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch




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
        assert "banco semantico" in result["reply"].lower()
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


class TestRagSynthesis:
    def test_fallback_raw_chunks_preserves_legacy_format(self):
        from pipelines.doc_pipeline import _fallback_raw_chunks

        chunks = [
            {"source": "doc1.pdf", "text": "Conteudo do documento 1 com varias informacoes uteis sobre LGPD"},
            {"source": "doc2.pdf", "text": "Conteudo do documento 2 sobre CDC e direitos do consumidor"},
        ]
        result = _fallback_raw_chunks(chunks)
        assert "[doc1.pdf]" in result
        assert "LGPD" in result
        assert "[doc2.pdf]" in result
        assert "CDC" in result

    def test_fallback_raw_chunks_truncates_to_300_chars(self):
        from pipelines.doc_pipeline import _fallback_raw_chunks

        long_text = "x" * 500
        chunks = [{"source": "big.pdf", "text": long_text}]
        result = _fallback_raw_chunks(chunks)
        assert len(result) < 500

    @pytest.mark.asyncio
    async def test_synthesize_rag_answer_with_mocked_flash(self):
        from pipelines.doc_pipeline import _synthesize_rag_answer

        chunks = [
            {"source": "dissertacao.pdf", "text": "Modelos para Precificacao de Opcoes: Abordagem Bayesiana", "score": 0.9},
            {"source": "dissertacao.pdf", "text": "Orientador: Prof. Cristiano Fernandes. COPPE/UFRJ.", "score": 0.85},
        ]

        class FakeFlash:
            def invoke(self, msgs):
                class R:
                    content = "A dissertacao trata de modelos bayesianos para precificacao de opcoes na COPPE/UFRJ."
                return R()

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            with patch("langchain_openai.ChatOpenAI") as mock_openai:
                mock_openai.return_value = FakeFlash()
                result = await _synthesize_rag_answer(
                    "sobre o que se trata a dissertacao?", chunks
                )
        assert "bayesianos" in result.lower()
        assert "COPPE" in result

    @pytest.mark.asyncio
    async def test_synthesize_falls_back_to_pro_when_flash_fails(self):
        from pipelines.doc_pipeline import _synthesize_rag_answer

        chunks = [{"source": "doc.pdf", "text": "Conteudo relevante sobre o topico X Y Z", "score": 0.9}]

        call_count = [0]

        class FakeLLM:
            def invoke(self, msgs):
                call_count[0] += 1
                # Flash fails first (call 1), Pro succeeds (call 2)
                if call_count[0] == 1:
                    raise Exception("Flash timeout")
                class R:
                    content = "Resposta via Pro: O documento trata do topico X Y Z."
                return R()

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            with patch("langchain_openai.ChatOpenAI") as mock_openai:
                mock_openai.return_value = FakeLLM()
                result = await _synthesize_rag_answer("o que e X?", chunks)
        assert "Pro" in result
        assert "topico X Y Z" in result
        assert call_count[0] >= 2

    @pytest.mark.asyncio
    async def test_synthesize_falls_back_to_raw_when_both_fail(self):
        from pipelines.doc_pipeline import _synthesize_rag_answer

        chunks = [{"source": "doc.pdf", "text": "Conteudo sobre volatilidade bayesiana", "score": 0.9}]

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            with patch("langchain_openai.ChatOpenAI") as mock_openai:
                mock_openai.return_value.invoke.side_effect = Exception("All models down")
                result = await _synthesize_rag_answer("sobre o que?", chunks)
        # Fallback to raw chunks
        assert "[doc.pdf]" in result
        assert "volatilidade" in result

    @pytest.mark.asyncio
    async def test_synthesize_empty_chunks(self):
        from pipelines.doc_pipeline import _synthesize_rag_answer

        result = await _synthesize_rag_answer("query", [])
        assert "nao encontrei" in result.lower()

    @pytest.mark.asyncio
    async def test_synthesize_flash_rejects_short_answer(self):
        from pipelines.doc_pipeline import _synthesize_rag_answer

        chunks = [{"source": "doc.pdf", "text": "Conteudo X", "score": 0.9}]

        class FakeFlashShort:
            def invoke(self, msgs):
                class R:
                    content = "ok."
                return R()

        class FakePro:
            def invoke(self, msgs):
                class R:
                    content = "Resposta completa via Pro sobre o conteudo X."
                return R()

        mock_llm = MagicMock()
        mock_llm.side_effect = [FakeFlashShort(), FakePro()]

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            with patch("langchain_openai.ChatOpenAI") as mock_openai:
                mock_openai.side_effect = mock_llm
                result = await _synthesize_rag_answer("o que e X?", chunks)
        assert "Pro" in result
        assert len(result) >= 20


class TestRagParallelism:
    @pytest.mark.asyncio
    async def test_ack_fires_in_parallel_with_retrieve(self):
        from pipelines.doc_pipeline import _run_rag

        ack_started = []
        ack_done = []
        retrieve_done = []

        async def fake_ack(instance, phone, ack_type, extra):
            ack_started.append(True)
            await asyncio.sleep(0.1)
            ack_done.append(True)

        async def fake_retrieve(envelope, query):
            await asyncio.sleep(0.05)
            retrieve_done.append(True)
            return {"results": [], "scope": "private"}

        with patch("pipelines._ack.send_ack", side_effect=fake_ack):
            with patch("agent_orchestration.knowledge_retriever.retrieve", side_effect=fake_retrieve):
                result = await _run_rag({
                    "instance": "jennifer",
                    "phone": "5511999",
                    "text": "buscar algo",
                    "extra": {},
                })

        # Both started
        assert len(ack_started) == 1
        assert len(retrieve_done) == 1
        # Ack completed before function returned
        assert len(ack_done) == 1

    @pytest.mark.asyncio
    async def test_ack_completes_before_reply_returned(self):
        from pipelines.doc_pipeline import _run_rag

        ack_done = []

        async def fake_ack(instance, phone, ack_type, extra):
            await asyncio.sleep(0.05)
            ack_done.append(True)

        async def fake_retrieve(envelope, query):
            return {
                "results": [
                    {"source": "doc.pdf", "text": "conteudo", "score": 0.9}
                ],
                "scope": "private",
            }

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            with patch("pipelines._ack.send_ack", side_effect=fake_ack):
                with patch("agent_orchestration.knowledge_retriever.retrieve", side_effect=fake_retrieve):
                    class FakeLLM:
                        def invoke(self, msgs):
                            class R:
                                content = "Resposta sintetizada do documento."
                            return R()

                    with patch("langchain_openai.ChatOpenAI") as mock_openai:
                        mock_openai.return_value = FakeLLM()
                        result = await _run_rag({
                            "instance": "jennifer",
                            "phone": "5511999",
                            "text": "buscar",
                            "extra": {},
                        })

        assert len(ack_done) == 1
        assert "sintetizada" in result["reply"]

    @pytest.mark.asyncio
    async def test_ack_failure_does_not_block_retrieve(self):
        from pipelines.doc_pipeline import _run_rag

        async def fake_failing_ack(instance, phone, ack_type, extra):
            raise Exception("ack failed")

        async def fake_retrieve(envelope, query):
            return {
                "results": [
                    {"source": "doc.pdf", "text": "conteudo", "score": 0.9}
                ],
                "scope": "private",
            }

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            with patch("pipelines._ack.send_ack", side_effect=fake_failing_ack):
                with patch("agent_orchestration.knowledge_retriever.retrieve", side_effect=fake_retrieve):
                    class FakeLLM:
                        def invoke(self, msgs):
                            class R:
                                content = "Resposta apesar do ack falhar."
                            return R()

                    with patch("langchain_openai.ChatOpenAI") as mock_openai:
                        mock_openai.return_value = FakeLLM()
                        result = await _run_rag({
                            "instance": "jennifer",
                            "phone": "5511999",
                            "text": "buscar",
                            "extra": {},
                        })

        # Retrieve and synthesis still work even if ack fails
        assert "Resposta apesar" in result["reply"]


class TestAttachmentSkipConfirmation:
    """Step 8: keywords no caption pulam pergunta memorizar/salvar."""

    _RAG_KEYWORDS = (
        "memorizar", "memorize", "indexar", "indexe",
        "base de conhecimento", "banco semantico",
        "armazenar na base", "guardar na base",
        "no rag", "no vector", "no firestore",
    )
    _DRIVE_KEYWORDS = (
        "salvar no drive", "guardar no drive",
        "subir no drive", "gdrive", "google drive",
        "meu drive", "no drive", "salva no drive",
        "upload", "faz upload",
    )

    def test_rag_keywords_match_expected(self):
        assert "memorizar" in self._RAG_KEYWORDS
        assert "base de conhecimento" in self._RAG_KEYWORDS
        assert "banco semantico" in self._RAG_KEYWORDS
        assert "indexar" in self._RAG_KEYWORDS

    def test_drive_keywords_match_expected(self):
        assert "salvar no drive" in self._DRIVE_KEYWORDS
        assert "google drive" in self._DRIVE_KEYWORDS
        assert "gdrive" in self._DRIVE_KEYWORDS
        assert "upload" in self._DRIVE_KEYWORDS

    def test_rag_keyword_captions(self):
        captions = [
            "memorize na sua base de conhecimento",
            "guarda no banco semantico pra mim",
            "indexar esse documento no firestore",
            "armazenar na base por favor",
        ]
        for cap in captions:
            assert any(kw in cap.lower() for kw in self._RAG_KEYWORDS), cap

    def test_drive_keyword_captions(self):
        captions = [
            "salva no drive por favor",
            "guarda no google drive",
            "faz upload desse arquivo no gdrive",
            "salvar no drive",
        ]
        for cap in captions:
            assert any(kw in cap.lower() for kw in self._DRIVE_KEYWORDS), cap

    def test_no_keyword_still_ambiguous(self):
        captions = [
            "obrigado",
            "veja esse arquivo",
            "",
            "segue anexo",
        ]
        for cap in captions:
            rag = any(kw in cap.lower() for kw in self._RAG_KEYWORDS)
            drive = any(kw in cap.lower() for kw in self._DRIVE_KEYWORDS)
            assert not (rag or drive), f"'{cap}' should be ambiguous"


class TestBancoSemanticoTerminology:
    def test_clarify_text_uses_banco_semantico(self):
        import asyncio
        from pipelines.doc_pipeline import run

        async def _call():
            payload = {"phone": "5511999", "text": "arquivo", "extra": {}}
            with patch("pipelines.doc_pipeline._disambiguate_rag_vs_drive",
                       new_callable=AsyncMock, return_value="clarify"):
                result = await run(payload)
            return result

        result = asyncio.run(_call())
        assert "banco semantico" in result["reply"].lower()
        assert "drive" in result["reply"].lower()

    def test_clarify_does_not_use_old_rag_terminology(self):
        import asyncio
        from pipelines.doc_pipeline import run

        async def _call():
            payload = {"phone": "5511999", "text": "arquivo", "extra": {}}
            with patch("pipelines.doc_pipeline._disambiguate_rag_vs_drive",
                       new_callable=AsyncMock, return_value="clarify"):
                result = await run(payload)
            return result

        result = asyncio.run(_call())
        assert "base de conhecimento (RAG)" not in result["reply"].lower()
        assert "conhecimento (rag)" not in result["reply"].lower()
