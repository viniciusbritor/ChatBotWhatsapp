"""Tests for orchestrator module."""
from typing import Dict

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


def close_coroutine(coroutine):
    coroutine.close()
    return MagicMock()


class TestDetectIntent:
    def test_clean_message(self):
        from orchestrator import _detect_intent
        intent = _detect_intent("Oi Jennifer, tudo bem?")
        assert intent["is_gross"] is False
        assert intent["is_assault_related"] is False
        assert intent["is_correction"] is False

    def test_gross_message(self):
        from orchestrator import _detect_intent
        intent = _detect_intent("Vai se foder, sua piranha")
        assert intent["is_gross"] is True

    def test_assault_related(self):
        from orchestrator import _detect_intent
        intent = _detect_intent("Sofri assedio moral no trabalho")
        assert intent["is_assault_related"] is True

    def test_correction_message(self):
        from orchestrator import _detect_intent
        intent = _detect_intent("Na verdade, meu nome e Vinicius")
        assert intent["is_correction"] is True


class TestResolveAgentForIntent:
    def test_gross_routes_to_morality(self):
        from orchestrator import _resolve_agent_for_intent
        intent = {"is_gross": True, "is_assault_related": False, "is_correction": False, "is_calendar": False, "is_drive": False, "is_email": False, "is_web_search": False, "is_intimacy": False}
        assert _resolve_agent_for_intent(intent, "jennifer") == "agent-morality"

    def test_assault_routes_to_morality(self):
        from orchestrator import _resolve_agent_for_intent
        intent = {"is_gross": False, "is_assault_related": True, "is_correction": False, "is_calendar": False, "is_drive": False, "is_email": False, "is_web_search": False, "is_intimacy": False}
        assert _resolve_agent_for_intent(intent, "jennifer") == "agent-morality"

    def test_correction_routes_to_learning(self):
        from orchestrator import _resolve_agent_for_intent
        intent = {"is_gross": False, "is_assault_related": False, "is_correction": True, "is_calendar": False, "is_drive": False, "is_email": False, "is_web_search": False, "is_intimacy": False}
        assert _resolve_agent_for_intent(intent, "jennifer") == "agent-learning"

    def test_clean_returns_none(self):
        from orchestrator import _resolve_agent_for_intent
        intent = {"is_gross": False, "is_assault_related": False, "is_correction": False, "is_calendar": False, "is_drive": False, "is_email": False, "is_web_search": False, "is_intimacy": False}
        assert _resolve_agent_for_intent(intent, "jennifer") is None


class TestExtractToolCalls:
    def test_extract_mentioned_tool(self):
        from orchestrator import _extract_tool_calls
        result = _extract_tool_calls(
            "Vou verificar o calendar agora",
            ["calendar.list_events", "gmail.search_messages"],
        )
        assert len(result) >= 1
        assert result[0]["tool_id"] == "calendar.list_events"

    def test_no_match(self):
        from orchestrator import _extract_tool_calls
        result = _extract_tool_calls("Apenas texto", ["calendar.list_events"])
        assert result == []

    def test_empty_tools(self):
        from orchestrator import _extract_tool_calls
        result = _extract_tool_calls("algum texto", [])
        assert result == []


class TestBindToolArgs:
    def test_user_phone_overrides_model_supplied_phone(self):
        from orchestrator import _bind_tool_args

        result = _bind_tool_args(
            "gmail.search_messages",
            {"query": "in:inbox", "phone": "attacker-phone"},
            "5511966830020",
        )
        assert result["phone"] == "5511966830020"

    def test_public_tool_does_not_receive_phone(self):
        from orchestrator import _bind_tool_args

        result = _bind_tool_args("web.search", {"query": "teste"}, "5511966830020")
        assert "phone" not in result


class TestBuildSkillsSection:
    def test_no_skills(self):
        from orchestrator import _build_skills_section
        assert _build_skills_section([]) == ""


