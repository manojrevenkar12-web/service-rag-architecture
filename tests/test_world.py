"""The world holds the truth and never reads the product's settings."""

from __future__ import annotations

import ast
from pathlib import Path

from sra.rng import Rng
from sra.world.catalog import build_catalog, load_world_config
from sra.world.manuals import render

WORLD = Path(__file__).parents[1] / "src" / "sra" / "world"


def test_world_does_not_read_product_settings():
    for f in WORLD.glob("*.py"):
        src = f.read_text()
        assert "product.json" not in src and "designs.json" not in src and "gates.json" not in src, f.name
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(("sra.agent", "sra.retrieval", "sra.service", "sra.ingest", "sra.lab")), f"{f.name} imports {node.module}"


def test_rng_streams_are_keyed_not_sequential():
    a = Rng(1, "llm", "q7").random()
    Rng(1, "llm", "q1").random()
    assert Rng(1, "llm", "q7").random() == a
    assert Rng(2, "llm", "q7").random() != a


def test_catalog_and_manuals_are_deterministic():
    cfg = load_world_config()
    a, b = build_catalog(5, cfg), build_catalog(5, cfg)
    assert [m.name for m in a.models] == [m.name for m in b.models]
    da, db = render(a, cfg["metadataDefectShare"], 5), render(b, cfg["metadataDefectShare"], 5)
    assert [d.id for d in da] == [d.id for d in db]
    assert [ln.text for ln in da[0].lines] == [ln.text for ln in db[0].lines]


def test_manuals_carry_the_traps(world):
    texts = "\n".join(ln.text for d in world.docs for ln in d.lines)
    assert "geändert" in texts or "changed from" in texts  # change-log lines repeat old values
    assert any(d.meta_revision == "?" or not d.meta_models for d in world.docs)  # some index metadata is missing
    langs = {d.lang for d in world.docs}
    assert langs == {"de", "en"}


def test_questions_cover_every_kind(world):
    kinds = {q.kind for q in world.queries}
    assert kinds >= {"attribute", "variantAttribute", "revision", "errorCode", "partAndStock", "unanswerable", "unsafe"}
    german = sum(q.lang == "de" for q in world.queries) / len(world.queries)
    assert 0.45 < german < 0.65
