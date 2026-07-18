from unittest.mock import patch


class TestAgentInventory:
    def setup_method(self):
        from core.agent_status import _telemetry

        _telemetry.clear()

    def test_unverified_agent_is_not_healthy(self, monkeypatch):
        from core.agent_status import build_agent_inventory

        monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
        agents = [
            {
                "id": "jennifier",
                "name": "Jennifer",
                "role": "orchestrator",
                "model": "MiniMax-M3",
                "enabled": True,
                "instances": ["jennifer"],
                "tools": [],
            }
        ]
        with patch("agent_loader.list_agents", return_value=agents):
            with patch("agent_loader.get_cache_stats", return_value={"agents": 1}):
                with patch("agent_loader.get_user", return_value=None):
                    with patch("agent_loader.get_config", return_value=None):
                        inventory = build_agent_inventory()

        assert inventory["agents"][0]["status"] == "unverified"
        assert inventory["counts"]["healthy"] == 0
        assert inventory["counts"]["routable"] == 1

    def test_recent_success_marks_agent_healthy(self, monkeypatch):
        from core.agent_status import build_agent_inventory, record_agent_success, start_agent_execution

        monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
        started = start_agent_execution("jennifier")
        record_agent_success("jennifier", started, "MiniMax-M3", "minimax")
        agents = [
            {
                "id": "jennifier",
                "name": "Jennifer",
                "role": "orchestrator",
                "model": "MiniMax-M3",
                "enabled": True,
                "instances": ["jennifer"],
                "tools": [],
            }
        ]
        with patch("agent_loader.list_agents", return_value=agents):
            with patch("agent_loader.get_cache_stats", return_value={"agents": 1}):
                with patch("agent_loader.get_user", return_value=None):
                    with patch("agent_loader.get_config", return_value=None):
                        inventory = build_agent_inventory()

        assert inventory["agents"][0]["status"] == "healthy"
        assert inventory["counts"]["healthy"] == 1

    def test_missing_tool_blocks_operational_status(self, monkeypatch):
        from core.agent_status import build_agent_inventory

        monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
        agents = [
            {
                "id": "manager-web",
                "name": "Web",
                "role": "manager",
                "model": "MiniMax-M3",
                "enabled": True,
                "instances": ["jennifer"],
                "tools": ["missing.tool"],
            }
        ]
        with patch("agent_loader.list_agents", return_value=agents):
            with patch("agent_loader.get_cache_stats", return_value={}):
                with patch("agent_loader.get_user", return_value=None):
                    with patch("agent_loader.get_config", return_value=None):
                        with patch("tool_registry.list_tool_ids", return_value=[]):
                            inventory = build_agent_inventory()

        assert inventory["agents"][0]["status"] == "tools_missing"
        assert inventory["agents"][0]["missing_tools"] == ["missing.tool"]

    def test_google_agent_distinguishes_user_setup(self, monkeypatch):
        from core.agent_status import build_agent_inventory

        monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
        agents = [
            {
                "id": "manager-calendar",
                "name": "Calendar",
                "role": "manager",
                "model": "MiniMax-M3",
                "enabled": True,
                "instances": ["jennifer"],
                "tools": ["calendar.list_events"],
            }
        ]
        with patch("agent_loader.list_agents", return_value=agents):
            with patch("agent_loader.get_cache_stats", return_value={}):
                with patch("agent_loader.get_user", return_value={}):
                    with patch("agent_loader.get_config", return_value=None):
                        inventory = build_agent_inventory(phone="5511999999999")

        assert inventory["agents"][0]["platform_ready"] is True
        assert inventory["agents"][0]["user_ready"] is False
        assert inventory["agents"][0]["status"] == "user_setup_required"

    def test_inventory_reply_explains_counts(self):
        from core.agent_status import format_inventory_reply

        inventory = {
            "counts": {
                "configured": 15,
                "routable": 10,
                "healthy": 2,
                "in_flight": 1,
                "unverified": 8,
            },
            "agents": [
                {"name": "Jennifer", "status": "healthy"},
                {"name": "Web", "status": "provider_unavailable"},
            ],
        }
        reply = format_inventory_reply(inventory)

        assert "15 agentes cadastrados" in reply
        assert "10 roteaveis" in reply
        assert "Em execucao agora: 1" in reply
