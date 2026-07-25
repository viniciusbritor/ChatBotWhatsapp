from unittest.mock import patch


class TestAgentInventory:
    def setup_method(self):
        from core.agent_status import _telemetry

        _telemetry.clear()

    def test_unverified_agent_is_not_healthy(self, monkeypatch):
        from core.agent_status import build_agent_inventory

        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        agents = [
            {
                "id": "jennifier",
                "name": "Jennifer",
                "role": "orchestrator",
                "model": "deepseek-v4-flash",
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

        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        started = start_agent_execution("jennifier")
        record_agent_success("jennifier", started, "deepseek-v4-flash", "deepseek")
        agents = [
            {
                "id": "jennifier",
                "name": "Jennifer",
                "role": "orchestrator",
                "model": "deepseek-v4-flash",
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

        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        agents = [
            {
                "id": "manager-web",
                "name": "Web",
                "role": "manager",
                "model": "deepseek-v4-flash",
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

    def test_provider_ready_uses_llm_cascade(self, monkeypatch):
        from core import agent_status

        class FakeLLM:
            deepseek_key = None

            def is_available(self) -> bool:
                return False

            def __init__(self):
                pass

        monkeypatch.setattr(agent_status, "_LLMProvider", FakeLLM)
        with patch("core.rag._validate_embedding", return_value=[0.0] * 1536):
            with patch("core.secrets.get_secret", return_value=None):
                assert agent_status._model_provider_ready("deepseek-v4-flash") is False
                assert agent_status._model_provider_ready("anything-else") is False
                assert agent_status._model_provider_ready("") is False

        class FakeLLMAvailable(FakeLLM):
            def is_available(self) -> bool:
                return True

        monkeypatch.setattr(agent_status, "_LLMProvider", FakeLLMAvailable)
        assert agent_status._model_provider_ready("deepseek-v4-flash") is True
        assert agent_status._model_provider_ready("anything-else") is True

    def test_google_agent_distinguishes_user_setup(self, monkeypatch):
        from core.agent_status import build_agent_inventory

        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        agents = [
            {
                "id": "manager-calendar",
                "name": "Calendar",
                "role": "manager",
                "model": "deepseek-v4-flash",
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
