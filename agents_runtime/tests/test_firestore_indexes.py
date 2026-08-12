"""Tests dos firestore composite indexes (knowledge-database).

Garante que firestore.indexes.json inclui os vector composite indexes para
``knowledge-database`` com todos os filtros usados por ``core.rag``
(_find_nearest / retrieval) e NENHUM index para as colecoes mortas
(agent-knowledge-v2, agent-knowledge-sections, public-knowledge-v2,
conversation-memory-v2, group-knowledge-v2), removidas na migracao para
``knowledge-database``.
"""
import json
import os


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIRESTORE_INDEXES_PATH = os.path.join(
    REPO_ROOT, "..", "firestore.indexes.json",
)

DEAD_COLLECTIONS = {
    "agent-knowledge-v2",
    "agent-knowledge-sections",
    "public-knowledge-v2",
    "conversation-memory-v2",
    "group-knowledge-v2",
}


def _load_config():
    with open(FIRESTORE_INDEXES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _kd_indexes(config):
    return [
        idx for idx in config["indexes"]
        if idx.get("collectionGroup") == "knowledge-database"
    ]


def test_no_dead_collection_indexes():
    """firestore.indexes.json NAO deve referenciar colecoes mortas."""
    config = _load_config()
    groups = {idx.get("collectionGroup") for idx in config["indexes"]}
    dead = groups & DEAD_COLLECTIONS
    assert not dead, f"Indexes para colecoes mortas ainda presentes: {dead}"


def test_knowledge_database_has_vector_indexes():
    config = _load_config()
    kd = _kd_indexes(config)
    assert kd, "knowledge-database sem indexes"

    vector_indexes = [
        idx for idx in kd
        if any("vectorConfig" in f for f in idx["fields"])
    ]
    assert vector_indexes, "knowledge-database sem vector composite index"

    first_fields = set()
    for idx in vector_indexes:
        first_fields.add(idx["fields"][0]["fieldPath"])
    expected = {"scope"}
    missing = expected - first_fields
    assert not missing, f"Vector indexes devem cobrir scope, faltam: {missing}"


def test_firestore_vector_dim_matches_rag_config():
    config = _load_config()
    for idx in _kd_indexes(config):
        for field in idx["fields"]:
            if "vectorConfig" in field:
                assert field["vectorConfig"]["dimension"] == 1536, (
                    f"Vector dimension deve ser 1536 (OpenAI text-embedding-3-small). "
                    f"Encontrado: {field['vectorConfig']['dimension']}"
                )


def test_knowledge_database_covers_scope_owner_hash_source_title():
    """Index cobrindo scope + owner_hash + source_title (delete/retrieval)."""
    config = _load_config()
    required = ["scope", "owner_hash", "source_title"]
    for idx in _kd_indexes(config):
        field_paths = [f["fieldPath"] for f in idx["fields"]]
        if all(r in field_paths for r in required):
            return
    assert False, f"Nenhum index knowledge-database cobre {required}"


def test_knowledge_database_covers_source_title_class_vector():
    """Index COBRINDO source_title + class + vector (hint + class hint)."""
    config = _load_config()
    for idx in _kd_indexes(config):
        field_paths = [f["fieldPath"] for f in idx["fields"]]
        if "source_title" in field_paths and "class" in field_paths:
            assert any("vectorConfig" in f for f in idx["fields"]), (
                "Index (source_title + class) precisa ser vector composite"
            )
            return
    assert False, "Nenhum index knowledge-database cobre source_title + class + vector"