class TestOrchestrate:
    @pytest.mark.asyncio
    async def test_orchestrate_with_no_agents_loaded(self):
        from orchestrator import orchestrate

        with patch("orchestrator.get_agent", return_value=None):
            with patch("orchestrator._select_orchestrator_agent", return_value=None):
                result = await orchestrate({
                    "instance": "jennifer",
                    "phone": "+5511966830020",
                    "text": "oi",
                    "sender_name": "Vinicius",
                    "extra": {},
                })

        assert "error" in result["metadata"]
        assert result["metadata"]["error"] == "no_orchestrator"

    @pytest.mark.asyncio
    async def test_orchestrate_gross_routes_to_morality(self):
        from orchestrator import orchestrate

        mock_morality = {
            "id": "agent-morality",
            "name": "Morality Agent",
            "enabled": True,
            "model": "deepseek-v4-flash",
            "system_prompt": "Test",
            "tools": ["rag.search_legal_knowledge"],
            "skills": [],
        }

        with patch("orchestrator.get_agent", return_value=mock_morality):
            with patch("orchestrator._execute_agent", new_callable=AsyncMock) as mock_exec:
                with patch("orchestrator._schedule_indexing", side_effect=close_coroutine):
                    mock_exec.return_value = {"reply": "OK", "delay_ms": 100, "presence": "composing", "metadata": {"agent_id": "agent-morality"}}
                    await orchestrate({
                        "instance": "jennifer",
                        "phone": "+5511966830020",
                        "text": "Vai se foder",
                        "sender_name": "User",
                        "extra": {},
                    })

        assert mock_exec.called
        call_args = mock_exec.call_args
        assert call_args[0][0]["id"] == "agent-morality"


def _calendar_intent() -> Dict[str, bool]:
    return {
        "is_gross": False,
        "is_assault_related": False,
        "is_correction": False,
        "is_calendar": True,
        "is_drive": False,
        "is_email": False,
        "is_web_search": False,
        "is_intimacy": False,
        "is_personal_access": True,
    }


class TestPrivacyGuard:
    """Tests for agent-privacy-guard automatic trigger (Fase E)."""

    @pytest.mark.asyncio
    async def test_personal_intent_in_group_unconfirmed_member_sets_pending_action(self):
        from orchestrator import orchestrate
        from core.pending_actions import _local_actions

        _local_actions.clear()

        with patch("orchestrator._detect_intent", return_value=_calendar_intent()):
            with patch("tools.group.get_member_confirmation", AsyncMock(return_value=False)):
                with patch("core.pending_actions.set_pending_action", AsyncMock()) as mock_set:
                    with patch("orchestrator.get_user", return_value={"phone": "5511966830020"}):
                        with patch("orchestrator._resolve_agent_for_intent", return_value="manager-calendar"):
                            with patch("orchestrator.get_agent", return_value={"id": "manager-calendar", "tools": []}):
                                result = await orchestrate({
                                    "instance": "jennifer",
                                    "phone": "5511966830020",
                                    "text": "minha agenda de hoje",
                                    "sender_name": "Vini",
                                    "extra": {"remote_jid": "120363123456@g.us"},
                                })

        assert mock_set.called
        args = mock_set.call_args.args
        kwargs = mock_set.call_args.kwargs
        assert args[0] == "5511966830020"
        assert args[1] == "group_consent"
        assert kwargs["ttl_sec"] == 300
        assert result["metadata"]["agent_id"] == "privacy-guard"
        assert result["metadata"]["blocked"] == "group_unconfirmed_member"
        assert result["metadata"]["pending_action"] == "group_consent"
        assert "Portal" in result["reply"]

    @pytest.mark.asyncio
    async def test_personal_intent_in_group_confirmed_member_proceeds(self):
        from orchestrator import orchestrate
        from core.pending_actions import _local_actions

        _local_actions.clear()

        with patch("orchestrator._detect_intent", return_value=_calendar_intent()):
            with patch("tools.group.get_member_confirmation", AsyncMock(return_value=True)):
                with patch("orchestrator.get_user", return_value={"phone": "5511966830020"}):
                    with patch("orchestrator._run_guard_graph", AsyncMock(return_value={"verdict": "allow"})):
                        with patch("orchestrator._resolve_agent_for_intent", return_value="manager-calendar"):
                            with patch("orchestrator.get_agent", return_value={"id": "manager-calendar", "tools": []}):
                                with patch("orchestrator._execute_agent", new_callable=AsyncMock) as mock_exec:
                                    with patch("orchestrator._schedule_indexing", side_effect=close_coroutine):
                                        mock_exec.return_value = {
                                            "reply": "Voce tem 2 eventos hoje",
                                            "delay_ms": 100,
                                            "presence": "composing",
                                            "metadata": {"agent_id": "manager-calendar"},
                                        }
                                        await orchestrate({
                                            "instance": "jennifer",
                                            "phone": "5511966830020",
                                            "text": "minha agenda",
                                            "sender_name": "Vini",
                                            "extra": {"remote_jid": "120363123456@g.us"},
                                        })

        assert mock_exec.called
        assert mock_exec.call_args[0][0]["id"] == "manager-calendar"

    @pytest.mark.asyncio
    async def test_personal_intent_in_private_proceeds(self):
        from orchestrator import orchestrate

        with patch("orchestrator._detect_intent", return_value=_calendar_intent()):
            with patch("orchestrator.get_user", return_value={"phone": "5511966830020"}):
                with patch("orchestrator._run_guard_graph", AsyncMock(return_value={"verdict": "allow"})):
                    with patch("orchestrator._resolve_agent_for_intent", return_value="manager-calendar"):
                        with patch("orchestrator.get_agent", return_value={"id": "manager-calendar", "tools": []}):
                            with patch("orchestrator._execute_agent", new_callable=AsyncMock) as mock_exec:
                                with patch("orchestrator._schedule_indexing", side_effect=close_coroutine):
                                    mock_exec.return_value = {
                                        "reply": "ok",
                                        "delay_ms": 100,
                                        "presence": "composing",
                                        "metadata": {"agent_id": "manager-calendar"},
                                    }
                                    await orchestrate({
                                        "instance": "jennifer",
                                        "phone": "5511966830020",
                                        "text": "minha agenda",
                                        "sender_name": "Vini",
                                        "extra": {},
                                    })

        assert mock_exec.called

    @pytest.mark.asyncio
    async def test_personal_intent_unregistered_user_returns_portal_link(self):
        from orchestrator import orchestrate

        with patch("orchestrator._detect_intent", return_value=_calendar_intent()):
            with patch("orchestrator.get_user", return_value=None):
                result = await orchestrate({
                    "instance": "jennifer",
                    "phone": "5511999999999",
                    "text": "minha agenda",
                    "sender_name": "User",
                    "extra": {},
                })

        assert result["metadata"]["agent_id"] == "privacy-guard"
        assert result["metadata"]["blocked"] == "unregistered_user"
        assert "Portal" in result["reply"]


