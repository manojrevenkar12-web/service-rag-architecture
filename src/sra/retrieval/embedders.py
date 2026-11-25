"""Embedders behind one interface: fit on a corpus (or not), embed texts to unit vectors.

The lab uses LsaEmbedder (sra.retrieval.index) so results reproduce offline. A deployment swaps in a
hosted model; HostedEmbedder speaks the OpenAI-compatible embeddings API (Azure OpenAI, or a
self-hosted model behind vLLM / TEI). It is not exercised against a live endpoint in this repo.
"""

from __future__ import annotations

from typing import Protocol

import httpx
import numpy as np


class Embedder(Protocol):
    def fit(self, texts: list[str]) -> Embedder: ...
    def embed(self, texts: list[str]) -> np.ndarray: ...


class HostedEmbedder:
    def __init__(self, url: str, api_key: str, dims: int, client: httpx.Client | None = None, batch: int = 64) -> None:
        self.url = url
        self.api_key = api_key
        self.dims = dims
        self.client = client or httpx.Client(timeout=30)
        self.batch = batch

    def fit(self, texts: list[str]) -> HostedEmbedder:
        return self

    def embed(self, texts: list[str]) -> np.ndarray:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch):
            res = self.client.post(self.url, headers={"api-key": self.api_key, "authorization": f"Bearer {self.api_key}"},
                                   json={"input": texts[i: i + self.batch], "dimensions": self.dims})
            res.raise_for_status()
            out += [d["embedding"] for d in sorted(res.json()["data"], key=lambda d: d["index"])]
        v = np.asarray(out, dtype=np.float64)
        return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)
