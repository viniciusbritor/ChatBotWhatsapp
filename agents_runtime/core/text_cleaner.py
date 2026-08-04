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

import unicodedata

_ORDERS = ("after", "before")

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


def clean_portuguese(text: str) -> str:
    """Reconstitute spacing diacritics into proper Portuguese characters.

    Handles both orders (base+diacritic and diacritic+base) because PDF
    font positioning can place the glyph in either order.
    """
    if not text:
        return text

    for diacritic, base_map in _DIACRITIC_TABLE:
        for order in _ORDERS:
            for base, composed in base_map.items():
                if order == "after":
                    pattern = base + diacritic
                else:
                    pattern = diacritic + base
                text = text.replace(pattern, composed)

    text = text.replace(LIG_FI, "fi")
    text = text.replace(LIG_FL, "fl")

    return unicodedata.normalize("NFC", text)


__all__ = ["clean_portuguese"]
