"""Testes para validacao de OPENAI_API_KEY no boot (PHASE 2)."""
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_validate_openai_key_logs_failure(monkeypatch):
    """OPENAI_API_KEY invalida -> log error + NAO crasha startup."""
    import logging
    from main import _validate_openai_key_on_startup

    monkeypatch.setenv("OPENAI_API_KEY", "sk-abc123def456")
    fake_error = Exception("Invalid API key")

    captured = []
    handler = logging.Handler()
    handler.setLevel(logging.DEBUG)

    def emit(record):
        captured.append(record.getMessage())

    handler.emit = emit
    main_logger = logging.getLogger("main")
    main_logger.addHandler(handler)
    main_logger.setLevel(logging.DEBUG)

    try:
        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.embeddings.create.side_effect = fake_error
            mock_openai.return_value = mock_client

            await _validate_openai_key_on_startup()
    finally:
        main_logger.removeHandler(handler)

    auth_errors = [m for m in captured if "OPENAI_API_KEY validation failed" in m]
    assert len(auth_errors) == 1
    assert "sk-abc1***" in auth_errors[0]
    assert "sk-abc123def456" not in auth_errors[0]


@pytest.mark.asyncio
async def test_validate_openai_key_logs_missing(monkeypatch):
    """OPENAI_API_KEY ausente -> log error + NAO crasha."""
    import logging
    from main import _validate_openai_key_on_startup

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    captured = []
    handler = logging.Handler()
    handler.setLevel(logging.DEBUG)

    def emit(record):
        captured.append(record.getMessage())

    handler.emit = emit
    main_logger = logging.getLogger("main")
    main_logger.addHandler(handler)
    main_logger.setLevel(logging.DEBUG)

    try:
        await _validate_openai_key_on_startup()
    finally:
        main_logger.removeHandler(handler)

    missing = [m for m in captured if "not set" in m]
    assert len(missing) == 1


@pytest.mark.asyncio
async def test_validate_openai_key_logs_success(monkeypatch):
    """OPENAI_API_KEY valida -> log info (boot ping succeeded)."""
    import logging
    from main import _validate_openai_key_on_startup

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test123abc456")

    captured = []
    handler = logging.Handler()
    handler.setLevel(logging.DEBUG)

    def emit(record):
        captured.append(record.getMessage())

    handler.emit = emit
    main_logger = logging.getLogger("main")
    main_logger.addHandler(handler)
    main_logger.setLevel(logging.DEBUG)

    try:
        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.embeddings.create.return_value = MagicMock()
            mock_openai.return_value = mock_client

            await _validate_openai_key_on_startup()
    finally:
        main_logger.removeHandler(handler)

    successes = [m for m in captured if "boot ping succeeded" in m]
    assert len(successes) == 1


@pytest.mark.asyncio
async def test_validate_openai_key_handles_short_key(monkeypatch):
    """Key muito curta (sem prefixo) nao quebra log de prefixo."""
    import logging
    from main import _validate_openai_key_on_startup

    monkeypatch.setenv("OPENAI_API_KEY", "x")

    captured = []
    handler = logging.Handler()
    handler.setLevel(logging.DEBUG)

    def emit(record):
        captured.append(record.getMessage())

    handler.emit = emit
    main_logger = logging.getLogger("main")
    main_logger.addHandler(handler)
    main_logger.setLevel(logging.DEBUG)

    try:
        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.embeddings.create.side_effect = Exception("bad key")
            mock_openai.return_value = mock_client

            await _validate_openai_key_on_startup()
    finally:
        main_logger.removeHandler(handler)

    errors = [m for m in captured if "OPENAI_API_KEY validation failed" in m]
    assert len(errors) == 1
    assert "x***" in errors[0]