class TestResponseCleanup:
    def test_strips_minimax_prefix_suffix(self):
        from orchestrator import _strip_provider_artifacts

        cleaned = _strip_provider_artifacts(
            "Oi, Vinicius! Tudo bem? [<minimax>[<tool_call>o que nao devia"
        )
        assert "[<minimax>" not in cleaned
        assert "<tool_call" not in cleaned
        assert "Oi, Vinicius!" in cleaned

    def test_strips_tool_call_xml(self):
        from orchestrator import _strip_provider_artifacts

        dirty = (
            "Vou checar sua agenda [<minimax>[<tool_call>"
            "<invoke name=\"calendar.list_events\">foo</invoke>"
            "</tool_call>]"
        )
        cleaned = _strip_provider_artifacts(dirty)
        assert "<tool_call>" not in cleaned
        assert "<invoke" not in cleaned
        assert "[<minimax>" not in cleaned
        assert "Vou checar sua agenda" in cleaned

    def test_strips_invoke_blocks(self):
        from orchestrator import _strip_provider_artifacts

        dirty = "<invoke name=\"gmail.search_messages\"></invoke><tool_call>"
        cleaned = _strip_provider_artifacts(dirty)
        assert "<invoke" not in cleaned
        assert "<tool_call>" not in cleaned

    def test_preserves_normal_text(self):
        from orchestrator import _strip_provider_artifacts

        text = "OI! Hoje voce tem 2 compromissos: 17h-18h CoherenceAI e 19h-20h 1:1 Marketing."
        cleaned = _strip_provider_artifacts(text)
        assert cleaned == text

    def test_normalize_response_identity_strips_first(self):
        from orchestrator import _normalize_response_identity

        dirty = "[<minimax>[<tool_call>x</tool_call>] Eu sou a Web Manager."
        out = _normalize_response_identity(dirty)
        assert "[<minimax>" not in out
        assert "sou a Jennifer".casefold() in out.casefold()


def _calendar_intent_full() -> Dict[str, bool]:
    return {
        "is_gross": False,
        "is_assault_related": False,
        "is_correction": False,
        "is_calendar": True,
        "is_drive": False,
        "is_email": False,
        "is_web_search": False,
        "is_intimacy": False,
        "is_personal_access": True,
    }


def _email_intent_full() -> Dict[str, bool]:
    base = _calendar_intent_full()
    base["is_calendar"] = False
    base["is_email"] = True
    return base


