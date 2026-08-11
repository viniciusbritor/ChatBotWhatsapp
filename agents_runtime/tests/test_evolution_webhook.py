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
        "message": {
            "extendedTextMessage": {
                "text": "Bom dia grupo",
                "contextInfo": {"mentionedJid": ["5511966830020@s.whatsapp.net"]},
            }
        },
        "messageType": "extendedTextMessage",
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
    assert envelope["instance"] in ("Jennifer", "jennifer")
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
    with _patch_bot_jid():
        envelope = extract_envelope(SAMPLE_GROUP_PAYLOAD)
    assert envelope is not None
    assert envelope["extra"]["is_group"] is True
    # Patch 01/08/2026: phone em grupo vem do key.participant, nao do remoteJid.
    assert envelope["phone"] == "5511966830020"
    assert envelope["remote_jid"] == "120363@g.us"
    assert envelope["text"] == "Bom dia grupo"
    assert envelope["extra"]["phone_source"] == "participant"


def test_extract_group_phone_uses_participant_not_remotejid():
    """Regression: phone em grupo deve vir do participant, nao do group_id.

    Antes do fix (01/08/2026), o codigo pegava `remoteJid.split('@')[0]`
    que em grupo retornava o group_id ('120363') em vez do user_phone.
    Consequencia: _owner_hash ficava errado, RAG pessoal nunca encontrava,
    e _is_user_member retornava False para todos.
    """
    with _patch_bot_jid():
        envelope = extract_envelope(SAMPLE_GROUP_PAYLOAD)
    assert envelope is not None
    # phone do user, NAO do grupo
    assert envelope["phone"] == "5511966830020"
    assert envelope["phone"] != "120363"
    # group_jid preservado em remote_jid (nao foi perdido)
    assert envelope["remote_jid"].endswith("@g.us")


def test_extract_group_falls_back_to_remotejid_when_participant_missing():
    """Se a Evolution API nao mandar `participant` (improvavel em v2.3.7),
    faz fallback para `remoteJid` (comportamento antigo, evita None).
    """
    payload = {
        "event": "MESSAGES_UPSERT",
        "instance": "jennifer",
        "data": {
            "key": {
                "remoteJid": "120363@g.us",
                "fromMe": False,
                "id": "NO_PARTICIPANT_001",
                # sem participant
            },
            "pushName": "Vini",
            "message": {
                "extendedTextMessage": {
                    "text": "sem participant",
                    "contextInfo": {"mentionedJid": [BOT_JID]},
                }
            },
            "messageType": "extendedTextMessage",
        },
    }
    with _patch_bot_jid():
        envelope = extract_envelope(payload)
    assert envelope is not None
    # Fallback: usa remoteJid (group_id) em vez de quebrar.
    assert envelope["phone"] == "120363"
    assert envelope["extra"]["phone_source"] == "remote_jid"


def test_extract_private_phone_source_is_remotejid():
    """Em privado (sem @g.us), phone vem sempre de remoteJid."""
    envelope = extract_envelope(SAMPLE_TEXT_PAYLOAD)
    assert envelope is not None
    assert envelope["extra"]["phone_source"] == "remote_jid"
    assert envelope["phone"] == "5511966830020"


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


def test_messages_update_event_accepted():
    """Evolution dispatches messages.update in addition to MESSAGES_UPSERT."""
    payload = {**SAMPLE_TEXT_PAYLOAD, "event": "messages.update"}
    envelope = extract_envelope(payload)
    assert envelope is not None
    assert envelope["text"] == "Oi Jennifer, tudo bem?"


def test_invalid_payload_returns_none():
    assert extract_envelope(None) is None
    assert extract_envelope("string") is None
    assert extract_envelope(42) is None
    assert extract_envelope({}) is None


def test_missing_message_id_generates_deterministic_id():
    payload = {
        "event": "MESSAGES_UPSERT",
        "instance": "jennifer",
        "data": {
            "key": {"remoteJid": "5511966830020@s.whatsapp.net", "fromMe": False},
            "message": {"conversation": "sem id"},
            "messageTimestamp": 1700000000,
        },
    }
    envelope = extract_envelope(payload)
    assert envelope is not None
    assert envelope["message_id"]
    assert envelope["message_id"] == envelope["request_id"]
    assert not envelope["message_id"].startswith("webhook-")
    # Deterministic: same input -> same id
    second = extract_envelope(payload)
    assert second["message_id"] == envelope["message_id"]


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


