"""Testes do FIX Bug #2 (15/08/2026): sanitizacao de @LID de pessoas em grupos.

O WhatsApp grava o LID cru (ex: '@94756306710762') no texto quando alguem
digita '@Nome'. Antes do fix, a LLM recebia o @LID literal e replicava
verbatim nas respostas, vazando o id interno do contato. Este teste
valida que o @LID e substituido pelo nome real do membro em
``core.evolution_webhook.extract_envelope``.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("EVO_BASE_URL", "https://evolution.coherenceai.com.br")

from core.evolution_webhook import extract_envelope  # noqa: E402


GROUP_JID = "120363429893582550@g.us"
OWNER_JID = "5511966830020@s.whatsapp.net"
ERIK_LID = "94756306710762@lid"
ERIK_PHONE = "5511966830020@s.whatsapp.net"  # owner (used only to verify bypass)
OTHER_LID = "82927262154987@lid"
BOT_LID = "75793925419076@lid"
BOT_PN = "5511917389901@s.whatsapp.net"


def _resolve_mentioned_mock_factory(members):
    """Factory que devolve uma funcao que imita ``tools.group.resolve_mentioned``."""

    def _resolve_mentioned(group_jid, mentioned_jids):
        if not group_jid or not mentioned_jids:
            return []
        wanted = set()
        for j in mentioned_jids:
            wanted.add(str(j).split("@")[0])
        out = []
        for m in members:
            lid_raw = str(m.get("lid") or "").split("@")[0]
            phone = str(m.get("phone") or "")
            if lid_raw in wanted or phone in wanted:
                out.append({"lid": m.get("lid"), "phone": phone, "name": m.get("name") or ""})
        return out

    return _resolve_mentioned


def _make_group_payload(text: str, mentioned_jids, *, msg_id="LID_SANITIZE_001"):
    # O filtro de mencao em grupo exige que o BOT esteja mencionado junto
    # com a pessoa, senao o envelope e descartado (return None). Entao
    # sempre adicionamos BOT_LID na lista de mentioned_jids.
    if BOT_LID not in mentioned_jids:
        mentioned_jids = list(mentioned_jids) + [BOT_LID]
    return {
        "event": "MESSAGES_UPSERT",
        "instance": "Jennifer",
        "data": {
            "key": {
                "remoteJid": GROUP_JID,
                "fromMe": False,
                "id": msg_id,
                "participant": OWNER_JID,
                "participantAlt": OWNER_JID,
                "addressingMode": "lid",
            },
            "pushName": "Vinicius Rocha",
            "message": {
                "extendedTextMessage": {
                    "text": text,
                    "contextInfo": {"mentionedJid": mentioned_jids},
                }
            },
            "messageType": "extendedTextMessage",
        },
    }


def test_sanitize_person_lid_replaces_with_name():
    """Caso real: usuario digita '@Erik' mas o WhatsApp grava '@94756306710762'.

    Esperado: o envelope['text'] chega com '@Erik' no lugar do LID.
    """
    members = [
        {"lid": BOT_LID, "phone": BOT_PN, "name": "Jennifer"},
        {"lid": ERIK_LID, "phone": "5511966830020@s.whatsapp.net", "name": "Erik"},
    ]
    payload = _make_group_payload(
        "explique para o @94756306710762 a diferenca de RAG e Drive",
        [ERIK_LID],
    )
    with patch("core.evolution_webhook._resolve_bot_jid", return_value=BOT_PN), patch(
        "core.evolution_webhook._resolve_bot_lid", return_value=BOT_LID
    ), patch("tools.group.resolve_mentioned", _resolve_mentioned_mock_factory(members)):
        envelope = extract_envelope(payload)
    assert envelope is not None
    assert "@94756306710762" not in envelope["text"]
    assert "@Erik" in envelope["text"]


def test_sanitize_bot_lid_still_replaces_with_jennifer():
    """Regressao: o caminho antigo (bot LID -> @Jennifer) continua funcionando."""
    members = [
        {"lid": BOT_LID, "phone": BOT_PN, "name": "Jennifer"},
        {"lid": ERIK_LID, "phone": "5511966830020@s.whatsapp.net", "name": "Erik"},
    ]
    payload = _make_group_payload(
        "oi @75793925419076 me ajuda",
        [BOT_LID],
    )
    with patch("core.evolution_webhook._resolve_bot_jid", return_value=BOT_PN), patch(
        "core.evolution_webhook._resolve_bot_lid", return_value=BOT_LID
    ), patch("tools.group.resolve_mentioned", _resolve_mentioned_mock_factory(members)):
        envelope = extract_envelope(payload)
    assert envelope is not None
    assert "@75793925419076" not in envelope["text"]
    assert "@Jennifer" in envelope["text"]


def test_sanitize_skips_member_without_name():
    """Se o snapshot nao tem nome, NAO substitui (fallback seguro)."""
    members = [
        {"lid": BOT_LID, "phone": BOT_PN, "name": "Jennifer"},
        {"lid": ERIK_LID, "phone": "5511966830020@s.whatsapp.net", "name": ""},
    ]
    payload = _make_group_payload(
        "oi @94756306710762",
        [ERIK_LID],
    )
    with patch("core.evolution_webhook._resolve_bot_jid", return_value=BOT_PN), patch(
        "core.evolution_webhook._resolve_bot_lid", return_value=BOT_LID
    ), patch("tools.group.resolve_mentioned", _resolve_mentioned_mock_factory(members)):
        envelope = extract_envelope(payload)
    assert envelope is not None
    assert "@94756306710762" in envelope["text"]


def test_sanitize_handles_multiple_mentions():
    """Multiplas pessoas mencionadas: cada @LID -> @Nome."""
    members = [
        {"lid": BOT_LID, "phone": BOT_PN, "name": "Jennifer"},
        {"lid": ERIK_LID, "phone": "5511966830020@s.whatsapp.net", "name": "Erik"},
        {"lid": OTHER_LID, "phone": "5511997931324@s.whatsapp.net", "name": "Clarissa"},
    ]
    payload = _make_group_payload(
        "@94756306710762 e @82927262154987, vamos?",
        [ERIK_LID, OTHER_LID],
        msg_id="LID_SANITIZE_MULTI_002",
    )
    with patch("core.evolution_webhook._resolve_bot_jid", return_value=BOT_PN), patch(
        "core.evolution_webhook._resolve_bot_lid", return_value=BOT_LID
    ), patch("tools.group.resolve_mentioned", _resolve_mentioned_mock_factory(members)):
        envelope = extract_envelope(payload)
    assert envelope is not None
    assert "@94756306710762" not in envelope["text"]
    assert "@82927262154987" not in envelope["text"]
    assert "@Erik" in envelope["text"]
    assert "@Clarissa" in envelope["text"]


def test_sanitize_skips_when_group_members_unavailable():
    """Se resolve_mentioned falha (Firestore indisponivel), texto NAO e modificado."""
    payload = _make_group_payload(
        "oi @94756306710762",
        [ERIK_LID],
        msg_id="LID_SANITIZE_FALLBACK_003",
    )

    def _raise(*args, **kwargs):
        raise RuntimeError("firestore_unavailable")

    with patch("core.evolution_webhook._resolve_bot_jid", return_value=BOT_PN), patch(
        "core.evolution_webhook._resolve_bot_lid", return_value=BOT_LID
    ), patch("tools.group.resolve_mentioned", _raise):
        envelope = extract_envelope(payload)
    assert envelope is not None
    assert "@94756306710762" in envelope["text"]


def test_private_message_skips_lid_sanitization():
    """Mensagem privada NAO e afetada pela sanitizacao."""
    payload = {
        "event": "MESSAGES_UPSERT",
        "instance": "jennifer",
        "data": {
            "key": {"remoteJid": OWNER_JID, "fromMe": False, "id": "PVT_SANITIZE_004"},
            "pushName": "Vinicius",
            "message": {"conversation": "oi"},
            "messageType": "conversation",
        },
    }
    with patch("core.evolution_webhook._resolve_bot_jid", return_value=BOT_PN):
        envelope = extract_envelope(payload)
    assert envelope is not None
    assert envelope["text"] == "oi"
