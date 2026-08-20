from unittest.mock import MagicMock, patch

from core.oauth_per_user import (
    _persist_token,
    clear_all_google_caches,
    create_oauth_state,
    delete_oauth_token,
    get_user_credentials,
    is_user_connected,
    parse_oauth_state,
    revoke_google_token,
    revoke_user_oauth,
)


def _token_data(expiry):
    return {
        "token": "access-old",
        "refresh_token": "refresh-token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": ["scope-a"],
        "expiry": str(expiry),
    }


def test_oauth_state_is_signed_and_normalizes_phone(monkeypatch):
    monkeypatch.setenv("OAUTH_STATE_SECRET", "state-secret")
    with patch("core.oauth_per_user.time.time", return_value=1000):
        state = create_oauth_state("+55 (11) 96683-0020")
        assert parse_oauth_state(state) == "5511966830020"


def test_oauth_state_rejects_tampering(monkeypatch):
    monkeypatch.setenv("OAUTH_STATE_SECRET", "state-secret")
    state = create_oauth_state("5511966830020")
    encoded, signature = state.split(".")
    assert parse_oauth_state(f"{encoded}x.{signature}") is None


def test_oauth_state_rejects_expiration(monkeypatch):
    monkeypatch.setenv("OAUTH_STATE_SECRET", "state-secret")
    with patch("core.oauth_per_user.time.time", return_value=1000):
        state = create_oauth_state("5511966830020")
    with patch("core.oauth_per_user.time.time", return_value=1000 + 8 * 24 * 60 * 60):
        assert parse_oauth_state(state) is None


