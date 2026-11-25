"""Code checks a draft before anyone sees it: the passage must be about the asked product and
edition, must not be a change-log line, and must contain the value the model gave."""

from __future__ import annotations

import re

from sra.agent.llm import Draft
from sra.ingest.chunking import Chunk
from sra.retrieval.query import ParsedQuery

HISTORY_RE = re.compile(r"(changed from|von .+ auf .+ geändert)", re.IGNORECASE)
EDITION_RE = re.compile(r"(?:Ausgabe|Edition) ([AB])\b")


def edition(chunk: Chunk) -> str:
    """The edition from the index metadata, or from the passage's own breadcrumb or title."""
    if chunk.revision in ("A", "B"):
        return chunk.revision
    m = EDITION_RE.search(chunk.text)
    return m.group(1) if m else "?"


def verify(draft: Draft, chunk: Chunk | None, q: ParsedQuery, current_revision: str) -> list[str]:
    problems: list[str] = []
    if draft.kind not in ("value", "remedy"):
        return ["no answer"]
    if chunk is None or draft.value is None:
        return ["no passage cited"]
    if draft.kind == "value":
        if q.model is None or q.model not in (draft.line or ""):
            problems.append(f"quoted line does not name {q.model}")
        if edition(chunk) != (q.revision or current_revision):
            problems.append(f"passage is edition {edition(chunk)}")
        if q.variant and f"| {q.variant.split()[0]} kW |" not in (draft.line or "").replace(",", "."):
            problems.append("line is not the asked power variant")
    else:
        if q.family_prefix is None or f"{q.family_prefix}-" not in chunk.text:
            problems.append("passage is about another product family")
        if q.code and q.code not in (draft.line or ""):
            problems.append("line does not name the fault code")
    if draft.line and draft.line.startswith("["):
        problems.append("quoted line is the passage's breadcrumb")
    if draft.kind == "value" and q.unit and not _has_unit(draft.value, q.unit):
        problems.append(f"value is not in {q.unit}, the unit of the quantity asked")
    if draft.line is None or draft.line not in chunk.text:
        problems.append("quoted line is not in the passage")
    elif HISTORY_RE.search(draft.line):
        problems.append("value comes from the change log")
    if draft.value not in (draft.line or ""):
        problems.append("value is not in the quoted line")
    if draft.part and draft.part not in chunk.text:
        problems.append("part number is not in the passage")
    return problems


def _has_unit(value: str, unit: str) -> bool:
    v = value.strip()
    if unit == "IP":
        return v.upper().startswith("IP")
    return v.endswith(" " + unit) or v.endswith(unit) and v[: -len(unit)].strip().replace(",", ".").replace(".", "", 1).isdigit()
