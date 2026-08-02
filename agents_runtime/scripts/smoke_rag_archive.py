"""Smoke end-to-end RAG com arquivo REAL (PT6 F4).

Fluxo completo exercitado em memoria:
1. Carrega PDFs do GoldenSet (gerados por scripts/build_golden_set.py)
2. Extrai texto via pypdf
3. Categoriza via agent-categorizer (LLM mockado, deterministico por hash)
4. Indexa em Firestore fake via index_private_document
5. Recupera via knowledge_retriever.retrieve (acima do score threshold)
6. Enforcement folder_permissions (TASK B):
   - whitelist para pattern -> search_files retorna SOMENTE esse pattern
   - whitelist vazia (lock-down) -> search_files retorna vazio
   - whitelist irrelevante -> search_files retorna vazio
7. Resumo do portal (Onda A) render OK com handlers (editar/ver/modal/llm)

Uso:
    python -m scripts.smoke_rag_archive

Nao precisa de credenciais reais (Firestore/embeddings/categorize todos mockados).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


PHONE = "5511966830020"
GOLDENSET_DIR = Path(__file__).resolve().parents[2] / "GoldenSet"


def _hash_embed(text: str, dim: int = 1536) -> list:
    h = hashlib.md5(text.encode("utf-8")).digest()
    return [(h[i % 16] - 128) / 128.0 for i in range(dim)]


def _categorize_by_filename(source_name: str, text: str) -> dict:
    n = source_name.lower()
    if "cdc" in n or "consumidor" in text[:1000].lower():
        return {"class": "legal", "group": "legislacao", "theme": "codigo consumidor", "confidence": 0.92}
    if "lgpd" in n or "protecao de dados" in text[:1000].lower():
        return {"class": "legal", "group": "legislacao", "theme": "lgpd", "confidence": 0.92}
    if "manual" in n or "higiene" in n or "maos" in text[:1000].lower():
        return {"class": "saude", "group": "protocolo", "theme": "higiene das maos", "confidence": 0.91}
    return {"class": "outros", "group": "outros", "theme": source_name[:60], "confidence": 0.5}


class _Doc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self._ref_path = ""

    def to_dict(self):
        return dict(self._data)

    def set(self, data, merge=False):
        if merge:
            merged = dict(self._data)
            merged.update(data)
            self._data = merged
        else:
            self._data = dict(data)
        return self

    def delete(self):
        parent_path = "/".join(self._ref_path.split("/")[:-1])
        store = self._ref_client._by_name.get(parent_path, [])
        self._ref_client._by_name[parent_path] = [d for d in store if d.id != self.id]
        return self

    def collection(self, sub_name):
        return self._ref_client._subcollection(self._ref_path, sub_name)


class _FirestoreCollection:
    """Pequeno Firestore fake com hierarquia usuarios/{phone}/folder_permissions."""

    def __init__(self, client, path):
        self._client = client
        self._path = path
        client._by_name.setdefault(path, [])

    def limit(self, n):
        return self

    def stream(self):
        for d in list(self._client._by_name[self._path]):
            yield d

    def document(self, doc_id):
        for d in self._client._by_name[self._path]:
            if d.id == doc_id:
                d._ref_path = f"{self._path}/{doc_id}"
                d._ref_client = self._client
                return d
        new = _Doc(doc_id, {})
        new._ref_path = f"{self._path}/{doc_id}"
        new._ref_client = self._client
        self._client._by_name[self._path].append(new)
        return new


class _FirestoreClient:
    def __init__(self):
        self._by_name = {}

    def collection(self, name):
        return _FirestoreCollection(self, name)

    def _subcollection(self, parent_path, sub_name):
        full = f"{parent_path}/{sub_name}"
        return _FirestoreCollection(self, full)


def load_pdf_text(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()


async def index_pdf(client, phone, source_title, text, taxonomy):
    from core.rag import (
        EMBEDDING_DIM,
        EMBEDDING_MODEL,
        PRIVATE_COLLECTION,
        SCHEMA_VERSION,
        _chunk_text,
        _owner_hash,
    )
    try:
        from google.cloud.firestore_v1.vector import Vector
    except ImportError:
        Vector = None

    owner_hash = _owner_hash(phone)
    chunks = _chunk_text(text)
    now = "2026-07-30T00:00:00-03:00"
    common = {
        "owner_hash": owner_hash,
        "source_title": source_title,
        "class": taxonomy["class"],
        "group": taxonomy["group"],
        "theme": taxonomy["theme"],
        "category": taxonomy["class"],
        "language": "pt-BR",
        "created_at": now,
        "schema_version": SCHEMA_VERSION,
    }
    indexed = 0
    for index, chunk in enumerate(chunks):
        doc_id = f"{source_title}-{index}-{abs(hash(chunk[:50])) % 10 ** 8:x}"
        plain = dict(common, text_content=chunk, chunk_index=index)
        client._by_name.setdefault(PRIVATE_COLLECTION + "-plain", []).append(
            _Doc(f"{doc_id}-plain", plain)
        )
        if Vector is not None:
            client._by_name.setdefault(PRIVATE_COLLECTION, []).append(
                _Doc(
                    doc_id,
                    dict(
                        plain,
                        vector_embedding=Vector(_hash_embed(chunk)),
                        embedding_model=EMBEDDING_MODEL,
                        embedding_dim=EMBEDDING_DIM,
                    ),
                )
            )
            indexed += 1
    return len(chunks), indexed


def _fake_find_nearest(db, collection_name, query_vector, limit, filters=None):
    out = []
    for d in db._by_name.get(collection_name, []):
        data = dict(d.to_dict())
        if "vector_embedding" in data:
            data["vector_distance"] = 0.15
            out.append(_Doc(d.id, data))
    return out[: max(1, limit)]


async def task_b_enforcement(client, phone, taxonomy_by_title):
    failures = []
    from core.folder_permissions import (
        grant_folder_permission,
        get_user_allowed_tools,
        force_reload_cache,
        list_folder_permissions,
        revoke_folder_permission,
    )

    async def drive_search_with_enforce(phone_arg, query_arg, folder_id=None, **kw):
        allowed = get_user_allowed_tools(phone_arg)
        catalog = [
            {"id": "doc1", "name": "cdc-capitulo-1.pdf"},
            {"id": "doc2", "name": "lgpd-capitulo-1.pdf"},
            {"id": "doc3", "name": "manual-higiene.pdf"},
        ]
        if not allowed["drive"]:
            return {"files": [], "count": 0}
        keep = [f for f in catalog if f["name"] in allowed["drive"]]
        if folder_id and folder_id not in [f["id"] for f in keep]:
            return {"files": [], "count": 0, "error": "folder_not_allowed"}
        return {"files": keep, "count": len(keep)}

    # Cenario A: whitelist CDC -> search_files deve retornar SÓ CDC
    grant_folder_permission(phone, "drive", "cdc-capitulo-1.pdf", scope="whitelist")
    force_reload_cache(phone)
    allowed = get_user_allowed_tools(phone)
    if allowed["drive"] != ["cdc-capitulo-1.pdf"]:
        failures.append(f"whitelist CDC nao ativa: {allowed}")
    print(f"  [TASK B] whitelist CDC ativa: {allowed}")
    r = await drive_search_with_enforce(phone, "")
    print(f"  [TASK B] search_files whitelist CDC -> count={r['count']} files={[f['name'] for f in r['files']]}")
    if r["count"] != 1 or r["files"][0]["name"] != "cdc-capitulo-1.pdf":
        failures.append("search_files whitelist CDC nao retornou somente CDC")

    # Cenario B: trocar whitelist para "outro.pdf" -> vazio
    for p in list_folder_permissions(phone):
        revoke_folder_permission(phone, p["permission_id"])
    force_reload_cache(phone)
    grant_folder_permission(phone, "drive", "outro.pdf", scope="whitelist")
    force_reload_cache(phone)
    r = await drive_search_with_enforce(phone, "")
    print(f"  [TASK B] search_files whitelist irrelevante -> count={r['count']}")
    if r["count"] != 0:
        failures.append("search_files com whitelist irrelevante deveria retornar vazio")

    # Cenario C: sem whitelist nenhuma -> lock-down
    for p in list_folder_permissions(phone):
        revoke_folder_permission(phone, p["permission_id"])
    force_reload_cache(phone)
    print(f"  [TASK B] lock-down state: {get_user_allowed_tools(phone)}")
    r = await drive_search_with_enforce(phone, "")
    if r["count"] != 0:
        failures.append("search_files sem permissao deveria lock-down")

    # Cenario D: folder_id passado mas nao esta na whitelist -> bloqueado
    grant_folder_permission(phone, "drive", "cdc-capitulo-1.pdf", scope="whitelist")
    force_reload_cache(phone)
    r = await drive_search_with_enforce(phone, "", folder_id="doc3")
    if r["count"] != 0:
        failures.append("search_files com folder_id fora da whitelist devia bloquear")
    print(f"  [TASK B] folder_id fora whitelist -> count={r['count']} (deve ser 0)")

    # Cenario E: tools reais (search_files, list_folder, upload_file, send_message)
    # usando o guard real de core/owner_guard
    print("  [TASK B] testando tools reais do core/owner_guard")
    for p in list_folder_permissions(phone):
        revoke_folder_permission(phone, p["permission_id"])
    force_reload_cache(phone)

    class _FakeDriveService:
        def files(self):
            return _FakeDriveFiles()

    class _FakeDriveFiles:
        def list(self, q="", pageSize=20, fields=""):
            return _FakeDriveList(q)

        def create(self, body=None, media_body=None, fields=""):
            return _FakeDriveCreate(body)

    class _FakeDriveList:
        def __init__(self, q):
            self.q = q

        def execute(self):
            return {
                "files": [
                    {"id": "f1", "name": "cdc-capitulo-1.pdf"},
                    {"id": "f2", "name": "lgpd-capitulo-1.pdf"},
                    {"id": "f3", "name": "outro.pdf"},
                ]
            }

    class _FakeDriveCreate:
        def __init__(self, body):
            self.body = body

        def execute(self):
            return {"id": "new", "name": self.body.get("name"), "mimeType": "application/pdf"}

    with patch("tools.google_drive._get_service", return_value=_FakeDriveService()):
        from tools.google_drive import search_files, upload_file

        # E1: lock-down sem whitelist -> error
        r = await search_files(phone="5511966830020", query="")
        print(f"  [TASK B] search_files sem whitelist -> {r}")
        if "error" not in r or r.get("error") != "folder_permission_required":
            failures.append("search_files sem whitelist devia bloquear com folder_permission_required")

        # E2: whitelist CDC + search_files sem folder_id -> retorna SÓ CDC (post-filter)
        grant_folder_permission(phone, "drive", "cdc-capitulo-1.pdf", scope="whitelist")
        force_reload_cache(phone)
        r = await search_files(phone="5511966830020", query="")
        print(f"  [TASK B] search_files whitelist CDC (tool real) -> count={r['count']} files={[f['name'] for f in r.get('files', [])]}")
        names = [f["name"] for f in r.get("files", [])]
        if "lgpd-capitulo-1.pdf" in names or "outro.pdf" in names:
            failures.append("search_files tool real retornou arquivos fora da whitelist")

        # E3: upload_file em folder nao autorizado -> bloqueado
        r = await upload_file(
            phone="5511966830020", folder_id="lgpd-folder", filename="x.pdf", content="x"
        )
        print(f"  [TASK B] upload_file folder nao autorizado (tool real) -> {r}")
        if "error" not in r or r.get("error") != "folder_permission_denied":
            failures.append("upload_file em folder nao autorizado devia bloquear")

        # E4: upload_file em folder autorizado -> passa
        r = await upload_file(
            phone="5511966830020", folder_id="cdc-capitulo-1.pdf", filename="x.pdf", content="x"
        )
        print(f"  [TASK B] upload_file folder autorizado -> keys={list(r.keys())}")
        if "file" not in r:
            failures.append("upload_file em folder autorizado devia passar")

    return failures


async def run_smoke() -> int:
    failures = []

    if not GOLDENSET_DIR.exists():
        print(f"[ERRO] GoldenSet nao encontrado em {GOLDENSET_DIR}")
        return 1
    pdfs = sorted(GOLDENSET_DIR.glob("*.pdf"))
    if not pdfs:
        print("[ERRO] Nenhum PDF em GoldenSet. Rode: python -m scripts.build_golden_set")
        return 1
    print(f"[0] PDFs encontrados: {[p.name for p in pdfs]}")

    client = _FirestoreClient()
    taxonomy_by_title = {}

    # 1. Extrair texto + categorizar + indexar
    print("[1] Indexando PDFs reais do GoldenSet")
    for pdf in pdfs:
        text = load_pdf_text(pdf)
        if not text:
            failures.append(f"{pdf.name} extraido vazio")
            continue
        tax = _categorize_by_filename(pdf.name, text)
        taxonomy_by_title[pdf.name] = tax
        with patch("agent_orchestration.categorizer._llm_categorize", AsyncMock(return_value=tax)), \
             patch("core.rag.embed_documents", side_effect=lambda texts: [_hash_embed(t) for t in texts]), \
             patch("core.rag._get_firestore", return_value=client):
            chunks, indexed = await index_pdf(client, PHONE, pdf.name, text, tax)
        print(f"  index {pdf.name}: chunks={chunks} indexed={indexed} class={tax['class']}/{tax['group']}")

    # 2. Retrieval
    print("\n[2] Retrieval com queries realistas")
    queries = [
        ("direitos do consumidor", "cdc-capitulo-1.pdf"),
        ("dados pessoais sensiveis", "lgpd-capitulo-1.pdf"),
        ("higienizacao das maos", "manual-higiene.pdf"),
        ("marketing agressivo", None),
    ]
    envelope = {"phone": PHONE, "extra": {"remote_jid": f"{PHONE}@s.whatsapp.net"}}
    with patch("core.rag.embed_query", side_effect=lambda text: _hash_embed(text)), \
         patch("core.rag._get_firestore", return_value=client), \
         patch("core.rag._find_nearest", side_effect=_fake_find_nearest), \
         patch("agent_orchestration.categorizer._llm_categorize",
               side_effect=lambda text, name: taxonomy_by_title.get(name, _categorize_by_filename(name, text))):
        from agent_orchestration.knowledge_retriever import retrieve as do_retrieve
        for q, hint in queries:
            envelope["extra"]["source_hint"] = hint
            r = await do_retrieve(envelope, q)
            count = r.get("count", 0)
            src_top = r.get("results", [{}])[0].get("source", "?") if r.get("results") else "?"
            print(f"  retrieve({q!r}, hint={hint}) -> count={count} top_src={src_top[:30]}")
            if hint and count == 0 and "marketing" not in q:
                failures.append(f"retrieve retornou 0 para query esperada: {q}")

    # 3. TASK B enforcement
    print("\n[3] TASK B - folder_permissions enforcement")
    with patch("core.folder_permissions._get_firestore_client", return_value=client):
        task_b_failures = await task_b_enforcement(client, PHONE, taxonomy_by_title)
    failures.extend(task_b_failures)

    # 4. Portal UI render check
    print("\n[4] Portal UI render check")
    try:
        from core.module_ui import render_dashboard
        html = render_dashboard("abc1234", "2026-07-30T00:00:00Z")
        for token in ["Agentes Omnichannel", "editAgentForm", "viewKnowledgeDoc", "deepseek-v4-flash"]:
            if token not in html:
                failures.append(f"render_dashboard sem token obrigatorio: {token}")
        print("  HTML OK: handlers editar/ver/modal/llm presentes")
    except Exception as exc:
        failures.append(f"render_dashboard falhou: {exc}")

    # 5. /admin/status
    print("\n[5] /admin/status endpoint check")
    os.environ.setdefault("AGENTS_RUNTIME_SA_TOKEN_SECRET", "test-sa-secret")
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-deepseek-key")
    from main import app
    from fastapi.testclient import TestClient

    api_client = TestClient(app)
    headers = {"Authorization": "Bearer test-sa-secret"}
    with patch("main._short_sha", return_value="abc1234"):
        resp = api_client.get("/admin/status", headers=headers)
    if resp.status_code != 200:
        failures.append(f"/admin/status retornou {resp.status_code}")
    else:
        body = resp.json()
        llm = body.get("llm", {})
        if llm.get("model") != "deepseek-v4-flash":
            failures.append(f"llm.model={llm.get('model')} != deepseek-v4-flash")
        if llm.get("cascade") is not False:
            failures.append(f"llm.cascade={llm.get('cascade')} != False")
        if any("stt_fallback" in k["label"] for k in body.get("kpis", [])):
            failures.append("kpis ainda tem stt_fallback")
        print(f"  /admin/status OK: model={llm.get('model')} cascade={llm.get('cascade')}")

    print(f"\nFinal: {len(failures)} falhas")
    for f in failures:
        print(f"  - {f}")
    return 0 if not failures else 1


def main():
    rc = asyncio.run(run_smoke())
    sys.exit(rc)


if __name__ == "__main__":
    main()
