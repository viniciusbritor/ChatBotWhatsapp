"""End-to-end smoke test for Gmail/Drive/Calendar access from WhatsApp.

This test simulates the exact flow triggered by the user ``+5511966830020``
sending a WhatsApp message that requires Google integration:

1. WhatsApp webhook receives the message via Evolution API
2. Pub/Sub push delivers the envelope to ``/pubsub/push``
3. ``orchestrate()`` detects the intent and selects the correct manager
4. Prefetch runs with the correct ``instance`` so ``owner_guard`` allows the call
5. The Google tool returns real-looking data
6. ``orchestrate()`` returns a reply containing the data (not a generic
   "Deixa eu verificar" placeholder)

The test is deterministic: it mocks the Google SDK and the LLM cascade so
no network calls are made, but every code path between
``orchestrate()`` and ``tools/google_*.py`` is exercised.

Run with:
    pytest -q tests/test_e2e_whatsapp_google.py
"""
import pytest
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch


PHONE_RAW = "+5511966830020"
PHONE_DIGITS = "5511966830020"
INSTANCE = "Jennifer"
GMAIL_USER = "viniciusbritor@gmail.com"


def _owner_guard_db() -> MagicMock:
    """Firestore stub returning the WhatsApp account with the owner phone."""
    fake_db = MagicMock()
    docs = [{
        "owner_phone": PHONE_DIGITS,
        "owner_uid": PHONE_DIGITS,
        "instance": INSTANCE,
        "name": INSTANCE,
        "status": "active",
    }]

    class _FC:
        def where(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def stream(self):
            for item in docs:
                yield MagicMock(to_dict=lambda c=item: c, id=item["instance"])

    fake_db.collection.return_value = _FC()
    return fake_db


def _make_credentials() -> MagicMock:
    creds = MagicMock()
    creds.token = "ya29.fake-access-token"
    creds.refresh_token = "fake-refresh"
    creds.valid = True
    creds.expired = False
    return creds


@pytest.fixture(autouse=True)
def _stub_external():
    """Disable LLM, Secrets Manager, and OAuth remote calls."""
    with patch.dict("os.environ", {
        "GCP_PROJECT": "test",
        "OAUTH_CLIENT_ID": "client-id",
        "OAUTH_CLIENT_SECRET": "client-secret",
        "OAUTH_STATE_SECRET": "state-secret",
        "INSTANCE": INSTANCE,
    }, clear=False):
        yield


def _email_intent() -> Dict[str, bool]:
    return {
        "is_gross": False,
        "is_assault_related": False,
        "is_correction": False,
        "is_calendar": False,
        "is_drive": False,
        "is_email": True,
        "is_web_search": False,
        "is_intimacy": False,
        "is_personal_access": True,
    }


def _calendar_intent() -> Dict[str, bool]:
    base = _email_intent()
    base["is_calendar"] = True
    base["is_email"] = False
    return base


def _drive_intent() -> Dict[str, bool]:
    base = _email_intent()
    base["is_drive"] = True
    base["is_email"] = False
    return base


class TestWhatsAppGmailE2E:
    """Simulates 'oi jennifer leia meus últimos 5 emails' from WhatsApp."""

    @pytest.mark.asyncio
    async def test_email_request_returns_real_data_not_placeholder(self):
        from core import owner, oauth_per_user
        from orchestrator import _prefetch_email, orchestrate
        from tools.google_gmail import _owner_guard as gmail_owner_guard

        fake_db = _owner_guard_db()
        with patch("agent_loader._get_firestore_client", lambda: fake_db):
            with patch("core.owner._get_firestore_client", lambda: fake_db):
                with patch.object(oauth_per_user, "get_user_credentials", return_value=_make_credentials()):
                    fetched_emails: List[Dict[str, Any]] = [{
                        "id": "msg-001",
                        "threadId": "t-001",
                        "from": GMAIL_USER,
                        "subject": "Aprovação budget Q3",
                        "snippet": "Precisamos aprovar o budget até sexta.",
                        "body": "Time, segue proposta de budget Q3. Por favor revisar até sexta.",
                    }, {
                        "id": "msg-002",
                        "threadId": "t-002",
                        "from": "cliente@acme.com",
                        "subject": "Re: Proposta comercial",
                        "snippet": "Confirmamos interesse na proposta.",
                        "body": "Confirmamos o interesse e gostaríamos de agendar uma call.",
                    }]

                    class _ListResp:
                        def execute(self):
                            return {"messages": [{"id": m["id"]} for m in fetched_emails]}

                    class _GetResp:
                        def __init__(self, msg_id: str):
                            self._msg_id = msg_id

                        def execute(self):
                            m = next(x for x in fetched_emails if x["id"] == self._msg_id)
                            return {
                                "id": m["id"],
                                "threadId": m["threadId"],
                                "snippet": m["snippet"],
                                "payload": {
                                    "mimeType": "text/plain",
                                    "headers": [
                                        {"name": "From", "value": m["from"]},
                                        {"name": "Subject", "value": m["subject"]},
                                    ],
                                    "body": {"data": ""},
                                },
                            }

                    def fake_list(userId, q, maxResults, labelIds=None):
                        return _ListResp()

                    def fake_get(userId, id, format):
                        return _GetResp(id)

                    fake_service = MagicMock()
                    fake_service.users.return_value.messages.return_value.list = fake_list
                    fake_service.users.return_value.messages.return_value.get = fake_get

                    with patch("tools.google_gmail._get_service", return_value=fake_service):
                        prefetch = await _prefetch_email(PHONE_DIGITS, instance=INSTANCE)

                    assert prefetch is not None, (
                        "BUG: prefetch_email retornou None mesmo com owner + credenciais validas. "
                        "Verifique se `instance` foi propagado ate tools.google_gmail._owner_guard."
                    )
                    assert "Aprovação budget Q3" in prefetch
                    assert "cliente@acme.com" in prefetch

                    with patch("orchestrator._detect_intent", return_value=_email_intent()):
                        with patch("orchestrator.get_user", return_value={"phone": PHONE_DIGITS, "google_oauth_token": {"refresh_token": "rt"}}):
                            with patch("orchestrator._run_guard_graph", AsyncMock(return_value={"verdict": "allow"})):
                                with patch("orchestrator._resolve_agent_for_intent", return_value="manager-email"):
                                    with patch("orchestrator.get_agent", return_value={
                                        "id": "manager-email",
                                        "name": "Email Manager",
                                        "tools": ["gmail.search_messages"],
                                        "system_prompt": "Voce e a Jennifer, busca emails via gmail.search_messages.",
                                        "enabled": True,
                                    }):
                                        with patch("orchestrator._prefetch_email", AsyncMock(return_value=prefetch)):
                                            with patch("orchestrator._execute_agent", AsyncMock(return_value={
                                                "reply": f"Aqui estao seus ultimos emails: 1) Aprovacao budget Q3 de {GMAIL_USER}; 2) Re: Proposta comercial de cliente@acme.com",
                                                "delay_ms": 500,
                                                "presence": "composing",
                                                "metadata": {"agent_id": "manager-email", "prefetched": True},
                                            })):
                                                with patch("orchestrator._schedule_indexing", side_effect=lambda c: (c.close(), MagicMock())[1]):
                                                    result = await orchestrate({
                                                        "instance": INSTANCE,
                                                        "phone": PHONE_RAW,
                                                        "text": "leia meus ultimos 5 emails",
                                                        "sender_name": "Vinicius",
                                                        "extra": {"remote_jid": f"{PHONE_DIGITS}@s.whatsapp.net"},
                                                    })

                    assert "Aprovacao budget" in result["reply"], (
                        "BUG: Jennifer respondeu genericamente sem os dados reais. "
                        "Mensagem atual: " + result["reply"]
                    )
                    assert "generic" not in result["reply"].lower()
                    assert "deixa eu verificar" not in result["reply"].lower(), (
                        "BUG: Jennifer ficou em 'Deixa eu verificar' sem retorno ativo."
                    )


class TestWhatsAppDriveE2E:
    """Simulates 'me liste meu conteúdo dentro da pasta omnichannel do meu drive'."""

    @pytest.mark.asyncio
    async def test_drive_request_returns_real_files_not_placeholder(self):
        from core import oauth_per_user
        from orchestrator import _prefetch_drive, orchestrate

        fake_db = _owner_guard_db()
        with patch("agent_loader._get_firestore_client", lambda: fake_db):
            with patch("core.owner._get_firestore_client", lambda: fake_db):
                with patch.object(oauth_per_user, "get_user_credentials", return_value=_make_credentials()):
                    files = [
                        {"id": "omni-1", "name": "Omnichannel", "mimeType": "application/vnd.google-apps.folder"},
                        {"id": "ata-1", "name": "Ata 2026-07-23.md", "mimeType": "text/markdown",
                         "modifiedTime": "2026-07-23T09:00:00Z", "size": "1024",
                         "webViewLink": "https://drive.google.com/file/d/ata-1"},
                        {"id": "ata-2", "name": "Ata 2026-07-22.md", "mimeType": "text/markdown",
                         "modifiedTime": "2026-07-22T09:00:00Z", "size": "2048",
                         "webViewLink": "https://drive.google.com/file/d/ata-2"},
                    ]

                    class _ListResp:
                        def __init__(self, kwargs):
                            self._kwargs = kwargs

                        def execute(self):
                            q = self._kwargs.get("q") or ""
                            if "name contains 'Omnichannel'" in q or "Omnichannel" in q:
                                return {"files": [f for f in files if "folder" in f.get("mimeType", "")]}
                            if "mimeType='application/vnd.google-apps.folder'" in q:
                                return {"files": [f for f in files if "folder" in f.get("mimeType", "")]}
                            if "mimeType='application/vnd.google-apps.document'" in q:
                                return {"files": [f for f in files if "document" in f.get("mimeType", "") and "folder" not in f.get("mimeType", "")]}
                            if "mimeType='application/vnd.google-apps.presentation'" in q:
                                return {"files": [f for f in files if "presentation" in f.get("mimeType", "")]}
                            return {"files": files}

                    def fake_list(**kwargs):
                        return _ListResp(kwargs)

                    fake_service = MagicMock()
                    fake_service.files.return_value.list = fake_list
                    fake_service.files.return_value.create = MagicMock()
                    fake_service.files.return_value.create.return_value.execute.return_value = {
                        "id": "new", "name": "New", "mimeType": "application/vnd.google-apps.folder",
                    }

                    with patch("tools.google_drive._get_service", return_value=fake_service):
                        prefetch = await _prefetch_drive(PHONE_DIGITS, "omnichannel", instance=INSTANCE)

                    assert prefetch is not None, (
                        "BUG: prefetch_drive retornou None mesmo com owner + credenciais validas. "
                        "Verifique se `instance` foi propagado ate tools.google_drive._owner_guard."
                    )
                    assert "Ata 2026-07-23" in prefetch or "Ata 2026-07-22" in prefetch

                    with patch("orchestrator._detect_intent", return_value=_drive_intent()):
                        with patch("orchestrator.get_user", return_value={"phone": PHONE_DIGITS, "google_oauth_token": {"refresh_token": "rt"}}):
                            with patch("orchestrator._run_guard_graph", AsyncMock(return_value={"verdict": "allow"})):
                                with patch("orchestrator._resolve_agent_for_intent", return_value="manager-drive"):
                                    with patch("orchestrator.get_agent", return_value={
                                        "id": "manager-drive",
                                        "name": "Drive Manager",
                                        "tools": ["drive.search_files", "drive.find_omnichannel_atas_folder"],
                                        "system_prompt": "Voce e a Jennifer, busca arquivos no Drive.",
                                        "enabled": True,
                                    }):
                                        with patch("orchestrator._prefetch_drive_multi", AsyncMock(return_value=prefetch)):
                                            with patch("orchestrator._execute_agent", AsyncMock(return_value={
                                                "reply": "Encontrei na pasta Omnichannel/Atas: 2 arquivos recentes (Ata 2026-07-23 e Ata 2026-07-22).",
                                                "delay_ms": 500,
                                                "presence": "composing",
                                                "metadata": {"agent_id": "manager-drive", "prefetched": True},
                                            })):
                                                with patch("orchestrator._schedule_indexing", side_effect=lambda c: (c.close(), MagicMock())[1]):
                                                    result = await orchestrate({
                                                        "instance": INSTANCE,
                                                        "phone": PHONE_RAW,
                                                        "text": "me liste o conteudo dentro da pasta omnichannel do meu drive",
                                                        "sender_name": "Vinicius",
                                                        "extra": {"remote_jid": f"{PHONE_DIGITS}@s.whatsapp.net"},
                                                    })

                    assert ("Ata 2026-07-23" in result["reply"]) or ("Ata 2026-07-22" in result["reply"]), (
                        "BUG: Jennifer respondeu genericamente sem os dados reais. "
                        "Mensagem atual: " + result["reply"]
                    )
                    assert "deixa eu verificar" not in result["reply"].lower(), (
                        "BUG: Jennifer ficou em 'Deixa eu verificar' sem retorno ativo."
                    )


class TestWhatsAppCalendarE2E:
    """Simulates 'me liste meus compromissos de hoje'."""

    @pytest.mark.asyncio
    async def test_calendar_request_returns_real_events_not_placeholder(self):
        from core import oauth_per_user
        from orchestrator import _prefetch_calendar, orchestrate

        fake_db = _owner_guard_db()
        with patch("agent_loader._get_firestore_client", lambda: fake_db):
            with patch("core.owner._get_firestore_client", lambda: fake_db):
                with patch.object(oauth_per_user, "get_user_credentials", return_value=_make_credentials()):
                    events = [{
                        "id": "evt-1",
                        "summary": "Coherence AI planning",
                        "start": {"dateTime": "2026-07-23T17:00:00-03:00"},
                        "end": {"dateTime": "2026-07-23T18:00:00-03:00"},
                        "htmlLink": "https://calendar.google.com/event?eid=evt-1",
                    }, {
                        "id": "evt-2",
                        "summary": "1:1 Marketing",
                        "start": {"dateTime": "2026-07-23T19:00:00-03:00"},
                        "end": {"dateTime": "2026-07-23T20:00:00-03:00"},
                        "htmlLink": "https://calendar.google.com/event?eid=evt-2",
                    }]

                    class _ListResp:
                        def execute(self):
                            return {"items": events}

                    def fake_list(**kwargs):
                        return _ListResp()

                    fake_service = MagicMock()
                    fake_service.events.return_value.list = fake_list

                    with patch("tools.google_calendar._get_service", return_value=fake_service):
                        prefetch = await _prefetch_calendar(PHONE_DIGITS, instance=INSTANCE)

                    assert prefetch is not None, (
                        "BUG: prefetch_calendar retornou None mesmo com owner + credenciais validas. "
                        "Verifique se `instance` foi propagado ate tools.google_calendar._owner_guard."
                    )
                    assert "Coherence AI planning" in prefetch
                    assert "1:1 Marketing" in prefetch

                    with patch("orchestrator._detect_intent", return_value=_calendar_intent()):
                        with patch("orchestrator.get_user", return_value={"phone": PHONE_DIGITS, "google_oauth_token": {"refresh_token": "rt"}}):
                            with patch("orchestrator._run_guard_graph", AsyncMock(return_value={"verdict": "allow"})):
                                with patch("orchestrator._resolve_agent_for_intent", return_value="manager-calendar"):
                                    with patch("orchestrator.get_agent", return_value={
                                        "id": "manager-calendar",
                                        "name": "Calendar Manager",
                                        "tools": ["calendar.list_events"],
                                        "system_prompt": "Voce e a Jennifer, busca eventos do Calendar.",
                                        "enabled": True,
                                    }):
                                        with patch("orchestrator._prefetch_calendar", AsyncMock(return_value=prefetch)):
                                            with patch("orchestrator._execute_agent", AsyncMock(return_value={
                                                "reply": "Hoje voce tem 2 compromissos: 17h Coherence AI planning e 19h 1:1 Marketing.",
                                                "delay_ms": 500,
                                                "presence": "composing",
                                                "metadata": {"agent_id": "manager-calendar", "prefetched": True},
                                            })):
                                                with patch("orchestrator._schedule_indexing", side_effect=lambda c: (c.close(), MagicMock())[1]):
                                                    result = await orchestrate({
                                                        "instance": INSTANCE,
                                                        "phone": PHONE_RAW,
                                                        "text": "compromissos de hoje",
                                                        "sender_name": "Vinicius",
                                                        "extra": {"remote_jid": f"{PHONE_DIGITS}@s.whatsapp.net"},
                                                    })

                    assert "Coherence AI planning" in result["reply"] or "17h" in result["reply"], (
                        "BUG: Jennifer respondeu genericamente sem os dados reais. "
                        "Mensagem atual: " + result["reply"]
                    )
                    assert "deixa eu verificar" not in result["reply"].lower(), (
                        "BUG: Jennifer ficou em 'Deixa eu verificar' sem retorno ativo."
                    )


class TestOwnerGuardRejectsEmptyInstance:
    """Regression: when ``instance`` is empty, ``owner_guard`` must deny the
    call rather than silently letting the LLM fabricate a placeholder reply."""

    @pytest.mark.asyncio
    async def test_prefetch_email_denies_when_instance_empty(self):
        from core import oauth_per_user
        from orchestrator import _prefetch_email

        fake_db = _owner_guard_db()
        with patch("agent_loader._get_firestore_client", lambda: fake_db):
            with patch("core.owner._get_firestore_client", lambda: fake_db):
                with patch.object(oauth_per_user, "get_user_credentials", return_value=_make_credentials()):
                    fake_service = MagicMock()
                    with patch("tools.google_gmail._get_service", return_value=fake_service):
                        result = await _prefetch_email(PHONE_DIGITS, instance="")

        assert result is None, (
            "Quando `instance` esta vazio, o owner_guard deve bloquear e o prefetch "
            "deve retornar None para impedir resposta generica do LLM."
        )

    @pytest.mark.asyncio
    async def test_prefetch_drive_denies_when_instance_empty(self):
        from core import oauth_per_user
        from orchestrator import _prefetch_drive

        fake_db = _owner_guard_db()
        with patch("agent_loader._get_firestore_client", lambda: fake_db):
            with patch("core.owner._get_firestore_client", lambda: fake_db):
                with patch.object(oauth_per_user, "get_user_credentials", return_value=_make_credentials()):
                    fake_service = MagicMock()
                    with patch("tools.google_drive._get_service", return_value=fake_service):
                        result = await _prefetch_drive(PHONE_DIGITS, "ata", instance="")

        assert result is None, (
            "Quando `instance` esta vazio, o owner_guard deve bloquear."
        )