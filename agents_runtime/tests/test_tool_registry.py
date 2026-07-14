"""Tests for tool_registry."""
import pytest


class TestToolRegistry:
    def test_calendar_tools_registered(self):
        from tool_registry import TOOL_REGISTRY, list_tool_ids
        tools = list_tool_ids()
        assert "calendar.list_events" in tools
        assert "calendar.create_event" in tools
        assert "calendar.update_event" in tools
        assert "calendar.delete_event" in tools
        assert "calendar.freebusy" in tools

    def test_drive_tools_registered(self):
        from tool_registry import list_tool_ids
        tools = list_tool_ids()
        assert "drive.search_files" in tools
        assert "drive.upload_file" in tools
        assert "drive.list_folder" in tools
        assert "drive.create_folder" in tools
        assert "drive.find_omnichannel_atas_folder" in tools

    def test_gmail_tools_registered(self):
        from tool_registry import list_tool_ids
        tools = list_tool_ids()
        assert "gmail.search_messages" in tools
        assert "gmail.get_thread" in tools
        assert "gmail.send_message" in tools

    def test_web_tools_registered(self):
        from tool_registry import list_tool_ids
        tools = list_tool_ids()
        assert "web.search" in tools
        assert "web.fetch_url" in tools

    def test_nickname_tools_registered(self):
        from tool_registry import list_tool_ids
        tools = list_tool_ids()
        assert "nickname.lookup" in tools
        assert "nickname.set_consent" in tools
        assert "nickname.get_preferred_name" in tools

    def test_get_tool_returns_callable(self):
        from tool_registry import get_tool
        func = get_tool("calendar.list_events")
        assert callable(func)

    def test_get_tool_unknown_returns_none(self):
        from tool_registry import get_tool
        assert get_tool("nonexistent.tool") is None

    def test_get_tool_schema(self):
        from tool_registry import get_tool_schema
        schema = get_tool_schema("calendar.create_event")
        assert schema["name"] == "calendar.create_event"
        assert "description" in schema
        assert schema["parameters"]["type"] == "object"
        assert "start" in schema["parameters"]["required"]

    def test_get_tools_for_agent(self):
        from tool_registry import get_tools_for_agent
        tools = get_tools_for_agent(["calendar.list_events", "gmail.search_messages"])
        assert len(tools) == 2
        assert tools[0]["name"] == "calendar.list_events"

    def test_total_tools_count(self):
        from tool_registry import TOOL_REGISTRY
        assert len(TOOL_REGISTRY) >= 17