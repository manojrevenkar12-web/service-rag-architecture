"""Retrieval designs as settings: chunking, lexical/dense/hybrid, metadata filters, reranker, k."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sra.retrieval.index import Index, rrf, top
from sra.retrieval.query import ParsedQuery
from sra.retrieval.rerank import Reranker, features


@dataclass(frozen=True)
class RetrievalSettings:
    mode: str = "hybrid"  # lexical, dense, hybrid
    filters: bool = True
    rerank: bool = True
    candidates: int = 60
    k: int = 5
    current_revision: str = "B"


@dataclass
class Hit:
    index: int
    score: float
    features: np.ndarray | None = None


def candidate_mask(index: Index, q: ParsedQuery, s: RetrievalSettings) -> np.ndarray | None:
    """Keep chunks about the asked product (or its family, for fault codes) and edition."""
    if not s.filters or not q.model_known:
        return None
    if q.code:
        mask = np.array([bool(c.models) and c.models[0].split("-")[0] == q.family_prefix for c in index.chunks])
    else:
        mask = np.array([q.model in c.models for c in index.chunks])
    mask &= np.array([c.revision == (q.revision or s.current_revision) for c in index.chunks])
    return mask


def retrieve(index: Index, q: ParsedQuery, s: RetrievalSettings, reranker: Reranker | None = None) -> list[Hit]:
    allowed = candidate_mask(index, q, s)
    if allowed is not None and not allowed.any():
        return []
    lex = index.lexical(q.text) if s.mode in ("lexical", "hybrid") else None
    den = index.dense(q.text) if s.mode in ("dense", "hybrid") else None
    if s.mode == "lexical":
        assert lex is not None
        ranked = [(int(i), float(lex[i])) for i in top(lex, s.candidates, allowed)]
    elif s.mode == "dense":
        assert den is not None
        ranked = [(int(i), float(den[i])) for i in top(den, s.candidates, allowed)]
    else:
        assert lex is not None and den is not None
        fused = rrf([top(lex, s.candidates, allowed), top(den, s.candidates, allowed)])
        ranked = sorted(fused.items(), key=lambda kv: (-kv[1], kv[0]))[: s.candidates]
    if s.rerank and reranker is not None and ranked:
        feats = np.vstack([features(index, i, q, lex, den, rank) for rank, (i, _) in enumerate(ranked)])
        scores = reranker.score(feats)
        order = np.argsort(-scores, kind="stable")
        return [Hit(ranked[j][0], float(scores[j]), feats[j]) for j in order[: s.k]]
    return [Hit(i, sc) for i, sc in ranked[: s.k]]
