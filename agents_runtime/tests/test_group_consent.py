"""Testes do group_consent (self-confirm) — membro de grupo acessa
suas proprias tools Google apos confirmar com 'sim'."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGuardGroupConsent:
    @pytest.mark.asyncio
    async def test_non_owner_in_group_creates_pending_and_returns_needs_consent(self):
        """Membro nao-owner em grupo -> pending_action group_consent + verdict."""
        from pipelines._guard import check_google_access

        decision = MagicMock()
        decision.verdict = "deny"
        decision.reason = "not_owner"
        decision.oauth_link = None

        with patch(
            "agent_orchestration.access_guardian.decide_guardian",
            return_value=decision,
        ):
            with patch(
                "pipelines._guard._handle_group_member_access",
                AsyncMock(return_value={
                    "verdict": "needs_group_consent",
                    "reason": "group_consent_required",
                    "capability": "gmail.search_messages",
                }),
            ):
                result = await check_google_access(
                    "jennifer", "5511777777777", "email",
                    is_group=True, group_jid="120363@g.us", original_text="quais meus emails",
                )
        assert result["verdict"] == "needs_group_consent"

    @pytest.mark.asyncio
    async def test_confirmed_member_gets_allow(self):
        """Membro ja confirmado -> allow (usa token do proprio membro)."""
        from pipelines._guard import _handle_group_member_access

        with patch("tools.group.get_member_confirmation", AsyncMock(return_value=True)):
            result = await _handle_group_member_access(
                "5511777777777", "email", "120363@g.us", "quais meus emails"
            )
        assert result["verdict"] == "allow"
        assert result["reason"] == "group_member_confirmed"

    @pytest.mark.asyncio
    async def test_unconfirmed_member_creates_pending_action(self):
        """Membro nao confirmado -> cria pending_action com intent+grupo+texto."""
        from pipelines._guard import _handle_group_member_access

        set_pending = AsyncMock(return_value={})
        with patch("tools.group.get_member_confirmation", AsyncMock(return_value=False)):
            with patch("core.pending_actions.set_pending_action", set_pending):
                result = await _handle_group_member_access(
                    "5511777777777", "calendar", "120363@g.us", "minha agenda"
                )
        assert result["verdict"] == "needs_group_consent"
        set_pending.assert_awaited_once()
        call = set_pending.await_args
        assert call.args[0] == "5511777777777"
        assert call.args[1] == "group_consent"
        payload = call.args[2]
        assert payload["intent"] == "calendar"
        assert payload["group_jid"] == "120363@g.us"
        assert payload["original_text"] == "minha agenda"

    @pytest.mark.asyncio
    async def test_private_message_non_owner_still_denied(self):
        """Fora de grupo, nao-owner continua bloqueado (sem group_consent)."""
        from pipelines._guard import check_google_access

        decision = MagicMock()
        decision.verdict = "deny"
        decision.reason = "not_owner"
        decision.oauth_link = None

        with patch(
            "agent_orchestration.access_guardian.decide_guardian",
            return_value=decision,
        ):
            result = await check_google_access("jennifer", "5511777777777", "drive")
        assert result["verdict"] == "deny"
        assert result["reason"] == "not_owner"


class TestBlockedResponseGroupConsent:
    def test_needs_group_consent_message(self):
        from pipelines._guard import blocked_response

        response = blocked_response({
            "verdict": "needs_group_consent",
            "capability": "gmail.search_messages",
        })
        assert "digite 'sim'" in response["reply"]
        assert response["metadata"]["pending_action"] == "group_consent"
        assert response["metadata"]["blocked_reason"] == "group_consent_required"


class TestPipelinesPassGroupContext:
    @pytest.mark.asyncio
    async def test_calendar_pipeline_passes_group_context(self):
        """calendar_pipeline repassa is_group/group_jid/original_text ao guard."""
        from pipelines.calendar_pipeline import run

        payload = {
            "instance": "jennifer",
            "phone": "5511777777777",
            "text": "minha agenda hoje",
            "remote_jid": "120363@g.us",
            "extra": {"is_group": True},
        }
        with patch(
            "pipelines._guard.check_google_access",
            AsyncMock(return_value={"verdict": "needs_group_consent", "capability": "calendar"}),
        ) as guard_mock:
            result = await run(payload)
        assert "digite 'sim'" in result["reply"]
        kwargs = guard_mock.await_args.kwargs
        assert kwargs["is_group"] is True
        assert kwargs["group_jid"] == "120363@g.us"
        assert kwargs["original_text"] == "minha agenda hoje"

    @pytest.mark.asyncio
    async def test_email_pipeline_passes_group_context(self):
        """email_pipeline repassa is_group/group_jid/original_text ao guard."""
        from pipelines.email_pipeline import run

        payload = {
            "instance": "jennifer",
            "phone": "5511777777777",
            "text": "quais meus emails",
            "remote_jid": "120363@g.us",
            "extra": {"is_group": True},
        }
        with patch(
            "pipelines._guard.check_google_access",
            AsyncMock(return_value={"verdict": "needs_group_consent", "capability": "gmail"}),
        ) as guard_mock:
            result = await run(payload)
        assert "digite 'sim'" in result["reply"]
        kwargs = guard_mock.await_args.kwargs
        assert kwargs["is_group"] is True
        assert kwargs["group_jid"] == "120363@g.us"
        assert kwargs["original_text"] == "quais meus emails"


class TestMultiTenantUserAccess:
    def test_non_owner_with_valid_oauth_allowed_in_decide_guardian(self):
        """Usuário não-owner com token próprio válido recebe allow no access_guardian."""
        from agent_orchestration.access_guardian import decide_guardian
        from core.owner import OwnerResolution

        mock_resolution = OwnerResolution(
            owner_phone="5511966830020",
            owner_uid="vinicius",
            account_id="acc1",
            instance="Jennifer",
        )
        mock_token_data = {
            "scopes": ["https://www.googleapis.com/auth/calendar"],
            "user_email": "maycon@alterego.business",
        }

        with patch("agent_orchestration.access_guardian.resolve_owner", return_value=mock_resolution):
            with patch("agent_orchestration.access_guardian.get_user_oauth", return_value=mock_token_data):
                decision = decide_guardian(
                    instance="Jennifer",
                    phone="5511992303650",
                    capability="calendar.list_events",
                )
        assert decision.verdict == "allow"
        assert decision.user_email == "maycon@alterego.business"

    def test_non_owner_without_oauth_requests_oauth_in_decide_guardian(self):
        """Usuário não-owner sem token recebe request_oauth com link."""
        from agent_orchestration.access_guardian import decide_guardian
        from core.owner import OwnerResolution

        mock_resolution = OwnerResolution(
            owner_phone="5511966830020",
            owner_uid="vinicius",
            account_id="acc1",
            instance="Jennifer",
        )

        with patch("agent_orchestration.access_guardian.resolve_owner", return_value=mock_resolution):
            with patch("agent_orchestration.access_guardian.get_user_oauth", return_value=None):
                with patch("agent_loader.is_user_approved", return_value=True):
                    decision = decide_guardian(
                        instance="Jennifer",
                        phone="5511888888888",
                        capability="calendar.list_events",
                    )
        assert decision.verdict == "request_oauth"
        assert decision.reason == "oauth_missing"
        assert "5511888888888" in decision.oauth_link

    def test_unapproved_guest_returns_unapproved_guest(self):
        """Visitante não aprovado recebe unapproved_guest sem link direto."""
        from agent_orchestration.access_guardian import decide_guardian
        from core.owner import OwnerResolution

        mock_resolution = OwnerResolution(
            owner_phone="5511966830020",
            owner_uid="vinicius",
            account_id="acc1",
            instance="Jennifer",
        )

        with patch("agent_orchestration.access_guardian.resolve_owner", return_value=mock_resolution):
            with patch("agent_orchestration.access_guardian.get_user_oauth", return_value=None):
                with patch("agent_loader.is_user_approved", return_value=False):
                    decision = decide_guardian(
                        instance="Jennifer",
                        phone="5511888888888",
                        capability="calendar.list_events",
                    )
        assert decision.verdict == "unapproved_guest"
        assert decision.reason == "user_not_approved_by_admin"

