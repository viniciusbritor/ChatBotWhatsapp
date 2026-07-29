"""Tests for observability hooks (Fase 0 / F4d.12)."""
import os
import time

import pytest

from core import observability
from core.observability import (
    LatencyTracker,
    attach_to_metadata,
    current_tracker,
    new_tracker,
    set_current_tracker,
)


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset thread-local and env var between tests."""
    observability.reset()
    set_current_tracker(None)
    yield
    observability.reset()
    set_current_tracker(None)


def test_disabled_tracker_is_noop():
    os.environ["OBSERVABILITY_ENABLED"] = "false"
    observability.reset()
    tracker = new_tracker()
    with tracker.stage("x"):
        time.sleep(0.01)
    assert tracker.stages() == []
    assert tracker.costs() == {}
    assert tracker.total_ms() == 0
    assert tracker.breakdown() == {}


def test_enabled_tracker_records_stage_and_cost():
    os.environ["OBSERVABILITY_ENABLED"] = "true"
    observability.reset()
    tracker = new_tracker()
    with tracker.stage("intent", sample_meta="x"):
        time.sleep(0.01)
    tracker.add_cost("deepseek_input_tokens", 1200)
    tracker.add_cost("deepseek_input_tokens", 300)
    breakdown = tracker.breakdown()
    assert breakdown["total_ms"] >= 10
    assert len(breakdown["stages"]) == 1
    assert breakdown["stages"][0]["stage"] == "intent"
    assert breakdown["stages"][0]["meta"]["sample_meta"] == "x"
    assert breakdown["costs"]["deepseek_input_tokens"] == 1500


def test_thread_local_returns_null_when_unset():
    assert current_tracker() is not None
    assert current_tracker()._enabled is False


def test_set_current_tracker_makes_it_visible():
    tracker = LatencyTracker(enabled=True)
    set_current_tracker(tracker)
    assert current_tracker() is tracker
    with current_tracker().stage("from_outer"):
        pass
    assert len(current_tracker().stages()) == 1


def test_attach_to_metadata_merges_breakdown():
    os.environ["OBSERVABILITY_ENABLED"] = "true"
    observability.reset()
    tracker = new_tracker()
    tracker.add_cost("deepseek_input_tokens", 100)
    md: dict = {"agent_id": "manager-email"}
    attach_to_metadata(md, tracker)
    assert "latency_breakdown" in md
    assert md["agent_id"] == "manager-email"
    assert md["latency_breakdown"]["costs"]["deepseek_input_tokens"] == 100


def test_disabled_attach_is_noop():
    os.environ["OBSERVABILITY_ENABLED"] = "false"
    observability.reset()
    tracker = new_tracker()
    md: dict = {"agent_id": "x"}
    attach_to_metadata(md, tracker)
    assert "latency_breakdown" not in md


def test_multiple_stages_order_preserved():
    os.environ["OBSERVABILITY_ENABLED"] = "true"
    observability.reset()
    tracker = new_tracker()
    with tracker.stage("a"):
        pass
    with tracker.stage("b"):
        pass
    with tracker.stage("c"):
        pass
    breakdown = tracker.breakdown()
    stages = [s["stage"] for s in breakdown["stages"]]
    assert stages == ["a", "b", "c"]
    orders = [s["order"] for s in breakdown["stages"]]
    assert orders == [0, 1, 2]