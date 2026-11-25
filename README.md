# service-rag-architecture

A reference architecture for a GenAI service assistant at an industrial equipment maker: field
technicians ask about drives, compressors, chillers and robot controllers in German or English, and get
an answer from the right manual, for the right model, power rating and firmware edition, with the
passage it came from — or a plain "the manuals do not say". Requests to bypass safety functions are
refused. Spare-part stock comes from the ERP, never from text.

Retrieval (hybrid BM25 + vectors, product and edition filters, a learned reranker), agents in one
LangGraph state machine (safety guard, product registry, reader, ERP tool, verifier, fallback), and
PostgreSQL + pgvector as the store of record, behind a FastAPI service with tenants from API keys and
an audit log. A lab measures every architecture choice on the same simulated manuals, questions and
model behaviour.

## Results

<!-- results:start -->
Dev: 3 simulated equipment makers, 700 questions each, 1,180 manual passages per maker. Every design meets the same manuals, questions and model behaviour. **9 of 9 gates pass.**

| | Model alone | Naive RAG | Platform |
|---|---:|---:|---:|
| Answerable questions answered correctly | 4.2% | 54.7% | **96.5%** |
| Wrong answers per 1,000 questions | 601.0 | 402.4 | **0.5** |
| Firmware questions answered from the wrong edition | 0.9% | 16.4% | **0.0%** |
| Unknown products and undocumented values declined | 36.9% | 36.9% | **100.0%** |
| Requests to bypass safety functions refused | 54.8% | 54.8% | **100.0%** |
| Model cost per 1,000 questions | €1.68 | €4.23 | **€3.88** |

**All designs**

| Design | Correct | Wrong per 1,000 | Declined unanswerable | Unsafe refused | Wrong edition | Recall@5 | Citations right | € per 1,000 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| The model alone, no retrieval | 4.2% | 601.0 | 36.9% | 54.8% | 0.9% | – | – | 1.68 |
| Naive RAG: fixed chunks, vector search, top 5 | 54.7% | 402.4 | 36.9% | 54.8% | 16.4% | 79.2% | 74.6% | 4.23 |
| **Platform: structure chunks, hybrid search, filters, reranker, agents with tools and verifier** | 96.5% | 0.5 | 100.0% | 100.0% | 0.0% | 96.5% | 100.0% | 3.88 |
| Platform with fixed 800-character chunks | 87.9% | 0.5 | 100.0% | 100.0% | 0.0% | 87.9% | 99.9% | 7.11 |
| Platform with vector search only | 96.6% | 0.5 | 100.0% | 100.0% | 0.0% | 96.7% | 100.0% | 3.89 |
| Platform with keyword (BM25) search only | 95.2% | 0.5 | 100.0% | 100.0% | 0.0% | 95.3% | 100.0% | 4.06 |
| Platform without product and edition filters | 92.5% | 0.5 | 100.0% | 100.0% | 0.0% | 92.5% | 100.0% | 4.69 |
| Platform without the reranker | 92.8% | 0.5 | 100.0% | 100.0% | 0.0% | 92.9% | 100.0% | 4.21 |
| Platform without the verifier | 94.3% | 66.7 | 68.8% | 100.0% | 1.0% | 98.1% | 99.3% | 2.88 |
| Platform without the stock tool | 81.6% | 0.5 | 100.0% | 100.0% | 0.0% | 81.7% | 100.0% | 5.97 |
| Platform without the safety and unknown-product guards | 96.5% | 0.5 | 100.0% | 54.8% | 0.0% | 96.5% | 100.0% | 5.25 |
| Platform reading 10 passages instead of 5 | 96.9% | 0.5 | 100.0% | 100.0% | 0.0% | 96.6% | 100.0% | 5.77 |

**Platform by question type**

| Question type | Questions | Correct | Wrong |
|---|---:|---:|---:|
| attribute | 874 | 94.5% | 0.0% |
| errorCode | 328 | 100.0% | 0.0% |
| partAndStock | 170 | 100.0% | 0.0% |
| revision | 211 | 95.9% | 0.0% |
| unanswerable | 161 | 100.0% | 0.0% |
| unsafe | 86 | 100.0% | 0.0% |
| variantAttribute | 270 | 97.0% | 0.4% |

**Gates (dev)**

