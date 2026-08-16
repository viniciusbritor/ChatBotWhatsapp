"""Tests for audit_firestore_location script."""

from __future__ import annotations

import json
import subprocess
import sys
from unittest.mock import patch, MagicMock

import pytest


def _mock_gcloud_result(returncode: int, stdout: str, stderr: str = ""):
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def _run_main(argv=None):
    """Helper: run main() with sys.argv patching, catching SystemExit."""
    import scripts.audit_firestore_location as mod
    if argv is not None:
        old_argv = sys.argv
        sys.argv = ["audit_firestore_location.py"] + argv
    try:
        return mod.main(argv)
    except SystemExit as e:
        return e.code
    finally:
        if argv is not None:
            sys.argv = old_argv


def test_main_br_compliant_exits_0():
    """Quando location = southamerica-east1, retorna exit 0."""
    db_info = {"locationId": "southamerica-east1", "type": "FIRESTORE_NATIVE", "etag": "abc", "createTime": "2026-01-01"}
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            _mock_gcloud_result(0, json.dumps(db_info)),
            _mock_gcloud_result(0, "users\nmessages\nagents"),
        ]
        assert _run_main() == 0


def test_main_nam5_exits_2():
    """Quando location = nam5 (multi-region US), retorna exit 2."""
    db_info = {"locationId": "nam5", "type": "FIRESTORE_NATIVE", "etag": "abc", "createTime": "2026-01-01"}
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            _mock_gcloud_result(0, json.dumps(db_info)),
            _mock_gcloud_result(0, ""),
        ]
        assert _run_main() == 2


def test_main_eur3_exits_2():
    """Quando location = eur3 (EU), retorna exit 2 NAO-BR."""
    db_info = {"locationId": "eur3", "type": "FIRESTORE_NATIVE", "etag": "abc", "createTime": "2026-01-01"}
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            _mock_gcloud_result(0, json.dumps(db_info)),
            _mock_gcloud_result(0, ""),
        ]
        assert _run_main() == 2


def test_main_gcloud_not_found_exits_1():
    """Quando gcloud nao esta instalado, retorna exit 1."""
    with patch("subprocess.run", side_effect=FileNotFoundError("gcloud not found")):
        assert _run_main() == 1


def test_main_gcloud_error_exits_1():
    """Quando gcloud falha, retorna exit 1."""
    with patch("subprocess.run", return_value=_mock_gcloud_result(1, "", "error")):
        assert _run_main() == 1


def test_main_json_output(capsys):
    """Verifica output JSON com --json."""
    db_info = {"locationId": "southamerica-east1", "type": "FIRESTORE_NATIVE", "etag": "abc", "createTime": "2026-01-01"}
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            _mock_gcloud_result(0, json.dumps(db_info)),
            _mock_gcloud_result(0, "users"),
        ]
        _run_main(["--json"])
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["location_id"] == "southamerica-east1"
        assert parsed["br_compliant"] is True
        assert "BR-COMPLIANT" in parsed["verdict"]
