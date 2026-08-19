"""Testes para o helper is_owner_request com admin_phones (Front 1d)."""
from unittest.mock import MagicMock, patch

import pytest

from core.owner import OwnerResolution, is_owner_request, resolve_owner


def test_is_owner_request_owner_phone_match():
    """Inbound phone == owner_phone -> True."""
    res = OwnerResolution(
        owner_phone="5511917389901",
        owner_uid="5511917389901",
        account_id="Jennifer",
        instance="Jennifer",
        admin_phones=[],
    )
    assert is_owner_request(res, "5511917389901") is True
    assert is_owner_request(res, "+55 (11) 91738-9901") is True


def test_is_owner_request_admin_phone_match():
    """Inbound phone em admin_phones -> True (Front 1d)."""
    res = OwnerResolution(
        owner_phone="5511917389901",  # numero da Jennifer
        owner_uid="5511917389901",
        account_id="Jennifer",
        instance="Jennifer",
        admin_phones=["5511966830020"],  # admin (Vinicius) pessoal
    )
    # Owner numerico (Jennifer) passa
    assert is_owner_request(res, "5511917389901") is True
    # Admin (Vinicius pessoal) passa - pode mandar mensagem do seu WhatsApp
    # pessoal para a Jennifer e ela responde normalmente
    assert is_owner_request(res, "5511966830020") is True
    # Outro numero nao passa
    assert is_owner_request(res, "5511900000000") is False


def test_is_owner_request_no_phones_match():
    """Inbound phone nao bate com owner nem admin -> False."""
    res = OwnerResolution(
        owner_phone="5511917389901",
        owner_uid="5511917389901",
        account_id="Jennifer",
        instance="Jennifer",
        admin_phones=["5511966830020"],
    )
    assert is_owner_request(res, "5511988887777") is False


def test_is_owner_request_no_resolution():
    """Sem resolution -> False."""
    assert is_owner_request(None, "5511917389901") is False


def test_is_owner_request_empty_inbound():
    """inbound vazio -> False."""
    res = OwnerResolution(
        owner_phone="5511917389901",
        owner_uid="5511917389901",
        account_id="Jennifer",
        instance="Jennifer",
        admin_phones=[],
    )
    assert is_owner_request(res, "") is False


def test_is_owner_request_admin_phone_with_country_code_variants():
    """admin_phone com 55 prefixo cobre variantes sem prefixo."""
    res = OwnerResolution(
        owner_phone="5511917389901",
        owner_uid="5511917389901",
        account_id="Jennifer",
        instance="Jennifer",
        admin_phones=["5511966830020"],
    )
    # variantes
    assert is_owner_request(res, "11966830020") is True
    assert is_owner_request(res, "5511966830020") is True


def test_resolve_owner_includes_admin_phones(monkeypatch):
    """resolve_owner retorna admin_phones do Firestore no OwnerResolution."""
    fake_db = MagicMock()
    fake_collection = MagicMock()

    # Mock do stream() que retorna um doc com admin_phones
    class FakeDoc:
        def __init__(self, data):
            self._data = data
            self.id = "Jennifer"
        def to_dict(self):
            return self._data

    doc = FakeDoc({
        "owner_phone": "5511917389901",
        "owner_uid": "5511917389901",
        "admin_phones": ["5511966830020", "5511924441779"],
    })
    def stream_iter():
        yield doc
    fake_query = MagicMock()
    fake_query.stream = stream_iter
    fake_collection.where.return_value.limit.return_value = fake_query
    fake_db.collection.return_value = fake_collection
    with patch("core.owner._get_firestore_client", return_value=fake_db):
        res = resolve_owner("Jennifer", fallback_phone="5511966830020")
    assert res is not None
    assert res.admin_phones == ["5511966830020", "5511924441779"]