SAMPLE_DOCUMENT_PAYLOAD_BASE64 = {
    "event": "MESSAGES_UPSERT",
    "instance": "jennifer",
    "data": {
        "key": {
            "remoteJid": "5511966830020@s.whatsapp.net",
            "fromMe": False,
            "id": "DOC_MSG_005",
        },
        "pushName": "Vinicius",
        "message": {
            "documentMessage": {
                "mimetype": "application/pdf",
                "fileName": "contrato.pdf",
                "fileLength": 123456,
                "caption": "Guarde na sua base de conhecimento",
                "base64": "JVBERi0xLjQKJeLjz9MK",
            }
        },
        "messageType": "documentMessage",
    },
}


SAMPLE_DOCUMENT_PAYLOAD_WITHOUT_BASE64 = {
    "event": "MESSAGES_UPSERT",
    "instance": "jennifer",
    "data": {
        "key": {
            "remoteJid": "5511966830020@s.whatsapp.net",
            "fromMe": False,
            "id": "DOC_MSG_006",
        },
        "pushName": "Vinicius",
        "message": {
            "documentMessage": {
                "mimetype": "application/pdf",
                "fileName": "relatorio.pdf",
                "fileLength": 99999,
                "caption": "memorize esse relatorio",
            }
        },
        "messageType": "documentMessage",
    },
}


SAMPLE_GROUP_DOCUMENT_PAYLOAD = {
    "event": "MESSAGES_UPSERT",
    "instance": "jennifer",
    "data": {
        "key": {
            "remoteJid": "120363@g.us",
            "fromMe": False,
            "id": "GROUP_DOC_007",
            "participant": "5511966830020@s.whatsapp.net",
        },
        "pushName": "Vini",
        "message": {
            "documentMessage": {
                "mimetype": "application/pdf",
                "fileName": "ata_reuniao.pdf",
                "fileLength": 5000,
                "caption": "@Jennifer salva essa ata",
                "contextInfo": {"mentionedJid": ["5511966830020@s.whatsapp.net"]},
                "base64": "JVBERi0xLjQK",
            }
        },
        "messageType": "documentMessage",
    },
}


def test_extract_document_with_base64():
    envelope = extract_envelope(SAMPLE_DOCUMENT_PAYLOAD_BASE64)
    assert envelope is not None
    assert envelope["text"] == "Guarde na sua base de conhecimento"
    assert envelope["extra"]["has_document"] is True
    assert envelope["extra"]["doc_mimetype"] == "application/pdf"
    assert envelope["extra"]["doc_file_name"] == "contrato.pdf"
    assert envelope["extra"]["doc_file_length"] == 123456
    assert envelope["extra"]["doc_base64"] == "JVBERi0xLjQKJeLjz9MK"
    assert envelope["extra"]["is_group"] is False
    assert envelope["phone"] == "5511966830020"


def test_extract_document_without_base64_fallback():
    envelope = extract_envelope(SAMPLE_DOCUMENT_PAYLOAD_WITHOUT_BASE64)
    assert envelope is not None
    assert envelope["text"] == "memorize esse relatorio"
    assert envelope["extra"]["has_document"] is True
    assert envelope["extra"]["doc_mimetype"] == "application/pdf"
    assert envelope["extra"]["doc_file_name"] == "relatorio.pdf"
    assert "doc_base64" not in envelope["extra"]
    assert envelope["extra"]["is_group"] is False


def test_extract_document_group_with_caption_fallback():
    with _patch_bot_jid():
        envelope = extract_envelope(SAMPLE_GROUP_DOCUMENT_PAYLOAD)
    assert envelope is not None
    assert envelope["text"] == "@Jennifer salva essa ata"
    assert envelope["extra"]["has_document"] is True
    assert envelope["extra"]["doc_file_name"] == "ata_reuniao.pdf"
    assert envelope["extra"]["is_group"] is True
    # Patch 01/08/2026: phone em grupo vem do key.participant.
    assert envelope["phone"] == "5511966830020"
    assert envelope["remote_jid"] == "120363@g.us"
    assert envelope["extra"]["phone_source"] == "participant"


def test_extract_document_text_falls_back_to_filename_when_no_caption():
    payload = {
        "event": "MESSAGES_UPSERT",
        "instance": "jennifer",
        "data": {
            "key": {
                "remoteJid": "5511966830020@s.whatsapp.net",
                "fromMe": False,
                "id": "DOC_NO_CAPTION_008",
            },
            "message": {
                "documentMessage": {
                    "mimetype": "application/pdf",
                    "fileName": "doc.pdf",
                    "fileLength": 100,
                }
            },
        },
    }
    envelope = extract_envelope(payload)
    assert envelope is not None
    assert envelope["text"] == "doc.pdf"