def _drive_intent_full() -> Dict[str, bool]:
    base = _calendar_intent_full()
    base["is_calendar"] = False
    base["is_drive"] = True
    return base


class TestPrefetchInstancePropagation:
    """Ensure the orchestrator propagates ``instance`` to Google prefetch
    functions so that the per-instance ``owner_guard`` does not block the
    owner phone from Gmail/Drive/Calendar access."""

    @pytest.mark.asyncio
    async def test_prefetch_calendar_passes_instance(self):
        from orchestrator import _prefetch_calendar
        with patch("tools.google_calendar.list_events", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = {"events": [{"id": "e1"}]}
            await _prefetch_calendar("5511966830020", instance="Jennifer")
            assert mock_list.called
            kwargs = mock_list.call_args.kwargs
            assert kwargs.get("instance") == "Jennifer"

    @pytest.mark.asyncio
    async def test_prefetch_email_passes_instance(self):
        from orchestrator import _prefetch_email
        with patch("tools.google_gmail.search_messages", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = {"messages": [{"id": "m1"}]}
            await _prefetch_email("5511966830020", instance="Jennifer")
            assert mock_search.called
            kwargs = mock_search.call_args.kwargs
            assert kwargs.get("instance") == "Jennifer"

    @pytest.mark.asyncio
    async def test_prefetch_drive_passes_instance(self):
        from orchestrator import _prefetch_drive
        with patch("tools.google_drive.search_files", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = {"files": [{"id": "f1"}]}
            await _prefetch_drive("5511966830020", "ata", instance="Jennifer")
            assert mock_search.called
            kwargs = mock_search.call_args.kwargs
            assert kwargs.get("instance") == "Jennifer"

    @pytest.mark.asyncio
    async def test_prefetch_drive_docs_passes_instance(self):
        from orchestrator import _prefetch_drive_docs
        with patch("tools.google_drive.search_files", new_callable=AsyncMock) as mock_search:
            mock_search.side_effect = [
                {"files": []},
                {"files": []},
            ]
            await _prefetch_drive_docs("5511966830020", "ata", instance="Jennifer")
            assert mock_search.call_count >= 1
            for call in mock_search.call_args_list:
                assert call.kwargs.get("instance") == "Jennifer"

    @pytest.mark.asyncio
    async def test_prefetch_drive_multi_passes_instance(self):
        from orchestrator import _prefetch_drive_multi
        with patch("tools.google_drive.search_files", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = {"files": [{"id": "f1"}]}
            await _prefetch_drive_multi("5511966830020", "atas recentes", instance="Jennifer")
            assert mock_search.call_count >= 1
            for call in mock_search.call_args_list:
                assert call.kwargs.get("instance") == "Jennifer"

    @pytest.mark.asyncio
    async def test_orchestrate_calendar_intent_passes_instance_to_prefetch(self):
        from orchestrator import orchestrate

        with patch("orchestrator._detect_intent", return_value=_calendar_intent_full()):
            with patch("orchestrator.get_user", return_value={"phone": "5511966830020"}):
                with patch("orchestrator._run_guard_graph", AsyncMock(return_value={"verdict": "allow"})):
                    with patch("orchestrator._resolve_agent_for_intent", return_value="manager-calendar"):
                        with patch("orchestrator.get_agent", return_value={"id": "manager-calendar", "name": "Calendar", "tools": ["calendar.list_events"], "system_prompt": "Test", "enabled": True}):
                            with patch("orchestrator._prefetch_calendar", new_callable=AsyncMock) as mock_prefetch:
                                with patch("orchestrator._execute_agent", new_callable=AsyncMock) as mock_exec:
                                    with patch("orchestrator._schedule_indexing", side_effect=close_coroutine):
                                        mock_prefetch.return_value = "[{\"id\":\"e1\"}]"
                                        mock_exec.return_value = {"reply": "ok", "delay_ms": 0, "presence": "composing", "metadata": {"agent_id": "manager-calendar"}}
                                        await orchestrate({
                                            "instance": "Jennifer",
                                            "phone": "5511966830020",
                                            "text": "compromissos de hoje",
                                            "sender_name": "Vinicius",
                                            "extra": {},
                                        })
                                        assert mock_prefetch.called, "_prefetch_calendar should have been called for calendar intent"
                                        called_args = mock_prefetch.call_args
                                        assert called_args.args[0] == "5511966830020"
                                        assert called_args.args[1] == "Jennifer"
