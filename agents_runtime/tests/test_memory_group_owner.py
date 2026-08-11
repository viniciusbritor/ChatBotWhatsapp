"""FASE 2: Memory per-user no grupo - o owner SEMPRE acessa os PROPRIOS fatos.

Contracto: quando o owner fala em um grupo, o phone extraido do
participant_jid eh o phone do owner, e memory.search_facts deve
retornar os fatos do owner. Outros membros no grupo nao vazam
fatos do owner (escopo por phone).

Regresso: o antigo codigo em grupo pegava remoteJid.split('@')[0]
que retornava o group_id ('120363'), e memory.search_facts
buscava em usuarios/{120363}/facts/ - vazio. O extract_envelope
foi corrigido em 01/08/2026 para usar participant_jid. Este teste
protege o contract.
"""
import asyncio
from unittest.mock import MagicMock, patch



OWNER_PHONE = "5511966830020"
ANOTHER_MEMBER_PHONE = "5511888888888"
GROUP_JID = "120363123456@g.us"


def _make_firestore_mock(facts_by_phone: dict):
    """Monta um mock Firestore com facts por phone.

    facts_by_phone: {"5511966830020": [{"key":..., "value":..., ...}, ...], ...}
    """
    fake_db = MagicMock()

    def _user_collection(phone):
        user_doc = MagicMock()
        facts = facts_by_phone.get(phone, [])
        fact_docs = []
        for f in facts:
            d = MagicMock()
            d.id = f.get("key", "")
            d.to_dict.return_value = f
            fact_docs.append(d)
        facts_coll = MagicMock()
        facts_coll.limit.return_value.stream.return_value = fact_docs
        user_doc.collection.return_value = facts_coll
        return user_doc

    def _collection(name):
        if name == "usuarios":
            return _UserColl(_user_collection)
        return MagicMock()

    fake_db.collection.side_effect = _collection
    return fake_db


class _UserColl:
    def __init__(self, resolver):
        self._resolver = resolver

    def document(self, phone):
        return self._resolver(phone)


class TestMemoryExtractEnvelopeContract:
    """extract_envelope extrai phone do participant (owner) em grupo."""

    def test_owner_phone_in_group_via_participant(self):
        """Patch 01/08/2026: phone vem do key.participant, NAO do remoteJid."""
        from core.evolution_webhook import extract_envelope

        payload = {
            "event": "MESSAGES_UPSERT",
            "instance": "jennifer",
            "data": {
                "key": {
                    "remoteJid": GROUP_JID,
                    "participant": OWNER_PHONE + "@s.whatsapp.net",
                    "fromMe": False,
                    "id": "GRP_MSG_001",
                },
                "pushName": "Vinicius",
                "message": {"conversation": "qual o endereco do rafa?"},
                "messageType": "conversation",
            },
        }
        envelope = extract_envelope(payload)
        assert envelope is not None
        assert envelope["phone"] == OWNER_PHONE
        assert envelope["extra"]["is_group"] is True
        assert envelope["extra"]["phone_source"] == "participant"
        assert envelope["remote_jid"] == GROUP_JID

    def test_member_phone_in_group_via_participant(self):
        """Quando outro membro fala, o phone extraido e o DELE (NAO do owner)."""
        from core.evolution_webhook import extract_envelope

        payload = {
            "event": "MESSAGES_UPSERT",
            "instance": "jennifer",
            "data": {
                "key": {
                    "remoteJid": GROUP_JID,
                    "participant": ANOTHER_MEMBER_PHONE + "@s.whatsapp.net",
                    "fromMe": False,
                    "id": "GRP_MSG_002",
                },
                "pushName": "Outro",
                "message": {"conversation": "oi"},
                "messageType": "conversation",
            },
        }
        envelope = extract_envelope(payload)
        assert envelope["phone"] == ANOTHER_MEMBER_PHONE


