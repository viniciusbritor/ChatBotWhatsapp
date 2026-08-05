"""Testes do clean_portuguese — combining marks (Mn) e spacing diacritics (Sk)."""
from __future__ import annotations

import pytest

from core.text_cleaner import clean_portuguese

C_ACUTE = "\u0301"
C_CEDILLA = "\u0327"
C_TILDE = "\u0303"


class TestCombiningMarks:
    def test_combining_acute_detached_before_a(self):
        dirty = f"necess {C_ACUTE}arios"
        assert clean_portuguese(dirty) == "necess\u00e1rios"

    def test_combining_acute_detached_before_e(self):
        dirty = f"H {C_ACUTE}elio"
        assert clean_portuguese(dirty) == "H\u00e9lio"

    def test_combining_tilde_detached_before_ao(self):
        dirty = f"previs {C_TILDE}ao"
        assert clean_portuguese(dirty) == "previs\u00e3o"

    def test_combining_tilde_detached_before_o(self):
        dirty = f"na {C_TILDE}o"
        assert clean_portuguese(dirty) == "n\u00e3o"

    def test_combining_cedilla_detached_before_c(self):
        dirty = f"obten {C_CEDILLA}ca"
        assert clean_portuguese(dirty) == "obten\u00e7a"

    def test_no_combining_unchanged(self):
        assert clean_portuguese("texto normal sem acentos") == "texto normal sem acentos"

    def test_empty_returns_empty(self):
        assert clean_portuguese("") == ""


class TestCombiningRegressionNoBreak:
    def test_already_composed_agua_unchanged(self):
        assert clean_portuguese("\u00e1gua") == "\u00e1gua"

    def test_already_composed_precificacao_unchanged(self):
        assert clean_portuguese("precifica\u00e7\u00e3o") == "precifica\u00e7\u00e3o"

    def test_already_composed_sao_unchanged(self):
        assert clean_portuguese("s\u00e3o") == "s\u00e3o"

    def test_mark_adjacent_to_letter_not_moved(self):
        dirty = f"precifica{C_CEDILLA}{C_TILDE}o"
        result = clean_portuguese(dirty)
        assert "\u0303" not in result or "\u0327" not in result


class TestSpacingDiacriticsRegression:
    def test_spacing_cedilla_adjacent(self):
        assert clean_portuguese("c\u00b8") == "\u00e7"

    def test_spacing_cedilla_with_space(self):
        assert clean_portuguese("c \u00b8") == "\u00e7"

    def test_spacing_tilde_with_space(self):
        assert clean_portuguese("s\u02dc ao") == "s\u00e3o"

    def test_spacing_acute(self):
        assert clean_portuguese("a\u00b4gua") == "\u00e1gua"

    def test_ligature_fi(self):
        assert clean_portuguese("\ufb01ce") == "fice"
