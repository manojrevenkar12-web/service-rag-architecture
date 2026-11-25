# 7. Tenant from the API key; an audit row per request, without contact details

Status: accepted

## Context
Several business units or customers share the service. A request body must not be able to name
another tenant, and the audit log must not collect personal data technicians paste into questions.

## Decision
- The tenant comes from the API key (SHA-256 compared in constant time), never from the request.
- Every query to the store carries the tenant. A tenant without ingested manuals gets 404.
- The audit log stores the question with e-mail addresses, phone numbers and names after a title
  redacted, the status, the citation, the step log, the reader and the latency.
- `x-request-id` makes a retried request return the first answer and write no second audit row.
- A per-tenant request limit per minute (config).

## Consequences
- Keys live in the environment (`SRA_API_KEYS`); production would put them in a secret store
  (Azure Key Vault, AWS Secrets Manager) and add OIDC for people.
