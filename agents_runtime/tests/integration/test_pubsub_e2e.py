import json
import os
import re
import uuid

import pytest

if os.getenv("RUN_PUBSUB_E2E") != "1":
    pytest.skip("RUN_PUBSUB_E2E is not enabled", allow_module_level=True)

pubsub_v1 = pytest.importorskip("google.cloud.pubsub_v1")

from core.pubsub_publisher import PubSubPublisher  # noqa: E402


pytestmark = pytest.mark.integration


def test_real_pubsub_publish_pull_roundtrip():
    project = os.getenv("PUBSUB_E2E_PROJECT", "")
    if not project:
        pytest.fail("PUBSUB_E2E_PROJECT is required")
    run_id = re.sub(r"[^a-z0-9-]", "-", os.getenv("PUBSUB_E2E_RUN_ID", uuid.uuid4().hex).lower())[:32]
    topic_name = f"agents-runtime-ci-{run_id}"
    subscription_name = f"{topic_name}-sub"
    publisher_client = pubsub_v1.PublisherClient()
    subscriber_client = pubsub_v1.SubscriberClient()
    topic_path = publisher_client.topic_path(project, topic_name)
    subscription_path = subscriber_client.subscription_path(project, subscription_name)

    try:
        publisher_client.create_topic(request={"name": topic_path})
        subscriber_client.create_subscription(
            request={"name": subscription_path, "topic": topic_path}
        )
        publisher = PubSubPublisher(project=project, topic=topic_name)
        payload = {
            "message_id": f"E2E-{run_id}",
            "instance": "jennifer",
            "phone": "0000000000000",
            "text": "pubsub e2e",
        }
        publisher.publish(payload, attributes={"source": "cloud-build-e2e"})
        response = subscriber_client.pull(
            request={"subscription": subscription_path, "max_messages": 1},
            timeout=20,
        )
        assert len(response.received_messages) == 1
        received = response.received_messages[0]
        assert json.loads(received.message.data.decode("utf-8")) == payload
        assert received.message.attributes["source"] == "cloud-build-e2e"
        subscriber_client.acknowledge(
            request={
                "subscription": subscription_path,
                "ack_ids": [received.ack_id],
            }
        )
    finally:
        try:
            subscriber_client.delete_subscription(request={"subscription": subscription_path})
        except Exception:
            pass
        try:
            publisher_client.delete_topic(request={"topic": topic_path})
        except Exception:
            pass
