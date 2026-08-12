"""Test configuration: auto-load API keys from GCP Secret Manager (cached)."""
import os
import warnings

os.environ.setdefault("RAG_FOLDER_PERMISSIONS_ENFORCE", "false")

_KEYS_LOADED = False

def _load_keys_once():
    global _KEYS_LOADED
    if _KEYS_LOADED:
        return
    _KEYS_LOADED = True
    try:
        import subprocess
        for env_var, secret_name in [("DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY"), ("OPENAI_API_KEY", "OPENAI_API_KEY")]:
            if (os.getenv(env_var, "") or "").strip():
                continue
            result = subprocess.run(
                f'gcloud secrets versions access latest --secret={secret_name} --project=coherence-ominichannel-fs',
                shell=True, capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                os.environ[env_var] = result.stdout.strip()
    except Exception:
        pass

_load_keys_once()

try:
    from langchain_core._api.deprecation import LangChainPendingDeprecationWarning
    warnings.filterwarnings("ignore", category=LangChainPendingDeprecationWarning, message="The default value of `allowed_objects`")
except ImportError:
    pass

# Suprime UserWarning de DEPRECIACAO do SDK Firestore sobre ".where() posicional".
# O SDK ainda suporta; migracao para FieldFilter e backlog (BACKLOG 12/08/2026).
warnings.filterwarnings(
    "ignore",
    message="Detected filter using positional arguments. Prefer using the",
    category=UserWarning,
)
