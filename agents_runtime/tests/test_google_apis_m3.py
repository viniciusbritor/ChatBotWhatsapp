"""Tests for new Google API tools (M3): translate, vision, sheets, tasks, people, photos."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _fake_resolution(phone: str = "5511966830020"):
    return SimpleNamespace(
        instance="Jennifer",
        owner_phone=phone,
        owner_uid=phone,
        is_owner=True,
    )


class _FakeClient:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, params=None, **kwargs):
        return _Resp(self._payload)

    async def post(self, url, params=None, json=None, **kwargs):
        return _Resp(self._payload)


async def new_async_pass(*args, **kwargs):
    return args[0] if args else kwargs.get("result", {})


# ---------- Translate ----------
class TestTranslate:
    @pytest.mark.asyncio
    async def test_translate_text(self):
        from tools import translate

        fake = _FakeClient({"data": {"translations": [{"translatedText": "Olá mundo", "detectedSourceLanguage": "en"}]}})
        with patch("tools.translate._get_key", return_value="KEY"), \
             patch("tools.translate.httpx.AsyncClient", return_value=fake):
            result = await translate.translate_text("Hello world")
        assert result["texto_traduzido"] == "Olá mundo"
        assert result["idioma_detectado"] == "en"

    @pytest.mark.asyncio
    async def test_translate_sem_chave(self):
        from tools import translate

        with patch("tools.translate._get_key", return_value=""):
            result = await translate.translate_text("x")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_detect_language(self):
        from tools import translate

        fake = _FakeClient({"data": {"detections": [[{"language": "pt", "confidence": 0.98, "isReliable": True}]]}})
        with patch("tools.translate._get_key", return_value="KEY"), \
             patch("tools.translate.httpx.AsyncClient", return_value=fake):
            result = await translate.detect_language("olá")
        assert result["idioma"] == "pt"


# ---------- Vision ----------
class TestVision:
    @pytest.mark.asyncio
    async def test_ocr(self):
        from tools import vision

        fake = _FakeClient({"responses": [{"textAnnotations": [{"description": "texto extraido"}]}]})
        with patch("tools.vision._get_key", return_value="KEY"), \
             patch("tools.vision.httpx.AsyncClient", return_value=fake):
            result = await vision.ocr_image("data:image/png;base64,AAA=")
        assert result["texto"] == "texto extraido"
        assert result["encontrou_texto"] is True

    @pytest.mark.asyncio
    async def test_ocr_sem_chave(self):
        from tools import vision

        with patch("tools.vision._get_key", return_value=""):
            result = await vision.ocr_image("x")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_detect_labels(self):
        from tools import vision

        fake = _FakeClient({"responses": [{"labelAnnotations": [{"description": "carro", "score": 0.95}]}]})
        with patch("tools.vision._get_key", return_value="KEY"), \
             patch("tools.vision.httpx.AsyncClient", return_value=fake):
            result = await vision.detect_labels("img")
        assert result["labels"][0]["descricao"] == "carro"


# ---------- Tasks / People (OAuth) ----------
class TestTasks:
    @pytest.mark.asyncio
    async def test_list_tasks(self):
        from tools import google_tasks

        fake_service = MagicMock()
        fake_service.tasks().list().execute.return_value = {
            "items": [{"id": "t1", "title": "Comprar pão", "status": "needsAction"}]
        }
        with patch("tools.google_tasks._get_service", return_value=fake_service), \
             patch("core.owner.resolve_owner", return_value=_fake_resolution()), \
             patch("core.owner.deny_if_not_owner", return_value=None), \
             patch("core.owner_guard.check_folder_permission", return_value=None), \
             patch("core.owner_guard.post_filter_tool_result", new_async_pass):
            result = await google_tasks.list_tasks("5511966830020")
        assert result["count"] == 1
        assert result["tasks"][0]["title"] == "Comprar pão"


class TestPeople:
    @pytest.mark.asyncio
    async def test_search_contacts(self):
        from tools import google_people

        fake_service = MagicMock()
        fake_service.people().searchContacts().execute.return_value = {
            "results": [{"person": {"names": [{"displayName": "João"}], "emailAddresses": [{"value": "joao@x.com"}]}}]
        }
        with patch("tools.google_people._get_service", return_value=fake_service), \
             patch("core.owner.resolve_owner", return_value=_fake_resolution()), \
             patch("core.owner.deny_if_not_owner", return_value=None), \
             patch("core.owner_guard.check_folder_permission", return_value=None), \
             patch("core.owner_guard.post_filter_tool_result", new_async_pass):
            result = await google_people.search_contacts("5511966830020", "joao")
        assert result["count"] == 1
        assert result["contacts"][0]["nome"] == "João"



class TestSheetsComposio:
    @pytest.mark.asyncio
    async def test_read_cells_sem_composio(self):
        from tools import googlesheets_composio

        with patch("tools.googlesheets_composio.composio_call", 
AsyncMock(return_value={"error": "composio_sdk_missing"})):
            result = await googlesheets_composio.read_cells("spr1", "A1:B2", phone="5511966830020")
        assert "error" in result


# ---------- Tool registry ----------
class TestRegistry:
    def test_new_tools_registered(self):
        from tool_registry import list_tool_ids, get_tool_schema

        ids = set(list_tool_ids())
        expected = {
            "translate.text", "translate.detect", "vision.ocr", "vision.detect_labels",
            "tasks.list", "tasks.create", "tasks.update",
            "people.search", "people.get_profile",
            "googlesheets.read_cells", "googlesheets.write_cells", "googlesheets.create_spreadsheet",
        }
        missing = expected - ids
        assert not missing, f"tools faltando: {missing}"
        for tid in expected:
            assert get_tool_schema(tid) is not None, f"schema ausente para {tid}"

    def test_meet_formatter(self):
        from tools.google_calendar import _format_event

        evt = {"conferenceData": {"entryPoints": [{"entryPointType": "video", "uri": "https://meet.google.com/abc"}]}}
        out = _format_event(evt)
        assert out["hangout_link"] == "https://meet.google.com/abc"