def test_expired_user_token_is_refreshed_and_persisted(monkeypatch):
    monkeypatch.setenv("OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("OAUTH_CLIENT_SECRET", "client-secret")
    db = MagicMock()
    with patch("core.oauth_per_user.time.time", return_value=1000):
        with patch("core.oauth_per_user.get_user_oauth", return_value=_token_data(900)):
            with patch(
                "core.oauth_per_user._refresh_token",
                return_value={
                    "token": "access-new",
                    "refresh_token": "refresh-token",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "expiry": "4600",
                },
            ):
                with patch("core.oauth_per_user._get_firestore", return_value=db):
                    credentials = get_user_credentials("5511966830020")

    assert credentials is not None
    assert credentials.token == "access-new"
    assert credentials.client_id == "client-id"
    assert credentials.client_secret == "client-secret"
    assert credentials.expiry is not None
    assert credentials.expiry.tzinfo is None
    assert db.collection.call_args.args[0] == "usuarios"
    persisted = db.collection().document().set.call_args.args[0]["google_oauth_token"]
    assert "client_secret" not in persisted
    assert "client_id" not in persisted


def test_expired_user_token_fails_closed_when_refresh_fails():
    with patch("core.oauth_per_user.time.time", return_value=1000):
        with patch("core.oauth_per_user.get_user_oauth", return_value=_token_data(900)):
            with patch("core.oauth_per_user._refresh_token", return_value=None):
                assert get_user_credentials("5511966830020") is None


def test_persist_token_strips_client_credentials():
    db = MagicMock()
    _persist_token(
        db,
        "5511966830020",
        {
            "token": "access",
            "client_id": "client-id",
            "client_secret": "client-secret",
        },
    )
    persisted = db.collection().document().set.call_args.args[0]["google_oauth_token"]
    assert persisted["token"] == "access"
    assert "client_id" not in persisted
    assert "client_secret" not in persisted


# ---------------------------------------------------------------------------
# GUARDRAIL §0.7 (19/08/2026) — testes do fix de desconexão no Portal
# ---------------------------------------------------------------------------


def test_is_user_connected_true_when_token_present():
    with patch(
        "core.oauth_per_user.get_user_oauth",
        return_value={"token": "access", "refresh_token": "refresh", "expiry": "9999999999"},
    ):
        assert is_user_connected("5511966830020") is True


def test_is_user_connected_true_with_only_refresh_token():
    with patch(
        "core.oauth_per_user.get_user_oauth",
        return_value={"refresh_token": "refresh", "expiry": "0"},
    ):
        assert is_user_connected("5511966830020") is True


def test_is_user_connected_false_when_no_token():
    with patch("core.oauth_per_user.get_user_oauth", return_value=None):
        assert is_user_connected("5511966830020") is False


def test_is_user_connected_false_when_empty_token_dict():
    with patch(
        "core.oauth_per_user.get_user_oauth",
        return_value={"token": None, "refresh_token": None},
    ):
        assert is_user_connected("5511966830020") is False


def test_get_user_credentials_blocked_after_disconnect():
    """GUARDRAIL §0.7: defesa em profundidade — se o token foi apagado
    (mesmo que por cache stale), get_user_credentials DEVE retornar None."""
    with patch("core.oauth_per_user.is_user_connected", return_value=False):
        with patch("core.oauth_per_user.get_user_oauth", return_value=_token_data(9999999999)):
            assert get_user_credentials("5511966830020") is None


def test_revoke_google_token_returns_true_on_200():
    fake_response = MagicMock(status_code=200)
    with patch("core.oauth_per_user.requests.post", return_value=fake_response):
        assert revoke_google_token("access-token") is True


def test_revoke_google_token_returns_true_on_400_already_revoked():
    """Google retorna 400 para tokens ja invalidos; ainda eh sucesso."""
    fake_response = MagicMock(status_code=400)
    with patch("core.oauth_per_user.requests.post", return_value=fake_response):
        assert revoke_google_token("expired-token") is True


def test_revoke_google_token_returns_false_on_network_error():
    import requests as _req
    with patch(
        "core.oauth_per_user.requests.post",
        side_effect=_req.exceptions.ConnectTimeout("boom"),
    ):
        assert revoke_google_token("access-token") is False


def test_revoke_google_token_empty_input_returns_false():
    assert revoke_google_token("") is False


def test_delete_oauth_token_removes_fields_from_firestore():
    """GUARDRAIL §0.7: apaga google_oauth_token e google_oauth_linked_at
    do Firestore usando DELETE_FIELD para preservar outros campos."""
    from google.cloud import firestore as _fs

    doc_mock = MagicMock()
    doc_mock.exists = True
    doc_mock.to_dict.return_value = {
        "google_oauth_token": {"token": "x"},
        "google_oauth_linked_at": "2026-08-19",
        "email": "user@example.com",
        "phone": "5511966830020",
    }
    doc_ref = MagicMock()
    doc_ref.get.return_value = doc_mock
    db = MagicMock()
    db.collection.return_value.document.return_value = doc_ref

    with patch("core.oauth_per_user._get_firestore", return_value=db):
        result = delete_oauth_token("5511966830020")

    assert result is True
    # Firestore's update() aceita dict posicional ou kwargs
    if doc_ref.update.call_args.kwargs:
        update_kwargs = doc_ref.update.call_args.kwargs
    else:
        update_kwargs = doc_ref.update.call_args.args[0]
    assert update_kwargs["google_oauth_token"] == _fs.DELETE_FIELD
    assert update_kwargs["google_oauth_linked_at"] == _fs.DELETE_FIELD
    assert "google_oauth_revoked_at" in update_kwargs


def test_delete_oauth_token_returns_false_when_no_token_present():
    doc_mock = MagicMock()
    doc_mock.exists = True
    doc_mock.to_dict.return_value = {"email": "user@example.com"}
    doc_ref = MagicMock()
    doc_ref.get.return_value = doc_mock
    db = MagicMock()
    db.collection.return_value.document.return_value = doc_ref

    with patch("core.oauth_per_user._get_firestore", return_value=db):
        assert delete_oauth_token("5511966830020") is False


def test_delete_oauth_token_returns_false_when_firestore_unavailable():
    with patch("core.oauth_per_user._get_firestore", return_value=None):
        assert delete_oauth_token("5511966830020") is False


def test_delete_oauth_token_handles_normalized_phone_variants():
    """Testa que delete_oauth_token tenta multiplas variacoes do telefone."""
    doc_mock = MagicMock()
    doc_mock.exists = True
    doc_mock.to_dict.return_value = {"google_oauth_token": {"token": "x"}}
    doc_ref = MagicMock()
    doc_ref.get.return_value = doc_mock
    db = MagicMock()
    db.collection.return_value.document.return_value = doc_ref

    with patch("core.oauth_per_user._get_firestore", return_value=db):
        # Sem o +55 — vai tentar a versao com 55 e sem 55
        result = delete_oauth_token("11966830020")

    assert result is True
    # Deve ter chamado update pelo menos uma vez
    assert doc_ref.update.called


def test_revoke_user_oauth_end_to_end_success():
    """Testa o fluxo completo: revoga tokens no Google + apaga do Firestore."""
    token_data = {
        "token": "access-active",
        "refresh_token": "refresh-active",
        "expiry": "9999999999",
    }
    doc_mock = MagicMock()
    doc_mock.exists = True
    doc_mock.to_dict.return_value = {"google_oauth_token": token_data}
    doc_ref = MagicMock()
    doc_ref.get.return_value = doc_mock
    db = MagicMock()
    db.collection.return_value.document.return_value = doc_ref

    fake_response = MagicMock(status_code=200)
    with patch("core.oauth_per_user.get_user_oauth", return_value=token_data):
        with patch("core.oauth_per_user._get_firestore", return_value=db):
            with patch("core.oauth_per_user.revoke_google_token", return_value=True) as mock_revoke:
                with patch("core.oauth_per_user.now_brt") as mock_now:
                    mock_now.return_value.isoformat.return_value = "2026-08-19T22:00:00-03:00"
                    result = revoke_user_oauth("5511966830020")

    assert result["phone"] == "5511966830020"
    assert result["access_revoked"] is True
    assert result["refresh_revoked"] is True
    assert result["firestore_deleted"] is True
    assert "revoked_at" in result
    # revoke_google_token deve ter sido chamado 2x (access + refresh)
    assert mock_revoke.call_count == 2


def test_revoke_user_oauth_returns_graceful_when_no_token():
    """Se nao ha token, retorna status sem falhar."""
    doc_mock = MagicMock()
    doc_mock.exists = True
    doc_mock.to_dict.return_value = {"email": "user@example.com"}
    doc_ref = MagicMock()
    doc_ref.get.return_value = doc_mock
    db = MagicMock()
    db.collection.return_value.document.return_value = doc_ref

    with patch("core.oauth_per_user.get_user_oauth", return_value=None):
        with patch("core.oauth_per_user._get_firestore", return_value=db):
            result = revoke_user_oauth("5511966830020")

    assert result["access_revoked"] is False
    assert result["refresh_revoked"] is False
    assert result["firestore_deleted"] is False


def test_revoke_user_oauth_clears_caches():
    """GUARDRAIL §0.7: revoke_user_oauth tambem chama clear_all_google_caches
    para invalidar _calendar_services e similares."""
    token_data = {"token": "access", "refresh_token": "refresh", "expiry": "9999999999"}
    doc_mock = MagicMock()
    doc_mock.exists = True
    doc_mock.to_dict.return_value = {"google_oauth_token": token_data}
    doc_ref = MagicMock()
    doc_ref.get.return_value = doc_mock
    db = MagicMock()
    db.collection.return_value.document.return_value = doc_ref

    with patch("core.oauth_per_user.get_user_oauth", return_value=token_data):
        with patch("core.oauth_per_user._get_firestore", return_value=db):
            with patch("core.oauth_per_user.revoke_google_token", return_value=True):
                with patch(
                    "core.oauth_per_user.clear_all_google_caches",
                    return_value={"calendar": True, "drive": True, "gmail": True},
                ) as mock_clear:
                    result = revoke_user_oauth("5511966830020")

    assert mock_clear.called
    assert result["caches_cleared"]["calendar"] is True


def test_clear_all_google_caches_iterates_all_services():
    """GUARDRAIL §0.7: clear_all_google_caches tenta limpar todos os 5
    servicos Google mesmo se algum falhar (graceful degradation)."""
    with patch("importlib.import_module") as mock_import:
        # Mock do modulo de calendar
        cal_mod = MagicMock()
        cal_mod.clear_user_cache.return_value = True
        # Mock do modulo de drive que falha
        drive_mod = MagicMock()
        drive_mod.clear_user_cache.side_effect = RuntimeError("cache miss")
        mock_import.side_effect = lambda path: cal_mod if "calendar" in path else drive_mod

        result = clear_all_google_caches("5511966830020")

    assert "calendar" in result
    # Drive pode estar presente como False (excepcao capturada)
    assert all(isinstance(v, bool) for v in result.values())
