"""PostgreSQL + pgvector. Skipped when SRA_DATABASE_URL is not set (CI sets it)."""

from __future__ import annotations

import os

import numpy as np
import pytest

from sra.service.store import PgStore

pytestmark = pytest.mark.skipif(not os.environ.get("SRA_DATABASE_URL"), reason="needs SRA_DATABASE_URL")


@pytest.fixture(scope="module")
def store(product):
    s = PgStore(os.environ["SRA_DATABASE_URL"], 256, product["service"]["pgvector"])
    s.conn.execute("DELETE FROM passages WHERE tenant IN ('t-a', 't-b')")
    s.conn.execute("DELETE FROM audit WHERE tenant IN ('t-a', 't-b')")
    return s


def test_upsert_is_idempotent_and_tenants_are_separate(store, world):
    idx = world.indexes["structure"]
    chunks = idx.chunks[:300]
    store.upsert("t-a", chunks, idx.vectors[:300])
    store.upsert("t-a", chunks, idx.vectors[:300])
    assert store.count("t-a") == 300
    assert store.count("t-b") == 0
    assert store.search("t-b", idx.vectors[0], 5) == []


def test_hnsw_finds_what_exact_search_finds(store, world):
    idx = world.indexes["structure"]
    store.upsert("t-a", idx.chunks, idx.vectors)
    rng = np.random.default_rng(0)
    recalls = []
    for i in rng.choice(len(idx.chunks), 40, replace=False):
        v = idx.embedder.embed([idx.chunks[i].text[:80]])[0]
        a = {x for x, _ in store.search("t-a", v, 10)}
        e = {x for x, _ in store.search("t-a", v, 10, exact=True)}
        recalls.append(len(a & e) / len(e))
    assert np.mean(recalls) >= 0.95


def test_filters_run_in_the_same_query(store, world):
    idx = world.indexes["structure"]
    m = sorted(world.registry.models)[3]
    hits = store.search("t-a", idx.vectors[0], 10, model=m, revision="A")
    by_id = {c.id: c for c in idx.chunks}
    assert hits and all(m in by_id[h].models and by_id[h].revision == "A" for h, _ in hits)


def test_exact_search_matches_numpy(store, world):
    idx = world.indexes["structure"]
    v = idx.vectors[10]
    got = [x for x, _ in store.search("t-a", v, 5, exact=True)]
    want = [idx.chunks[i].id for i in np.argsort(-(idx.vectors @ v))[:5]]
    assert got[0] == want[0] and len(set(got) & set(want)) >= 4


def test_audit_is_kept_once_per_request(store):
    assert store.audit("t-a", "r-1", "q", "answer", None, ["guard"], "sim", 1.0)
    assert not store.audit("t-a", "r-1", "q", "answer", None, ["guard"], "sim", 1.0)
    assert len(store.recent_audit("t-a")) == 1
