# 2. Hybrid retrieval, metadata filters and a learned reranker

Status: accepted

## Context
Questions name products in many spellings (`VD 340`, `vd-340`, by order number), mix German and
English, and depend on firmware. Manuals cover a series of two or three models per document.

## Decision
- Lexical (BM25) and dense search fused with reciprocal rank fusion.
- Filters on product and edition before ranking. The edition comes from the firmware the question
  names (`firmwareToRevision` in config), otherwise the current edition.
- A logistic-regression reranker over 13 features, trained on separate training seeds only.
- When the filters leave nothing (7% of documents have missing index metadata), search once more
  without filters and let the verifier check the edition from the passage's own breadcrumb.

## Consequences
- On the dev seeds, vector-only search is level with hybrid (96.6% against 96.5% correct) and keyword-only
  is 1.3 points lower. We keep hybrid because part numbers, fault codes and order numbers are exact strings
  that dense embeddings of a hosted model may blur; the lab's LSA embeddings include character n-grams,
  which flatters vector search here. This is reported, not hidden.
- Filters are worth 4.0 points and the reranker 3.7 points of correct answers.
