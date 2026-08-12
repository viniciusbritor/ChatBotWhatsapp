import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(os.environ.get("REPO_ROOT", ROOT.parent)).resolve()
REQUIRED_FILES = [
    ROOT / "core" / "masker.py",
    REPO_ROOT / "docs" / "PRIVACIDADE.md",
    REPO_ROOT / "docs" / "TERMOS.md",
    ROOT / "Dockerfile",
    ROOT / "ata_worker" / "Dockerfile",
    ROOT / "proactive_worker" / "Dockerfile",
]
REQUIRED_SNIPPETS = {
    ROOT / "core" / "audio_pipeline.py": ["mask_pii(transcript)"],
    ROOT / "orchestrator.py": ["masked_text = mask_pii(text)"],
    ROOT / "cloudbuild-test.yaml": ["scripts/check_lgpd_compliance.py"],
}


def main() -> int:
    errors = []
    for path in REQUIRED_FILES:
        if not path.is_file():
            try:
                display = path.relative_to(ROOT)
            except ValueError:
                display = path.relative_to(REPO_ROOT)
            errors.append(f"missing required LGPD file: {display}")
    for path, snippets in REQUIRED_SNIPPETS.items():
        if not path.is_file():
            try:
                display = path.relative_to(ROOT)
            except ValueError:
                display = path.relative_to(REPO_ROOT)
            errors.append(f"missing required file: {display}")
            continue
        content = path.read_text(encoding="utf-8")
        try:
            display = path.relative_to(ROOT)
        except ValueError:
            display = path.relative_to(REPO_ROOT)
        for snippet in snippets:
            if snippet not in content:
                errors.append(f"missing LGPD control in {display}: {snippet}")
    if errors:
        for error in errors:
            print(error)
        return 1
    print("LGPD compliance checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
