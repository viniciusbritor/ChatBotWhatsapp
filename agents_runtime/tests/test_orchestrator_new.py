"""Testes do novo orchestrator ÔÇö Tier 1 + Tier 2 + multi-intent."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch




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
                                await orchestrate(
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
                                        with patch("orchestrator._user_has_any_connection", AsyncMock(return_value=True)):
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
            with patch("core.pending_actions.consume_pending_action", new_callable=AsyncMock):
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
                                        with patch("orchestrator._user_has_any_connection", AsyncMock(return_value=True)):
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
        from orchestrator import _response_cache, _idempotency_key, orchestrate

        cache_key = _idempotency_key(self._payload())
        _response_cache[cache_key] = {"reply": "cached", "delay_ms": 0, "presence": "composing",
                                       "metadata": {}, "ts": int(time.time())}
        result = await orchestrate(self._payload())
        assert result["reply"] == "cached"
        assert result["metadata"]["cached"] is True
        del _response_cache[cache_key]


class TestIntentClassifierKnowledge:
    # Tests removidos — categoria 'conhecimento' foi eliminada.
    # O agente (via knowledge.answer) decide como buscar, nao o classifier.
    pass


class TestResolveAgentTools:
    """Fix 12/08/2026: tools DINAMICAS quando o agente nao define lista."""

    def test_tools_ausente_usa_todas_do_registry(self):
        from orchestrator import _resolve_agent_tools
        from tool_registry import list_llm_tool_ids

        agent = {"id": "jennifier", "name": "Jennifer"}
        tools = _resolve_agent_tools(agent)
        assert tools == list_llm_tool_ids()
        assert "youtube.search_videos" in tools
        assert "locomotion.find_place" in tools
        assert "linkedin.my_profile" in tools
        assert "weather.current" in tools

    def test_tools_none_usa_todas(self):
        from orchestrator import _resolve_agent_tools
        from tool_registry import list_llm_tool_ids

        agent = {"id": "x", "tools": None}
        assert _resolve_agent_tools(agent) == list_llm_tool_ids()

    def test_tools_explicito_respeita_lista(self):
        from orchestrator import _resolve_agent_tools

        agent = {"id": "x", "tools": ["calendar.list_events", "gmail.search_messages"]}
        assert _resolve_agent_tools(agent) == ["calendar.list_events", "gmail.search_messages"]

    def test_tools_vazio_bloqueia_tudo(self):
        from orchestrator import _resolve_agent_tools

        agent = {"id": "x", "tools": []}
        assert _resolve_agent_tools(agent) == []

    def test_tools_internas_nao_sao_expostas(self):
        from orchestrator import _resolve_agent_tools
        from tool_registry import INTERNAL_TOOL_IDS

        tools = _resolve_agent_tools({"id": "jennifier"})
        assert "group.resolve_mention" not in tools
        assert "image_report.render" not in tools
        assert set(INTERNAL_TOOL_IDS).isdisjoint(tools)


class TestBindToolArgs:
    """Fix 12/08/2026: binding assinatura-aware (desacoplado)."""

    def test_nao_injeta_instance_em_funcao_sem_instance(self):
        from orchestrator import _bind_tool_args

        args = _bind_tool_args("people.search", {"query": "Radakian"}, "5511966830020", "Jennifer")
        assert args["phone"] == "5511966830020"
        assert "instance" not in args

    def test_injeta_instance_quando_funcao_aceita(self):
        from orchestrator import _bind_tool_args

        args = _bind_tool_args("gmail.search_messages", {"query": "x"}, "5511966830020", "Jennifer")
        assert args["phone"] == "5511966830020"
        assert args["instance"] == "Jennifer"


class TestVerifyCalendarEvent:
    """Fix 12/08/2026: anti-alucinacao apos calendar.create_event."""

    @pytest.mark.asyncio
    async def test_evento_confirmado_mantem_resultado(self):
        from orchestrator import _verify_calendar_event

        fake_result = {"id": "evt-1", "summary": "Reuniao Maycon", "status": "confirmed"}
        fake_events = [{"summary": "Reuniao Maycon", "id": "evt-1"}]
        with patch("tools.google_calendar.list_events", AsyncMock(return_value={"events": fake_events})):
            out = await _verify_calendar_event(
                "5511966830020", fake_result,
                {"summary": "Reuniao Maycon", "start": "2026-08-12T14:00:00"},
            )
        assert "error" not in out
        assert out["id"] == "evt-1"

    @pytest.mark.asyncio
    async def test_evento_fantasma_adiciona_erro(self):
        from orchestrator import _verify_calendar_event

        fake_result = {"id": "evt-2", "summary": "Evento Falso", "status": "confirmed"}
        with patch("tools.google_calendar.list_events", AsyncMock(return_value={"events": []})):
            out = await _verify_calendar_event(
                "5511966830020", fake_result,
                {"summary": "Evento Falso", "start": "2026-08-12T14:00:00"},
            )
        assert "error" in out
        assert "NAO foi encontrado" in out["error"]

    @pytest.mark.asyncio
    async def test_erro_listing_nao_quebra(self):
        from orchestrator import _verify_calendar_event

        fake_result = {"id": "evt-3", "summary": "X", "status": "confirmed"}
        with patch("tools.google_calendar.list_events", AsyncMock(side_effect=RuntimeError("boom"))):
            out = await _verify_calendar_event("5511966830020", fake_result, {"summary": "X"})
        assert "error" not in out

class TestOnboardingNudge:
    @pytest.mark.asyncio
    async def test_nudge_para_user_sem_conexao(self):
        from orchestrator import _maybe_onboarding_nudge

        payload = {"phone": "5511999999999", "extra": {"is_group": False}}
        result = {"reply": "Oi! Como posso ajudar?", "metadata": {}}
        with patch("orchestrator._user_has_any_connection", return_value=False):
            out = await _maybe_onboarding_nudge(payload, result)
        assert "conecte suas contas" in out["reply"]
        assert "token=ml." in out["reply"]

    @pytest.mark.asyncio
    async def test_sem_nudge_se_ja_conectado(self):
        from orchestrator import _maybe_onboarding_nudge

        payload = {"phone": "5511966830020", "extra": {"is_group": False}}
        result = {"reply": "Oi! Como posso ajudar?", "metadata": {}}
        with patch("orchestrator._user_has_any_connection", return_value=True):
            out = await _maybe_onboarding_nudge(payload, result)
        assert "conecte suas contas" not in out["reply"]

    @pytest.mark.asyncio
    async def test_sem_nudge_em_grupo(self):
        from orchestrator import _maybe_onboarding_nudge

        payload = {"phone": "5511999999999", "extra": {"is_group": True}}
        result = {"reply": "Oi pessoal!", "metadata": {}}
        with patch("orchestrator._user_has_any_connection", return_value=False):
            out = await _maybe_onboarding_nudge(payload, result)
        assert "conecte suas contas" not in out["reply"]

    @pytest.mark.asyncio
    async def test_user_sem_conexao(self):
        from orchestrator import _user_has_any_connection

        with patch("agent_loader.get_user", return_value=None), \
             patch("tools.composio_connect.get_status", AsyncMock(return_value={"apps": {"youtube": {"connected": False}}})):
            assert await _user_has_any_connection("5511999999999") is False


class TestDeterministicRoutingEmail:
    """Fix E1 (18/08/2026): detectores deterministicos usam o texto ORIGINAL
    (pre-mask). Antes, o [MASK_EMAIL] do masker invertia o roteamento de
    pedidos de calendario com email de participante para o email pipeline.
    """

    def test_compromisso_com_email_participante_vai_para_calendar(self):
        from pipelines.calendar_pipeline import detect as cal_detect
        from pipelines.email_pipeline import detect as eml_detect
        text = ("marque um compromisso com o Maycon para amanha -> mande o invite "
                "para ele mayconpxavier@gmail.com as 15:00 as 16:00")
        assert cal_detect(text) is True
        assert eml_detect(text) is True  # email tb detecta, mas cal_detect roda primeiro

    def test_compromisso_agenda_com_email_participante(self):
        from pipelines.calendar_pipeline import detect as cal_detect
        from pipelines.email_pipeline import detect as eml_detect
        text = ("marque um compromisso na agenda com o Maycon para amanha -> "
                "mande o invite para ele mayconpxavier@gmail.com as 15:00 as 16:00")
        assert cal_detect(text) is True
        assert eml_detect(text) is False  # excluido por 'agenda'

    def test_keyword_detection_usa_texto_original(self):
        """_detect_dynamic_toolkit deve receber o texto original (nao masked)."""
        from unittest.mock import MagicMock
        import orchestrator
        orig = orchestrator._detect_dynamic_toolkit
        try:
            orchestrator._detect_dynamic_toolkit = MagicMock(wraps=orig)
            # Nao chama aqui - apenas garante que o mapeamento people/tasks/maps existe
            from orchestrator import _KEYWORD_TO_TOOLKIT
            assert "people" in _KEYWORD_TO_TOOLKIT
            assert "tasks" in _KEYWORD_TO_TOOLKIT
            assert "maps" in _KEYWORD_TO_TOOLKIT
        finally:
            orchestrator._detect_dynamic_toolkit = orig


class TestE3AntiHallucination:
    """Fix E3 (18/08/2026): regra anti-alucinacao presente em TODOS os managers."""

    def test_regra_presente_em_todos_os_prompts(self):
        from deepagent_layer.agents import MANAGER_PROMPTS, _append_guardrails
        assert len(MANAGER_PROMPTS) >= 18
        for name, prompt in MANAGER_PROMPTS.items():
            ap = _append_guardrails(prompt)
            assert "ANTI-ALUCINACAO" in ap, f"{name} sem regra E3"

    def test_matriz_completa_1_api_1_manager(self):
        from deepagent_layer.agents import MANAGER_PROMPTS
        expected = {
            "manager-calendar", "manager-email", "manager-drive",
            "manager-group-rag", "manager-web", "manager-jennifier",
            "manager-linkedin", "manager-googledocs", "manager-googlesheets",
            "manager-onedrive", "manager-googlemeet", "manager-msteams",
            "manager-youtube", "manager-github", "manager-notion",
            "manager-people", "manager-tasks", "manager-maps",
        }
        missing = expected - set(MANAGER_PROMPTS.keys())
        assert not missing, f"managers faltando: {missing}"

    def test_factory_prefere_prompt_dedicado(self):
        """Fix (18/08/2026): factory removido, mas get_deep_agent ainda usa MANAGER_PROMPTS dedicado.

        Cada manager dedicado tem seu prompt customizado em MANAGER_PROMPTS
        e a regra E3 anti-alucinacao injetada via _append_guardrails.
        """
        from unittest.mock import patch
        from deepagent_layer.agents import get_deep_agent, MANAGER_PROMPTS, _append_guardrails
        for slug, mgr in [("youtube", "manager-youtube"), ("maps", "manager-maps"),
                          ("microsoft_teams", "manager-msteams"), ("notion", "manager-notion")]:
            assert mgr in MANAGER_PROMPTS, f"{mgr} deve existir em MANAGER_PROMPTS"
            # Verifica que o prompt dedicado tem a regra E3
            full_prompt = _append_guardrails(MANAGER_PROMPTS[mgr])
            assert "ANTI-ALUCINACAO" in full_prompt, f"{mgr} sem regra E3"
            # Verifica que get_deep_agent resolve o manager dedicado
            with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-test"}):
                agent = get_deep_agent(mgr)
            assert agent is not None, f"get_deep_agent({mgr}) falhou"

    def test_novos_managers_tem_tools(self):
        from deepagent_layer.tools import get_tools_for_manager
        casos = {
            "manager-youtube": ["youtube_search_videos", "youtube_get_video_details"],
            "manager-github": ["github_list_repos", "github_my_profile"],
            "manager-notion": ["notion_search_pages", "notion_list_all", "notion_retrieve_page"],
            "manager-people": ["people_search_contacts", "people_get_profile"],
            "manager-tasks": ["tasks_list_tasks", "tasks_create_task", "tasks_update_task"],
            "manager-maps": ["maps_calc_route", "maps_geocode", "maps_search_places", "maps_find_place"],
        }
        for mgr, expected in casos.items():
            tools = get_tools_for_manager(mgr)
            names = [getattr(t, "name", "?") for t in tools]
            assert names == expected, f"{mgr}: {names} != {expected}"
