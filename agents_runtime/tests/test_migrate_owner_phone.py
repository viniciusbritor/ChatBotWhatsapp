"""Tests for owner_phone migration script."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


OLD = "5511966830020"
NEW = "5511967389901"


def _mock_doc(doc_id, owner_phone, instance="jennifer"):
    doc = MagicMock()
    doc.id = doc_id
    doc.to_dict.return_value = {"owner_phone": owner_phone, "instance": instance}
    doc.reference = MagicMock()
    return doc


def _import_main_with_mock(mock_db):
    """Helper: import main() com _get_firestore_client mockado."""
    # Patch ANTES de importar o modulo
    import sys
    import importlib
    # Patch no agent_loader onde _get_firestore_client eh usado pelo script
    with patch("agent_loader._get_firestore_client", return_value=mock_db):
        if "scripts.migrate_owner_phone_to_9901" in sys.modules:
            importlib.reload(sys.modules["scripts.migrate_owner_phone_to_9901"])
        from scripts.migrate_owner_phone_to_9901 import main as m
    return m


def test_migrate_no_docs_found():
    """Quando collection esta vazia, retorna exit 0 sem erro."""
    mock_db = MagicMock()
    mock_coll = MagicMock()
    mock_coll.stream.return_value = []
    mock_db.collection.return_value = mock_coll
    main = _import_main_with_mock(mock_db)
    assert main([]) == 0


def test_migrate_all_already_correct():
    """Quando todos os phones ja foram migrados, retorna exit 0."""
    mock_db = MagicMock()
    mock_coll = MagicMock()
    mock_coll.stream.return_value = [
        _mock_doc("doc1", NEW),
        _mock_doc("doc2", NEW),
    ]
    mock_db.collection.return_value = mock_coll
    main = _import_main_with_mock(mock_db)
    assert main([]) == 0


def test_migrate_dry_run_no_patch():
    """Em dry-run, batch NAO deve ser chamado."""
    mock_db = MagicMock()
    mock_coll = MagicMock()
    mock_coll.stream.return_value = [_mock_doc("doc1", OLD)]
    mock_db.collection.return_value = mock_coll
    main = _import_main_with_mock(mock_db)
    result = main([])
    assert result == 0
    mock_db.batch.assert_not_called()


def test_migrate_apply_patches_batch():
    """Em --apply, batch.update + batch.commit devem ser chamados."""
    mock_db = MagicMock()
    mock_coll = MagicMock()
    mock_batch = MagicMock()
    mock_db.batch.return_value = mock_batch
    mock_coll.stream.return_value = [
        _mock_doc("doc1", OLD),
        _mock_doc("doc2", OLD),
    ]
    mock_db.collection.return_value = mock_coll
    main = _import_main_with_mock(mock_db)
    result = main(["--apply"])
    assert result == 0
    assert mock_batch.update.call_count == 2
    mock_batch.commit.assert_called_once()


def test_migrate_no_firestore_client():
    """Quando Firestore nao disponivel, retorna exit 1."""
    import sys
    import importlib
    with patch("agent_loader._get_firestore_client", return_value=None):
        if "scripts.migrate_owner_phone_to_9901" in sys.modules:
            importlib.reload(sys.modules["scripts.migrate_owner_phone_to_9901"])
        from scripts.migrate_owner_phone_to_9901 import main as m
    assert m([]) == 1
