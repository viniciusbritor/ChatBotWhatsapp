"""TASK B - folder_permissions enforcement nas tools Google (PT6 F5)."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


os.environ.setdefault("RAG_FOLDER_PERMISSIONS_ENFORCE", "true")
os.environ.setdefault("GCP_PROJECT", "test-project")
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "")


# ---------------------------------------------------------------------------
# Firestore fake para folder_permissions (precisa setar/criar hierarquia)
# ---------------------------------------------------------------------------

class _FakeDoc:
    def __init__(self, doc_id, path):
        self.id = doc_id
        self._path = path

    def to_dict(self):
        d = self._store_get().get(self._path, {})
        return dict(d)

    def _store_get(self):
        # estado compartilhado via classe
        return _FakeFirestoreStore.STORE

    def set(self, data, merge=False):
        store = self._store_get()
        cur = store.get(self._path, {}) or {}
        if merge:
            cur = {**cur, **(data or {})}
        else:
            cur = dict(data or {})
        store[self._path] = cur
        return self

    def delete(self):
        store = self._store_get()
        store.pop(self._path, None)
        return self

    def collection(self, sub):
        parent = self._path
        return _FakeCollection(f"{parent}/{sub}")


class _FakeCollection:
    def __init__(self, path):
        self._path = path

    def document(self, doc_id):
        return _FakeDoc(doc_id, f"{self._path}/{doc_id}")

    def stream(self):
        store = _FakeFirestoreStore.STORE
        for path, data in store.items():
            # /usuarios/5511966830020/folder_permissions/X
            if path.startswith(self._path + "/") and path.count("/") == self._path.count("/") + 1:
                doc_id = path.split("/")[-1]
                payload = dict(data)
                row = _Row(doc_id, payload, _FakeDoc(doc_id, path))
                yield row


class _Row:
    """Row fake do Firestore com .id e .to_dict() retornando dict simples."""

    def __init__(self, doc_id, payload, reference):
        self.id = doc_id
        self._payload = payload
        self.reference = reference

    def to_dict(self):
        return dict(self._payload)


class _FakeFirestoreStore:
    """Singleton store - chave é o path completo do document."""

    STORE = {}


class _FakeFirestoreClient:
    def collection(self, name):
        return _FakeCollection(name)


@pytest.fixture(autouse=True)
def _bypass_owner_guard_and_firestore(monkeypatch):
    """Patches owner guard e Firestore para isolacao de folder_permissions."""
    # limpa store de testes anteriores
    _FakeFirestoreStore.STORE.clear()

    # Liga enforcement para os testes deste arquivo
    monkeypatch.setenv("RAG_FOLDER_PERMISSIONS_ENFORCE", "true")

    def _always_allow(resolution, phone, capability):
        return None

    monkeypatch.setattr("core.owner.deny_if_not_owner", _always_allow)
    monkeypatch.setattr("core.owner.resolve_owner", lambda *a, **kw: None)
    monkeypatch.setattr("core.folder_permissions._get_firestore_client", lambda: _FakeFirestoreClient())
    monkeypatch.setattr("tools.google_drive.resolve_owner", lambda *a, **kw: None, raising=False)
    monkeypatch.setattr("tools.google_drive.deny_if_not_owner", _always_allow, raising=False)
    monkeypatch.setattr("tools.google_gmail.resolve_owner", lambda *a, **kw: None, raising=False)
    monkeypatch.setattr("tools.google_gmail.deny_if_not_owner", _always_allow, raising=False)
    monkeypatch.setattr("tools.google_calendar.resolve_owner", lambda *a, **kw: None, raising=False)
    monkeypatch.setattr("tools.google_calendar.deny_if_not_owner", _always_allow, raising=False)
    yield


@pytest.fixture
def _fake_drive_service():
    service = MagicMock()
    files_resp = {
        "files": [
            {"id": "f1", "name": "cdc-capitulo-1.pdf"},
            {"id": "f2", "name": "lgpd-capitulo-1.pdf"},
            {"id": "f3", "name": "outro.pdf"},
        ]
    }
    service.files.return_value.list.return_value.execute.return_value = files_resp
    service.files.return_value.create.return_value.execute.return_value = {
        "id": "new", "name": "x.pdf"
    }
    return service


class TestEnforcementCapable:
    def test_lockdown_when_no_whitelist(self):
        from core.folder_permissions import (
            get_user_allowed_tools,
            force_reload_cache,
        )
        force_reload_cache("5511966830020")
        allowed = get_user_allowed_tools("5511966830020")
        assert allowed["drive"] == []
        assert allowed["gmail"] == []
        assert allowed["calendar"] == []


class TestCheckFolderPermission:
    def test_no_phone_returns_error(self):
        from core.owner_guard import check_folder_permission
        result = check_folder_permission("", "drive.search", {})
        assert result["error"] == "missing_phone"

    def test_no_whitelist_returns_denied(self):
        from core.owner_guard import check_folder_permission
        from core import folder_permissions

        with patch.object(folder_permissions, "get_user_allowed_tools") as get:
            get.return_value = {"drive": [], "gmail": [], "calendar": []}
            result = check_folder_permission("5511966830020", "drive.search", {"query": ""})
        assert result["error"] == "folder_permission_required"


class TestToolsWithEnforcement:
    @pytest.mark.asyncio
    async def test_search_files_with_whitelist(self, _fake_drive_service):
        from core.folder_permissions import (
            grant_folder_permission,
            force_reload_cache,
            list_folder_permissions,
            revoke_folder_permission,
        )

        with patch("tools.google_drive._get_service", return_value=_fake_drive_service):
            for p in list_folder_permissions("5511966830020"):
                revoke_folder_permission("5511966830020", p["permission_id"])
            grant_folder_permission("5511966830020", "drive", "cdc-capitulo-1.pdf")
            force_reload_cache("5511966830020")
            from tools.google_drive import search_files
            r = await search_files(phone="5511966830020", query="")
            names = [f["name"] for f in r["files"]]
            assert names == ["cdc-capitulo-1.pdf"], names
            assert r["count"] == 1

    @pytest.mark.asyncio
    async def test_search_files_without_whitelist_denied(self, _fake_drive_service):
        from core.folder_permissions import (
            force_reload_cache,
            list_folder_permissions,
            revoke_folder_permission,
        )

        with patch("tools.google_drive._get_service", return_value=_fake_drive_service):
            for p in list_folder_permissions("5511966830020"):
                revoke_folder_permission("5511966830020", p["permission_id"])
            force_reload_cache("5511966830020")
            from tools.google_drive import search_files
            r = await search_files(phone="5511966830020", query="")
            assert "error" in r
            assert r["error"] == "folder_permission_required"

    @pytest.mark.asyncio
    async def test_post_filter_matches_by_id_not_only_name(self, _fake_drive_service):
        """Whitelist por folder/file ID filtra a listagem (match em `id`)."""
        from core.folder_permissions import (
            force_reload_cache,
            grant_folder_permission,
            list_folder_permissions,
            revoke_folder_permission,
        )

        with patch("tools.google_drive._get_service", return_value=_fake_drive_service):
            for p in list_folder_permissions("5511966830020"):
                revoke_folder_permission("5511966830020", p["permission_id"])
            grant_folder_permission("5511966830020", "drive", "f2")
            force_reload_cache("5511966830020")
            from tools.google_drive import search_files
            r = await search_files(phone="5511966830020", query="")
            names = [f["name"] for f in r["files"]]
            assert names == ["lgpd-capitulo-1.pdf"], names
            assert r["count"] == 1

    @pytest.mark.asyncio
    async def test_upload_file_within_whitelist_passes(self, _fake_drive_service):
        from core.folder_permissions import (
            grant_folder_permission,
            force_reload_cache,
            list_folder_permissions,
            revoke_folder_permission,
        )

        with patch("tools.google_drive._get_service", return_value=_fake_drive_service):
            for p in list_folder_permissions("5511966830020"):
                revoke_folder_permission("5511966830020", p["permission_id"])
            grant_folder_permission("5511966830020", "drive", "cdc-folder-id")
            force_reload_cache("5511966830020")
            from tools.google_drive import upload_file
            r = await upload_file(
                phone="5511966830020",
                folder_id="cdc-folder-id",
                filename="x.pdf",
                content="x",
            )
            assert "file" in r, r

    @pytest.mark.asyncio
    async def test_upload_file_outside_whitelist_denied(self, _fake_drive_service):
        from core.folder_permissions import (
            grant_folder_permission,
            force_reload_cache,
            list_folder_permissions,
            revoke_folder_permission,
        )

        with patch("tools.google_drive._get_service", return_value=_fake_drive_service):
            for p in list_folder_permissions("5511966830020"):
                revoke_folder_permission("5511966830020", p["permission_id"])
            grant_folder_permission("5511966830020", "drive", "cdc-folder-id")
            force_reload_cache("5511966830020")
            from tools.google_drive import upload_file
            r = await upload_file(
                phone="5511966830020",
                folder_id="lgpd-folder",
                filename="x.pdf",
                content="x",
            )
            assert "error" in r
            assert r["error"] == "folder_permission_denied", r


class TestEnforcementToggleable:
    def test_disabled_when_env_false(self, monkeypatch):
        monkeypatch.setenv("RAG_FOLDER_PERMISSIONS_ENFORCE", "false")
        # reimportar para pegar o novo valor
        import importlib
        from core import owner_guard
        importlib.reload(owner_guard)
        assert owner_guard.is_enforce_enabled() is False
        # restaurar
        monkeypatch.setenv("RAG_FOLDER_PERMISSIONS_ENFORCE", "true")
        importlib.reload(owner_guard)
