from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def close_coroutine(coroutine):
    coroutine.close()
    return MagicMock()


class TestRuntimeStatusRouting:
    def test_status_question_has_priority_over_web(self):
        from orchestrator import _detect_intent, _resolve_agent_for_intent

        intent = _detect_intent("Quais agentes estao ativos e o que eles fazem?")
        assert intent["is_runtime_status"] is True
        assert intent["is_web_search"] is False
        assert _resolve_agent_for_intent(intent, "jennifer") == "runtime-status"

    def test_generic_o_que_eles_fazem_is_not_web(self):
        from orchestrator import _detect_intent

        intent = _detect_intent("Me diga o que eles fazem")
        assert intent["is_runtime_status"] is False
        assert intent["is_web_search"] is False

    def test_explicit_web_search_still_routes_web(self):
        from orchestrator import _detect_intent, _resolve_agent_for_intent

        intent = _detect_intent("Pesquise na web as noticias atuais")
        assert intent["is_web_search"] is True
        assert _resolve_agent_for_intent(intent, "jennifer") == "manager-web"

    @pytest.mark.asyncio
    async def test_status_query_bypasses_llm(self):
        from orchestrator import orchestrate

        inventory = {
            "generated_at": "2026-07-18T12:00:00-03:00",
            "counts": {
                "configured": 15,
                "loaded": 15,
                "enabled": 15,
                "routable": 10,
                "healthy": 2,
                "operational": 2,
                "unverified": 8,
                "degraded": 0,
                "in_flight": 0,
            },
            "agents": [],
        }
        with patch("core.agent_status.build_agent_inventory", return_value=inventory):
            with patch("core.agent_status.format_inventory_reply", return_value="Status real"):
                with patch("orchestrator._execute_agent", new_callable=AsyncMock) as execute:
                    with patch("orchestrator._schedule_indexing", side_effect=close_coroutine):
                        result = await orchestrate(
                            {
                                "instance": "jennifer",
                                "phone": "5511999999999",
                                "text": "Quantos agentes estao funcionando?",
                                "sender_name": "Vinicius",
                                "extra": {"message_id": "status-1"},
                            }
                        )

        assert result["reply"] == "Status real"
        assert result["metadata"]["route"] == "deterministic"
        assert result["metadata"]["agent_id"] == "runtime-status"
        execute.assert_not_awaited()


class TestPendingActionsInConversation:
    @pytest.mark.asyncio
    async def test_yes_without_pending_action_does_not_save_nickname(self):
        from orchestrator import orchestrate

        orchestrator_agent = {
            "id": "jennifier",
            "name": "Jennifer",
            "role": "orchestrator",
            "enabled": True,
            "instances": ["jennifer"],
            "system_prompt": "Jennifer",
            "tools": [],
            "skills": [],
        }
        response = {
            "reply": "Certo.",
            "delay_ms": 10,
            "presence": "composing",
            "metadata": {"agent_id": "jennifier", "response_identity": "Jennifer"},
        }
        with patch("core.pending_actions.get_pending_action", new_callable=AsyncMock, return_value=None):
            with patch("tools.nickname.set_consent", new_callable=AsyncMock) as consent:
                with patch("orchestrator._get_orchestrator", new_callable=AsyncMock, return_value="jennifier"):
                    with patch("orchestrator.get_agent", return_value=orchestrator_agent):
                        with patch("orchestrator.has_nickname", return_value=True):
                            with patch("orchestrator._execute_agent", new_callable=AsyncMock, return_value=response):
                                with patch("orchestrator._schedule_indexing", side_effect=close_coroutine):
                                    result = await orchestrate(
                                        {
                                            "instance": "jennifer",
                                            "phone": "5511999999999",
                                            "text": "sim",
                                            "sender_name": "Vinicius",
                                            "extra": {},
                                        }
                                    )

        assert result["reply"] == "Certo."
        consent.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_yes_consumes_matching_nickname_action(self):
        from orchestrator import orchestrate

        pending = {
            "action_type": "nickname_consent",
            "payload": {"first_name": "Vinicius", "nickname": "Vini"},
        }
        with patch("core.pending_actions.get_pending_action", new_callable=AsyncMock, return_value=pending):
            with patch("core.pending_actions.consume_pending_action", new_callable=AsyncMock, return_value=pending) as consume:
                with patch("tools.nickname.set_consent", new_callable=AsyncMock, return_value={"accepted": True}) as consent:
                    with patch("orchestrator._schedule_indexing", side_effect=close_coroutine):
                        result = await orchestrate(
                            {
                                "instance": "jennifer",
                                "phone": "5511999999999",
                                "text": "sim",
                                "sender_name": "Vinicius",
                                "extra": {"message_id": "nickname-1"},
                            }
                        )

        assert "Vini" in result["reply"]
        assert result["metadata"]["accepted"] is True
        consume.assert_awaited_once_with("5511999999999", "nickname_consent")
        consent.assert_awaited_once_with("5511999999999", "Vinicius", "Vini", True)


class TestResponseIdentity:
    def test_internal_identity_is_removed(self):
        from orchestrator import _normalize_response_identity

        reply = _normalize_response_identity("Sou o Web Manager da Jennifer.")
        assert "Web Manager" not in reply
        assert "Jennifer" in reply

    @pytest.mark.asyncio
    async def test_manager_execution_keeps_jennifer_identity(self):
        from orchestrator import _execute_agent

        manager = {
            "id": "manager-web",
            "name": "Web Manager",
            "role": "manager",
            "model": "MiniMax-M3",
            "enabled": True,
            "system_prompt": "Busque dados.",
            "tools": [],
            "skills": [],
        }
        llm = MagicMock()
        llm.is_available.return_value = True
        llm.chat = AsyncMock(
            return_value={
                "content": "Sou o Web Manager da Jennifer.",
                "model_used": "deepseek-v4-flash",
                "provider": "deepseek-v4-flash",
            }
        )
        with patch("orchestrator.LLMProvider", return_value=llm):
            with patch("orchestrator._get_conversation_history", return_value=""):
                with patch("orchestrator._search_memory", new_callable=AsyncMock, return_value=""):
                    result = await _execute_agent(
                        manager,
                        "consulta",
                        {"phone": "5511999999999", "sender_name": "Vinicius", "first_name": "Vinicius"},
                        {},
                    )

        system_prompt = llm.chat.await_args.kwargs["system_prompt"]
        assert "componente interno da Jennifer" in system_prompt
        assert "Web Manager" not in result["reply"]
        assert result["metadata"]["executed_agent_id"] == "manager-web"
        assert result["metadata"]["response_identity"] == "Jennifer"


class TestIdempotency:
    def test_cache_requires_message_id(self):
        from orchestrator import _idempotency_key

        payload = {
            "instance": "jennifer",
            "phone": "5511999999999",
            "text": "oi",
            "extra": {},
        }
        assert _idempotency_key(payload) is None

    def test_different_message_ids_have_different_keys(self):
        from orchestrator import _idempotency_key

        first = {
            "instance": "jennifer",
            "phone": "5511999999999",
            "extra": {"remote_jid": "5511999999999@s.whatsapp.net", "message_id": "one"},
        }
        second = {
            "instance": "jennifer",
            "phone": "5511999999999",
            "extra": {"remote_jid": "5511999999999@s.whatsapp.net", "message_id": "two"},
        }
        assert _idempotency_key(first) != _idempotency_key(second)
