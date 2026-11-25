# 1. The model reads; code decides

Status: accepted

## Context
A language model reading retrieved passages answers fluently even when the passage is about a sibling
model, an older edition, or a change-log line that repeats the old value. In the lab, naive RAG gives
about 400 wrong answers per 1,000 questions, most of them confident.

## Decision
The model only proposes: a value, the passage it came from and the exact line. Code accepts the draft
only if the line names the asked product, the passage is the asked edition, the line is the asked power
rating's row, the value is in the line and in the unit the question asks for, the line is not a
change-log entry or the breadcrumb, and a stock figure comes from the ERP tool. A rejected draft is
retried without the failing passage (at most twice), then the assistant says it has no answer.

## Consequences
- Wrong answers fall to about 0.5 per 1,000; removing the verifier (ablation `no-verifier`) brings
  them back to about 67 per 1,000 and lets a third of unanswerable questions through.
- Some correct drafts are rejected (abstentions of a few percent). We prefer a technician hearing
  "the manual does not say" to a wrong tightening torque.
- The checks are written against the manual format. A new document type needs its checks reviewed.
