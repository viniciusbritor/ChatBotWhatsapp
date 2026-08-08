"""Tests for scripts/check_lgpd_compliance.py.

Verifies that the LGPD compliance checker enforces the canonical structure
required by the Fase C/E gates: mandatory files exist (including worker
Dockerfiles), mandatory snippets are present in the runtime code, and Cloud
Build triggers invoke the checker.

LGPD gate disabled in Fase K per product owner direction (velocidade na
implantacao). Remaining tests below validate the script itself.
"""
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.xfail(reason="LGPD gate disabled — requires full repo structure in CI")
def test_check_lgpd_compliance_passes_in_repo():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "scripts/check_lgpd_compliance.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "LGPD compliance checks passed" in result.stdout


def test_check_lgpd_compliance_reports_missing_file(tmp_path, monkeypatch):
    from scripts import check_lgpd_compliance

    fake_root = tmp_path
    (fake_root / "core").mkdir()
    (fake_root / "docs").mkdir()
    (fake_root / "ata_worker").mkdir()
    (fake_root / "proactive_worker").mkdir()
    (fake_root / "main.py").write_text("mask_pii(transcript)\n", encoding="utf-8")
    (fake_root / "orchestrator.py").write_text("masked_text = mask_pii(text)\n", encoding="utf-8")
    (fake_root / "cloudbuild-test.yaml").write_text("scripts/check_lgpd_compliance.py\n", encoding="utf-8")
    (fake_root / "cloudbuild.yaml").write_text("scripts/check_lgpd_compliance.py\n", encoding="utf-8")

    monkeypatch.setattr(check_lgpd_compliance, "ROOT", fake_root)
    monkeypatch.setattr(check_lgpd_compliance, "REQUIRED_FILES", [
        fake_root / "core" / "masker.py",
        fake_root / "docs" / "PRIVACIDADE.md",
        fake_root / "docs" / "TERMOS.md",
        fake_root / "Dockerfile",
        fake_root / "ata_worker" / "Dockerfile",
        fake_root / "proactive_worker" / "Dockerfile",
    ])
    monkeypatch.setattr(check_lgpd_compliance, "REQUIRED_SNIPPETS", {
        fake_root / "main.py": ["mask_pii(transcript)"],
        fake_root / "orchestrator.py": ["masked_text = mask_pii(text)"],
        fake_root / "cloudbuild-test.yaml": ["scripts/check_lgpd_compliance.py"],
        fake_root / "cloudbuild.yaml": ["scripts/check_lgpd_compliance.py"],
    })

    import io
    from contextlib import redirect_stdout
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        rc = check_lgpd_compliance.main()
    output = buffer.getvalue()
    assert rc == 1
    assert "missing required LGPD file" in output


def test_check_lgpd_compliance_reports_missing_snippet(tmp_path, monkeypatch):
    from scripts import check_lgpd_compliance

    fake_root = tmp_path
    (fake_root / "core").mkdir()
    (fake_root / "docs").mkdir()
    (fake_root / "ata_worker").mkdir()
    (fake_root / "proactive_worker").mkdir()
    (fake_root / "core" / "masker.py").write_text("# masker\n", encoding="utf-8")
    (fake_root / "docs" / "PRIVACIDADE.md").write_text("# privacidade\n", encoding="utf-8")
    (fake_root / "docs" / "TERMOS.md").write_text("# termos\n", encoding="utf-8")
    (fake_root / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    (fake_root / "ata_worker" / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    (fake_root / "proactive_worker" / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    (fake_root / "main.py").write_text("# sem masker\n", encoding="utf-8")
    (fake_root / "orchestrator.py").write_text("masked_text = mask_pii(text)\n", encoding="utf-8")
    (fake_root / "cloudbuild-test.yaml").write_text("scripts/check_lgpd_compliance.py\n", encoding="utf-8")
    (fake_root / "cloudbuild.yaml").write_text("scripts/check_lgpd_compliance.py\n", encoding="utf-8")

    monkeypatch.setattr(check_lgpd_compliance, "ROOT", fake_root)
    monkeypatch.setattr(check_lgpd_compliance, "REQUIRED_FILES", [
        fake_root / "core" / "masker.py",
        fake_root / "docs" / "PRIVACIDADE.md",
        fake_root / "docs" / "TERMOS.md",
        fake_root / "Dockerfile",
        fake_root / "ata_worker" / "Dockerfile",
        fake_root / "proactive_worker" / "Dockerfile",
    ])
    monkeypatch.setattr(check_lgpd_compliance, "REQUIRED_SNIPPETS", {
        fake_root / "main.py": ["mask_pii(transcript)"],
        fake_root / "orchestrator.py": ["masked_text = mask_pii(text)"],
        fake_root / "cloudbuild-test.yaml": ["scripts/check_lgpd_compliance.py"],
        fake_root / "cloudbuild.yaml": ["scripts/check_lgpd_compliance.py"],
    })

    import io
    from contextlib import redirect_stdout
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        rc = check_lgpd_compliance.main()
    output = buffer.getvalue()
    assert rc == 1
    assert "missing LGPD control" in output
