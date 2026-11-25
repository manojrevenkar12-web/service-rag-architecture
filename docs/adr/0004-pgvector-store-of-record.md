# 4. PostgreSQL + pgvector as the store of record

Status: accepted

## Context
The options were a dedicated vector database or PostgreSQL with pgvector. The corpus is in the tens
of thousands to low millions of passages per customer, filters on product and edition are always
present, and the audit log must sit next to the data under the same backup and access rules.

## Decision
One `passages` table with a `tenant` column in the primary key, an HNSW index (cosine, m=32,
ef_construction=200, ef_search=400) and GIN on the models array. Filters run in the same SQL statement with
`hnsw.iterative_scan = relaxed_order` so a narrow filter still returns k rows. The audit table is in
the same database; a request id is written once.

## What the measurement changed
Manuals are templated: in a 6,219-passage corpus, 85% of passages have a near-twin (cosine above 0.98),
the same section for a sibling model with different numbers. With pgvector's default-like settings
(m=16, ef_construction=64, ef_search=80) HNSW found only 39% of the exact top 10 on unfiltered queries.
m=32, ef_construction=200, ef_search=400 restores 100% at a p95 of about 9 ms. Queries filtered by
product go through the GIN index and are ordered exactly (100% recall either way). At this corpus size
exact search is as fast as HNSW; the index matters at hundreds of thousands of passages, and its recall
must be measured on the customer's own manuals, not assumed.

## Consequences
- One system to operate, back up and secure; row-level security can be added on the tenant column.
- HNSW recall against exact search is measured (`sra lab bench`) and reported, not assumed.
- Past roughly 10–50 million vectors per tenant, or with heavy write rates, a dedicated engine or
  partitioning by tenant should be re-evaluated.
- The service ranks in process (BM25 + dense + reranker over the tenant's passages held in memory);
  `/v1/search` serves dense search with filters directly from pgvector.
