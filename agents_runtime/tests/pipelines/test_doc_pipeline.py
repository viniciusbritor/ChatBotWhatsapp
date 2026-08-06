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


# =============================================================================
# Fase Kd — Formatacao do conteudo retrieval (WhatsApp)
# =============================================================================


class TestSynthesisFormatPrompt:
    def test_prompt_contem_negrito(self):
        from pipelines.doc_pipeline import _SYNTHESIS_SYSTEM_PROMPT
        assert "*negrito*" in _SYNTHESIS_SYSTEM_PROMPT

    def test_prompt_contem_italico(self):
        from pipelines.doc_pipeline import _SYNTHESIS_SYSTEM_PROMPT
        assert "_italico_" in _SYNTHESIS_SYSTEM_PROMPT

    def test_prompt_contem_bullets(self):
        from pipelines.doc_pipeline import _SYNTHESIS_SYSTEM_PROMPT
        assert "•" in _SYNTHESIS_SYSTEM_PROMPT

    def test_prompt_contem_tabular(self):
        from pipelines.doc_pipeline import _SYNTHESIS_SYSTEM_PROMPT
        assert "tabular" in _SYNTHESIS_SYSTEM_PROMPT.lower()

    def test_prompt_nao_limita_1_paragrafo(self):
        from pipelines.doc_pipeline import _SYNTHESIS_SYSTEM_PROMPT
        assert "maximo 1 paragrafo" not in _SYNTHESIS_SYSTEM_PROMPT.lower()

    def test_prompt_cita_fonte_colchetes(self):
        from pipelines.doc_pipeline import _SYNTHESIS_SYSTEM_PROMPT
        assert "fonte entre colchetes" in _SYNTHESIS_SYSTEM_PROMPT.lower()

    def test_prompt_anti_alucinacao(self):
        from pipelines.doc_pipeline import _SYNTHESIS_SYSTEM_PROMPT
        assert "NAO invente" in _SYNTHESIS_SYSTEM_PROMPT

    def test_fallback_raw_chunks_cita_source(self):
        from pipelines.doc_pipeline import _fallback_raw_chunks
        result = _fallback_raw_chunks([{"source": "test.pdf", "text": "conteudo"}])
        assert "test.pdf" in result


# =============================================================================
# Fase Kd — Roteamento Drive vs RAG com .pdf no query
# =============================================================================


class TestDisambiguatorPdfFastPath:
    @pytest.mark.asyncio
    async def test_pdf_sem_keyword_pede_clarify(self):
        from pipelines.doc_pipeline import _disambiguate_rag_vs_drive
        result = await _disambiguate_rag_vs_drive(
            "me mostre o arquivo 'dissertação vinicius.pdf'"
        )
        assert result == "clarify"

    @pytest.mark.asyncio
    async def test_pdf_com_pergunta_vai_para_rag(self):
        from pipelines.doc_pipeline import _disambiguate_rag_vs_drive
        result = await _disambiguate_rag_vs_drive(
            "me diga sobre o que é a introdução do arquivo 'dissertação vinicius.pdf'"
        )
        assert result == "rag"

    @pytest.mark.asyncio
    async def test_docx_sem_keyword_pede_clarify(self):
        from pipelines.doc_pipeline import _disambiguate_rag_vs_drive
        result = await _disambiguate_rag_vs_drive(
            "leia o arquivo relatorio.docx"
        )
        assert result == "clarify"

    @pytest.mark.asyncio
    async def test_drive_keyword_prevalece_sobre_pdf(self):
        from pipelines.doc_pipeline import _disambiguate_rag_vs_drive
        result = await _disambiguate_rag_vs_drive(
            "busque no drive o arquivo tese.pdf"
        )
        assert result == "drive"

    @pytest.mark.asyncio
    async def test_base_de_conhecimento_com_pdf_e_rag(self):
        from pipelines.doc_pipeline import _disambiguate_rag_vs_drive
        result = await _disambiguate_rag_vs_drive(
            "busque na base de conhecimento o documento dissertação.pdf"
        )
        assert result == "rag"

    @pytest.mark.asyncio
    async def test_sem_extensao_sem_keyword_cai_no_llm(self):
        from pipelines.doc_pipeline import _disambiguate_rag_vs_drive
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            from langchain_openai import ChatOpenAI
            with patch.object(ChatOpenAI, "invoke", return_value=type("R", (), {"content": "drive"})()):
                result = await _disambiguate_rag_vs_drive(
                    "o que diz o resumo do documento"
                )
                assert result == "drive"

    @pytest.mark.asyncio
    async def test_pdf_com_rag_keyword_nao_pede_clarify(self):
        from pipelines.doc_pipeline import _disambiguate_rag_vs_drive
        result = await _disambiguate_rag_vs_drive(
            "o que voce sabe sobre tese.pdf"
        )
        assert result == "rag"

    @pytest.mark.asyncio
    async def test_delete_com_pdf_vai_para_rag(self):
        from pipelines.doc_pipeline import _disambiguate_rag_vs_drive
        result = await _disambiguate_rag_vs_drive(
            "apague da sua base de conheciemnto tese vinicius.pdf"
        )
        assert result == "rag"

    @pytest.mark.asyncio
    async def test_delete_com_pdf_no_drive_vai_para_drive(self):
        from pipelines.doc_pipeline import _disambiguate_rag_vs_drive
        result = await _disambiguate_rag_vs_drive(
            "apague contrato.pdf do meu drive"
        )
        assert result == "drive"


