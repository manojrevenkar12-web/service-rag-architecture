"""Two ways to cut manuals into chunks.

fixed       every N characters with overlap, the common default. Tables lose their header and
            their unit, a fault-code line can be cut in half.
structure   along the manual's own sections; long sections are split between lines, table rows
            keep their header, and every chunk carries a breadcrumb naming the product, edition,
            firmware and section it came from.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from sra.world.manuals import Document


@dataclass
class Chunk:
    id: str
    doc_id: str
    text: str
    models: tuple[str, ...]  # from the index metadata; empty when the document had none
    family: str
    revision: str  # from the index metadata; "?" when unknown
    firmware: str
    lang: str
    section: str = ""
    kind: str = "text"
    # Facts stated in full inside this chunk, and per line. Known to the lab only: used to grade
    # answers and retrieval, never for ranking or answering.
    facts: set[str] = field(default_factory=set)
    line_facts: dict[str, tuple[str, ...]] = field(default_factory=dict)


def _cid(doc_id: str, n: int, text: str) -> str:
    return f"{doc_id}#{n}-{hashlib.sha1(text.encode()).hexdigest()[:6]}"


def fixed_chunks(doc: Document, size: int = 800, overlap: int = 120) -> list[Chunk]:
    text = doc.text
    spans = []
    pos = 0
    for line in doc.lines:
        spans.append((pos, pos + len(line.text), line))
        pos += len(line.text) + 1
    out: list[Chunk] = []
    start = 0
    n = 0
    while start < len(text):
        end = min(len(text), start + size)
        piece = text[start:end]
        inside = [line for a, b, line in spans if a >= start and b <= end]
        facts = {f for line in inside for f in line.facts}
        out.append(Chunk(_cid(doc.id, n, piece), doc.id, piece, doc.meta_models, doc.family, doc.meta_revision, doc.firmware, doc.lang,
                         facts=facts, line_facts={line.text: line.facts for line in inside if line.facts}))
        n += 1
        if end == len(text):
            break
        start = end - overlap
    return out


def breadcrumb(doc: Document, section: str) -> str:
    """Built from the document's own title (its content), so it survives missing index metadata."""
    edition = "Ausgabe" if doc.lang == "de" else "Edition"
    return f"[{', '.join(doc.models)} | {edition} {doc.revision}, Firmware {doc.firmware}.x | {section}]"


def structure_chunks(doc: Document, max_chars: int = 700) -> list[Chunk]:
    out: list[Chunk] = []
    sections: list[tuple[str, list]] = []
    for line in doc.lines:
        if line.kind in ("title", "heading"):
            if line.kind == "heading":
                sections.append((line.section, []))
            continue
        if not sections:
            sections.append(("", []))
        sections[-1][1].append(line)
    n = 0
    for section, lines in sections:
        if not lines:
            continue
        header = next((ln for ln in lines if ln.kind == "table_header"), None)
        crumb = breadcrumb(doc, section)
        group: list = []
        size = 0

        def flush(group: list, header=header, crumb=crumb, section=section) -> None:
            nonlocal n
            if not group:
                return
            body = [header] + [ln for ln in group if ln is not header] if header and header not in group else group
            text = crumb + "\n" + "\n".join(ln.text for ln in body)
            kind = "history" if any(ln.kind == "history" for ln in body) else ("table" if header else "text")
            facts = {f for ln in body for f in ln.facts}
            out.append(Chunk(_cid(doc.id, n, text), doc.id, text, doc.meta_models, doc.family, doc.meta_revision, doc.firmware, doc.lang, section, kind,
                             facts, {ln.text: ln.facts for ln in body if ln.facts}))
            n += 1

        for ln in lines:
            if ln is header:
                continue
            if group and size + len(ln.text) > max_chars:
                flush(group)
                group, size = [], 0
            group.append(ln)
            size += len(ln.text) + 1
        flush(group)
    return out


CHUNKERS = {"fixed": fixed_chunks, "structure": structure_chunks}
