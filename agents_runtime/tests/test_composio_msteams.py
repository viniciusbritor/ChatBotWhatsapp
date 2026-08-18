"""Tests Nível 1: Composio Direto - Microsoft Teams."""
import asyncio
from unittest.mock import MagicMock, patch


def composio_envelope(payload: dict) -> dict:
    return {
        "data": {
            "results": [
                {"response": {"successful": True, "data": payload}}
            ]
        }
    }


class TestMsteamsBasic:
    def test_send_message_imports(self):
        from tools.microsoft_teams_composio import send_message
        assert callable(send_message)

    def test_list_channels_imports(self):
        from tools.microsoft_teams_composio import list_channels
        assert callable(list_channels)

    def test_list_messages_imports(self):
        from tools.microsoft_teams_composio import list_messages
        assert callable(list_messages)


class TestMsteamsToolCalls:
    def test_send_message_returns_message_id(self):
        from tools.microsoft_teams_composio import send_message

        mock_data = {"id": "msg-123", "channelId": "channel-1"}
        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope(mock_data)

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(send_message(
                    channel_id="channel-1",
                    message="Ola turma!",
                    phone="5511966830020",
                ))

        assert mock_client.tools.execute.called
        assert mock_client.tools.execute.call_args.kwargs["slug"] == "MS_TEAMS_SEND_MESSAGE"
        assert result["id"] == "msg-123"

    def test_list_channels_returns_channels(self):
        from tools.microsoft_teams_composio import list_channels

        mock_data = {"value": [{"id": "channel-1", "displayName": "General"}, {"id": "channel-2", "displayName": "Dev"}]}
        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope(mock_data)

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(list_channels(phone="5511966830020"))

        assert mock_client.tools.execute.called
        assert mock_client.tools.execute.call_args.kwargs["slug"] == "MS_TEAMS_LIST_CHANNELS"
        assert len(result["value"]) == 2

    def test_list_messages_returns_messages(self):
        from tools.microsoft_teams_composio import list_messages

        mock_data = {"value": [{"id": "msg-1", "body": "Ola"}]}
        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope(mock_data)

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(list_messages(
                    channel_id="channel-1",
                    top=10,
                    phone="5511966830020",
                ))

        assert mock_client.tools.execute.called
        assert mock_client.tools.execute.call_args.kwargs["slug"] == "MS_TEAMS_LIST_MESSAGES"
        assert result["value"][0]["body"] == "Ola"


class TestMsteamsErrorHandling:
    def test_sdk_not_installed(self):
        from tools.microsoft_teams_composio import send_message

        with patch("composio.Composio", side_effect=ImportError()):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(send_message("channel-1", "Ola", phone="5511966830020"))
        assert result["error"] == "composio_sdk_missing"

    def test_api_error_envelope(self):
        from tools.microsoft_teams_composio import send_message

        with patch("composio.Composio", side_effect=Exception("Teams down")):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(send_message("channel-1", "Ola", phone="5511966830020"))
        assert "error" in result
        assert "Teams down" in result["error"]


class TestMsteamsTopParameter:
    def test_list_messages_clamps_top(self):
        from tools.microsoft_teams_composio import list_messages

        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope({"value": []})

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                asyncio.run(list_messages(channel_id="ch-1", top=10000, phone="5511966830020"))

        args = mock_client.tools.execute.call_args.kwargs["arguments"]
        assert args["top"] <= 999