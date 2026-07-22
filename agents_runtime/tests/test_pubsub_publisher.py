import json
from unittest.mock import MagicMock, patch

import pytest

from core.pubsub_publisher import PubSubPublisher, get_publisher


def test_publisher_sends_raw_json_bytes_to_pubsub():
    client = MagicMock()
    future = MagicMock()
    future.result.return_value = "message-001"
    client.topic_path.side_effect = lambda project, topic: f"projects/{project}/topics/{topic}"
    client.publish.return_value = future
    publisher = PubSubPublisher(project="project-test", topic="topic-test")
    publisher._client = client

    result = publisher.publish({"text": "olá", "message_id": "MSG_001"})

    assert result == "message-001"
    published_data = client.publish.call_args.kwargs["data"]
    assert json.loads(published_data.decode("utf-8")) == {
        "text": "olá",
        "message_id": "MSG_001",
    }


def test_ensure_client_builds_sdk_client_when_available():
    sdk = MagicMock()
    client = MagicMock()
    sdk.PublisherClient.return_value = client
    publisher = PubSubPublisher(project="project-test")
    with patch("core.pubsub_publisher._pubsub_v1", sdk):
        assert publisher._ensure_client() is client
    sdk.PublisherClient.assert_called_once_with()


def test_ensure_client_rejects_missing_sdk():
    publisher = PubSubPublisher(project="project-test")
    with patch("core.pubsub_publisher._pubsub_v1", None):
        with pytest.raises(RuntimeError, match="pubsub_v1 not available"):
            publisher._ensure_client()


def test_publish_dlq_uses_configured_dlq_topic():
    publisher = PubSubPublisher(project="project-test", dlq_topic="topic-dlq")
    publisher.publish = MagicMock(return_value="dlq-message")
    result = publisher.publish_dlq({"error": "failed"}, attributes={"reason": "exception"})
    assert result == "dlq-message"
    publisher.publish.assert_called_once_with(
        {"error": "failed"},
        attributes={"reason": "exception"},
        topic="topic-dlq",
    )


def test_publish_propagates_sdk_error():
    client = MagicMock()
    future = MagicMock()
    future.result.side_effect = RuntimeError("publish failed")
    client.topic_path.return_value = "projects/project-test/topics/topic-test"
    client.publish.return_value = future
    publisher = PubSubPublisher(project="project-test", topic="topic-test")
    publisher._client = client
    with pytest.raises(RuntimeError, match="publish failed"):
        publisher.publish({"message_id": "MSG_FAIL"})


def test_get_publisher_returns_singleton():
    with patch("core.pubsub_publisher._default", None):
        first = get_publisher()
        second = get_publisher()
    assert first is second
