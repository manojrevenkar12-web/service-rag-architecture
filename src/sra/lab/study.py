"""Runs every design on the same simulated company and grades each answer against the truth."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from sra.agent.graph import AgentSettings, Answer, ServiceAssistant
from sra.agent.tools import DictRegistry, DictStock
from sra.ingest.chunking import Chunk, fixed_chunks, structure_chunks
from sra.lab.simllm import SimulatedReader
from sra.retrieval.index import Index
from sra.retrieval.pipeline import RetrievalSettings, retrieve
from sra.retrieval.query import parse
from sra.retrieval.rerank import Reranker, features
from sra.world.catalog import ROOT, build_catalog, load_world_config
from sra.world.manuals import Document, render
from sra.world.queries import Query, make_queries

ANSWERABLE = ("attribute", "variantAttribute", "revision", "errorCode", "partAndStock")


def load_json(name: str) -> dict:
    return json.loads((ROOT / "config" / name).read_text())


@dataclass
class Design:
    id: str
    label: str
    kind: str
    chunking: str
    mode: str
    filters: bool
    rerank: bool
    k: int
    retrieval: bool
    guard: bool
    unknownCheck: bool
    tools: bool
    verify: bool


def load_designs(path: Path | None = None) -> list[Design]:
    raw = json.loads((path or ROOT / "config" / "designs.json").read_text())["designs"]
    by_id: dict[str, dict] = {}
    for d in raw:
        base = dict(by_id[d["base"]]) if "base" in d else {}
        merged = {**base, **{k: v for k, v in d.items() if k != "base"}}
        by_id[d["id"]] = merged
    return [Design(**d) for d in by_id.values()]


@dataclass
class World:
    seed: int
    docs: list[Document]
    queries: list[Query]
    stock: dict
    warehouses: list[str]
    registry: DictRegistry
    indexes: dict[str, Index] = field(default_factory=dict)


def build_world(seed: int, split: str, product: dict) -> World:
    cfg = load_world_config()
    cat = build_catalog(seed, cfg)
    docs = render(cat, cfg["metadataDefectShare"], seed)
    registry = DictRegistry({m.name for m in cat.models}, {m.order_number: m.name for m in cat.models})
    w = World(seed, docs, make_queries(seed, split, cat, cfg), cat.stock, cat.warehouses, registry)
    ch = product["chunking"]
    for name in ("fixed", "structure"):
        chunks: list[Chunk] = []
        for d in docs:
            if name == "fixed":
                chunks += fixed_chunks(d, ch["fixedSize"], ch["fixedOverlap"])
            else:
                chunks += structure_chunks(d, ch["structureMaxChars"])
        w.indexes[name] = Index.build(chunks, product["retrieval"]["embeddingDims"])
    return w


def train_reranker(seeds: list[int], product: dict) -> tuple[Reranker, dict]:
    xs, ys = [], []
    s = RetrievalSettings("hybrid", True, False, product["retrieval"]["candidates"], product["retrieval"]["candidates"])
    for seed in seeds:
        w = build_world(seed, "train", product)
        idx = w.indexes["structure"]
        known = w.registry.models
        for q in w.queries:
            if q.kind not in ANSWERABLE:
                continue
            p = parse(q.text, known, w.warehouses, product["firmwareToRevision"], product["glossary"])
            lex, den = idx.lexical(q.text), idx.dense(q.text)
            for rank, h in enumerate(retrieve(idx, p, s)):
                xs.append(features(idx, h.index, p, lex, den, rank))
                ys.append(int(bool(idx.chunks[h.index].facts & q.relevant_facts)))
    x, y = np.vstack(xs), np.array(ys)
    rr = Reranker(product["reranker"]["C"]).fit(x, y)
    return rr, {"examples": int(len(y)), "positives": int(y.sum()), "weights": rr.weights()}


NUM = re.compile(r"-?\d+(?:[.,]\d+)?")


def same_value(answer: str | None, truth: float | str | None) -> bool:
    if answer is None or truth is None:
        return False
    if isinstance(truth, str):
        return answer.strip().upper() == truth.upper()
    m = NUM.search(answer)
    return m is not None and abs(float(m.group(0).replace(",", ".")) - float(truth)) < 1e-6


def norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def grade(q: Query, a: Answer, other_revision_value: float | str | None) -> dict:
    g = {"kind": q.kind, "status": a.status, "correct": False, "wrong": False, "revisionError": False}
    if q.kind == "unsafe":
        g["correct"] = a.status == "refuse"
        g["wrong"] = a.status == "answer"
        return g
    if q.kind == "unanswerable":
        g["correct"] = a.status in ("abstain", "refuse")
        g["wrong"] = a.status == "answer"
        return g
    if a.status != "answer":
        return g
    if q.kind == "errorCode":
        ok = a.value is not None and norm(a.value) in {norm(t) for t in q.answer_texts}
    elif q.kind == "partAndStock":
        ok = a.part == q.part and a.stock == q.stock and a.value is not None and norm(a.value) in {norm(t) for t in q.answer_texts}
    else:
        ok = same_value(a.value, q.answer_value)
        if not ok and q.kind == "revision" and same_value(a.value, other_revision_value):
            g["revisionError"] = True
    g["correct"] = ok
    g["wrong"] = not ok
    return g


def run_seed(seed: int, split: str, designs: list[Design], reranker: Reranker, product: dict) -> dict:
    w = build_world(seed, split, product)
    cfg = load_world_config()
    reader = SimulatedReader(seed, {q.text: q for q in w.queries}, cfg["llm"])
    cat = build_catalog(seed, cfg)
    out: dict[str, dict] = {}
    for d in designs:
        settings = AgentSettings(
            RetrievalSettings(d.mode, d.filters, d.rerank, product["retrieval"]["candidates"], d.k, product["retrieval"]["currentRevision"]),
            use_retrieval=d.retrieval, guard=d.guard, unknown_product_check=d.unknownCheck, tools=d.tools, verify=d.verify,
            max_retries=product["agent"]["maxRetries"],
        )
        stock = DictStock(w.stock)
        idx = w.indexes[d.chunking]
        assistant = ServiceAssistant(idx, reader, stock, w.registry, settings, reranker if d.rerank else None, w.warehouses,
                                     product["firmwareToRevision"], product["glossary"])
        rows = []
        started = time.perf_counter()
        for q in w.queries:
            a = assistant.ask(q.text)
            other = None
            if q.kind == "revision" and q.model and q.attribute:
                f = cat.model(q.model).value(q.attribute, "B" if q.revision == "A" else "A", q.variant)
                other = f.value if f else None
            g = grade(q, a, other)
            hits = [idx.chunks[i] for i in _hit_indexes(idx, a)]
            g["recall"] = None
            if q.kind in ANSWERABLE and d.retrieval:
                g["recall"] = any(c.facts & q.relevant_facts for c in hits[:5])
                rank = next((r for r, c in enumerate(hits) if c.facts & q.relevant_facts), None)
                g["rr"] = 1.0 / (rank + 1) if rank is not None else 0.0
            if a.status == "answer" and a.citation:
                cited = next((c for c in idx.chunks if c.id == a.citation), None)
                g["citationOk"] = bool(cited and cited.facts & q.relevant_facts) if q.kind in ANSWERABLE else False
            g["stockFromTool"] = a.stock_from_tool
            g["llmCalls"] = a.llm_calls
            g["contextChars"] = a.context_chars
            rows.append(g)
        out[d.id] = summarise(rows, product, time.perf_counter() - started)
    return out


def _hit_indexes(idx: Index, a: Answer) -> list[int]:
    pos = {c.id: i for i, c in enumerate(idx.chunks)} if a.passages else {}
    return [pos[p] for p in a.passages if p in pos]


def summarise(rows: list[dict], product: dict, seconds: float) -> dict:
    def share(pred, among) -> float:
        sel = [r for r in rows if among(r)]
        return sum(1 for r in sel if pred(r)) / len(sel) if sel else float("nan")

    answerable = lambda r: r["kind"] in ANSWERABLE  # noqa: E731
    c = product["cost"]
    calls = np.mean([r["llmCalls"] for r in rows])
    tokens = np.mean([r["contextChars"] for r in rows]) / c["charsPerToken"]
    cost = (tokens * c["inputEurPerMillionTokens"] + calls * c["outputTokensPerCall"] * c["outputEurPerMillionTokens"]) / 1e6 * 1000
    recall = [r["recall"] for r in rows if r.get("recall") is not None]
    rr = [r["rr"] for r in rows if "rr" in r]
    cites = [r["citationOk"] for r in rows if "citationOk" in r]
    by_kind = {}
    for kind in sorted({r["kind"] for r in rows}):
        sel = [r for r in rows if r["kind"] == kind]
        by_kind[kind] = {"n": len(sel), "correct": sum(r["correct"] for r in sel) / len(sel), "wrong": sum(r["wrong"] for r in sel) / len(sel)}
    return {
        "questions": len(rows),
        "correctRate": share(lambda r: r["correct"], answerable),
        "wrongRate": share(lambda r: r["wrong"], answerable),
        "abstainRate": share(lambda r: r["status"] != "answer", answerable),
        "unanswerableHandled": share(lambda r: r["correct"], lambda r: r["kind"] == "unanswerable"),
        "unsafeRefused": share(lambda r: r["correct"], lambda r: r["kind"] == "unsafe"),
        "wrongPer1000": 1000 * sum(r["wrong"] for r in rows) / len(rows),
        "revisionErrors": share(lambda r: r["revisionError"], lambda r: r["kind"] == "revision"),
        "recallAt5": float(np.mean(recall)) if recall else float("nan"),
        "mrr": float(np.mean(rr)) if rr else float("nan"),
        "citationPrecision": float(np.mean(cites)) if cites else float("nan"),
        "stockFromTool": share(lambda r: r["stockFromTool"], lambda r: r["kind"] == "partAndStock" and r["status"] == "answer"),
        "llmCallsPerQuestion": float(calls),
        "contextTokensPerQuestion": float(tokens),
        "costPer1000Eur": float(cost),
        "byKind": by_kind,
    }
