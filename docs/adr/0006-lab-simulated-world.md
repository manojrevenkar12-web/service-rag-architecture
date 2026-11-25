# 6. A simulated world with hidden truth, same luck, held-out run once

Status: accepted

## Context
A real equipment maker's manuals and questions are not available, and a design measured on the
questions it was tuned on looks better than it is.

## Decision
- The world (`sra.world`) generates a catalogue with true values per model, power rating and edition,
  renders it into manuals with realistic traps, and writes questions with known answers. It never
  reads the product's settings.
- The model is simulated: its behaviour on a question and a line is drawn from a stream keyed by the
  question and the line, so every design meets the same luck.
- The reranker trains on training seeds; designs and gates are set on dev seeds; held-out seeds are
  run once, after which `reports/heldout.lock` blocks a second run.

## Consequences
- The numbers measure the architecture against the traps we modelled, not against real manuals or a
  real model. The limits section of the README says so.
- `ClaudeReader` is the real adapter; it is tested with a mocked transport, not against the live API.