| Gate | Value | Limit | |
|---|---:|---|---|
| Answerable questions answered correctly | 0.9649 | ≥ 0.9 | pass |
| Wrong answers per 1,000 questions | 0.4762 | ≤ 10 | pass |
| Wrong answers, as a share of naive RAG's | 0.4762 | ≤ 0.05 × naive RAG (402.4) | pass |
| Unanswerable questions declined | 1.0 | ≥ 0.95 | pass |
| Requests to bypass safety functions refused | 1.0 | ≥ 0.98 | pass |
| Firmware-specific questions answered from the wrong edition | 0.0 | ≤ 0.01 | pass |
| Answers whose cited passage states the answer | 1.0 | ≥ 0.98 | pass |
| Answer-bearing passage among the 5 read | 0.9654 | ≥ 0.95 | pass |
| Model cost per 1,000 questions, € | 3.8819 | ≤ 6.0 | pass |

**Held-out (2 further makers, run once after the design was frozen): 9 of 9 gates pass.** Correct 58.4% → 97.1%; wrong per 1,000 385.0 → 0.7.

| Gate | Value | Limit | |
|---|---:|---|---|
| Answerable questions answered correctly | 0.9707 | ≥ 0.9 | pass |
| Wrong answers per 1,000 questions | 0.7143 | ≤ 10 | pass |
| Wrong answers, as a share of naive RAG's | 0.7143 | ≤ 0.05 × naive RAG (385.0) | pass |
| Unanswerable questions declined | 1.0 | ≥ 0.95 | pass |
| Requests to bypass safety functions refused | 1.0 | ≥ 0.98 | pass |
| Firmware-specific questions answered from the wrong edition | 0.0 | ≤ 0.01 | pass |
| Answers whose cited passage states the answer | 1.0 | ≥ 0.98 | pass |
| Answer-bearing passage among the 5 read | 0.9715 | ≥ 0.95 | pass |
| Model cost per 1,000 questions, € | 3.9651 | ≤ 6.0 | pass |

**Measured, not simulated** (x86_64, 2 CPUs, Python 3.13.18): hybrid retrieval in process p50 4.3 ms, p95 5.3 ms. pgvector over 6,219 passages, 85% of which have a near-twin: HNSW top-10 recall against exact search 100.0% unfiltered and 100.0% filtered by product, query p95 8.5 ms (exact search 8.0 ms). See ADR 4 for why the HNSW settings changed.
<!-- results:end -->

## Architecture

```mermaid
flowchart LR
  subgraph Ingest
    M[Manuals DE/EN<br/>editions A/B] --> C[Structure-aware chunks<br/>table header + breadcrumb]
    C --> E[Embedder]
    E --> PG[(PostgreSQL + pgvector<br/>passages, HNSW, GIN, tenant)]
    C --> BM[BM25]
  end
  subgraph Ask[Ask: LangGraph]
    G[Safety guard] --> U[Understand<br/>registry: order no. to model]
    U --> R[Retrieve<br/>hybrid + filters + reranker]
    R --> L[Model reads<br/>Claude]
    L --> T[ERP stock tool]
    T --> V[Code verifies]
    V -- rejected --> L
    V -- nothing left --> W[Widen once<br/>without filters] --> L
    V --> O[Respond with citation]
    G -- unsafe --> O
    U -- unknown product --> O
  end
  API[FastAPI<br/>tenant from API key] --> G
  O --> A[(Audit log<br/>redacted, once per request)]
  PG -.-> R
  BM -.-> R
```

| Layer | Choice | Why (ADR) |
|---|---|---|
| Chunking | Sections, table header repeated, breadcrumb from the document's own title | [3](docs/adr/0003-structure-aware-chunking.md) |
| Retrieval | BM25 + dense with RRF, product and edition filters, logistic-regression reranker | [2](docs/adr/0002-hybrid-retrieval-filters-reranker.md) |
| Agents | One LangGraph `StateGraph`; each agent a node, each node a setting | [5](docs/adr/0005-langgraph-agents-as-settings.md) |
| Trust | The model proposes value, passage and line; code accepts or rejects | [1](docs/adr/0001-the-model-reads-and-code-decides.md) |
| Store | PostgreSQL + pgvector, HNSW settings measured on templated manuals | [4](docs/adr/0004-pgvector-store-of-record.md) |
| Tenancy and audit | Tenant from the API key, redacted audit row once per request id | [7](docs/adr/0007-tenancy-and-audit.md) |
| Evidence | Simulated world with hidden truth, same luck, held-out run once | [6](docs/adr/0006-lab-simulated-world.md) |

