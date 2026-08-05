"""Tests do fix TASK B (Fase 30/07/2026).

Garante que firestore.indexes.json inclui vector composite
indexes para agent-knowledge-v2 com todos os filtros usados
pelo _find_nearest().

Bug original (30/07 05:48): Edital.pdf foi indexado com sucesso
("Memorei 18 trechos") mas retrieval retornou 0 chunks com
erro 'Missing vector index configuration'. Causa: nenhum
vector composite index existia em production.

Este teste documenta o fix: ao menos um index vector composite
com todos os filtros esperados (embedding_model + embedding_dim
+ schema_version + owner_hash + source_title + class +
vector_embedding)."""
import json
import os


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIRESTORE_INDEXES_PATH = os.path.join(
    REPO_ROOT, "..", "firestore.indexes.json",
)


def _load_config():
    with open(FIRESTORE_INDEXES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_firestore_indexes_json_includes_required_vector_indexes():
    """firestore.indexes.json DEVE conter vector composite indexes
    para agent-knowledge-v2 cobrindo os filtros usados em
    core.rag._find_nearest()."""
    config = _load_config()

    akv2_indexes = [
        idx for idx in config["indexes"]
        if idx.get("collectionGroup") == "agent-knowledge-v2"
    ]
    assert akv2_indexes, "agent-knowledge-v2 sem indexes"

    vector_index_names = set()
    for idx in akv2_indexes:
        last_field = idx["fields"][-1]
        if "vectorConfig" in last_field:
            vector_index_names.add(idx["fields"][0]["fieldPath"])

    expected_filters = {"embedding_model", "owner_hash"}
    missing = expected_filters - vector_index_names
    assert not missing, (
        f"Vector composite indexes devem cobrir filtros {expected_filters}, "
        f"mas cobrem apenas {vector_index_names}. Faltam: {missing}"
    )


def test_firestore_vector_dim_matches_rag_config():
    """Dimensoes do vector_config batem com RAG_EMBEDDING_DIM (1536)."""
    config = _load_config()

    for idx in config["indexes"]:
        if idx.get("collectionGroup") != "agent-knowledge-v2":
            continue
        for field in idx["fields"]:
            if "vectorConfig" in field:
                assert field["vectorConfig"]["dimension"] == 1536, (
                    f"Vector dimension deve ser 1536 (OpenAI text-embedding-3-small). "
                    f"Encontrado: {field['vectorConfig']['dimension']}"
                )


def test_firestore_indexes_includes_filename_class_combo():
    """Index COBRINDO source_title + class (hint + class hint)

    Caso de uso: 'me fala sobre Edital.pdf' (filename + class=edital).
    Sem este index, query retorna 0 com erro 400.
    """
    config = _load_config()

    for idx in config["indexes"]:
        if idx.get("collectionGroup") != "agent-knowledge-v2":
            continue
        field_paths = [f["fieldPath"] for f in idx["fields"]]
        if "source_title" in field_paths and "class" in field_paths:
            assert any("vectorConfig" in f for f in idx["fields"]), (
                "Index (source_title + class) precisa ser vector composite"
            )
            return

    assert False, (
        "Nenhum index agent-knowledge-v2 cobre source_title + class + vector. "
        "Bug TASK B: queries com filename+class hint voltam 0 chunks."
    )


def test_firestore_indexes_includes_source_title_full():
    """Index cobrindo owner_hash + embedding_model + embedding_dim +
    schema_version + source_title + vector_embedding.

    Caso de uso: search_legal_knowledge com source_title filter.
    Sem este index, queries com filename hint (ex: 'dissertação.pdf')
    retornam 0 chunks.
    """
    config = _load_config()

    required_fields = [
        "owner_hash",
        "embedding_model",
        "embedding_dim",
        "schema_version",
        "source_title",
    ]

    for idx in config["indexes"]:
        if idx.get("collectionGroup") != "agent-knowledge-v2":
            continue
        field_paths = [f["fieldPath"] for f in idx["fields"]]
        if all(f in field_paths for f in required_fields):
            assert any("vectorConfig" in f for f in idx["fields"]), (
                "Index source_title_full precisa ser vector composite"
            )
            last_vector = next(
                f for f in idx["fields"] if "vectorConfig" in f
            )
            assert last_vector["fieldPath"] == "vector_embedding"
            return

    assert False, (
        f"Nenhum index agent-knowledge-v2 cobre {required_fields} + vector. "
        "Fase Kd: queries com source_title filter voltam 0 chunks."
    )


def test_firestore_indexes_source_title_full_dim():
    """Dimensao do source_title_full index = 1536."""
    config = _load_config()

    required_fields = [
        "owner_hash", "embedding_model", "embedding_dim",
        "schema_version", "source_title",
    ]

    for idx in config["indexes"]:
        if idx.get("collectionGroup") != "agent-knowledge-v2":
            continue
        field_paths = [f["fieldPath"] for f in idx["fields"]]
        if all(f in field_paths for f in required_fields):
            for f in idx["fields"]:
                if "vectorConfig" in f:
                    assert f["vectorConfig"]["dimension"] == 1536
                    return


def test_firestore_indexes_includes_sections_collection():
    """agent-knowledge-sections precisa de vector index para o search_sections."""
    config = _load_config()

    for idx in config["indexes"]:
        if idx.get("collectionGroup") != "agent-knowledge-sections":
            continue
        field_paths = [f["fieldPath"] for f in idx["fields"]]
        assert "owner_hash" in field_paths
        assert "vector_embedding" in field_paths
        for f in idx["fields"]:
            if "vectorConfig" in f:
                assert f["vectorConfig"]["dimension"] == 1536
                return

    assert False, "Nenhum vector index para agent-knowledge-sections em firestore.indexes.json"

