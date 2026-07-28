"""Tests for skills/knowledge handlers (Fase G)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _envelope(mime: str, name: str = "doc", doc_b64: str = "") -> dict:
    return {
        "phone": "5511999",
        "instance": "jennifer",
        "message_id": "MSG_SKILL",
        "extra": {
            "remote_jid": "5511999@s.whatsapp.net",
            "doc_mimetype": mime,
            "doc_file_name": name,
            "doc_base64": doc_b64,
        },
    }


class TestPdfHandler:
    @pytest.mark.asyncio
    async def test_extract_returns_text(self):
        from pypdf import PdfWriter

        from skills.knowledge import pdf_handler

        writer = PdfWriter()
        writer.add_blank_page(72, 72)
        import io as _io

        buf = _io.BytesIO()
        writer.write(buf)
        import base64

        envelope = _envelope(
            "application/pdf", "doc.pdf", base64.b64encode(buf.getvalue()).decode("ascii")
        )
        extracted = await pdf_handler.extract(envelope)
        assert extracted is not None
        assert extracted["source_name"] == "doc.pdf"
        assert extracted["mimetype"] == "application/pdf"

    @pytest.mark.asyncio
    async def test_persist_private_indexing(self):
        from skills.knowledge import pdf_handler

        database = MagicMock()

        async def _fake_embed(texts):
            return [[0.1] * 1536 for _ in texts]

        with patch("core.rag._get_firestore", return_value=database):
            with patch("core.rag.embed_documents", side_effect=_fake_embed):
                extracted = {
                    "text": "Lorem ipsum",
                    "source_name": "doc.pdf",
                    "mimetype": "application/pdf",
                }
                result = await pdf_handler.persist(
                    _envelope("application/pdf"), extracted, "private"
                )
        assert result["status"] == "rag_individual"
        assert result["scope"] == "private"
        assert "chunks" in result["index_result"]

    @pytest.mark.asyncio
    async def test_persist_group_indexing(self):
        from skills.knowledge import pdf_handler

        envelope = _envelope("application/pdf")
        envelope["extra"]["remote_jid"] = "120363123@g.us"

        async def _fake_embed(text, api_key=""):
            return [0.1] * 1536

        async def _fake_index(**kwargs):
            return {"indexed": 3, "chunks": 3, "truncated": False}

        with patch("tools.group.index_group_document", side_effect=_fake_index):
            with patch("tools.group._embed_text", side_effect=_fake_embed):
                extracted = {
                    "text": "Lorem ipsum",
                    "source_name": "doc.pdf",
                    "mimetype": "application/pdf",
                }
                result = await pdf_handler.persist(envelope, extracted, "group")
        assert result["status"] == "rag_group"
        assert result["scope"] == "group"


class TestTextHandler:
    @pytest.mark.asyncio
    async def test_extract_plain_text(self):
        import base64

        from skills.knowledge import text_handler

        payload = base64.b64encode(b"hello world").decode("ascii")
        extracted = await text_handler.extract(
            _envelope("text/plain", "note.txt", payload)
        )
        assert extracted is not None
        assert extracted["text"] == "hello world"
        assert extracted["mimetype"] == "text/plain"

    @pytest.mark.asyncio
    async def test_extract_no_base64_returns_none(self):
        from skills.knowledge import text_handler

        extracted = await text_handler.extract(_envelope("text/plain", "note.txt"))
        assert extracted is None


class TestRegistryDiscovery:
    def test_find_skill_by_mime_returns_pdf(self):
        from skills.knowledge import find_skill_by_mime

        skill = find_skill_by_mime("application/pdf")
        assert skill is not None

    def test_find_skill_by_mime_returns_unknown_none(self):
        from skills.knowledge import find_skill_by_mime

        assert find_skill_by_mime("") is None
        assert find_skill_by_mime("application/x-totally-unknown") is None

    def test_list_skills_contains_expected(self):
        from skills.knowledge import list_skills

        names = list_skills()
        assert "pdf" in names
        assert "docx" in names
        assert "xlsx" in names
        assert "text" in names
        assert "drive" in names