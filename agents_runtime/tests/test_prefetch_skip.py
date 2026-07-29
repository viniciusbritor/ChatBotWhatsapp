"""Tests for prefetch skip when agent already exposes a tool (F4d.9).

The orchestrator should NOT block on the 8s prefetch timeout when the
resolved specialist agent already has tools that fetch fresh data
(gmail/calendar/drive). This saves latency on personal-intent queries.
"""
from unittest.mock import patch

from orchestrator import _agent_has_tool


def test_agent_has_tool_returns_true_for_known_prefix():
    with patch(
        "orchestrator.get_agent",
        return_value={"tools": ["gmail.search_messages", "gmail.get_thread"]},
    ):
        assert _agent_has_tool("manager-email", "gmail.") is True


def test_agent_has_tool_returns_false_when_no_match():
    with patch(
        "orchestrator.get_agent",
        return_value={"tools": ["knowledge.retrieve"]},
    ):
        assert _agent_has_tool("agent-knowledge-retriever", "gmail.") is False


def test_agent_has_tool_returns_false_when_agent_missing():
    with patch("orchestrator.get_agent", return_value=None):
        assert _agent_has_tool("ghost-agent", "gmail.") is False


def test_agent_has_tool_handles_empty_tools():
    with patch("orchestrator.get_agent", return_value={"tools": []}):
        assert _agent_has_tool("manager-email", "calendar.") is False


def test_agent_has_tool_handles_empty_inputs():
    assert _agent_has_tool("", "gmail.") is False
    assert _agent_has_tool("manager-email", "") is False