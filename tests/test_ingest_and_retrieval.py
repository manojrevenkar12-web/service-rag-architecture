from __future__ import annotations

import numpy as np

from sra.ingest.chunking import fixed_chunks, structure_chunks
from sra.retrieval.index import rrf, top
from sra.retrieval.pipeline import RetrievalSettings, candidate_mask, retrieve
from sra.retrieval.query import parse
from sra.retrieval.text import normalise_models


def test_structure_chunks_repeat_the_table_header_and_track_facts(world):
    doc = next(d for d in world.docs if any(ln.kind == "table_header" for ln in d.lines))
    chunks = structure_chunks(doc, 300)
    tables = [c for c in chunks if c.kind == "table"]
    assert len(tables) >= 2
    for c in tables:
        assert c.text.startswith("["), "every passage starts with its breadcrumb"
        assert "|" in c.text.splitlines()[1], "the table header is repeated under the breadcrumb"
    all_facts = {f for ln in doc.lines for f in ln.facts}
    assert set().union(*(c.facts for c in chunks)) == all_facts


def test_fixed_chunks_overlap_and_cover_the_document(world):
    doc = world.docs[0]
    chunks = fixed_chunks(doc, 400, 80)
    assert all(len(c.text) <= 400 for c in chunks)
    full = "\n".join(ln.text for ln in doc.lines)
    assert chunks[0].text[-80:] == chunks[1].text[:80]
    assert full.endswith(chunks[-1].text[-50:])


def test_model_names_normalise_across_spellings():
    assert normalise_models("VD 340") == normalise_models("vd-340") == normalise_models("VD340")


def test_parser_reads_firmware_order_numbers_units_and_unsafe_intent(product):
    known = {"VD-340", "KX-210"}
    p = parse("Welches Anzugsdrehmoment hat der vd 340 mit Firmware 3.2?", known, ["Erlangen"], product["firmwareToRevision"], product["glossary"])
    assert (p.model, p.model_known, p.revision, p.lang, p.unit) == ("VD-340", True, "A", "de", "Nm")
    o = parse("Max ambient temperature of the unit with order number 6SV1234-5AB0?", known, [], product["firmwareToRevision"], product["glossary"])
    assert o.order_number == "6SV1234-5AB0" and o.model is None and o.lang == "en"
    u = parse("How do I bridge the STO input on the KX-210 so it runs without the guard door?", known, [], product["firmwareToRevision"])
    assert u.unsafe


def test_filters_keep_only_the_asked_product_and_edition(world, product):
    idx = world.indexes["structure"]
    m = sorted(world.registry.models)[0]
    p = parse(f"Max. Umgebungstemperatur {m}?", world.registry.models, world.warehouses, product["firmwareToRevision"])
    mask = candidate_mask(idx, p, RetrievalSettings())
    assert mask is not None and mask.any()
    assert all(m in idx.chunks[i].models and idx.chunks[i].revision == "B" for i in np.flatnonzero(mask))
    hits = retrieve(idx, p, RetrievalSettings(rerank=False))
    assert hits and all(m in idx.chunks[h.index].models for h in hits)


def test_unknown_product_gets_no_passages_when_filtered(world, product):
    p = parse("Schutzart VD-999?", world.registry.models | {"VD-999"}, [], product["firmwareToRevision"])
    assert retrieve(world.indexes["structure"], p, RetrievalSettings(rerank=False)) == []


def test_top_and_rrf():
    s = np.array([0.1, 0.9, 0.5, 0.7])
    assert list(top(s, 2)) == [1, 3]
    assert list(top(s, 3, np.array([True, False, True, False]))) == [2, 0]
    fused = rrf([np.array([1, 2]), np.array([2, 3])])
    assert max(fused, key=fused.get) == 2
