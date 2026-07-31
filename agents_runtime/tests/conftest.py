"""Test configuration: filter third-party warnings that are out of our control."""
import os
import warnings

# Default off do TASK B folder_permissions enforcement para nao quebrar
# testes existentes que nao se importam com lock-down. Testes que validam o
# enforcement (tests/test_folder_permissions_enforcement.py) re-ligam
# explicitamente via monkeypatch ou env var local.
os.environ.setdefault("RAG_FOLDER_PERMISSIONS_ENFORCE", "false")

try:
    from langchain_core._api.deprecation import LangChainPendingDeprecationWarning
    warnings.filterwarnings(
        "ignore",
        category=LangChainPendingDeprecationWarning,
        message="The default value of `allowed_objects`",
    )
except ImportError:
    pass