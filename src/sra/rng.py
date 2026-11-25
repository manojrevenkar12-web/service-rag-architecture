"""Seeded randomness in named streams: a stream depends only on its seed and keys, so every
design sees the same corpus, questions and model behaviour (same luck)."""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")


class Rng:
    def __init__(self, seed: int, *keys: object) -> None:
        digest = hashlib.sha256(repr((seed, *keys)).encode()).digest()
        self._seed = seed
        self._keys = keys
        self._r = random.Random(int.from_bytes(digest[:8], "big"))

    def child(self, *keys: object) -> Rng:
        return Rng(self._seed, *self._keys, *keys)

    def random(self) -> float:
        return self._r.random()

    def randint(self, a: int, b: int) -> int:
        return self._r.randint(a, b)

    def choice(self, seq: Sequence[T]) -> T:
        return self._r.choice(seq)

    def sample(self, seq: Sequence[T], k: int) -> list[T]:
        return self._r.sample(list(seq), k)

    def weighted(self, options: dict[str, float]) -> str:
        return self._r.choices(list(options), weights=list(options.values()))[0]
