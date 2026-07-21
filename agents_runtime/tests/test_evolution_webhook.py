"""Tests for core.evolution_webhook.extract_envelope."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("EVO_BASE_URL", "https://evolution.coherenceai.com.br")


from core.evolution_webhook import extract_envelope, extract_message_id  # noqa: E402


SAMPLE_TEXT_PAYLOAD = {
    "event": "MESSAGES_UPSERT",
    "instance": "jennifer",
    "data": {
        "key": {
            "remoteJid": "5511966830020@s.whatsapp.net",
            "fromMe": False,
            "id": "TEST_MSG_001",
        },
        "pushName": "Vinicius",
        "message": {"conversation": "Oi Jennifer, tudo bem?"},
        "messageType": "conversation",
    },
}


SAMPLE_EXTENDED_PAYLOAD = {
    "event": "MESSAGES_UPSERT",
    "instance": "jennifer",
    "data": {
        "key": {
            "remoteJid": "5511966830020@s.whatsapp.net",
            "fromMe": False,
            "id": "EXT_MSG_002",
        },
        "pushName": "Vinicius",
        "message": {
            "extendedTextMessage": {"text": "Marca reuniao amanha 15h"},
        },
        "messageType": "extendedTextMessage",
    },
}


SAMPLE_AUDIO_PAYLOAD = {
    "event": "MESSAGES_UPSERT",
    "instance": "jennifer",
    "data": {
        "key": {
            "remoteJid": "5511966830020@s.whatsapp.net",
            "fromMe": False,
            "id": "AUDIO_MSG_003",
        },
        "pushName": "Vinicius",
        "message": {
            "audioMessage": {
                "mimetype": "audio/ogg; codecs=opus",
                "ptt": True,
                "fileLength": 12345,
            }
        },
        "messageType": "audioMessage",
    },
}


SAMPLE_GROUP_PAYLOAD = {
    "event": "MESSAGES_UPSERT",
    "instance": "jennifer",
    "data": {
        "key": {
            "remoteJid": "120363@g.us",
            "fromMe": False,
            "id": "GROUP_MSG_004",
            "participant": "5511966830020@s.whatsapp.net",
        },
        "pushName": "Vini",
        "message": {"conversation": "Bom dia grupo"},
        "messageType": "conversation",
    },
}


def test_extract_text_conversation():
    envelope = extract_envelope(SAMPLE_TEXT_PAYLOAD)
    assert envelope is not None
    assert envelope["phone"] == "5511966830020"
    assert envelope["text"] == "Oi Jennifer, tudo bem?"
    assert envelope["sender_name"] == "Vinicius"
    assert envelope["message_id"] == "TEST_MSG_001"
    assert envelope["remote_jid"] == "5511966830020@s.whatsapp.net"
    assert envelope["instance"] == "jennifer"
    assert envelope["request_id"] == "TEST_MSG_001"
    assert envelope["extra"]["is_group"] is False
    assert envelope["extra"].get("has_audio") in (None, False)


def test_extract_extended_text():
    envelope = extract_envelope(SAMPLE_EXTENDED_PAYLOAD)
    assert envelope is not None
    assert envelope["text"] == "Marca reuniao amanha 15h"
    assert envelope["message_id"] == "EXT_MSG_002"


def test_extract_audio_message():
    envelope = extract_envelope(SAMPLE_AUDIO_PAYLOAD)
    assert envelope is not None
    assert envelope["text"] == "[audio]"
    assert envelope["extra"]["has_audio"] is True
    assert envelope["extra"]["audio_mimetype"] == "audio/ogg; codecs=opus"
    assert envelope["extra"]["audio_ptt"] is True
    assert "evolution.coherenceai.com.br" in envelope["extra"]["audio_url"]
    assert "AUDIO_MSG_003" in envelope["extra"]["audio_url"]


def test_extract_group_message():
    envelope = extract_envelope(SAMPLE_GROUP_PAYLOAD)
    assert envelope is not None
    assert envelope["extra"]["is_group"] is True
    assert envelope["phone"] == "120363"
    assert envelope["remote_jid"] == "120363@g.us"
    assert envelope["text"] == "Bom dia grupo"


def test_filter_fromMe():
    payload = {**SAMPLE_TEXT_PAYLOAD, "data": {**SAMPLE_TEXT_PAYLOAD["data"], "key": {**SAMPLE_TEXT_PAYLOAD["data"]["key"], "fromMe": True}}}
    assert extract_envelope(payload) is None


def test_filter_broadcast():
    payload = {
        "event": "MESSAGES_UPSERT",
        "instance": "jennifer",
        "data": {
            "key": {"remoteJid": "status@broadcast", "fromMe": False, "id": "BC_001"},
            "message": {"conversation": "story"},
        },
    }
    assert extract_envelope(payload) is None


def test_filter_non_message_event():
    payload = {"event": "CONNECTION_UPDATE", "instance": "jennifer", "data": {"state": "open"}}
    assert extract_envelope(payload) is None


def test_filter_missing_instance():
    payload = {**SAMPLE_TEXT_PAYLOAD, "instance": ""}
    assert extract_envelope(payload) is None


def test_filter_missing_phone():
    payload = {
        "event": "MESSAGES_UPSERT",
        "instance": "jennifer",
        "data": {
            "key": {"remoteJid": "", "fromMe": False, "id": "NO_PHONE"},
            "message": {"conversation": "oi"},
        },
    }
    assert extract_envelope(payload) is None


def test_filter_image_without_text():
    payload = {
        "event": "MESSAGES_UPSERT",
        "instance": "jennifer",
        "data": {
            "key": {"remoteJid": "5511966830020@s.whatsapp.net", "fromMe": False, "id": "IMG_001"},
            "message": {"imageMessage": {"mimetype": "image/jpeg", "fileLength": 9999}},
        },
    }
    assert extract_envelope(payload) is None


def test_lowercase_event_accepted():
    payload = {**SAMPLE_TEXT_PAYLOAD, "event": "messages.upsert"}
    envelope = extract_envelope(payload)
    assert envelope is not None
    assert envelope["text"] == "Oi Jennifer, tudo bem?"


def test_invalid_payload_returns_none():
    assert extract_envelope(None) is None
    assert extract_envelope("string") is None
    assert extract_envelope(42) is None
    assert extract_envelope({}) is None


def test_missing_message_id_generates_request_id():
    payload = {
        "event": "MESSAGES_UPSERT",
        "instance": "jennifer",
        "data": {
            "key": {"remoteJid": "5511966830020@s.whatsapp.net", "fromMe": False},
            "message": {"conversation": "sem id"},
        },
    }
    envelope = extract_envelope(payload)
    assert envelope is not None
    assert envelope["message_id"] == ""
    assert envelope["request_id"].startswith("webhook-")


def test_extract_message_id_helper():
    assert extract_message_id(SAMPLE_TEXT_PAYLOAD) == "TEST_MSG_001"
    assert extract_message_id({}) is None
    assert extract_message_id({"data": {}}) is None


def test_audio_url_uses_evolution_base_url(monkeypatch):
    monkeypatch.setattr(
        "core.evolution_webhook.EVOLUTION_BASE_URL",
        "https://custom.evo.example.com/",
    )
    payload = {**SAMPLE_AUDIO_PAYLOAD}
    envelope = extract_envelope(payload)
    assert envelope is not None
    assert envelope["extra"]["audio_url"].startswith("https://custom.evo.example.com/chat/getMedia/")
