"""Tests Nível 1: Composio Direto - LinkedIn.

Valida tools do linkedin_composio.py diretamente contra SDK mockado.
NAO envolve orchestrator/manager/DeepAgent.

Formato REAL do Composio SDK (visto em producao 17/08):
    {
      "data": {
        "results": [
          {
            "response": {
              "successful": true,
              "data": { ... payload real ... }
            }
          }
        ]
      }
    }
"""
import asyncio
from unittest.mock import MagicMock, patch


# Helpers para formatar resposta real do Composio
def make_composio_response(payload: dict) -> dict:
    """Formata resposta no envelope real do Composio."""
    return {
        "data": {
            "results": [
                {
                    "response": {
                        "successful": True,
                        "data": payload,
                    }
                }
            ]
        }
    }


class TestLinkedinBasic:
    def test_my_profile_imports(self):
        from tools.linkedin_composio import my_profile
        assert callable(my_profile)

    def test_create_post_imports(self):
        from tools.linkedin_composio import create_post
        assert callable(create_post)

    def test_read_post_imports(self):
        from tools.linkedin_composio import read_post
        assert callable(read_post)

    def test_create_article_imports(self):
        from tools.linkedin_composio import create_article
        assert callable(create_article)


class TestLinkedinToolCalls:
    """Valida que cada tool chama o slug Composio correto."""

    def test_my_profile_returns_full_profile(self):
        """my_profile deve retornar firstName, lastName, headline, id, vanityName."""
        from tools.linkedin_composio import my_profile

        real_profile = {
            "firstName": {"localized": {"pt_BR": "Vinicius", "en_US": "Vinicius"}, "preferredLocale": {"country": "BR", "language": "pt"}},
            "lastName": {"localized": {"pt_BR": "Brito Rocha, Ph.D.", "en_US": "Brito Rocha, Ph.D."}, "preferredLocale": {"country": "BR", "language": "pt"}},
            "headline": {"localized": {"pt_BR": "Data Science & AI Manager", "en_US": "Head of AI"}},
            "id": "u51Xljk3Nc",
            "vanityName": "viniciusbritorocha",
            "profilePicture": {"displayImage": "urn:li:digitalmediaAsset:D4D03AQ..."},
            "profileUrl": "https://www.linkedin.com/in/viniciusbritorocha",
        }
        mock_client = MagicMock()
        mock_client.tools.execute.return_value = make_composio_response(real_profile)

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test123"):
                result = asyncio.run(my_profile(phone="5511966830020"))

        # Verifica que o helper extraiu o data real
        assert result["firstName"]["localized"]["pt_BR"] == "Vinicius"
        assert result["lastName"]["localized"]["pt_BR"] == "Brito Rocha, Ph.D."
        assert result["headline"]["localized"]["pt_BR"] == "Data Science & AI Manager"
        assert result["id"] == "u51Xljk3Nc"
        assert result["vanityName"] == "viniciusbritorocha"
        assert result["profileUrl"] == "https://www.linkedin.com/in/viniciusbritorocha"

        # Verifica que o slug e user_id foram chamados corretamente
        assert mock_client.tools.execute.called
        call_kwargs = mock_client.tools.execute.call_args.kwargs
        assert call_kwargs["slug"] == "LINKEDIN_GET_MY_INFO"
        assert call_kwargs["user_id"] == "5511966830020"

    def test_my_profile_extracts_from_nested_envelope(self):
        """Garante que _extract_composio_data desempacota data.results[0].response.data."""
        from tools.linkedin_composio import my_profile

        # Envelope Composio real visto em producao
        real_envelope = {
            "data": {
                "results": [
                    {
                        "response": {
                            "successful": True,
                            "data": {
                                "firstName": {"localized": {"pt_BR": "Vinicius"}},
                                "id": "u51Xljk3Nc",
                                "vanityName": "viniciusbritorocha",
                            }
                        }
                    }
                ]
            }
        }
        mock_client = MagicMock()
        mock_client.tools.execute.return_value = real_envelope

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(my_profile(phone="5511966830020"))

        # Deve extrair o data interno, NAO retornar o envelope
        assert result["firstName"]["localized"]["pt_BR"] == "Vinicius"
        assert result["id"] == "u51Xljk3Nc"
        assert "results" not in result  # Nao devolve o envelope

    def test_create_post_calls_linkedin_create_post(self):
        from tools.linkedin_composio import create_post

        mock_create = {"id": "urn:li:activity:123", "created": True}
        real_envelope = {"data": {"results": [{"response": {"successful": True, "data": mock_create}}]}}

        mock_client = MagicMock()
        mock_client.tools.execute.return_value = real_envelope

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                with patch("tools.linkedin_composio._resolve_author_urn", return_value="urn:li:person:u51"):
                    result = asyncio.run(create_post(
                        text="Hello LinkedIn!",
                        visibility="PUBLIC",
                        phone="5511966830020",
                    ))

        assert mock_client.tools.execute.called
        assert mock_client.tools.execute.call_args.kwargs["slug"] == "LINKEDIN_CREATE_LINKED_IN_POST"
        assert result["id"] == "urn:li:activity:123"

    def test_read_post_calls_linkedin_get_post_content(self):
        from tools.linkedin_composio import read_post

        mock_post = {"commentary": "Post content here", "created_time": "2026-08-17T00:00:00Z"}
        real_envelope = {"data": {"results": [{"response": {"successful": True, "data": mock_post}}]}}

        mock_client = MagicMock()
        mock_client.tools.execute.return_value = real_envelope

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(read_post(
                    post_id="urn:li:activity:789",
                    phone="5511966830020",
                ))

        assert mock_client.tools.execute.called
        assert mock_client.tools.execute.call_args.kwargs["slug"] == "LINKEDIN_GET_POST_CONTENT"
        assert mock_client.tools.execute.call_args.kwargs["arguments"]["post_id"] == "urn:li:activity:789"
        assert result["commentary"] == "Post content here"

    def test_create_article_with_url(self):
        from tools.linkedin_composio import create_article

        mock_article = {"id": "urn:li:article:1", "url": "https://linkedin.com/post/1"}
        real_envelope = {"data": {"results": [{"response": {"successful": True, "data": mock_article}}]}}

        mock_client = MagicMock()
        mock_client.tools.execute.return_value = real_envelope

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                with patch("tools.linkedin_composio._resolve_author_urn", return_value="urn:li:person:u51"):
                    result = asyncio.run(create_article(
                        text="Artigo legal",
                        title="Meu Artigo",
                        url="https://example.com",
                        phone="5511966830020",
                    ))

        assert mock_client.tools.execute.called
        assert mock_client.tools.execute.call_args.kwargs["slug"] == "LINKEDIN_CREATE_ARTICLE_OR_URL_SHARE"
        # Verifica que arguments tem visibility=PUBLIC e specificContent com ARTICLE
        args = mock_client.tools.execute.call_args.kwargs["arguments"]
        assert args["visibility"] == "PUBLIC"
        assert args["specificContent"]["com.linkedin.ugc.ShareContent"]["shareMediaCategory"] == "ARTICLE"

    def test_create_article_without_url(self):
        from tools.linkedin_composio import create_article

        mock_article = {"id": "urn:li:article:2"}
        real_envelope = {"data": {"results": [{"response": {"successful": True, "data": mock_article}}]}}

        mock_client = MagicMock()
        mock_client.tools.execute.return_value = real_envelope

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                with patch("tools.linkedin_composio._resolve_author_urn", return_value="urn:li:person:u51"):
                    result = asyncio.run(create_article(
                        text="Sem URL",
                        title="Titulo",
                        phone="5511966830020",
                    ))

        # Verifica que arguments tem specificContent com NONE (sem URL)
        args = mock_client.tools.execute.call_args.kwargs["arguments"]
        assert args["specificContent"]["com.linkedin.ugc.ShareContent"]["shareMediaCategory"] == "NONE"


