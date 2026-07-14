"""Secrets resolver with cascading fallback.

Priority: env var -> GCP Secret Manager -> default.
Local dev: env var only.
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Resolve a secret from multiple sources.

    Order:
    1. Environment variable (always checked first)
    2. GCP Secret Manager (if GCP_PROJECT is set and not in emulator mode)
    3. Default value

    Args:
        key: Secret name (e.g., "DEEPSEEK_API_KEY")
        default: Fallback value if secret not found

    Returns:
        Secret value or default.
    """
    env_value = os.getenv(key)
    if env_value:
        return env_value

    gcp_project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
    emulator_host = os.getenv("FIRESTORE_EMULATOR_HOST")

    if gcp_project and not emulator_host:
        try:
            from google.cloud import secretmanager

            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{gcp_project}/secrets/{key}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8").strip().lstrip("\ufeff")
        except Exception as e:
            logger.warning(f"Could not fetch secret {key} from Secret Manager: {e}")

    if default is not None:
        return default

    logger.debug(f"Secret {key} not found, returning None")
    return None