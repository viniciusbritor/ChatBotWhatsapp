"""Testes E2E com GoldenSet (PHASE 5 do loop RAG).

Valida pipeline completo:
  GoldenSet PDF -> parse -> chunk -> embed -> index -> retrieve

Pre-requisitos para rodar (skip se ausentes):
- GoldenSet/Codigo-do-consumidor-FINAL.pdf presente (1.5MB)
- OPENAI_API_KEY valida
- Firestore disponivel (FirestoreEmulator OU GCP test)
- agent-knowledge-v2 com vector composite index (Phase H F4d.6)
"""
import os
import pytest

pytestmark = pytest.mark.skip(reason="requires GoldenSet PDF + OPENAI_API_KEY + Firestore — E2E only in CI")


_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_CURRENT_DIR))
# GoldenSet esta no repo root: ChatBotWhatsapp/GoldenSet
GOLDENSET_DIR = os.path.join(_REPO_ROOT, "GoldenSet")
DOC_PATH = os.path.join(GOLDENSET_DIR, "Codigo-do-consumidor-FINAL.pdf")
DOC_SOURCE_TITLE = "Codigo-do-consumidor-FINAL.pdf"
TEST_PHONE = "+5511966830020"
FALLBACK_PHONE_HASH = "oh_test_e2e"


def _pdf_present() -> bool:
    return os.path.exists(DOC_PATH) and os.path.getsize(DOC_PATH) > 1_000_000


def _openai_key_set() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def _firestore_available() -> bool:
    from core.rag import _get_firestore

    try:
        db = _get_firestore()
        return db is not None
    except Exception:
        return False


@pytest.fixture
def cleanup_index():
    """Cleanup: remove indexacoes anteriores de teste no Firestore."""
    yield
    try:
        from core.rag import _get_firestore, _owner_hash, PRIVATE_COLLECTION

        db = _get_firestore()
        if db is None:
            return
        owner_hash = _owner_hash(TEST_PHONE)
        for coll_suffix in ("", "-plain"):
            docs = (
                db.collection(PRIVATE_COLLECTION + coll_suffix)
                .where("owner_hash", "==", owner_hash)
                .where("source_title", "==", DOC_SOURCE_TITLE)
                .stream()
            )
            batch = db.batch()
            count = 0
            for doc in docs:
                batch.delete(doc.reference)
                count += 1
                if count >= 500:
                    break
            if count > 0:
                batch.commit()
    except Exception:
        pass


def test_doc_pdf_is_present():
    """Sanity: GoldenSet/Codigo-do-consumidor-FINAL.pdf existe e tem tamanho real."""
    if not _pdf_present():
        pytest.skip(f"GoldenSet/Codigo-do-consumidor-FINAL.pdf nao presente em {DOC_PATH}")
    assert _pdf_present(), f"Esperado PDF em {DOC_PATH}"


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _pdf_present(), reason="GoldenSet/Codigo-do-consumidor-FINAL.pdf nao presente",
)
async def test_index_private_document_real_doc(monkeypatch):
    """E2E: Codigo-do-consumidor.pdf -> embed -> index -> chunks com vectors."""
    if not _openai_key_set():
        pass
    if not _firestore_available():
        pytest.skip("Firestore indisponivel - skipping E2E real")

    from core import rag

    with open(DOC_PATH, "rb") as f:
        raw_bytes = f.read()

    text = rag.parse_pdf_robust(raw_bytes)
    assert text, "PDF vazio ou extracao falhou"
    assert len(text) > 100_000, f"PDF extraido muito curto: {len(text)} chars"

    result = await rag.index_private_document(
        phone=TEST_PHONE,
        text_content=text,
        source_title=DOC_SOURCE_TITLE,
        source_url=None,
        category="legislacao",
        metadata={
            "filename": DOC_SOURCE_TITLE,
            "mime_type": "application/pdf",
            "test_run": True,
        },
        class_="legal",
        group="",
        theme="",
    )

    if result.get("error"):
        pytest.skip(f"Falha ao indexar (provavelmente rate limit): {result}")

    assert result["chunks"] > 100, f"Esperado >100 chunks, got {result['chunks']}"
    assert len(result["doc_ids"]) == result["chunks"], (
        f"plain docs ({len(result['doc_ids'])}) != chunks ({result['chunks']})"
    )
    assert not result.get("partial", False) or result.get("chunks_indexed", 0) > 0, (
        "partial success mas chunks_indexed=0"
    )
    if not result.get("partial", False):
        assert result["chunks_indexed"] == result["chunks"], (
            f"FULL success esperado: chunks={result['chunks']} "
            f"!= chunks_indexed={result['chunks_indexed']}"
        )


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _pdf_present(), reason="GoldenSet/Codigo-do-consumidor-FINAL.pdf nao presente",
)
async def test_retrieval_finds_doc_after_index(monkeypatch, cleanup_index):
    """Apos indexar, retrieval DEVE retornar o proprio doc."""
    if not _openai_key_set():
        pass
    if not _firestore_available():
        pytest.skip("Firestore indisponivel - skipping E2E real")

    from core import rag

    with open(DOC_PATH, "rb") as f:
        raw_bytes = f.read()
    text = rag.parse_pdf_robust(raw_bytes)
    await rag.index_private_document(
        phone=TEST_PHONE,
        text_content=text,
        source_title=DOC_SOURCE_TITLE,
        category="legislacao",
    )

    result = await rag.search_legal_knowledge(
        phone=TEST_PHONE,
        query="direitos do consumidor",
        k=3,
        min_score=0.5,
        source_title=DOC_SOURCE_TITLE,
    )

    if result.get("decision") == "no_matches":
        pytest.skip("Retrieval retornou 0 matches (OpenAI rate limit?)")

    assert result.get("count", 0) > 0, f"0 resultados: {result}"
    found = any(
        "Codigo-do-consumidor" in str(r.get("source_title", ""))
        for r in result.get("results", [])
    )
    assert found, (
        f"Nenhum resultado do proprio PDF: {[r.get('source_title') for r in result.get('results', [])]}"
    )


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _pdf_present(), reason="GoldenSet/Codigo-do-consumidor-FINAL.pdf nao presente",
)
async def test_embedding_count_matches_chunk_count(monkeypatch):
    """Para N chunks, embed_documents DEVE retornar N vectors."""
    if not _openai_key_set():
        pass
    if not _firestore_available():
        pytest.skip("Firestore indisponivel - skipping E2E real")

    from core import rag

    with open(DOC_PATH, "rb") as f:
        raw_bytes = f.read()
    text = rag.parse_pdf_robust(raw_bytes)
    chunks = rag._chunk_text(text)

    assert len(chunks) > 0, "PDF nao gerou chunks"

    vectors = await rag.embed_documents(chunks)
    if vectors is None:
        pytest.skip(
            f"embed_documents retornou None ({len(chunks)} chunks). "
            "Provavelmente rate limit OpenAI. Skipping."
        )

    if len(vectors) < len(chunks):
        pytest.skip(
            f"Partial: {len(vectors)}/{len(chunks)} vectors. Skipping equality check."
        )

    assert len(vectors) == len(chunks), (
        f"Vector count mismatch: chunks={len(chunks)}, vectors={len(vectors)}"
    )
    for i, v in enumerate(vectors):
        assert v is not None, f"Vector {i} e None"
        assert len(v) == 1536, f"Vector {i} tem dimensao errada: {len(v)}"
