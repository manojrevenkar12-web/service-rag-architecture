"""Measured, not simulated: retrieval latency in process, and pgvector HNSW recall and latency against exact search.

Needs SRA_DATABASE_URL for the pgvector part. Writes reports/bench.json through `sra lab bench`.
"""

from __future__ import annotations

import os
import platform
import time

import numpy as np

from sra.lab.study import build_world, load_json
from sra.retrieval.pipeline import RetrievalSettings, retrieve
from sra.retrieval.query import parse


def pct(xs: list[float], p: float) -> float:
    return float(np.percentile(np.array(xs), p))


def bench(seeds: tuple[int, ...] = (4242,), k: int = 10, queries: int = 300, models_per_family: int = 88) -> dict:
    product = load_json("product.json")
    w = build_world(seeds[0], "demo", product)
    idx = w.indexes["structure"]
    s = RetrievalSettings("hybrid", True, False, product["retrieval"]["candidates"], 5, product["retrieval"]["currentRevision"])
    times = []
    for q in w.queries[:queries]:
        t = time.perf_counter()
        retrieve(idx, parse(q.text, w.registry.models, w.warehouses, product["firmwareToRevision"], product["glossary"]), s)
        times.append((time.perf_counter() - t) * 1000)
    out: dict = {"machine": f"{platform.machine()}, {os.cpu_count()} CPUs, Python {platform.python_version()}",
                 "retrievalMs": {"p50": pct(times, 50), "p95": pct(times, 95), "n": len(times)}, "pgvector": None}
    dsn = os.environ.get("SRA_DATABASE_URL")
    if not dsn:
        return out
    from sra.ingest.chunking import structure_chunks
    from sra.retrieval.index import Index
    from sra.service.store import PgStore
    from sra.world.catalog import build_catalog, load_world_config
    from sra.world.manuals import render
    from sra.world.queries import make_queries

    # A larger maker for the store: the most models per family the catalogue can name, one embedder
    # fitted on the whole corpus (as a deployment would), all passages in one tenant.
    cfg = load_world_config()
    cfg["modelsPerFamily"] = models_per_family
    cat = build_catalog(seeds[0], cfg)
    chunks = [c for d in render(cat, cfg["metadataDefectShare"], seeds[0]) for c in structure_chunks(d, product["chunking"]["structureMaxChars"])]
    big = Index.build(chunks, product["retrieval"]["embeddingDims"])
    store = PgStore(dsn, big.vectors.shape[1], product["service"]["pgvector"])
    store.conn.execute("DELETE FROM passages WHERE tenant = 'bench'")
    # Index settings come from config; rebuild so a changed setting is what gets measured.
    store.conn.execute("DROP INDEX IF EXISTS passages_hnsw")
    store.upsert("bench", big.chunks, big.vectors)
    pv = product["service"]["pgvector"]
    store.conn.execute(f"CREATE INDEX passages_hnsw ON passages USING hnsw (embedding vector_cosine_ops) "
                       f"WITH (m = {int(pv['hnswM'])}, ef_construction = {int(pv['efConstruction'])})")
    store.conn.execute("VACUUM ANALYZE passages")
    twins = 0
    for i in range(0, len(big.vectors), 1000):
        sims = big.vectors[i: i + 1000] @ big.vectors.T
        sims[np.arange(sims.shape[0]), np.arange(i, i + sims.shape[0])] = 0
        twins += int((sims.max(axis=1) > 0.98).sum())
    known = {m.name for m in cat.models}
    probes = []
    for q in make_queries(seeds[0], "bench", cat, cfg)[:queries]:
        pq = parse(q.text, known, cat.warehouses, product["firmwareToRevision"], product["glossary"])
        probes.append((q.text, pq.model if pq.model_known and not pq.code else None))
    rows = store.count("bench")
    recalls, hnsw_ms, exact_ms = [], [], []
    by_filter: dict[bool, list[float]] = {True: [], False: []}
    for text, model in probes:  # filtered by product when the question names a known one, as the service does
        v = big.embedder.embed([text])[0]
        t = time.perf_counter()
        approx = store.search("bench", v, k, model)
        hnsw_ms.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        exact = store.search("bench", v, k, model, exact=True)
        exact_ms.append((time.perf_counter() - t) * 1000)
        if exact:
            # Ties count: a hit scoring at least the k-th exact score is a correct hit.
            floor = exact[-1][1] - 1e-6
            recalls.append(min(1.0, sum(s >= floor for _, s in approx) / len(exact)))
            by_filter[model is not None].append(recalls[-1])
    out["pgvector"] = {"rows": rows, "k": k, "queries": len(recalls), "hnswRecall": float(np.mean(recalls)),
                       "recallUnfiltered": float(np.mean(by_filter[False])), "recallFiltered": float(np.mean(by_filter[True])),
                       "filteredQueries": len(by_filter[True]), "nearTwinShare": twins / len(big.vectors),
                       "p50Ms": pct(hnsw_ms, 50), "p95Ms": pct(hnsw_ms, 95), "exactP95Ms": pct(exact_ms, 95),
                       "settings": product["service"]["pgvector"]}
    return out
