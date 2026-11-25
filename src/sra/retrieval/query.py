"""Reads what a question is about with code, not a model: product, power variant, firmware,
fault code, warehouse and language. Unknown products are recognised as unknown."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sra.retrieval.text import MODEL_RE

VARIANT_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s?-?\s?kW\b", re.IGNORECASE)
FIRMWARE_RE = re.compile(r"\bfirmware\s+(\d+)(?:\.\d+)*", re.IGNORECASE)
CODE_RE = re.compile(r"\bF\d{4}\b")
ORDER_RE = re.compile(r"\b6[A-Z]{2}\d{4}-\d[A-E]{2}\d\b")
GERMAN_HINTS = re.compile(r"\b(der|die|das|welche|welcher|wie|beim|ist|was|zeigt|meldet|brauche|lager|darf|werden)\b|[äöüß]", re.IGNORECASE)
UNSAFE_RE = re.compile(r"(überbrück|brück|bypass|bridge|umgeh|disable).{0,40}(sto|not-?halt|emergency|schutzt|guard|safety|sicherheit)"
                       r"|(sto|not-?halt|emergency stop|safety).{0,40}(überbrück|brück|bypass|bridge|umgeh)", re.IGNORECASE)


@dataclass
class ParsedQuery:
    text: str
    lang: str
    model: str | None
    model_known: bool
    family_prefix: str | None
    variant: str | None
    revision: str | None
    code: str | None
    warehouse: str | None
    unsafe: bool
    order_number: str | None = None
    unit: str | None = None  # the unit of the quantity asked about, from the glossary


def parse(text: str, known_models: set[str], warehouses: list[str], firmware_to_revision: dict[str, str],
          glossary: list[dict] | None = None) -> ParsedQuery:
    order = ORDER_RE.search(text)
    m = MODEL_RE.search(ORDER_RE.sub(" ", text))
    model = f"{m.group(1).upper()}-{m.group(2)}" if m else None
    v = VARIANT_RE.search(text)
    variant = f"{float(v.group(1).replace(',', '.')):g} kW" if v else None
    fw = FIRMWARE_RE.search(text)
    code = CODE_RE.search(text)
    wh = next((w for w in warehouses if w.lower() in text.lower()), None)
    return ParsedQuery(
        text=text,
        lang="de" if len(GERMAN_HINTS.findall(text)) >= 1 else "en",
        model=model,
        model_known=model in known_models if model else False,
        family_prefix=model.split("-")[0] if model else None,
        variant=variant,
        revision=firmware_to_revision.get(fw.group(1)) if fw else None,
        code=code.group(0) if code else None,
        warehouse=wh,
        unsafe=bool(UNSAFE_RE.search(text)),
        order_number=order.group(0) if order else None,
        unit=next((g["unit"] for g in glossary or [] if re.search(g["pattern"], text, re.IGNORECASE)), None),
    )


def resolve(q: ParsedQuery, model: str) -> ParsedQuery:
    """The query after a registry lookup named its product."""
    q.model, q.model_known, q.family_prefix = model, True, model.split("-")[0]
    return q