def test_extract_document_default_mimetype_when_missing():
    payload = {
        "event": "MESSAGES_UPSERT",
        "instance": "jennifer",
        "data": {
            "key": {
                "remoteJid": "5511966830020@s.whatsapp.net",
                "fromMe": False,
                "id": "DOC_NO_MIME_009",
            },
            "message": {
                "documentMessage": {
                    "fileName": "doc.pdf",
                    "fileLength": 100,
                }
            },
        },
    }
    envelope = extract_envelope(payload)
    assert envelope is not None
    assert envelope["extra"]["doc_mimetype"] == "application/octet-stream"
    assert envelope["extra"]["doc_file_name"] == "doc.pdf"


def test_extract_document_default_filename_when_missing():
    payload = {
        "event": "MESSAGES_UPSERT",
        "instance": "jennifer",
        "data": {
            "key": {
                "remoteJid": "5511966830020@s.whatsapp.net",
                "fromMe": False,
                "id": "DOC_NO_NAME_010",
            },
            "message": {
                "documentMessage": {
                    "mimetype": "application/pdf",
                    "fileLength": 100,
                }
            },
        },
    }
    envelope = extract_envelope(payload)
    assert envelope is not None
    assert envelope["extra"]["doc_file_name"] == "document"
    assert envelope["text"] == ""


def test_extract_image_without_text_still_returns_none():
    """F4c: imageMessage continua descartado (apenas documentMessage é suportado)."""
    payload = {
        "event": "MESSAGES_UPSERT",
        "instance": "jennifer",
        "data": {
            "key": {"remoteJid": "5511966830020@s.whatsapp.net", "fromMe": False, "id": "IMG_002"},
            "message": {"imageMessage": {"mimetype": "image/jpeg", "fileLength": 9999}},
        },
    }
    assert extract_envelope(payload) is None


def test_extract_video_without_text_still_returns_none():
    """F4c: videoMessage continua descartado."""
    payload = {
        "event": "MESSAGES_UPSERT",
        "instance": "jennifer",
        "data": {
            "key": {"remoteJid": "5511966830020@s.whatsapp.net", "fromMe": False, "id": "VID_001"},
            "message": {"videoMessage": {"mimetype": "video/mp4", "fileLength": 9999}},
        },
    }
    assert extract_envelope(payload) is None


def test_extract_document_file_length_as_proto_long_dict():
    """F4d.2: fileLength como dict (proto Long do Baileys) e normalizado para int."""
    payload = {
        "event": "MESSAGES_UPSERT",
        "instance": "jennifer",
        "data": {
            "key": {
                "remoteJid": "5511966830020@s.whatsapp.net",
                "fromMe": False,
                "id": "DOC_LONG_011",
            },
            "message": {
                "documentMessage": {
                    "mimetype": "application/pdf",
                    "fileName": "cdc.pdf",
                    "fileLength": {"low": 12345, "high": 0, "unsigned": False},
                }
            },
        },
    }
    envelope = extract_envelope(payload)
    assert envelope is not None
    assert envelope["extra"]["has_document"] is True
    assert envelope["extra"]["doc_file_length"] == 12345
    assert envelope["extra"]["doc_file_name"] == "cdc.pdf"


def test_extract_document_file_length_as_int():
    """F4d.2: fileLength como int simples continua funcionando."""
    payload = {
        "event": "MESSAGES_UPSERT",
        "instance": "jennifer",
        "data": {
            "key": {
                "remoteJid": "5511966830020@s.whatsapp.net",
                "fromMe": False,
                "id": "DOC_INT_012",
            },
            "message": {
                "documentMessage": {
                    "mimetype": "application/pdf",
                    "fileName": "a.pdf",
                    "fileLength": 12345,
                }
            },
        },
    }
    envelope = extract_envelope(payload)
    assert envelope is not None
    assert envelope["extra"]["doc_file_length"] == 12345


def test_extract_document_file_length_missing():
    """F4d.2: fileLength ausente não quebra o extract_envelope."""
    payload = {
        "event": "MESSAGES_UPSERT",
        "instance": "jennifer",
        "data": {
            "key": {
                "remoteJid": "5511966830020@s.whatsapp.net",
                "fromMe": False,
                "id": "DOC_NO_LEN_013",
            },
            "message": {
                "documentMessage": {
                    "mimetype": "application/pdf",
                    "fileName": "a.pdf",
                }
            },
        },
    }
    envelope = extract_envelope(payload)
    assert envelope is not None
    assert envelope["extra"]["doc_file_length"] == 0


# ============================================================================
# Filtro de mencao @Jennifer em grupo (10/08/2026)
# ============================================================================