class TestLinkedinErrorHandling:
    """Tratamento de erros."""

    def test_sdk_not_installed_graceful(self):
        from tools.linkedin_composio import my_profile

        with patch("composio.Composio", side_effect=ImportError("composio_sdk_missing")):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(my_profile(phone="5511966830020"))
        assert result["error"] == "composio_sdk_missing"

    def test_api_returns_error_envelope(self):
        from tools.linkedin_composio import my_profile

        with patch("composio.Composio", side_effect=Exception("API rate limited")):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(my_profile(phone="5511966830020"))
        assert "error" in result
        assert "API rate limited" in result["error"]

    def test_graceful_when_no_data_in_response(self):
        """Se Composio retorna envelope vazio, nao quebra."""
        from tools.linkedin_composio import my_profile

        mock_client = MagicMock()
        mock_client.tools.execute.return_value = {"data": {"results": []}}

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(my_profile(phone="5511966830020"))

        # Nao quebra, retorna algo
        assert isinstance(result, dict)


class TestLinkedinAuthorUrn:
    """Testes do _resolve_author_urn."""

    def test_resolve_author_urn_caches_result(self):
        from tools.linkedin_composio import _resolve_author_urn, _AUTHOR_URN_CACHE

        _AUTHOR_URN_CACHE.clear()

        mock_client = MagicMock()
        mock_client.tools.execute.return_value = make_composio_response({"id": "u_test_123"})

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                urn1 = asyncio.run(_resolve_author_urn("5511966830020"))
                urn2 = asyncio.run(_resolve_author_urn("5511966830020"))

        assert urn1 == "urn:li:person:u_test_123"
        assert urn2 == "urn:li:person:u_test_123"
        # Segunda call usa cache (nao chama SDK)
        assert mock_client.tools.execute.call_count == 1

    def test_resolve_author_urn_returns_empty_when_no_id(self):
        from tools.linkedin_composio import _resolve_author_urn, _AUTHOR_URN_CACHE

        _AUTHOR_URN_CACHE.clear()

        mock_client = MagicMock()
        mock_client.tools.execute.return_value = make_composio_response({})  # sem id

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                urn = asyncio.run(_resolve_author_urn("5511966830020"))

        assert urn == ""


