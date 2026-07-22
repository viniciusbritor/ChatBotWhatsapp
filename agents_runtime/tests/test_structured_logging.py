import json
import logging

from core.logging import JsonFormatter


def test_json_formatter_emits_brt_structured_log():
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="webhook_queued",
        args=(),
        exc_info=None,
    )
    record.event_name = "webhook_queued"
    record.request_id = "REQ_001"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["severity"] == "INFO"
    assert payload["message"] == "webhook_queued"
    assert payload["event_name"] == "webhook_queued"
    assert payload["request_id"] == "REQ_001"
    assert payload["timestamp"].endswith("-03:00")
