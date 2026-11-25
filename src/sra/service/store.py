"""PostgreSQL + pgvector: the store of record for passages, their vectors and the audit log.

One table holds every tenant's passages; every query carries the tenant from the API key, so one
tenant never reads another's manuals. HNSW over cosine distance; product and edition filters run in
the same query, with pgvector's iterative scan so a narrow filter still returns k rows.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence

import numpy as np
import psycopg
from pgvector.psycopg import register_vector

from sra.ingest.chunking import Chunk


def schema(dims: int, m: int, ef_construction: int) -> list[str]:
    return [
        "CREATE EXTENSION IF NOT EXISTS vector",
        f"""CREATE TABLE IF NOT EXISTS passages (
            tenant text NOT NULL,
            id text NOT NULL,
            doc_id text NOT NULL,
            models text[] NOT NULL,
            family text NOT NULL,
            revision text NOT NULL,
            lang text NOT NULL,
            section text NOT NULL,
            kind text NOT NULL,
            body text NOT NULL,
            embedding vector({dims}) NOT NULL,
            PRIMARY KEY (tenant, id))""",
        f"CREATE INDEX IF NOT EXISTS passages_hnsw ON passages USING hnsw (embedding vector_cosine_ops) WITH (m = {m}, ef_construction = {ef_construction})",
        "CREATE INDEX IF NOT EXISTS passages_models ON passages USING gin (models)",
        "CREATE INDEX IF NOT EXISTS passages_tenant_rev ON passages (tenant, revision)",
        """CREATE TABLE IF NOT EXISTS audit (
            id bigserial PRIMARY KEY,
            at timestamptz NOT NULL DEFAULT now(),
            tenant text NOT NULL,
            request_id text NOT NULL UNIQUE,
            question text NOT NULL,
            status text NOT NULL,
            citation text,
            steps jsonb NOT NULL,
            reader text NOT NULL,
            latency_ms double precision NOT NULL)""",
    ]


class PgStore:
    def __init__(self, dsn: str, dims: int, cfg: dict) -> None:
        self.conn = psycopg.connect(dsn, autocommit=True)
        self.dims = dims
        self.cfg = cfg
        for stmt in schema(dims, cfg["hnswM"], cfg["efConstruction"]):
            self.conn.execute(stmt)
        register_vector(self.conn)

    def upsert(self, tenant: str, chunks: Sequence[Chunk], vectors: np.ndarray) -> int:
        """Idempotent: running the same ingest twice leaves the same rows."""
        with self.conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO passages (tenant, id, doc_id, models, family, revision, lang, section, kind, body, embedding)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (tenant, id) DO UPDATE SET body = EXCLUDED.body, embedding = EXCLUDED.embedding,
                     models = EXCLUDED.models, revision = EXCLUDED.revision, section = EXCLUDED.section""",
                [(tenant, c.id, c.doc_id, list(c.models), c.family, c.revision, c.lang, c.section, c.kind, c.text,
                  vectors[i].astype(np.float32)) for i, c in enumerate(chunks)],
            )
        return len(chunks)

    def count(self, tenant: str) -> int:
        row = self.conn.execute("SELECT count(*) FROM passages WHERE tenant = %s", (tenant,)).fetchone()
        return int(row[0]) if row else 0

    def search(self, tenant: str, vector: np.ndarray, k: int, model: str | None = None, revision: str | None = None,
               exact: bool = False) -> list[tuple[str, float]]:
        where, args = ["tenant = %s"], [tenant]
        if model:
            where.append("models @> ARRAY[%s]")
            args.append(model)
        if revision:
            where.append("revision = %s")
            args.append(revision)
        v = vector.astype(np.float32)
        # "+ 0" stops the planner from using the HNSW index: exact search, the reference for recall.
        order = "(embedding <=> %s) + 0" if exact else "embedding <=> %s"
        sql = f"SELECT id, 1 - (embedding <=> %s) FROM passages WHERE {' AND '.join(where)} ORDER BY {order} LIMIT %s"
        with self.conn.transaction():
            self.conn.execute(f"SET LOCAL hnsw.ef_search = {int(self.cfg['efSearch'])}")
            self.conn.execute(f"SET LOCAL hnsw.iterative_scan = {self.cfg['iterativeScan']}")
            rows = self.conn.execute(sql, [v, *args, v, k]).fetchall()
        return [(r[0], float(r[1])) for r in rows]

    def audit(self, tenant: str, request_id: str, question: str, status: str, citation: str | None, steps: list[str],
              reader: str, latency_ms: float) -> bool:
        """Kept once per request id: a retried request does not write a second row."""
        cur = self.conn.execute(
            """INSERT INTO audit (tenant, request_id, question, status, citation, steps, reader, latency_ms)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (request_id) DO NOTHING""",
            (tenant, request_id, question, status, citation, json.dumps(steps), reader, latency_ms),
        )
        return cur.rowcount == 1

    def recent_audit(self, tenant: str, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT at, request_id, question, status, citation, steps, reader, latency_ms FROM audit WHERE tenant = %s ORDER BY id DESC LIMIT %s",
            (tenant, limit),
        ).fetchall()
        keys = ["at", "requestId", "question", "status", "citation", "steps", "reader", "latencyMs"]
        return [dict(zip(keys, (r[0].isoformat(), *r[1:]), strict=True)) for r in rows]


def ingest_demo(seed: int, tenant: str = "demo") -> str:
    from sra.lab.study import build_world, load_json

    product = load_json("product.json")
    w = build_world(seed, "demo", product)
    idx = w.indexes["structure"]
    store = PgStore(os.environ["SRA_DATABASE_URL"], idx.vectors.shape[1], product["service"]["pgvector"])
    n = store.upsert(tenant, idx.chunks, idx.vectors)
    return f"{n} passages for tenant {tenant}; {store.count(tenant)} in the store"