class TestLinkedinPhoneExtraction:
    """Garante que o phone e extraido de kwargs."""

    def test_create_post_uses_phone_from_kwargs(self):
        from tools.linkedin_composio import create_post

        mock_client = MagicMock()
        mock_client.tools.execute.return_value = make_composio_response({"id": "x"})

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                with patch("tools.linkedin_composio._resolve_author_urn", return_value="urn:li:person:u51"):
                    asyncio.run(create_post(text="Test", visibility="PUBLIC", phone="5511999999999"))

        assert mock_client.tools.execute.call_args.kwargs["user_id"] == "5511999999999"

    def test_create_post_fails_without_author_urn(self):
        from tools.linkedin_composio import create_post

        with patch("tools.linkedin_composio._resolve_author_urn", return_value=""):
            result = asyncio.run(create_post(text="Test", visibility="PUBLIC", phone="5511999999999"))

        assert result["error"] == "linkedin_author_urn_resolution_failed"


class TestLinkedinFormatCompatibility:
    """Garante que funciona com formatos variados do Composio."""

    def test_alternative_format_without_response_envelope(self):
        """Alguns endpoints podem retornar formato simplificado."""
        from tools.linkedin_composio import my_profile

        mock_client = MagicMock()
        mock_client.tools.execute.return_value = {"id": "u_simple", "firstName": "Test"}

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(my_profile(phone="5511966830020"))

        # Sem envelope, retorna o proprio dict
        assert result["id"] == "u_simple"
        assert result["firstName"] == "Test"