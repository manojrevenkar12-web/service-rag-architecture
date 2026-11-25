"""The service: ask, search, passages, audit. The tenant comes from the API key, never from the request body.

Reader: Claude when ANTHROPIC_API_KEY is set; otherwise the lab's simulated reader, which only knows
the demo world's questions (GET /v1/questions lists them).
Store: PostgreSQL + pgvector when SRA_DATABASE_URL is set; otherwise in memory.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass, field

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from sra.agent.graph import AgentSettings, ServiceAssistant
from sra.agent.llm import ClaudeReader, Reader
from sra.agent.tools import DictStock
from sra.lab.simllm import SimulatedReader
from sra.lab.study import World, build_world, load_json
from sra.retrieval.index import top
from sra.retrieval.pipeline import RetrievalSettings
from sra.retrieval.rerank import Reranker
from sra.service.redact import redact
from sra.world.catalog import ROOT, load_world_config


class AskBody(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class SearchBody(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    model: str | None = None
    revision: str | None = None
    k: int = Field(default=5, ge=1, le=50)


@dataclass
class Tenant:
    id: str
    world: World | None
    assistant: ServiceAssistant | None
    audit: list[dict] = field(default_factory=list)
    seen: dict[str, dict] = field(default_factory=dict)
    window: list[float] = field(default_factory=list)


def _keys() -> dict[str, str]:
    """SRA_API_KEYS="tenant:key,tenant:key" -> {sha256(key): tenant}."""
    raw = os.environ.get("SRA_API_KEYS", "demo:demo-key,acme:acme-key")
    out = {}
    for pair in raw.split(","):
        tenant, key = pair.split(":", 1)
        out[hashlib.sha256(key.encode()).hexdigest()] = tenant
    return out


def create_app(product: dict | None = None, reader: Reader | None = None, store=None) -> FastAPI:
    product = product or load_json("product.json")
    svc = product["service"]
    keys = _keys()
    world = build_world(svc["demoSeed"], "demo", product)
    rr_path = ROOT / "reports" / "reranker.json"
    reranker = Reranker.from_json(json.loads(rr_path.read_text())) if rr_path.exists() else None
    if reader is None:
        key = os.environ.get("ANTHROPIC_API_KEY")
        reader = (ClaudeReader(key, product["reader"]["model"]) if key else
                  SimulatedReader(svc["demoSeed"], {q.text: q for q in world.queries}, load_world_config()["llm"]))
    settings = AgentSettings(RetrievalSettings("hybrid", True, reranker is not None, product["retrieval"]["candidates"], 5,
                                               product["retrieval"]["currentRevision"]), max_retries=product["agent"]["maxRetries"])
    assistant = ServiceAssistant(world.indexes["structure"], reader, DictStock(world.stock), world.registry, settings, reranker,
                                 world.warehouses, product["firmwareToRevision"], product["glossary"])
    tenants = {t: Tenant(t, world if t == svc["defaultTenant"] else None, assistant if t == svc["defaultTenant"] else None)
               for t in set(keys.values())}
    if store is None and os.environ.get("SRA_DATABASE_URL"):
        from sra.service.store import PgStore

        store = PgStore(os.environ["SRA_DATABASE_URL"], world.indexes["structure"].vectors.shape[1], svc["pgvector"])

    app = FastAPI(title="Service RAG", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])

    def tenant(x_api_key: str = Header(default="")) -> Tenant:
        digest = hashlib.sha256(x_api_key.encode()).hexdigest()
        match = next((t for h, t in keys.items() if hmac.compare_digest(h, digest)), None)
        if match is None:
            raise HTTPException(401, "Unknown API key.")
        t = tenants[match]
        now = time.monotonic()
        t.window = [s for s in t.window if now - s < 60]
        if len(t.window) >= svc["rateLimitPerMinute"]:
            raise HTTPException(429, "Too many requests for this tenant; try again in a minute.")
        t.window.append(now)
        return t

    def corpus(t: Tenant) -> tuple[World, ServiceAssistant]:
        if t.world is None or t.assistant is None:
            raise HTTPException(404, f"No manuals have been ingested for tenant {t.id}.")
        return t.world, t.assistant

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "reader": reader.name, "reranker": reranker is not None, "store": "pgvector" if store else "memory",
                "passages": len(world.indexes["structure"].chunks)}

    @app.get("/v1/questions")
    def questions(t: Tenant = Depends(tenant), limit: int = 40) -> list[dict]:
        w, _ = corpus(t)
        picked: dict[str, list] = {}
        for q in w.queries:
            picked.setdefault(q.kind, [])
            if len(picked[q.kind]) < max(1, limit // 7):
                picked[q.kind].append({"text": q.text, "kind": q.kind, "lang": q.lang})
        return [q for qs in picked.values() for q in qs]

    @app.post("/v1/ask")
    def ask(body: AskBody, t: Tenant = Depends(tenant), x_request_id: str | None = Header(default=None)) -> dict:
        w, a = corpus(t)
        rid = x_request_id or str(uuid.uuid4())
        if rid in t.seen:
            return t.seen[rid]
        started = time.perf_counter()
        ans = a.ask(body.question)
        ms = (time.perf_counter() - started) * 1000
        idx = w.indexes["structure"]
        by_id = {c.id: c for c in idx.chunks}
        cited = by_id.get(ans.citation) if ans.citation else None
        out = {"requestId": rid, "status": ans.status, "text": ans.text, "value": ans.value, "part": ans.part, "stock": ans.stock,
               "stockFromTool": ans.stock_from_tool, "line": ans.line, "problems": ans.problems, "steps": ans.steps, "latencyMs": round(ms, 1),
               "reader": reader.name,
               "citation": {"id": cited.id, "doc": cited.doc_id, "section": cited.section, "revision": cited.revision, "text": cited.text}
               if cited else None,
               "passages": [{"id": p, "section": by_id[p].section, "revision": by_id[p].revision} for p in ans.passages if p in by_id]}
        entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "requestId": rid,
                 "question": redact(body.question, svc["audit"]["redact"]), "status": ans.status, "citation": ans.citation,
                 "steps": ans.steps, "reader": reader.name, "latencyMs": round(ms, 1)}
        if store:
            store.audit(t.id, rid, entry["question"], ans.status, ans.citation, ans.steps, reader.name, ms)
        t.audit.insert(0, entry)
        del t.audit[200:]
        t.seen[rid] = out
        return out

    @app.post("/v1/search")
    def search(body: SearchBody, t: Tenant = Depends(tenant)) -> list[dict]:
        w, _ = corpus(t)
        idx = w.indexes["structure"]
        vec = idx.embedder.embed([body.query])[0]
        if store:
            hits = store.search(t.id, vec, body.k, body.model, body.revision)
            by_id = {c.id: c for c in idx.chunks}
            return [{"id": i, "score": round(s, 4), "section": by_id[i].section, "text": by_id[i].text} for i, s in hits if i in by_id]
        import numpy as np

        allowed = np.array([(body.model is None or body.model in c.models) and (body.revision is None or c.revision == body.revision)
                            for c in idx.chunks])
        scores = idx.vectors @ vec
        return [{"id": idx.chunks[i].id, "score": round(float(scores[i]), 4), "section": idx.chunks[i].section, "text": idx.chunks[i].text}
                for i in top(scores, body.k, allowed)]

    @app.get("/v1/passages/{pid}")
    def passage(pid: str, t: Tenant = Depends(tenant)) -> dict:
        w, _ = corpus(t)
        c = next((c for c in w.indexes["structure"].chunks if c.id == pid), None)
        if c is None:
            raise HTTPException(404, "No such passage.")
        return {"id": c.id, "doc": c.doc_id, "models": list(c.models), "revision": c.revision, "lang": c.lang, "section": c.section, "text": c.text}

    @app.get("/v1/audit")
    def audit(t: Tenant = Depends(tenant)) -> list[dict]:
        return store.recent_audit(t.id) if store else t.audit[:50]

    return app


def __getattr__(name: str):
    if name == "app":
        return create_app()
    raise AttributeError(name)
