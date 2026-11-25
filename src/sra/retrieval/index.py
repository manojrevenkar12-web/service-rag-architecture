"""Lexical (BM25) and dense (LSA embedding) indexes over a set of chunks.

The dense embedder is fitted on the corpus itself: TF-IDF over word and character n-grams, reduced
by truncated SVD and L2-normalised. It is a stand-in for a hosted embedding model (see
sra.retrieval.embedders for the hosted adapter); the interface is the same.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import sparse
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion

from sra.ingest.chunking import Chunk
from sra.retrieval.text import normalise_models, tokens


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.2, b: float = 0.75) -> None:
        vocab: dict[str, int] = {}
        rows, cols, vals = [], [], []
        lengths = np.zeros(len(docs))
        for i, toks in enumerate(docs):
            lengths[i] = len(toks)
            counts: dict[int, int] = {}
            for t in toks:
                j = vocab.setdefault(t, len(vocab))
                counts[j] = counts.get(j, 0) + 1
            for j, c in counts.items():
                rows.append(i)
                cols.append(j)
                vals.append(c)
        tf = sparse.csr_matrix((vals, (rows, cols)), shape=(len(docs), len(vocab)), dtype=np.float64)
        df = np.bincount(cols, minlength=len(vocab))
        n = len(docs)
        self.idf = np.log(1 + (n - df + 0.5) / (df + 0.5))
        avg = lengths.mean() if n else 1.0
        tf = tf.tocoo()
        norm = k1 * (1 - b + b * lengths[tf.row] / avg)
        weighted = tf.data * (k1 + 1) / (tf.data + norm) * self.idf[tf.col]
        self.matrix = sparse.csc_matrix((weighted, (tf.row, tf.col)), shape=tf.shape)
        self.vocab = vocab

    def scores(self, query_tokens: list[str]) -> np.ndarray:
        cols = [self.vocab[t] for t in set(query_tokens) if t in self.vocab]
        if not cols:
            return np.zeros(self.matrix.shape[0])
        return np.asarray(self.matrix[:, cols].sum(axis=1)).ravel()


class LsaEmbedder:
    """Corpus-fitted embeddings: word and character n-gram TF-IDF, then SVD to `dims`."""

    def __init__(self, dims: int = 256, seed: int = 0) -> None:
        self.dims = dims
        self.seed = seed
        self.features = FeatureUnion([
            ("words", TfidfVectorizer(preprocessor=normalise_models, lowercase=True, ngram_range=(1, 2), min_df=1, sublinear_tf=True)),
            ("chars", TfidfVectorizer(preprocessor=lambda s: normalise_models(s).lower(), analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True)),
        ])
        self.svd = TruncatedSVD(n_components=dims, random_state=seed)

    def fit(self, texts: list[str]) -> LsaEmbedder:
        x = self.features.fit_transform(texts)
        self.svd.fit(x)
        return self

    def embed(self, texts: list[str]) -> np.ndarray:
        v = self.svd.transform(self.features.transform(texts))
        norms = np.linalg.norm(v, axis=1, keepdims=True)
        return v / np.maximum(norms, 1e-12)


@dataclass
class Index:
    chunks: list[Chunk]
    bm25: BM25
    embedder: LsaEmbedder
    vectors: np.ndarray

    @classmethod
    def build(cls, chunks: list[Chunk], dims: int = 256) -> Index:
        texts = [c.text for c in chunks]
        embedder = LsaEmbedder(dims).fit(texts)
        return cls(chunks, BM25([tokens(t) for t in texts]), embedder, embedder.embed(texts))

    def lexical(self, text: str) -> np.ndarray:
        return self.bm25.scores(tokens(text))

    def dense(self, text: str) -> np.ndarray:
        return self.vectors @ self.embedder.embed([text])[0]


def top(scores: np.ndarray, k: int, allowed: np.ndarray | None = None) -> np.ndarray:
    s = scores if allowed is None else np.where(allowed, scores, -np.inf)
    k = min(k, int(np.isfinite(s).sum()))
    if k <= 0:
        return np.array([], dtype=int)
    idx = np.argpartition(-s, k - 1)[:k]
    return idx[np.argsort(-s[idx], kind="stable")]


def rrf(rankings: list[np.ndarray], k: int = 60) -> dict[int, float]:
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, i in enumerate(ranking):
            fused[int(i)] = fused.get(int(i), 0.0) + 1.0 / (k + rank + 1)
    return fused
