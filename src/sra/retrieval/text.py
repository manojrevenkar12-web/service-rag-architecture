"""Text normalisation shared by every retriever and by the query parser."""

from __future__ import annotations

import re

MODEL_RE = re.compile(r"\b([A-Za-z]{2})[\s-]?(\d{3})\b")
TOKEN_RE = re.compile(r"[a-z0-9äöüß]+(?:[.,]\d+)?")
STOP = {
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "und", "ist", "es", "zu", "mit", "am", "beim", "im", "in", "an",
    "wie", "was", "welche", "welcher", "welches", "the", "a", "of", "on", "for", "is", "what", "which", "how", "do", "i",
    "and", "to", "does", "it", "be", "should", "after", "von", "auf", "bei", "ab", "werk", "wird", "werden", "hat", "have",
}


def normalise_models(text: str) -> str:
    """VD-340, VD340, vd 340 and vd-340 all become vd340."""
    return MODEL_RE.sub(lambda m: f"{m.group(1).lower()}{m.group(2)}", text)


def tokens(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(normalise_models(text).lower()) if t not in STOP]