BOT_JID = "5511966830020@s.whatsapp.net"
GROUP_JID = "12036312345678@g.us"


def _group_payload(message, mention_jids=None):
    """Monta payload de grupo. mention_jids insere contextInfo.mentionedJid."""
    extended = {"text": "@Jennifer oi pessoal"}
    if mention_jids is not None:
        extended["contextInfo"] = {"mentionedJid": mention_jids}
    return {
        "event": "MESSAGES_UPSERT",
        "instance": "jennifer",
        "data": {
            "key": {
                "remoteJid": GROUP_JID,
                "participant": "5511777777777@s.whatsapp.net",
                "fromMe": False,
                "id": "GRP_MSG_001",
            },
            "pushName": "Ana",
            "message": {"extendedTextMessage": extended},
            "messageType": "extendedTextMessage",
        },
    }


def _patch_bot_jid(jid=BOT_JID):
    from unittest.mock import patch

    return patch("core.evolution_webhook._resolve_bot_jid", return_value=jid)


def test_group_message_mentioning_bot_passes():
    """Mencao explicita @Jennifer -> processa normalmente."""
    payload = _group_payload({"text": "@Jennifer oi"}, mention_jids=[BOT_JID])
    with _patch_bot_jid():
        envelope = extract_envelope(payload)
    assert envelope is not None
    assert envelope["extra"]["was_mentioned"] is True
    assert envelope["phone"] == "5511777777777"


def test_group_message_not_mentioning_bot_is_skipped():
    """Grupo sem @Jennifer (menciona outro user) -> None (ignorado)."""
    payload = _group_payload({"text": "@Carlos oi"}, mention_jids=["5511888888888@s.whatsapp.net"])
    with _patch_bot_jid():
        envelope = extract_envelope(payload)
    assert envelope is None


def test_group_message_no_mentions_is_skipped_aggressive():
    """Grupo sem contextInfo.mentionedJid -> None (agressivo desde 11/08/2026).

    O comportamento antigo era "backward compat" (mensagem sem @mention
    passava). Agora Jennifer so responde quando @mencionada. Isso evita
    responder a todas as mensagens do grupo (ex: "Bom dia senhores!").
    """
    payload = _group_payload({"text": "oi pessoal"})
    with _patch_bot_jid():
        envelope = extract_envelope(payload)
    assert envelope is None


def test_group_message_bot_jid_unknown_blocked():
    """Bot JID nao resolvido -> mensagem de grupo bloqueada (fail-safe).

    Se nao conseguimos resolver o JID do bot, NAO respondemos no grupo
    (evita false positives). Conversa privada nao e afetada.
    """
    payload = _group_payload({"text": "oi pessoal"}, mention_jids=["5511888888888@s.whatsapp.net"])
    with _patch_bot_jid(""):
        envelope = extract_envelope(payload)
    assert envelope is None


def test_private_message_ignores_mention_filter():
    """Mensagem privada nunca passa pelo filtro de mencao."""
    payload = {
        "event": "MESSAGES_UPSERT",
        "instance": "jennifer",
        "data": {
            "key": {"remoteJid": BOT_JID, "fromMe": False, "id": "PVT_MSG_001"},
            "pushName": "Ana",
            "message": {"conversation": "oi jennifer"},
            "messageType": "conversation",
        },
    }
    with _patch_bot_jid():
        envelope = extract_envelope(payload)
    assert envelope is not None
    assert envelope["extra"]["was_mentioned"] is False


def test_mention_at_message_root_level():
    """contextInfo.mentionedJid no nivel raiz do message (formato alternativo da Evolution)."""
    payload = {
        "event": "MESSAGES_UPSERT",
        "instance": "jennifer",
        "data": {
            "key": {
                "remoteJid": GROUP_JID,
                "participant": "5511777777777@s.whatsapp.net",
                "fromMe": False,
                "id": "GRP_ROOT_007",
            },
            "pushName": "Ana",
            "message": {
                "extendedTextMessage": {"text": "@Jennifer oi"},
                "contextInfo": {"mentionedJid": [BOT_JID]},  # nivel raiz!
            },
            "messageType": "extendedTextMessage",
        },
    }
    with _patch_bot_jid():
        envelope = extract_envelope(payload)
    assert envelope is not None
    assert envelope["extra"]["was_mentioned"] is True
    assert envelope["phone"] == "5511777777777"


REAL_BOT_PN_JID = "5511917389901@s.whatsapp.net"
REAL_BOT_LID_JID = "75793925419076@lid"
REAL_OWNER_PN_JID = "5511966830020@s.whatsapp.net"
REAL_GROUP_JID = "120363429893582550@g.us"


