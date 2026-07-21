"""Tests for tool_registry."""


class TestToolRegistry:
    def test_calendar_tools_registered(self):
        from tool_registry import list_tool_ids
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
        assert "phone" not in schema["parameters"]["properties"]

    def test_non_user_scoped_schema_is_unchanged(self):
        from tool_registry import get_tool_schema

        schema = get_tool_schema("web.search")
        assert "query" in schema["parameters"]["properties"]

    def test_get_tools_for_agent(self):
        from tool_registry import get_tools_for_agent
        tools = get_tools_for_agent(["calendar.list_events", "gmail.search_messages"])
        assert len(tools) == 2
        assert tools[0]["name"] == "calendar.list_events"

    def test_total_tools_count(self):
        from tool_registry import TOOL_REGISTRY
        assert len(TOOL_REGISTRY) >= 17

    def test_group_info_tool_registered(self):
        from tool_registry import get_tool

        assert callable(get_tool("group.get_info"))

    def test_default_agent_tools_are_executable(self):
        from scripts.seed_initial_data import DEFAULT_AGENTS
        from tool_registry import list_tool_ids

        registered = set(list_tool_ids())
        missing = {
            tool
            for agent in DEFAULT_AGENTS
            if agent.get("enabled", True)
            for tool in agent.get("tools", [])
            if tool not in registered
        }
        assert missing == set()
