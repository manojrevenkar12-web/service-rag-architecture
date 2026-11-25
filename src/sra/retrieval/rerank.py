"""A learned reranker: logistic regression over features a cross-encoder would otherwise learn,
trained on a separate set of judged questions (the training split), never on dev or held-out."""

from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression

from sra.retrieval.query import ParsedQuery
from sra.retrieval.text import tokens

FEATURES = ["rank", "lexical", "dense", "model", "family", "revision", "lang", "variant", "code", "overlap", "history", "table", "param"]


def features(index, i: int, q: ParsedQuery, lex: np.ndarray | None, den: np.ndarray | None, rank: int) -> np.ndarray:
    c = index.chunks[i]
    qt = set(tokens(q.text))
    ct = set(tokens(c.text))
    lmax = float(lex.max()) if lex is not None and lex.max() > 0 else 1.0
    params = {t for t in qt if t.startswith("p") and t[1:].isdigit()}
    return np.array([
        1.0 / (1 + rank),
        (float(lex[i]) / lmax) if lex is not None else 0.0,
        float(den[i]) if den is not None else 0.0,
        float(q.model is not None and (q.model in c.models or q.model in c.text)),
        float(q.family_prefix is not None and f"{q.family_prefix}-" in c.text),
        float(c.revision == (q.revision or "B")),
        float(c.lang == q.lang),
        float(q.variant is not None and q.variant.split()[0].replace(".", ",") in c.text.replace(".", ",")),
        float(q.code is not None and q.code in c.text),
        len(qt & ct) / max(1, len(qt)),
        float(c.kind == "history"),
        float(c.kind == "table"),
        float(bool(params & ct)),
    ])


class Reranker:
    def __init__(self, c: float = 1.0) -> None:
        self.model = LogisticRegression(C=c, max_iter=2000)

    def fit(self, x: np.ndarray, y: np.ndarray) -> Reranker:
        self.model.fit(x, y)
        return self

    def score(self, x: np.ndarray) -> np.ndarray:
        return self.model.decision_function(x)

    def to_json(self) -> dict:
        return {"features": list(FEATURES), "coef": [float(w) for w in self.model.coef_[0]], "intercept": float(self.model.intercept_[0])}

    @classmethod
    def from_json(cls, data: dict) -> Reranker:
        if list(data["features"]) != list(FEATURES):
            raise ValueError("reranker was trained on a different feature list")
        rr = cls()
        rr.model.classes_ = np.array([0, 1])
        rr.model.coef_ = np.array([data["coef"]])
        rr.model.intercept_ = np.array([data["intercept"]])
        return rr

    def weights(self) -> dict[str, float]:
        return {n: round(float(w), 3) for n, w in zip(FEATURES, self.model.coef_[0], strict=True)}