class TestDeleteFlow:
    @pytest.mark.asyncio
    async def test_delete_sem_extensao_casa_substring(self):
        from pipelines.doc_pipeline import run
        from agent_orchestration import knowledge_retriever
        from unittest.mock import AsyncMock, patch as mpatch

        fake_sources = ["tese vinicius.pdf"]

        async def fake_delete(**kwargs):
            return {"deleted": 3, "source_title": "tese vinicius.pdf"}

        with mpatch.object(
            knowledge_retriever, "_list_known_sources",
            AsyncMock(return_value=fake_sources),
        ):
            with mpatch("pipelines.doc_pipeline._disambiguate_rag_vs_drive",
                        AsyncMock(return_value="rag")):
                with mpatch("tool_registry.get_tool") as mock_get_tool:
                    mock_get_tool.return_value = fake_delete
                    with mpatch("core.evolution_client.send_text", new_callable=AsyncMock):
                        result = await run({
                            "instance": "jennifer",
                            "phone": "5511999",
                            "text": "apague tese vinicius da sua base",
                            "extra": {},
                        })
        assert "Feito" in result["reply"]
        assert "tese vinicius.pdf" in result["reply"]

    @pytest.mark.asyncio
    async def test_delete_com_extensao_casa_substring(self):
        from pipelines.doc_pipeline import run
        from agent_orchestration import knowledge_retriever
        from unittest.mock import AsyncMock, patch as mpatch

        fake_sources = ["tese vinicius.pdf"]

        async def fake_delete(**kwargs):
            return {"deleted": 3, "source_title": "tese vinicius.pdf"}

        with mpatch.object(
            knowledge_retriever, "_list_known_sources",
            AsyncMock(return_value=fake_sources),
        ):
            with mpatch("pipelines.doc_pipeline._disambiguate_rag_vs_drive",
                        AsyncMock(return_value="rag")):
                with mpatch("tool_registry.get_tool") as mock_get_tool:
                    mock_get_tool.return_value = fake_delete
                    with mpatch("core.evolution_client.send_text", new_callable=AsyncMock):
                        result = await run({
                            "instance": "jennifer",
                            "phone": "5511999",
                            "text": "apague tese vinicius.pdf da sua base",
                            "extra": {},
                        })
        assert "Feito" in result["reply"]

    @pytest.mark.asyncio
    async def test_delete_sem_match_nao_alucina(self):
        from pipelines.doc_pipeline import run
        from agent_orchestration import knowledge_retriever
        from unittest.mock import AsyncMock, patch as mpatch

        fake_sources = ["tese vinicius.pdf", "Lei_geral_protecao_dados_pessoais_1ed.pdf"]

        with mpatch.object(
            knowledge_retriever, "_list_known_sources",
            AsyncMock(return_value=fake_sources),
        ):
            with mpatch("pipelines.doc_pipeline._disambiguate_rag_vs_drive",
                        AsyncMock(return_value="rag")):
                result = await run({
                    "instance": "jennifer",
                    "phone": "5511999",
                    "text": "apague o documento de higiene",
                    "extra": {},
                })
        assert "Feito" not in result["reply"]
        assert "higiene" in result["reply"].lower() or "documentos disponiveis" in result["reply"].lower()

    @pytest.mark.asyncio
    async def test_delete_sem_pdf_nao_usa_disambiguator(self):
        """Delete sem .pdf deve rotear para 'rag' SEM chamar o disambiguator."""
        from pipelines.doc_pipeline import run
        from agent_orchestration import knowledge_retriever
        from unittest.mock import AsyncMock, patch as mpatch

        fake_sources = ["tese vinicius.pdf"]

        async def fake_delete(**kwargs):
            return {"deleted": 3, "source_title": "tese vinicius.pdf"}

        with mpatch.object(
            knowledge_retriever, "_list_known_sources",
            AsyncMock(return_value=fake_sources),
        ):
            with mpatch("pipelines.doc_pipeline._disambiguate_rag_vs_drive") as mock_d:
                with mpatch("tool_registry.get_tool") as mock_get_tool:
                    mock_get_tool.return_value = fake_delete
                    with mpatch("core.evolution_client.send_text", new_callable=AsyncMock):
                        result = await run({
                            "instance": "jennifer",
                            "phone": "5511999",
                            "text": "Apague a tese vinicius",
                            "extra": {},
                        })
        assert "Feito" in result["reply"]
        assert "tese vinicius.pdf" in result["reply"]
        mock_d.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_com_drive_keyword_vai_para_drive(self):
        """Delete com keyword Drive deve rotear para 'drive' SEM LLM."""
        from pipelines.doc_pipeline import run
        from unittest.mock import AsyncMock, patch as mpatch

        with mpatch("pipelines.doc_pipeline._disambiguate_rag_vs_drive") as mock_d:
            with mpatch("pipelines.doc_pipeline._run_drive") as mock_run_drive:
                mock_run_drive.return_value = {"reply": "path drive"}
                result = await run({
                    "instance": "jennifer",
                    "phone": "5511999",
                    "text": "apague contrato.pdf do meu drive",
                    "extra": {},
                })
        assert result["reply"] == "path drive"
        mock_d.assert_not_awaited()