def _patch_bot_lid(jid=REAL_BOT_LID_JID):
    from unittest.mock import patch

    return patch("core.evolution_webhook._resolve_bot_lid", return_value=jid)


def test_group_mention_lid_mode_matches_bot_pn():
    """WhatsApp LID mode: mentionedJid vem como @lid, bot_jid como PN.

    No LID mode o LID (75793925419076) e um numero DIFERENTE do PN do bot
    (5511917389901). O match por digits do PN nao casa; o caminho real e
    resolver o LID do bot no grupo via findGroupInfos (_resolve_bot_lid).
    Este teste cobre o caso em que o mentionedJid traz o PN diretamente
    (grupo que ainda nao migrou para LID) e o match e por digits.
    """
    payload = {
        "event": "MESSAGES_UPSERT",
        "instance": "Jennifer",
        "data": {
            "key": {
                "remoteJid": REAL_GROUP_JID,
                "fromMe": False,
                "id": "LID_GRP_001",
                "participant": "82927262154987@lid",
                "participantAlt": REAL_OWNER_PN_JID,
                "addressingMode": "lid",
            },
            "pushName": "Vinicius Rocha",
            "message": {
                "messageContextInfo": {"threadId": []},
                "conversation": "@5511917389901 oi",
            },
            "contextInfo": {"mentionedJid": [REAL_BOT_PN_JID], "groupMentions": []},
            "messageType": "conversation",
            "messageTimestamp": 1786464623,
            "instanceId": "2e0b001f-3ace-4576-a1ea-bcbb4d6e664c",
            "source": "web",
        },
    }
    with _patch_bot_jid(REAL_BOT_PN_JID):
        envelope = extract_envelope(payload)
    assert envelope is not None
    assert envelope["extra"]["was_mentioned"] is True
    # phone do remetente (owner) vem do participantAlt normalizado
    assert envelope["phone"] == "5511966830020"
    assert envelope["extra"]["is_group"] is True


def test_group_mention_lid_mode_matches_bot_lid_via_findgroupinfos():
    """Caso REAL do WhatsApp LID: mentionedJid = 75793925419076@lid (LID
    do bot), enquanto o ownerJid resolvido e o PN 5511917389901.

    Os digits nao casam (LID != PN), entao o filtro resolve o LID do bot
    no grupo via _resolve_bot_lid (findGroupInfos) e casa por digits.
    """
    payload = {
        "event": "MESSAGES_UPSERT",
        "instance": "Jennifer",
        "data": {
            "key": {
                "remoteJid": REAL_GROUP_JID,
                "fromMe": False,
                "id": "LID_GRP_002",
                "participant": "82927262154987@lid",
                "participantAlt": REAL_OWNER_PN_JID,
                "addressingMode": "lid",
            },
            "pushName": "Vinicius Rocha",
            "message": {"conversation": "@75793925419076 oi"},
            "contextInfo": {"mentionedJid": [REAL_BOT_LID_JID]},
            "messageType": "conversation",
            "messageTimestamp": 1786464624,
            "instanceId": "2e0b001f-3ace-4576-a1ea-bcbb4d6e664c",
            "source": "web",
        },
    }
    with _patch_bot_jid(REAL_BOT_PN_JID), _patch_bot_lid(REAL_BOT_LID_JID):
        envelope = extract_envelope(payload)
    assert envelope is not None
    assert envelope["extra"]["was_mentioned"] is True


def test_group_mention_other_lid_still_blocked():
    """Menção @lid de OUTRA pessoa (nao o bot) continua bloqueada."""
    payload = {
        "event": "MESSAGES_UPSERT",
        "instance": "Jennifer",
        "data": {
            "key": {
                "remoteJid": REAL_GROUP_JID,
                "fromMe": False,
                "id": "LID_GRP_003",
                "participant": "82927262154987@lid",
                "participantAlt": REAL_OWNER_PN_JID,
                "addressingMode": "lid",
            },
            "pushName": "Vinicius Rocha",
            "message": {"conversation": "@99999999999999 oi"},
            "contextInfo": {"mentionedJid": ["99999999999999@lid"]},
            "messageType": "conversation",
            "messageTimestamp": 1786464625,
            "instanceId": "2e0b001f-3ace-4576-a1ea-bcbb4d6e664c",
            "source": "web",
        },
    }
    with _patch_bot_jid(REAL_BOT_PN_JID), _patch_bot_lid(REAL_BOT_LID_JID):
        envelope = extract_envelope(payload)
    assert envelope is None
