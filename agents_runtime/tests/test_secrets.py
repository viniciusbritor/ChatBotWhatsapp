"""Tests for core.secrets module."""


def test_get_secret_from_env(monkeypatch):
    """Secret should be returned from env var first."""
    monkeypatch.setenv("TEST_SECRET_KEY", "env-value-123")
    from core.secrets import get_secret
    result = get_secret("TEST_SECRET_KEY")
    assert result == "env-value-123"


def test_get_secret_default(monkeypatch):
    """Default returned when env var not set."""
    monkeypatch.delenv("TEST_MISSING_KEY", raising=False)
    from core.secrets import get_secret
    result = get_secret("TEST_MISSING_KEY", default="default-value")
    assert result == "default-value"


def test_get_secret_none_when_no_default(monkeypatch):
    """None returned when no env and no default."""
    monkeypatch.delenv("TEST_NOT_SET_KEY", raising=False)
    from core.secrets import get_secret
    result = get_secret("TEST_NOT_SET_KEY")
    assert result is None


def test_get_secret_env_precedence(monkeypatch):
    """Env var takes precedence over Secret Manager."""
    monkeypatch.setenv("TEST_PRECEDENCE_KEY", "env-wins")
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "localhost:8080")
    monkeypatch.setenv("GCP_PROJECT", "")
    from core.secrets import get_secret
    result = get_secret("TEST_PRECEDENCE_KEY", default="fallback")
    assert result == "env-wins"