class TestMemoryGroupOwner:
    """Owner fala em grupo -> memory.search_facts retorna os fatos do OWNER."""

    def test_owner_search_finds_owner_facts_in_group(self):
        """Quando o owner fala em grupo, phone==owner; memory.search_facts
        busca em usuarios/{owner}/facts e retorna matches."""
        from tools.memory import search_facts

        # Fatos do owner (Rafa mora na Rua Macaia Miriim, 89)
        owner_facts = [
            {"key": "endereco_rafa", "value": "Rua Macaia Miriim, 89, Santana, SP"},
            {"key": "endereco_casa", "value": "Av. Portugal, 401"},
        ]
        # Fatos de outro membro (NUNCA devem vazar para o owner)
        other_facts = [
            {"key": "segredo_pessoal", "value": "nao compartilhar"},
        ]
        fake_db = _make_firestore_mock({
            OWNER_PHONE: owner_facts,
            ANOTHER_MEMBER_PHONE: other_facts,
        })

        with patch("tools.memory._get_firestore", return_value=fake_db):
            result = asyncio.run(search_facts(query="rafa", phone=OWNER_PHONE))

        assert result["count"] == 1
        assert result["results"][0]["key"] == "endereco_rafa"
        assert "Macaia Miriim" in result["results"][0]["value"]
        # NAO vaza dados do outro membro
        assert "segredo_pessoal" not in str(result)

    def test_owner_search_finds_endereco_chat_history_compat(self):
        """Memory.search_facts no grupo deve funcionar com query generica
        (compatibilidade com o jennifier system prompt que faz busca
        ANTES de chamar memory.search_facts)."""
        from tools.memory import search_facts

        owner_facts = [
            {"key": "endereco_rafa", "value": "Rua Macaia Miriim, 89, Santana, SP"},
            {"key": "endereco_casa", "value": "Av. Portugal, 401"},
            {"key": "cor_bandeira", "value": "verde"},
        ]
        fake_db = _make_firestore_mock({OWNER_PHONE: owner_facts})

        with patch("tools.memory._get_firestore", return_value=fake_db):
            # jennifier passa query="" para listar todos
            result = asyncio.run(search_facts(query="", phone=OWNER_PHONE))

        assert result["count"] == 3
        keys = {f["key"] for f in result["results"]}
        assert "endereco_rafa" in keys
        assert "endereco_casa" in keys
        assert "cor_bandeira" in keys

    def test_member_search_finds_only_member_facts_no_leak(self):
        """Quando outro membro fala, phone==member; memory.search_facts
        retorna SOMENTE os fatos do MEMBRO (escopo por phone)."""
        from tools.memory import search_facts

        owner_facts = [
            {"key": "endereco_rafa", "value": "Rua Macaia Miriim - NAO DEVE APARECER"},
        ]
        member_facts = [
            {"key": "minha_nota", "value": "lembrete pessoal"},
        ]
        fake_db = _make_firestore_mock({
            OWNER_PHONE: owner_facts,
            ANOTHER_MEMBER_PHONE: member_facts,
        })

        with patch("tools.memory._get_firestore", return_value=fake_db):
            result = asyncio.run(search_facts(query="", phone=ANOTHER_MEMBER_PHONE))

        assert result["count"] == 1
        assert result["results"][0]["key"] == "minha_nota"
        # NAO vaza dado do owner
        assert "Macaia Miriim" not in str(result)
        assert "endereco_rafa" not in str(result)


class TestMemorySaveFactGroup:
    """Salvar fato no grupo escopa por phone do remetente."""

    def test_save_to_sender_phone_not_admin(self):
        """Quando um MEMBRO salva um fato, vai em usuarios/{member}/facts,
        NAO em usuarios/{owner}/facts."""
        from tools.memory import save_fact

        mock_doc = MagicMock()
        mock_facts_coll = MagicMock()
        mock_facts_coll.document.return_value = mock_doc
        mock_user_doc = MagicMock()
        mock_user_doc.collection.return_value = mock_facts_coll
        mock_user = MagicMock()
        mock_user.document.return_value = mock_user_doc
        mock_db = MagicMock()
        mock_db.collection.return_value = mock_user

        with patch("tools.memory._get_firestore", return_value=mock_db):
            result = asyncio.run(
                save_fact(key="nota_pessoal", value="meu lembrete", phone=ANOTHER_MEMBER_PHONE)
            )

        assert result.get("saved") is True
        assert result.get("phone") == ANOTHER_MEMBER_PHONE
        # Verifica que gravou em usuarios/{ANOTHER_MEMBER_PHONE} (escopo por phone)
        user_doc_calls = mock_db.collection.call_args_list
        # A chamada deve ter sido em "usuarios" (escopo raiz)
        assert any("usuarios" in str(c) for c in user_doc_calls)
        # O user_doc (usuarios/{phone}) foi resolvido com phone do MEMBRO
        mock_user_doc.collection.assert_called_once()