## The lab

- **The world** (`src/sra/world`) generates an equipment maker: 5 product families, 16 models each, power
  ratings, two manual editions tied to firmware 3.x and 4.x, fault codes with remedies and spare parts,
  stock per warehouse. It renders series manuals (2–3 models per document) in German and English, with
  the traps real manuals have: tables for several models, a change log that repeats old values, 20% of
  series only in English, 7% of documents with missing index metadata, order numbers instead of model
  names. It writes 700 questions per maker with known answers, 55% in German, including questions about
  products that do not exist, values no manual states, and requests to bridge STO or the emergency stop.
- **The model** is simulated (`src/sra/lab/simllm.py`): it reads the way LLMs do — takes the first line that
  seems to answer, often without checking the model name, can read a change-log line, invents an answer
  when it finds nothing. Each draw is keyed by the question and the line, so every design meets the same
  behaviour.
- **Designs** (`config/designs.json`): the model alone, naive RAG, the platform, and nine ablations that
  each switch one part off. The reranker trains on training seeds; gates are set on dev seeds; held-out
  seeds are run once.

## Run it

```bash
python3.13 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
pytest -q                       # ~15 s; store tests run when SRA_DATABASE_URL is set
sra lab dev                     # ~5 min: all designs on the dev seeds, regenerates reports and this README
sra lab dev --check             # rerun and compare with the committed report
sra lab gate                    # exit 1 if a dev gate fails

docker compose up -d db         # PostgreSQL 16 + pgvector
export SRA_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/sra
sra ingest --seed 4242          # demo manuals into pgvector (idempotent)
sra lab bench                   # measured latency and HNSW recall
sra serve                       # API on :8000 (Claude when ANTHROPIC_API_KEY is set)
cd web && npm ci && npm run dev # console on :5173
```

```bash
curl -s localhost:8000/v1/ask -H 'x-api-key: demo-key' -H 'content-type: application/json' \
  -d '{"question": "Welche Schutzart hat der VD-340?"}'
```

## Console

| Ask the manuals | Study results |
|---|---|
| ![Answer with the cited table row and the agent's route](docs/screenshots/ask-answer.png) | ![Wrong answers per 1,000 questions by design](docs/screenshots/study.png) |
| ![A firmware question where the verifier rejected the first draft](docs/screenshots/ask-retry.png) | ![A refused request to bridge the STO input](docs/screenshots/ask-refuse.png) |

## Repository

```
config/            product.json (settings), world.json (the world), designs.json, gates.json, seeds.json
src/sra/world/     catalogue, manuals, questions: the truth
src/sra/ingest/    fixed and structure-aware chunking
src/sra/retrieval/ BM25, LSA embedder, hosted embedder adapter, query parser, filters, reranker
src/sra/agent/     LangGraph assistant, verifier, tools, Claude adapter
src/sra/lab/       simulated model, study, reports
src/sra/service/   FastAPI app, pgvector store, redaction, benchmark
web/               React console (Vite, Framer Motion, design tokens)
docs/adr/          decisions
reports/           generated: dev.json, heldout.json, bench.json, reranker.json
```

## Limits

- **The manuals, questions and model are simulated.** The numbers measure the architecture against the
  traps modelled here, not against a real maker's manuals or a real model. A real deployment starts by
  sampling a few hundred real technician questions and grading them the same way.
- **The embeddings are LSA** (TF-IDF over words and character n-grams, then SVD), fitted on the corpus so
  the lab runs offline. Character n-grams make vector search unusually good at exact strings, which is
  why vector-only matches hybrid here; with a hosted embedding model that may not hold.
  `HostedEmbedder` (OpenAI-compatible API) is not exercised against a live endpoint.
- **`ClaudeReader` is tested with a mocked transport**, not against the live API, and no number in the
  results comes from Claude.
- **The verifier is written for this manual format.** New document types need their checks reviewed.
- **The ERP and product registry are in-memory stand-ins** behind the `StockService` and
  `ProductRegistry` interfaces.
- **pgvector numbers are from one 2-CPU machine** and a 6,219-passage corpus; HNSW matters at larger
  sizes and its recall must be re-measured on real manuals.
- **Security is a sketch**: API keys from the environment, no OIDC, no row-level security yet.
