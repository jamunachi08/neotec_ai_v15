# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Arabic-aware text normalisation for knowledge search. Pure Python."""

from __future__ import annotations

import re

_TASHKEEL = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
_TATWEEL = "\u0640"
_MAP = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ئ": "ي", "ؤ": "و", "ة": "ه",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
})
_TOKEN = re.compile(r"[0-9a-z\u0621-\u064A]+")

STOPWORDS = {
    # English
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "was", "be",
    "what", "how", "do", "does", "can", "i", "we", "you", "it", "this", "that", "with", "by",
    "as", "at", "from", "our", "my", "me", "please", "about",
    # Arabic (normalised forms)
    "في", "من", "علي", "الي", "عن", "ما", "ماذا", "كيف", "هل", "هو", "هي", "هذا", "هذه",
    "التي", "الذي", "او", "و", "ان", "مع", "لا", "كل", "عند", "لدي",
}


def normalize(text: str) -> str:
    if not text:
        return ""
    text = _TASHKEEL.sub("", text).replace(_TATWEEL, "")
    return text.translate(_MAP).lower()


def strip_al(token: str) -> str:
    """Light Arabic stemming: drop the definite article and common attached prefixes."""
    for prefix in ("وال", "بال", "كال", "فال", "لل", "ال"):
        if token.startswith(prefix) and len(token) - len(prefix) >= 2:
            return token[len(prefix):]
    return token


def tokens(text: str, drop_stopwords: bool = True) -> list[str]:
    out = []
    for tok in _TOKEN.findall(normalize(text)):
        tok = strip_al(tok)
        if len(tok) < 2:
            continue
        if drop_stopwords and tok in STOPWORDS:
            continue
        out.append(tok)
    return out


def search_text(text: str) -> str:
    """Normalised, de-articled text stored alongside each knowledge passage."""
    return " ".join(tokens(text, drop_stopwords=False))
