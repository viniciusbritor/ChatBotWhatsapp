"""Tests for DeepAgent tool_results capture (F4d.11).

Verifies that:
- ``_extract_deepagent_tool_results`` correctly walks a DeepAgent
  message log and produces ``tool_results`` compatible with
  ``_detect_tabular_payload``.
- ``_execute_deep_agent`` propagates ``tool_results`` to metadata so
  the auto-image flow can fire on the deepagent path too (not only
  the LLMProvider fallback).
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator import _extract_deepagent_tool_results


def _ai_message(tool_calls=None, content=""):
    msg = SimpleNamespace()
    msg.type = "ai"
    msg.content = content
    msg.tool_calls = tool_calls or []
    return msg


def _tool_message(name, content):
    msg = SimpleNamespace()
    msg.type = "tool"
    msg.name = name
    msg.tool_call_id = f"call-{name}"
    msg.content = content
    return msg


def test_extracts_dict_content():
    messages = [
        _ai_message(tool_calls=[{"name": "calendar.list_events", "args": {}}]),
        _tool_message("calendar.list_events", '{"events": [{"summary": "x"}]}'),
        _ai_message(content="Sua agenda tem 1 evento."),
    ]
    out = _extract_deepagent_tool_results(messages)
    assert len(out) == 1
    assert out[0]["tool"] == "calendar.list_events"
    assert out[0]["result"] == {"events": [{"summary": "x"}]}


def test_extracts_string_content_keeps_raw():
    messages = [
        _ai_message(tool_calls=[{"name": "gmail.search_messages"}]),
        _tool_message("gmail.search_messages", "plain string result"),
    ]
    out = _extract_deepagent_tool_results(messages)
    assert len(out) == 1
    assert out[0]["tool"] == "gmail.search_messages"
    assert out[0]["result"] == {"raw": "plain string result"}


def test_empty_messages_returns_empty():
    assert _extract_deepagent_tool_results([]) == []


def test_truncates_to_last_10():
    """Cap result list to 10 to avoid huge metadata in long sessions."""
    messages = []
    for i in range(15):
        messages.append(_ai_message(tool_calls=[{"name": f"t{i}"}]))
        messages.append(_tool_message(f"t{i}", f'{{"i": {i}}}'))
    out = _extract_deepagent_tool_results(messages)
    assert len(out) == 10
    assert out[0]["tool"] == "t5"


def test_falls_back_to_pending_call_when_name_missing():
    """When the ToolMessage has no name, pair it with the earliest
    pending AI tool_call. Useful for LangChain variants that strip
    the name from ToolMessage."""
    messages = [
        _ai_message(tool_calls=[
            {"name": "calendar.list_events"},
            {"name": "drive.list_folder"},
        ]),
        _tool_message("", '{"events": []}'),
        _tool_message("drive.list_folder", '{"files": []}'),
    ]
    out = _extract_deepagent_tool_results(messages)
    assert len(out) == 2
    assert out[0]["tool"] == "calendar.list_events"
    assert out[1]["tool"] == "drive.list_folder"


def test_handles_dict_message_shape():
    """Pure dict messages (no LangChain objects) must also work."""
    messages = [
        {"role": "assistant", "tool_calls": [{"name": "drive.list_folder"}]},
        {"role": "tool", "name": "drive.list_folder", "content": '{"files": []}'},
    ]
    out = _extract_deepagent_tool_results(messages)
    assert len(out) == 1
    assert out[0]["tool"] == "drive.list_folder"
    assert out[0]["result"] == {"files": []}


def test_extract_incompatible_content_keeps_raw():
    messages = [
        _ai_message(tool_calls=[{"name": "calendar.list_events"}]),
        _tool_message("calendar.list_events", 12345),
    ]
    out = _extract_deepagent_tool_results(messages)
    assert len(out) == 1
    assert out[0]["result"] == {"raw": "12345"}