"""Testes para Phase B: verificacao de key OpenAI no fluxo de embeddings.

Valida que a key OPENAI_API_KEY esta sendo inserida corretamente
no header Authorization do POST para a API de embeddings.
"""
import asyncio
from unittest.mock import MagicMock, patch


def test_embed_direct_uses_correct_authorization_header():
    """_embed_direct envia Bearer <key> no header Authorization."""
    from core import rag

    test_key = "sk-test-1234567890abcdef"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [{"embedding": [0.1] * 1536}]
    }

    with patch("core.rag.requests.post", return_value=mock_response) as mock_post, \
         patch("core.rag.get_secret", return_value=test_key), \
         patch("core.rag.os.getenv", return_value=""):
        result = rag._embed_direct("texto de teste")

    assert result == [0.1] * 1536
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    headers = call_args.kwargs.get("headers", {})
    assert headers.get("Authorization") == f"Bearer {test_key}", \
        f"Key nao foi inserida corretamente: {headers}"


def test_embed_direct_strips_bom_from_key():
    """_embed_direct remove BOM (\\ufeff) do inicio da key."""
    from core import rag

    test_key_with_bom = "\ufeffsk-test-1234567890"
    expected_key = "sk-test-1234567890"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [{"embedding": [0.1] * 1536}]
    }

    with patch("core.rag.requests.post", return_value=mock_response) as mock_post, \
         patch("core.rag.get_secret", return_value=""), \
         patch("core.rag.os.getenv", return_value=test_key_with_bom):
        rag._embed_direct("texto de teste")

    headers = mock_post.call_args.kwargs.get("headers", {})
    assert headers.get("Authorization") == f"Bearer {expected_key}"


def test_embed_direct_strips_whitespace_from_key():
    """_embed_direct remove whitespace nas pontas."""
    from core import rag

    test_key = "  sk-test-1234567890  "

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [{"embedding": [0.1] * 1536}]
    }

    with patch("core.rag.requests.post", return_value=mock_response) as mock_post, \
         patch("core.rag.get_secret", return_value=""), \
         patch("core.rag.os.getenv", return_value=test_key):
        rag._embed_direct("texto de teste")

    headers = mock_post.call_args.kwargs.get("headers", {})
    assert headers.get("Authorization") == "Bearer sk-test-1234567890"


def test_embed_direct_uses_get_secret_first():
    """_embed_direct prioriza get_secret sobre env var."""
    from core import rag

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [{"embedding": [0.1] * 1536}]
    }

    with patch("core.rag.requests.post", return_value=mock_response) as mock_post, \
         patch("core.rag.get_secret", return_value="sk-from-secret") as mock_secret, \
         patch("core.rag.os.getenv", return_value="sk-from-env"):
        rag._embed_direct("texto de teste")

    headers = mock_post.call_args.kwargs.get("headers", {})
    assert headers.get("Authorization") == "Bearer sk-from-secret", \
        "Deve usar get_secret (Secret Manager) quando disponivel"
    mock_secret.assert_called_once_with("OPENAI_API_KEY")


def test_embed_direct_falls_back_to_env_when_secret_unavailable():
    """_embed_direct usa env var se get_secret retorna vazio."""
    from core import rag

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [{"embedding": [0.1] * 1536}]
    }

    with patch("core.rag.requests.post", return_value=mock_response) as mock_post, \
         patch("core.rag.get_secret", return_value=""), \
         patch("core.rag.os.getenv", return_value="sk-from-env"):
        rag._embed_direct("texto de teste")

    headers = mock_post.call_args.kwargs.get("headers", {})
    assert headers.get("Authorization") == "Bearer sk-from-env"


def test_embed_direct_returns_none_when_no_key():
    """_embed_direct retorna None se nenhuma key disponivel (get_secret + env)."""
    from core import rag

    with patch("core.rag.requests.post") as mock_post, \
         patch("core.rag.get_secret", return_value=""), \
         patch("core.rag.os.getenv", return_value=""):
        result = rag._embed_direct("texto de teste")

    assert result is None
    mock_post.assert_not_called()


def test_embed_direct_logs_401_status():
    """401 do OpenAI: loga status code + body, mas NAO expoe a key completa."""
    from core import rag

    test_key = "sk-abc123456789XYZ"

    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Incorrect API key"

    with patch("core.rag.requests.post", return_value=mock_response), \
         patch("core.rag.get_secret", return_value=""), \
         patch("core.rag.os.getenv", return_value=test_key), \
         patch("core.rag.logger") as mock_logger:
        result = rag._embed_direct("texto de teste")

    assert result is None
    # Log emitido com status code + body
    assert mock_logger.error.called
    log_call_str = str(mock_logger.error.call_args_list)
    assert "401" in log_call_str
    assert "Incorrect API key" in log_call_str
    # Mas a key completa NAO deve aparecer no log
    assert test_key not in log_call_str, \
        f"Key completa ({test_key}) nao deve aparecer no log"


def test_embed_query_propagates_key_to_embed_best():
    """embed_query -> embed_best -> _embed_direct: key chega intacta."""
    from core import rag

    test_key = "sk-propagation-test-12345"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [{"embedding": [0.5] * 1536}]
    }

    async def run_test():
        with patch("core.rag.requests.post", return_value=mock_response) as mock_post, \
             patch("core.rag.get_secret", return_value=""), \
             patch("core.rag.os.getenv", return_value=test_key):
            result = await rag.embed_query("texto de teste")

        headers = mock_post.call_args.kwargs.get("headers", {})
        assert headers.get("Authorization") == f"Bearer {test_key}"
        assert result == [0.5] * 1536

    asyncio.run(run_test())

