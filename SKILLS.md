# Repeatable tasks

## Add an ablation
1. Add a design to `config/designs.json` with `"base": "platform"` and the one setting it changes.
2. If it needs a new setting, add it to `Design`, `AgentSettings` or `RetrievalSettings` and pass it in
   `run_seed`; keep the default equal to the platform.
3. `sra lab dev`, read `REPORT.md`, commit the regenerated files.

## Add a trap to the manuals
1. Change `sra.world.manuals` (rendering) or `sra.world.queries` (questions); keep the truth in
   `sra.world.catalog`.
2. Add a test in `tests/test_world.py` that the trap is present.
3. Run `sra lab dev`; if the platform fails a gate, fix the platform, not the world.

## Add a verifier check
1. Add the check to `sra.agent.verify.verify` with a problem message a person can read.
2. Add a passing and a failing case in `tests/test_agent.py`.
3. `sra lab dev` and look at the abstain rate as well as the wrong rate.

## Connect a real model or embedder
- Model: set `ANTHROPIC_API_KEY`; the service uses `ClaudeReader` with the model in `config/product.json`.
- Embeddings: implement `sra.retrieval.embedders.Embedder` (the hosted adapter speaks the
  OpenAI-compatible API) and rebuild the index; re-run `sra lab bench` for HNSW recall.

## Ingest a tenant's manuals into pgvector
`SRA_DATABASE_URL=postgresql://... sra ingest --seed 4242` (demo corpus). Ingest is idempotent.

## Refresh reports and screenshots
`sra lab report` regenerates from `reports/*.json`. `python scripts/screenshots.py` (service on :8000,
console preview on :4173) writes `docs/screenshots/`.
