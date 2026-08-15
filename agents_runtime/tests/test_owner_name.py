"""Tests for core.owner_name (D3 hybrid resolver)."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from core.owner_name import resolve_owner_name, _mask_phone, _firestore_lookup, _evolution_lookup, clear_cache_for_phone


def test_mask_phone_br():
    """Telefone BR deve ser mascardo como +55 11 9****-XXXX."""
    assert _mask_phone("5511966830020") == "+55 11 9****-0020"
    assert _mask_phone("5511912345678") == "+55 11 9****-5678"


def test_mask_phone_intl():
    """Telefone intl (>=12 digitos) -> +CC AA 9****-XXXX."""
    # 13 digits: +41 78 9****-1234 (CH mobile)
    assert _mask_phone("417812345678") == "+41 78 9****-5678"


def test_mask_phone_short():
    """Telefone muito curto -> fallback generico."""
    assert _mask_phone("123") == "+123"


def test_resolve_owner_name_empty():
    """Empty/None phone -> empty string."""
    assert resolve_owner_name("") == ""
    assert resolve_owner_name(None) == ""  # type: ignore[arg-type]


def test_resolve_owner_name_firestore_name():
    """Cascata 1: Firestore name."""
    with patch("core.owner_name._firestore_lookup", return_value="Vinicius Brito"):
        with patch("core.owner_name._evolution_lookup", return_value="") as mock_evo:
            assert resolve_owner_name("5511966830020") == "Vinicius Brito"
            mock_evo.assert_not_called()  # short-circuit on Firestore hit


def test_resolve_owner_name_firestore_push_name():
    """Cascata 1: Firestore push_name (fallback when name empty)."""
    fake_doc = MagicMock()
    fake_doc.exists = True
    fake_doc.to_dict.return_value = {"push_name": "Vinicius"}  # no name
    with patch("core.owner_name._get_db") as mock_db:
        mock_db.return_value.collection.return_value.document.return_value.get.return_value = fake_doc
        assert resolve_owner_name("5511966830020") == "Vinicius"


def test_resolve_owner_name_evolution_fallback():
    """Cascata 2: Evolution contacts API when Firestore empty."""
    with patch("core.owner_name._firestore_lookup", return_value=""):
        with patch("core.owner_name._evolution_lookup", return_value="Vini Social"):
            assert resolve_owner_name("5511966830020") == "Vini Social"


def test_resolve_owner_name_mask_fallback():
    """Cascata 3: Mascardo quando Firestore + Evolution falham."""
    with patch("core.owner_name._firestore_lookup", return_value=""):
        with patch("core.owner_name._evolution_lookup", return_value=""):
            assert resolve_owner_name("5511966830020") == "+55 11 9****-0020"


def test_resolve_owner_name_firestore_exception_safe():
    """Firestore exception nao quebra o caller."""
    # Mocka _get_db (interno do _firestore_lookup) para raise
    with patch("core.owner_name._get_db", side_effect=Exception("firestore down")):
        with patch("core.owner_name._evolution_lookup", return_value="Vinicius"):
            assert resolve_owner_name("5511966830020") == "Vinicius"


def test_resolve_owner_name_phone_normalization():
    """Phone formatado (+, espacos) deve ser normalizado para digitos."""
    with patch("core.owner_name._firestore_lookup", return_value="Vinicius") as mock_fs:
        resolve_owner_name("+55 11 96683-0020")
        # Confere que Firestore foi chamado com digits apenas
        mock_fs.assert_called_once_with("5511966830020")


def test_evolution_lookup_uses_cache():
    """Evolution cache deve ser respeitado em chamadas subsequentes."""
    import time
    from core.owner_name import _cache
    clear_cache_for_phone("5511966830020")
    # Popula cache diretamente (timestamp futuro)
    _cache["5511966830020"] = ("Vinicius Cached", time.time())
    result = _evolution_lookup("5511966830020")
    assert result == "Vinicius Cached"
    # Nenhuma chamada Evolution deve ter sido feita (served from cache)


def test_evolution_lookup_no_find_contact_method_safe():
    """Se evolution_client nao expoe find_contact, retorna '' sem crash."""
    import sys
    import time
    from core.owner_name import _cache
    clear_cache_for_phone("5511966830020")
    with patch.dict(sys.modules, {"core.evolution_client": MagicMock(spec=[])}, clear=False):
        # Forca reload do modulo
        import importlib
        import core.owner_name
        importlib.reload(core.owner_name)
        result = core.owner_name._evolution_lookup("5511966830020")
        assert result == ""  # graceful fallback
        importlib.reload(core.owner_name)  # restore


def test_clear_cache_for_phone():
    """clear_cache_for_phone invalida cache."""
    import time
    from core.owner_name import _cache
    _cache["5511966830020"] = ("Old Name", time.time())
    clear_cache_for_phone("5511966830020")
    assert "5511966830020" not in _cache
    clear_cache_for_phone("+55 11 96683-0020")  # formatado
    assert "5511966830020" not in _cache


def test_clear_cache_for_phone():
    """clear_cache_for_phone invalida cache."""
    import time
    from core.owner_name import _cache
    _cache["5511966830020"] = ("Old Name", time.time())
    clear_cache_for_phone("5511966830020")
    assert "5511966830020" not in _cache
    clear_cache_for_phone("+55 11 96683-0020")  # formatado
    assert "5511966830020" not in _cache
