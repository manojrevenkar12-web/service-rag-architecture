"""What is written to the audit log: the question with contact details and names taken out."""

from __future__ import annotations

import re

PATTERNS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "phone": re.compile(r"(?<!\w)\+?\d[\d ()/-]{7,}\d"),
    "person": re.compile(r"\b(Herr|Frau|Mr\.?|Mrs\.?|Ms\.?)\s+[A-ZÄÖÜ][\wäöüß-]+"),
}


def redact(text: str, kinds: list[str]) -> str:
    for kind in kinds:
        pattern = PATTERNS[kind]
        if kind == "person":
            text = pattern.sub(lambda m: f"{m.group(1)} [name]", text)
        else:
            text = pattern.sub(f"[{kind}]", text)
    return text
