# Working in this repository

## Fast feedback
- `pytest -q` runs in about 15 seconds (the store tests run when `SRA_DATABASE_URL` is set).
- `ruff check . && mypy src` before every commit.
- `cd web && npm test && npm run build` for the console.
- `sra lab dev` takes about 5 minutes; run it when a change can move a number.

## Invariants
1. **The truth stays in the world.** Only `sra.world` knows true values. Retrieval, agents and the
   service never import from it; the lab grades against it.
2. **The world does not read the product's settings.** `sra.world` never opens `product.json`,
   `designs.json` or `gates.json` (a test checks this).
3. **Same luck for every design.** The simulated model draws from streams keyed by question and line
   (`sra.rng.Rng`), never from a shared sequence, so designs differ only by their settings.
4. **The model reads and code decides.** A model's draft is shown only after `sra.agent.verify`
   accepts it. Stock comes from the ERP tool, never from text.
5. **Unsafe requests are refused before retrieval.** Requests to bypass STO, emergency stop or guard
   doors never reach a model.
6. **The tenant comes from the API key.** Never from a request body or query parameter.
7. **A request is answered once and audited once** (`x-request-id`); contact details are redacted
   before the audit row is written.
8. **Settings live in `config/`.** No thresholds or prices in code.
9. **Reports are generated.** `reports/*.json`, `REPORT.md`, the README results block and
   `web/public/data/study.json` are written by `sra lab ...`; do not edit them by hand.

## The held-out rule
Held-out seeds (`config/seeds.json`) are run once, with `sra lab heldout`, after designs and gates are
frozen. The run writes `reports/heldout.lock`; the command refuses to run again. Do not delete the lock
to rerun. If a design changes afterwards, report dev results only and say the held-out numbers are for
the earlier design.
