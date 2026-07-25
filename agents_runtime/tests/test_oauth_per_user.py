from unittest.mock import MagicMock, patch

from core.oauth_per_user import (
    _persist_token,
    create_oauth_state,
    get_user_credentials,
    parse_oauth_state,
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