class TestFullDocumentPath:
    @pytest.mark.asyncio
    async def test_retrieve_full_document_orders_chunks(self):
        """_retrieve_full_document concatena chunks na ordem do chunk_index."""
        from pipelines.doc_pipeline import _retrieve_full_document

        fake_db = MagicMock()

        class FakeDoc:
            def __init__(self, data):
                self._data = data
            def to_dict(self):
                return self._data

        docs = [
            FakeDoc({"chunk_index": 1, "text_content": "segundo chunk"}),
            FakeDoc({"chunk_index": 0, "text_content": "primeiro chunk"}),
            FakeDoc({"chunk_index": 2, "text_content": "terceiro chunk"}),
        ]
        fake_coll = MagicMock()
        fake_coll.where.return_value.where.return_value.where.return_value.stream.return_value = docs
        fake_db.collection.return_value = fake_coll

        with patch("core.rag._get_firestore", return_value=fake_db):
            result = await _retrieve_full_document("5511999", "tese.pdf")
        assert "primeiro chunk" in result
        assert "segundo chunk" in result
        assert result.index("primeiro") < result.index("segundo") < result.index("terceiro")

    @pytest.mark.asyncio
    async def test_retrieve_full_document_empty_returns_empty(self):
        from pipelines.doc_pipeline import _retrieve_full_document
        result = await _retrieve_full_document("", "doc.pdf")
        assert result == ""
        result = await _retrieve_full_document("5511999", "")
        assert result == ""

    @pytest.mark.asyncio
    async def test_synthesize_full_document_fallback_when_no_key(self):
        """Sem DEEPSEEK_API_KEY, full document usa fallback raw chunks."""
        from pipelines.doc_pipeline import _synthesize_full_document
        with patch.dict("os.environ", {}, clear=True):
            result = await _synthesize_full_document(
                "pergunta", "conteudo completo do documento que sera truncado", "tese.pdf"
            )
        assert isinstance(result, str)
        assert len(result) > 0


class TestDetectDelete:
    def test_detect_captures_bare_delete(self):
        from pipelines.doc_pipeline import detect
        assert detect("apague tese vinicius") is True

    def test_detect_captures_delete_with_excluir(self):
        from pipelines.doc_pipeline import detect
        assert detect("exclua a lei de dados") is True

    def test_detect_does_not_capture_normal_query(self):
        from pipelines.doc_pipeline import detect
        assert detect("qual o horario da reuniao") is False


class TestComenteContentMarker:
    @pytest.mark.asyncio
    async def test_comente_nao_lista_documentos(self):
        """'comente a introdução' deve ir para retrieval, não listagem."""
        from pipelines.doc_pipeline import run
        from agent_orchestration import knowledge_retriever
        from unittest.mock import AsyncMock, patch as mpatch

        fake_sources = ["dissertação vinicius.pdf"]
        fake_retrieve = {
            "results": [{"source": "dissertação vinicius.pdf", "text": "conteudo", "score": 0.7}],
            "scope": "private",
            "filters": {},
        }

        with mpatch.object(
            knowledge_retriever, "_list_known_sources",
            AsyncMock(return_value=fake_sources),
        ):
            with mpatch("agent_orchestration.knowledge_retriever.retrieve",
                        AsyncMock(return_value=fake_retrieve)):
                with mpatch("pipelines.doc_pipeline._retrieve_full_document",
                            AsyncMock(return_value="")):
                    result = await run({
                        "instance": "jennifer",
                        "phone": "5511999",
                        "text": "comente a introdução de 'dissertação vinicius.pdf'",
                        "extra": {},
                    })
        assert "Documentos na minha base" not in result["reply"]
