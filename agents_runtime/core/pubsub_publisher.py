import base64
import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_pubsub_v1: Any = None
_google_api_error: Any = Exception
try:
    from google.cloud import pubsub_v1 as _pubsub_v1_import  # type: ignore[attr-defined]
    from google.api_core.exceptions import GoogleAPIError as _google_api_error_import

    _pubsub_v1 = _pubsub_v1_import
    _google_api_error = _google_api_error_import
except ImportError:
    pass


def _pubsub_available() -> bool:
    return _pubsub_v1 is not None


DEFAULT_PROJECT = os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")
DEFAULT_TOPIC = os.getenv("WHATSAPP_PUBSUB_TOPIC", "whatsapp-messages")
DEFAULT_DLQ_TOPIC = os.getenv("WHATSAPP_PUBSUB_DLQ", "whatsapp-messages-dlq")


class PubSubPublisher:
    def __init__(self, project: str = DEFAULT_PROJECT, topic: str = DEFAULT_TOPIC, dlq_topic: str = DEFAULT_DLQ_TOPIC):
        self._project = project
        self._topic = topic
        self._dlq_topic = dlq_topic
        self._client = None

    def _ensure_client(self):
        if not _pubsub_available():
            raise RuntimeError("pubsub_v1 not available in this environment")
        if self._client is None:
            self._client = _pubsub_v1.PublisherClient()
        return self._client

    def _topic_path(self, name: Optional[str] = None) -> str:
        client = self._ensure_client()
        return client.topic_path(self._project, name or self._topic)

    def _dlq_topic_path(self) -> str:
        return self._topic_path(self._dlq_topic)

    def publish(self, payload: Dict[str, Any], *, attributes: Optional[Dict[str, str]] = None, topic: Optional[str] = None) -> str:
        client = self._ensure_client()
        data = base64.b64encode(json.dumps(payload, default=str).encode("utf-8")).decode("ascii")
        future = client.publish(
            self._topic_path(topic),
            data=data.encode("ascii"),
            **(attributes or {}),
        )
        try:
            message_id = future.result(timeout=10)
        except _google_api_error as exc:
            logger.error("pubsub publish failed: %s", exc)
            raise
        return message_id

    def publish_dlq(self, payload: Dict[str, Any], *, attributes: Optional[Dict[str, str]] = None) -> str:
        return self.publish(payload, attributes=attributes, topic=self._dlq_topic)


_default: Optional[PubSubPublisher] = None


def get_publisher() -> PubSubPublisher:
    global _default
    if _default is None:
        _default = PubSubPublisher()
    return _default
