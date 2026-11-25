# 3. Structure-aware chunks with a breadcrumb from the document

Status: accepted

## Context
Fixed 800-character chunks cut tables from their header rows, so the model reads "45 | IP55" without
knowing which column is which, and splits a series table across chunks.

## Decision
Chunk by section; repeat the table header in every chunk of a table; start every chunk with a
breadcrumb built from the document's own title: models, edition, firmware, section. The breadcrumb
comes from content, not from the index metadata, so it survives missing metadata.

## Consequences
- Fixed chunks cost 8.6 points of correct answers and almost double the model cost per 1,000 questions
  (longer, less relevant context).
- The verifier rejects a value quoted from the breadcrumb line itself.
