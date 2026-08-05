"""Text cleaner for Portuguese (pt-BR) diacritic reconstitution.

PDF fonts with broken ToUnicode tables often extract spacing diacritics
(U+00B8 CEDILLA, U+02DC SMALL TILDE, U+02C6 MODIFIER LETTER CIRCUMFLEX,
U+00B4 ACUTE ACCENT) as independent characters instead of precomposed
forms.  NFKC normalization does NOT fix these because they are category
Sk (modifier symbol), not Mn (combining mark).

This module reconstitutes correct Portuguese characters BEFORE embedding
and storage, preventing garbage vectors in Firestore.
"""

from __future__ import annotations

import re
import unicodedata

CEDA = "\u00B8"
TILDE = "\u02DC"
CIRC = "\u02C6"
ACUTE = "\u00B4"
GRAVE = "\u0060"
LIG_FI = "\ufb01"
LIG_FL = "\ufb02"

_DIACRITIC_TABLE = [
    (CEDA, {"c": "\u00e7", "C": "\u00c7"}),
    (TILDE, {"a": "\u00e3", "A": "\u00c3", "o": "\u00f5", "O": "\u00d5"}),
    (CIRC, {"a": "\u00e2", "A": "\u00c2", "e": "\u00ea", "E": "\u00ca", "o": "\u00f4", "O": "\u00d4"}),
    (ACUTE, {"a": "\u00e1", "A": "\u00c1", "e": "\u00e9", "E": "\u00c9",
              "i": "\u00ed", "I": "\u00cd", "o": "\u00f3", "O": "\u00d3",
              "u": "\u00fa", "U": "\u00da"}),
    (GRAVE, {"a": "\u00e0", "A": "\u00c0"}),
]


_COMBINING_COLLAPSE_RE = re.compile(
    r"(\s)([\u0300-\u036f])(\s*)([a-zA-Z\u00C0-\u024F])"
)

# "na ̃o" -> "não": a/o + ws + tilde + letra -> a/o + tilde + letra (tilde no 'a')
_TILDE_ENDING_RE = re.compile(
    r"(a|A|o|O)\s+(\u0303)\s*([a-zA-Z\u00C0-\u024F])"
)


def _collapse_combining(m: re.Match) -> str:
    return m.group(4) + m.group(2)


def _tilde_ending(m: re.Match) -> str:
    return m.group(1) + m.group(2) + m.group(3)


def _normalize_combining_marks(text: str) -> str:
    """Reconstitute combining marks (Mn) detached from base letters.

    PDFs like the dissertacao emit U+0301/U+0327/U+0303 as combining
    marks detached by whitespace: 'necess ́arios', 'H ́elio', 'na ̃o'.

    Rules:
    1. Tilde in Portuguese endings ('ão', 'õe'): a/o + ws + tilde + letra
       -> tilde attaches to the a/o (handles 'na ̃o' -> 'não').
    2. Generic detached mark: ws + mark + letra -> mark attaches to the
       NEXT letter (handles 'necess ́ arios' -> 'necessários').
    3. Marks already adjacent to a base letter are left for NFC.
    """
    if not text:
        return text
    text = unicodedata.normalize("NFKD", text)
    text = _TILDE_ENDING_RE.sub(_tilde_ending, text)
    text = _COMBINING_COLLAPSE_RE.sub(_collapse_combining, text)
    return unicodedata.normalize("NFC", text)


def clean_portuguese(text: str) -> str:
    """Reconstitute spacing diacritics into proper Portuguese characters.

    Three-pass strategy:
    1. Adjacent: ``c + ¸ → ç``  (original str.replace, handles ``c¸`` and ``¸c``)
    2. With whitespace: ``c + \\s + ¸ → ç`` (regex, handles ``c ¸`` and ``¸ c``)
    3. Combining marks: NFKD + space-collapse + NFC (handles ``necess ́arios``)
    """
    if not text:
        return text

    for diacritic, base_map in _DIACRITIC_TABLE:
        for base, composed in base_map.items():
            _pat_after = re.escape(base) + r"\s*" + re.escape(diacritic)
            _pat_before = re.escape(diacritic) + r"\s*" + re.escape(base)
            text = re.sub(_pat_after, composed, text)
            text = re.sub(_pat_before, composed, text)

    text = text.replace(LIG_FI, "fi")
    text = text.replace(LIG_FL, "fl")

    text = _normalize_combining_marks(text)

    return text


__all__ = ["clean_portuguese"]
