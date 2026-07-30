"""Tests para folder_permissions (TASK A 30/07/2026).

Cobre:
- grant_folder_permission cria documento em usuarios/{phone}/folder_permissions
- list_folder_permissions retorna lista
- revoke_folder_permission remove
- Cache in-process com TTL 60s
- get_user_allowed_tools agrega whitelist por tool
- Validacao de tool/scope/pattern
"""
from unittest.mock import MagicMock, patch

import pytest


def test_grant_folder_permission_calls_firestore():
    """Grant deve escrever em usuarios/{phone}/folder_permissions/{id}.

    Validamos via MagicMock do Firestore client.
    """
    with patch("core.folder_permissions._get_firestore_client") as get_db:
        fake_db = MagicMock()
        get_db.return_value = fake_db
        from core.folder_permissions import grant_folder_permission

        result = grant_folder_permission(
            phone="+5511966830020",
            tool="drive",
            pattern="folder-abc-123",
            scope="whitelist",
            created_by="admin",
        )

    assert result is not None
    assert result["phone"] == "+5511966830020"
    assert result["tool"] == "drive"
    assert result["scope"] == "whitelist"
    assert result["pattern"] == "folder-abc-123"
    assert result["created_by"] == "admin"
    fake_db.collection.assert_called_once_with("usuarios")
    fake_db.collection.return_value.document.assert_called_once_with(
        "+5511966830020",
    )
    fake_db.collection.return_value.document.return_value.collection.assert_called_once_with(
        "folder_permissions",
    )


def test_grant_rejects_invalid_tool():
    from core.folder_permissions import grant_folder_permission

    with pytest.raises(ValueError, match="tool invalido"):
        grant_folder_permission(
            phone="+5511",
            tool="notion",
            pattern="*",
        )


def test_grant_rejects_empty_pattern():
    from core.folder_permissions import grant_folder_permission

    with pytest.raises(ValueError, match="pattern"):
        grant_folder_permission(
            phone="+5511",
            tool="drive",
            pattern="",
        )


def test_grant_rejects_invalid_scope():
    from core.folder_permissions import grant_folder_permission

    with pytest.raises(ValueError, match="scope invalido"):
        grant_folder_permission(
            phone="+5511",
            tool="drive",
            pattern="*",
            scope="deny",
        )


def test_grant_returns_none_when_firestore_unavailable():
    """Sem Firestore client (emulator off, no GCP), grant retorna None."""
    with patch("core.folder_permissions._get_firestore_client") as get_db:
        get_db.return_value = None
        from core.folder_permissions import grant_folder_permission

        result = grant_folder_permission(
            phone="+5511",
            tool="drive",
            pattern="*",
        )
        assert result is None


def test_grant_writes_blacklist_too():
    """scope='blacklist' ainda persiste (negacao explicita)."""
    with patch("core.folder_permissions._get_firestore_client") as get_db:
        fake_db = MagicMock()
        get_db.return_value = fake_db
        from core.folder_permissions import grant_folder_permission

        result = grant_folder_permission(
            phone="+5511",
            tool="drive",
            pattern="restrict",
            scope="blacklist",
        )
        assert result["scope"] == "blacklist"


def test_list_returns_empty_when_no_permissions():
    """User sem permissoes -> lista vazia."""
    with patch("core.folder_permissions._get_firestore_client") as get_db:
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value.stream.return_value = []
        get_db.return_value = mock_db
        from core.folder_permissions import list_folder_permissions

        assert list_folder_permissions("+5511") == []


def test_revoke_calls_delete():
    """Revoke chama .document(id).delete()."""
    with patch("core.folder_permissions._get_firestore_client") as get_db:
        fake_db = MagicMock()
        get_db.return_value = fake_db
        from core.folder_permissions import revoke_folder_permission

        ok = revoke_folder_permission("+5511", "abc123")
    assert ok is True
    fake_db.collection.return_value.document.return_value.collection.return_value.document.assert_called_once_with(
        "abc123",
    )


def test_get_user_allowed_tools_aggregates_whitelist():
    """get_user_allowed_tools agrega whitelist por tool."""
    from core.folder_permissions import (
        force_reload_cache,
        get_user_allowed_tools,
    )
    force_reload_cache()
    fake_perms = [
        {"tool": "drive", "scope": "whitelist", "pattern": "folder1"},
        {"tool": "drive", "scope": "whitelist", "pattern": "folder2"},
        {"tool": "drive", "scope": "blacklist", "pattern": "bad"},
        {"tool": "gmail", "scope": "whitelist", "pattern": "*"},
    ]
    with patch(
        "core.folder_permissions.list_folder_permissions",
        return_value=fake_perms,
    ):
        result = get_user_allowed_tools("+5511")
    assert sorted(result["drive"]) == ["folder1", "folder2"]
    assert result["gmail"] == ["*"]
    assert result["calendar"] == []
    assert "bad" not in result["drive"]


def test_force_reload_clears_cache():
    """force_reload_cache(None) limpa TODO o cache."""
    from core.folder_permissions import (
        _PERMISSION_CACHE,
        force_reload_cache,
    )
    _PERMISSION_CACHE["+5511"] = ([{"tool": "drive"}], 0.0)
    _PERMISSION_CACHE["+5522"] = ([{"tool": "gmail"}], 0.0)
    assert len(_PERMISSION_CACHE) == 2

    force_reload_cache()
    assert _PERMISSION_CACHE == {}


def test_permission_id_is_deterministic_from_tool_pattern():
    """Mesmo tool+pattern = mesmo permission_id (idempotencia)."""
    with patch("core.folder_permissions._get_firestore_client") as get_db:
        fake_db = MagicMock()
        get_db.return_value = fake_db
        from core.folder_permissions import grant_folder_permission

        r1 = grant_folder_permission("+5511", "drive", "folder-1")
        r2 = grant_folder_permission("+5511", "drive", "folder-1")
    assert r1["permission_id"] == r2["permission_id"]
