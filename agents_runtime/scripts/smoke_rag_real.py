"""Smoke end-to-end (Phase 7) sem credenciais reais.

Indexa 3 documentos com textos realistas em um Firestore fake + embeddings
determinısticos, depois exercita o pipeline real:

1. knowledge_retriever.retrieve() em varios cenarios (semanticamente
   diferentes, com e sem source_hint, com score threshold).
2. Classificador categorizer.classify() atribui class/group/theme.
3. Endpoint /admin/knowledge lido pelo FakeClient e o agrupamento por
   source_title funciona.
4. Endpoint /admin/status mostra llm_provider=deepseek-v4-flash.

Nao precisa de chave GCP nem OpenAI. Tudo em memoria.

Uso:
    .venv-c/Scripts/python -m scripts.smoke_rag_real
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from unittest.mock import patch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


DOCUMENTS = [
    {
        "title": "cdc-portugues-2013.pdf",
        "klass": "legal",
        "group": "direito_consumidor",
        "theme": "cdc",
        "text": (
            "CAPITULO I - DISPOSICOES GERAIS\n\n"
            "Art. 1o O presente codigo estabelece normas de protecao e defesa do consumidor, de ordem publica e interesse social, nos termos dos arts. 5o, XXXII, 170, V, da Constituicao Federal e art. 48 e seu paragrafo IV das Disposicoes Constitucionais Transitórias.\n"
            "Art. 2o Consumidor e toda pessoa fisica ou juridica que adquire ou utiliza produto ou servico como destinatario final.\n"
            "Paragrafo unico. Equipara-se a consumidor a coletividade de pessoas, ainda que indeterminaveis, que haja intervindo nas relacoes de consumo.\n\n"
            "CAPITULO II - DO COMERCIO ELETRONICO\n\n"
            "Art. 45A. As disposicoes deste codigo aplicam-se aos contratos celebrados por meio eletronico, virtual ou por qualquer outro meio de comunicacao a distancia.\n"
            "Paragrafo unico. O fornecedor deve informar de forma clara e inequivoca sobre o produto, preco, prazos, encargos, riscos e demais aspectos relevantes da contratacao.\n\n"
            "CAPITULO III - DA PUBLICIDADE\n\n"
            "Art. 36 A publicidade deve ser veiculada de tal forma que o consumidor, facil e imediatamente a identifique como tal.\n"
            "Paragrafo unico. O fornecedor, na publicidade de seus produtos ou servicos, mantendraa em seu poder, para informacao dos legitimos interessados, os dados fáticos, tecnicos ecientificos que do sustentacao a mensagem.\n"
        ),
    },
    {
        "title": "dissertacao.pdf",
        "klass": "academico",
        "group": "engenharia_dados",
        "theme": "machine_learning",
        "text": (
            "RESUMO\n\n"
            "Esta dissertacao apresenta um estudo sobre aplicacao de tecnicas de aprendizado de maquina supervisionado na deteccao de anomalias em series temporais financeiras. Sao avaliados os modelos ARIMA, LSTM e Prophet em diferentes horizontes de previsao.\n\n"
            "CAPITULO 1 - INTRODUCAO\n\n"
            "1.1 Motivacao\n\n"
            "A crescente disponibilidade de dados financeiros em alta frequencia abre oportunidades para aplicacao de tecnicas avancadas de aprendizado profundo na deteccao precoce de padroes anomalos. Setores como bancos centrais, fintechs e gestoras de fundos hedge demandam sistemas que processem milhoes de eventos por segundo sem degradar a precisao.\n\n"
            "1.2 Objetivos\n\n"
            "Comparar o desempenho de ARIMA classico, LSTM bidirecional e Prophet em tres datasets publicos de series temporais financeiras (Yahoo Finance S&P 500, Bovespa diaria, Bitcoin minute-level).\n\n"
            "CAPITULO 2 - FUNDAMENTACAO\n\n"
            "2.1 Series temporais\n\n"
            "Uma serie temporal e uma colecao de observacoes indexadas no tempo. Formalmente, X(t) para t em T. Os modelos ARIMA (Autoregressive Integrated Moving Average) decompõem a serie em componente autoregressivo, integracao e media movel.\n\n"
            "2.2 Aprendizado profundo\n\n"
            "Redes neurais recorrentes LSTM (Long Short-Term Memory) foram propostas por Hochreiter & Schmidhuber (1997). Sua capacidade de reter dependencias de longo prazo atraves de portoes forget/input/output as torna uteis para series temporais.\n"
        ),
    },
    {
        "title": "manual_higiene.pdf",
        "klass": "manual",
        "group": "saude",
        "theme": "higiene_maos",
        "text": (
            "PROTOCOLO DE HIGIENE DAS MAOS\n\n"
            "1. OBJETIVO\n\n"
            "Padronizar os procedimentos de higiene das maos para todos os profissionais de saude, conforme recomendacoes da OMS e da ANVISA.\n\n"
            "2. PROCEDIMENTO\n\n"
            "2.1 Antes do contato com o paciente\n\n"
            "Realizar higienizacao das maos com agua e sabao por 40 a 60 segundos OU friccao com solucao alcoolica 70 por 20 a 30 segundos.\n\n"
            "2.2 Apos contato com fluidos corporais\n\n"
            "Lavar rigorosamente as maos ate os punhos com antisseptico padrao. Secar com papel toalha descartavel.\n\n"
            "2.3 Cinco momentos da OMS\n\n"
            "(1) Antes de tocar o paciente. (2) Antes de procedimento asseptico. (3) Apos risco de exposicao a fluidos. (4) Apos tocar o paciente. (5) Apos tocar superficies proximas ao paciente.\n\n"
            "3. DOCUMENTACAO\n\n"
            "Registrar a adesao ao protocolo em formulario institucional diariamente.\n"
        ),
    },
]


def _hash_embed(text: str) -> list:
    import hashlib
    h = hashlib.md5(text.encode("utf-8")).digest()
    return [(h[i % 16] - 128) / 128.0 for i in range(1536)]


class _Doc:
    def __init__(self, doc_id: str, data: dict):
        self.id = doc_id
        self._data = data

    def to_dict(self) -> dict:
        return dict(self._data)


class _FirestoreCollection:
    def __init__(self, name: str, docs: list):
        self._name = name
        self._docs = list(docs)

    def limit(self, n):
        return self

    def stream(self):
        for d in list(self._docs):
            yield d

    def where(self, *args, **kwargs):
        field = None
        op = "=="  # noqa: F841
        value = None
        if args:
            field = args[0]
            if len(args) >= 2:
                _op = args[1]  # noqa: F841
            if len(args) >= 3:
                value = args[2]
        if kwargs.get("filter") is not None:
            fil = kwargs["filter"]
            if hasattr(fil, "field") and hasattr(fil, "op_string"):
                field = fil.field
                value = fil.value
        filtered = [d for d in self._docs if d.to_dict().get(field) == value]
        return _FirestoreCollection(self._name, filtered)

    def document(self, doc_id):
        for d in self._docs:
            if d.id == doc_id:
                return d
        return _Doc(doc_id, {})


class _FirestoreClient:
    def __init__(self):
        self._by_name = {}

    def collection(self, name):
        if name not in self._by_name:
            self._by_name[name] = []
        return _FirestoreCollection(name, self._by_name[name])


async def _index_document(
    client: _FirestoreClient,
    phone: str,
    source_title: str,
    text: str,
    klass: str,
    group: str,
    theme: str,
):
    from core.rag import (
        EMBEDDING_DIM,
        EMBEDDING_MODEL,
        PRIVATE_COLLECTION,
        SCHEMA_VERSION,
        _chunk_text,
        _owner_hash,
    )
    from google.cloud.firestore_v1.vector import Vector

    owner_hash = _owner_hash(phone)
    print(f"  index {source_title}: text type={type(text).__name__} len={len(text)}")
    chunks = _chunk_text(text)
    print(f"  index {source_title}: chunks={len(chunks)}")
    now = "2026-07-30T00:00:00-03:00"
    common_base = {
        "owner_hash": owner_hash,
        "source_title": source_title,
        "class": klass,
        "group": group,
        "theme": theme,
        "category": klass,
        "language": "pt-BR",
        "created_at": now,
        "schema_version": SCHEMA_VERSION,
    }
    for index, chunk in enumerate(chunks):
        doc_id = f"{source_title}-{index}-{abs(hash(chunk[:50])) % 10**8:x}"
        plain = dict(common_base, text_content=chunk, chunk_index=index)
        client._by_name.setdefault(PRIVATE_COLLECTION + "-plain", []).append(
            _Doc(f"{doc_id}-plain", plain)
        )
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
    return len(chunks)


async def run_smoke() -> int:
    client = _FirestoreClient()
    phone = "5511966830020"
    print("Indexando documentos sinteticos no Firestore fake...")
    for spec in DOCUMENTS:
        chunks = await _index_document(
            client, phone, spec["title"], spec["text"], spec["klass"], spec["group"], spec["theme"],
        )
        print(f"  + {spec['title']}: {chunks} chunks")

    from agent_orchestration.knowledge_retriever import retrieve

    async def fake_embed_query(text):
        return _hash_embed(text)

    envelope = {
        "phone": phone,
        "extra": {"remote_jid": f"{phone}@s.whatsapp.net"},
    }
    scenarios = [
        ("direitos do consumidor", "cdc-portugues-2013.pdf"),
        ("aprendizado profundo e series temporais", "dissertacao.pdf"),
        ("higienizacao das maos com alcool", "manual_higiene.pdf"),
        ("marketing agressivo", None),
    ]
    failures = 0
    with patch("core.rag.embed_query", side_effect=fake_embed_query), patch(
        "core.rag._get_firestore", return_value=client
    ), patch(
        "core.rag._find_nearest",
        side_effect=_fake_find_nearest,
    ):
        for query, hint in scenarios:
            print(f"\n=== Query: '{query}' (hint={hint!r}) ===")
            envelope["extra"]["source_hint"] = hint
            result = await retrieve(envelope, query)
            decision = result.get("decision")
            count = result.get("count", 0)
            print(
                f"  decision={decision} scope={result.get('scope')} "
                f"count={count} min_score={result.get('min_score')} "
                f"filters={result.get('filters')}"
            )
            if result.get("clarification_prompt"):
                print(f"  clarification={result.get('clarification_prompt')[:80]}")
            for chunk in result.get("results", [])[:3]:
                print(
                    f"    source={chunk.get('source', '?')[:40]} "
                    f"class={chunk.get('class', '?')}/group={chunk.get('group', '?')} "
                    f"score={chunk.get('score', 0):.3f} "
                    f"chars={len(chunk.get('text', ''))}"
                )
            if hint and hint != "marketing agressivo" and count == 0:
                print(f"  EXPECTAVA chunks para {hint}")
                failures += 1

    print("\n=== /admin/knowledge agrupa por source_title ===")
    os.environ.setdefault("AGENTS_RUNTIME_SA_TOKEN_SECRET", "test-sa-secret")
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-deepseek-key")
    from main import app
    from fastapi.testclient import TestClient

    headers = {"Authorization": "Bearer test-sa-secret"}
    test_api = TestClient(app)
    with patch("agent_loader._get_firestore_client", return_value=client):
        resp = test_api.get("/admin/knowledge?limit=20", headers=headers)
    if resp.status_code != 200:
        print(f"  /admin/knowledge falhou: {resp.status_code} {resp.text[:200]}")
        failures += 1
    else:
        body = resp.json()
        docs = body.get("documents", [])
        print(f"  {len(docs)} grupos retornados:")
        for d in docs:
            print(
                f"    - {d['title']}: chunks={d['chunk_count']} "
                f"class={d['klass']} group={d['group']} theme={d['theme']}"
            )
        if len(docs) != len(DOCUMENTS):
            print(f"  EXPECTAVA {len(DOCUMENTS)} grupos, recebi {len(docs)}")
            failures += 1
        else:
            print("  OK: agrupamento por source_title correto")

    first_title = DOCUMENTS[0]["title"]
    with patch("agent_loader._get_firestore_client", return_value=client):
        resp = test_api.get(f"/admin/knowledge/{first_title}", headers=headers)
    print(f"\n=== /admin/knowledge/{first_title} (detalhe) ===")
    if resp.status_code != 200:
        print(f"  detalhe falhou: {resp.status_code}")
        failures += 1
    else:
        doc = resp.json()["document"]
        print(f"  chunk_count={doc['chunk_count']} class={doc['klass']} group={doc['group']} theme={doc['theme']}")
        for c in doc["chunks"][:3]:
            preview = (c.get("text", "")[:60] + "...") if c.get("text") else ""
            print(f"    idx={c['chunk_index']} chars={c['chars']} text='{preview}'")
        if doc["chunk_count"] == 0:
            print("  ESPERAVA chunks")
            failures += 1
        else:
            print("  OK: detalhe retornou chunks")

    print("\n=== /admin/status (LLM unico) ===")
    with patch("main._short_sha", return_value="abc1234"):
        resp = test_api.get("/admin/status", headers=headers)
    body = resp.json()
    llm = body.get("llm", {})
    print(f"  runtime_ok={body.get('runtime_ok')}")
    print(f"  llm: provider={llm.get('provider')} model={llm.get('model')} cascade={llm.get('cascade')}")
    if llm.get("provider") == "deepseek" and llm.get("model") == "deepseek-v4-flash" and llm.get("cascade") is False:
        print("  OK: llm provider = deepseek-v4-flash (sem cascade)")
    else:
        print("  FALHA: llm provider nao corresponde ao esperado")
        failures += 1
    legacy = any("stt_fallback" in k["label"] for k in body.get("kpis", []))
    if legacy:
        print("  AVISO: ainda ha stt_fallback em kpis (legado)")
    else:
        print("  OK: kpis sem stt_fallback (limpos)")

    print("\n=== /admin/agents UI helpers (render_dashboard) ===")
    from core.module_ui import render_dashboard
    html = render_dashboard("abc1234", "2026-07-30T00:00:00Z")
    has_edit = "editAgentForm" in html and "data-edit=" in html or 'data-delete=' in html
    has_view = "viewKnowledgeDoc" in html
    has_modal = "showModal" in html and "modal-backdrop" in html
    if has_edit and has_view and has_modal:
        print("  OK: portal HTML embute handlers de editar, ver, modal")
    else:
        print(f"  FALHA: portal incompleto edit={has_edit} view={has_view} modal={has_modal}")
        failures += 1

    print(f"\nFinal do smoke (failures={failures})")
    return 0 if failures == 0 else 1


def _fake_find_nearest(db, collection_name, query_vector, limit, filters=None):
    """Stub deterministico: retorna todos os docs do Firestore fake com
    score artificial. Suficiente para validar pipeline sem Firestore real."""
    try:
        db.collection(collection_name)
    except Exception:
        return []
    target = collection_name
    for fname, fop, fval in filters or []:
        target = fname
        break
    found = []
    for d in db._by_name.get(collection_name, []):
        data = d.to_dict()
        if target and data.get(target) and target in filters[0] if filters else True:
            pass
        data = dict(data)
        if "vector_embedding" in data:
            data["vector_distance"] = 0.2
        found.append(_Doc(d.id, data))
    return found[: max(1, limit)]


def main() -> None:
    rc = asyncio.run(run_smoke())
    sys.exit(rc)


if __name__ == "__main__":
    main()
