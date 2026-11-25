# 5. The agents as one LangGraph state machine whose nodes are settings

Status: accepted

## Context
The assistant has several agents: a safety guard, a product resolver that calls the product registry,
retrieval, the reading model, the ERP stock tool, a verifier, and a widening fallback. Each needs to be
switched off to measure what it is worth.

## Decision
One `StateGraph` with nodes guard → understand → retrieve → read → tools → verify → respond, a retry
edge from verify back to read and a widen edge back to retrieve. Which nodes act is set by
`AgentSettings`; the lab's designs are those settings in `config/designs.json`. Every node appends to
a step log, which the console draws and the audit log keeps.

## Consequences
- Ablations differ from the platform in one setting each, so each part's worth is measured on the
  same questions and the same model behaviour.
- Tools are plain Python protocols (`StockService`, `ProductRegistry`); an MCP server or an SAP OData
  client can implement them without touching the graph.
