"""The service assistant as a LangGraph state machine.

guard ─► understand ─► retrieve ─► read ─► tools ─► verify ─► respond
  │     (order number   ▲            ▲                 │
  │      → registry)    │            └── retry without the failing passage (at most twice)
  │          │          └── widen: search again without product filters, once
  │ unsafe   │ unknown product
  ▼          ▼
respond    respond

Each agent is a node; which nodes are active is a setting, so the lab can switch parts off.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from sra.agent.llm import Draft, Reader
from sra.agent.tools import ProductRegistry, StockService
from sra.agent.verify import verify
from sra.retrieval.index import Index
from sra.retrieval.pipeline import RetrievalSettings, retrieve
from sra.retrieval.query import ParsedQuery, parse, resolve
from sra.retrieval.rerank import Reranker

PART_RE = re.compile(r"\b[A-Z]{2}\d{4}-[A-C]\b")


@dataclass(frozen=True)
class AgentSettings:
    retrieval: RetrievalSettings = RetrievalSettings()
    use_retrieval: bool = True
    guard: bool = True
    unknown_product_check: bool = True
    tools: bool = True
    verify: bool = True
    widen: bool = True
    max_retries: int = 2


@dataclass
class Answer:
    status: str  # answer, abstain, refuse
    text: str
    value: str | None = None
    citation: str | None = None
    part: str | None = None
    stock: int | None = None
    stock_from_tool: bool = False
    problems: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    llm_calls: int = 0
    context_chars: int = 0
    passages: list[str] = field(default_factory=list)
    line: str | None = None  # the line of the cited passage the answer was read from


class State(TypedDict, total=False):
    question: str
    parsed: ParsedQuery
    hits: list[int]
    excluded: set[int]
    draft: Draft
    stock: int | None
    problems: list[str]
    attempts: int
    widened: bool
    reader_question: str
    answer: Answer
    steps: list[str]
    llm_calls: int
    context_chars: int


class ServiceAssistant:
    def __init__(self, index: Index, reader: Reader, stock: StockService, registry: ProductRegistry, settings: AgentSettings,
                 reranker: Reranker | None, warehouses: list[str], firmware_to_revision: dict[str, str],
                 glossary: list[dict] | None = None) -> None:
        self.index = index
        self.reader = reader
        self.stock = stock
        self.registry = registry
        self.s = settings
        self.reranker = reranker
        self.warehouses = warehouses
        self.fw = firmware_to_revision
        self.glossary = glossary or []
        self.graph = self._build()

    def _build(self) -> Any:
        g: Any = StateGraph(State)
        g.add_node("guard", self._guard)
        g.add_node("understand", self._understand)
        g.add_node("retrieve", self._retrieve)
        g.add_node("read", self._read)
        g.add_node("tools", self._tools)
        g.add_node("verify", self._verify)
        g.add_node("widen", self._widen)
        g.add_node("respond", self._respond)
        g.set_entry_point("guard")
        g.add_conditional_edges("guard", lambda s: "respond" if s.get("answer") else "understand")
        g.add_conditional_edges("understand", lambda s: "respond" if s.get("answer") else "retrieve")
        g.add_edge("retrieve", "read")
        g.add_edge("read", "tools")
        g.add_edge("tools", "verify")
        g.add_conditional_edges("verify", self._after_verify)
        g.add_edge("widen", "read")
        g.add_edge("respond", END)
        return g.compile()

    def ask(self, question: str) -> Answer:
        out = self.graph.invoke({"question": question, "reader_question": question, "excluded": set(), "attempts": 0, "widened": False,
                                 "steps": [], "llm_calls": 0, "context_chars": 0})
        return out["answer"]

    # Nodes ---------------------------------------------------------------------------------
    def _guard(self, s: State) -> State:
        parsed = parse(s["question"], set(), self.warehouses, self.fw, self.glossary)
        if parsed.model:
            parsed.model_known = self.registry.known(parsed.model)
        steps = [*s["steps"], "guard"]
        if self.s.guard and parsed.unsafe:
            text = ("Das kann ich nicht beantworten: Sicherheitsfunktionen wie STO und Not-Halt dürfen nicht überbrückt werden."
                    if parsed.lang == "de" else "I can't help with that: safety functions such as STO and emergency stop must never be bypassed.")
            return {"parsed": parsed, "steps": steps, "answer": Answer("refuse", text, steps=steps)}
        return {"parsed": parsed, "steps": steps}

    def _understand(self, s: State) -> State:
        p = s["parsed"]
        steps = [*s["steps"], "understand"]
        if p.model is None and p.order_number and self.s.tools:
            model = self.registry.by_order_number(p.order_number)
            steps.append(f"registry {p.order_number} -> {model}")
            if model:
                resolve(p, model)
                return {"steps": steps, "parsed": p, "reader_question": f"{s['question']} (= {model})"}
        if self.s.unknown_product_check and p.model is not None and not p.model_known:
            text = (f"{p.model} ist in den Unterlagen nicht vorhanden. Bitte Typenschild prüfen." if p.lang == "de"
                    else f"{p.model} is not in the documentation. Please check the rating plate.")
            return {"steps": steps, "answer": Answer("abstain", text, steps=steps)}
        return {"steps": steps}

    def _retrieve(self, s: State) -> State:
        if not self.s.use_retrieval:
            return {"hits": [], "steps": [*s["steps"], "no retrieval"]}
        hits = retrieve(self.index, s["parsed"], self.s.retrieval, self.reranker)
        return {"hits": [h.index for h in hits], "steps": [*s["steps"], f"retrieve {len(hits)}"]}

    def _passages(self, s: State) -> list[int]:
        return [i for i in s.get("hits", []) if i not in s.get("excluded", set())]

    def _read(self, s: State) -> State:
        idx = self._passages(s)
        texts = [self.index.chunks[i].text for i in idx]
        draft = self.reader.read(s["reader_question"], texts, self.s.tools)
        if draft.chunk is not None and 0 <= draft.chunk < len(idx):
            draft.chunk = idx[draft.chunk]  # back to index positions
        else:
            draft.chunk = None
        return {"draft": draft, "llm_calls": s["llm_calls"] + 1, "context_chars": s["context_chars"] + sum(map(len, texts)),
                "attempts": s["attempts"] + 1, "steps": [*s["steps"], "read"]}

    def _tools(self, s: State) -> State:
        d = s["draft"]
        p = s["parsed"]
        if not (self.s.tools and p.warehouse and d.kind == "remedy"):
            return {"stock": None}
        part = d.part or (PART_RE.search(d.line or "") or [None])[0]
        if not part:
            return {"stock": None}
        d.part = part
        return {"stock": self.stock.available(part, p.warehouse), "steps": [*s["steps"], f"stock {part} @ {p.warehouse}"]}

    def _verify(self, s: State) -> State:
        if not self.s.verify:
            return {"problems": []}
        d = s["draft"]
        chunk = self.index.chunks[d.chunk] if d.chunk is not None else None
        problems = verify(d, chunk, s["parsed"], self.s.retrieval.current_revision)
        if s["parsed"].warehouse and d.kind == "remedy" and s.get("stock") is None:
            problems.append("no stock figure from the ERP")
        excluded = set(s["excluded"])
        if problems and d.chunk is not None:
            excluded.add(d.chunk)
        return {"problems": problems, "excluded": excluded, "steps": [*s["steps"], "verify: " + ("ok" if not problems else "; ".join(problems))]}

    def _after_verify(self, s: State) -> str:
        if not s.get("problems"):
            return "respond"
        if s["attempts"] <= self.s.max_retries and self._passages(s):
            return "read"
        if self.s.widen and self.s.retrieval.filters and not s.get("widened"):
            return "widen"
        return "respond"

    def _widen(self, s: State) -> State:
        """Documents without index metadata are invisible to filters: search once more without them."""
        wide = RetrievalSettings(self.s.retrieval.mode, False, self.s.retrieval.rerank, self.s.retrieval.candidates,
                                 self.s.retrieval.k, self.s.retrieval.current_revision)
        hits = retrieve(self.index, s["parsed"], wide, self.reranker)
        return {"hits": [h.index for h in hits], "excluded": set(), "attempts": 0, "widened": True,
                "steps": [*s["steps"], f"widen {len(hits)}"]}

    def _respond(self, s: State) -> State:
        if s.get("answer"):
            return {}
        d = s["draft"]
        p = s["parsed"]
        steps = [*s["steps"], "respond"]
        base: dict[str, Any] = {"steps": steps, "llm_calls": s["llm_calls"], "context_chars": s["context_chars"]}
        if s.get("problems") or d.kind in ("none", "refuse"):
            if d.kind == "refuse":
                return {"answer": Answer("refuse", "Refused by the model.", **base)}
            text = ("Dazu finde ich keine belastbare Angabe in den Unterlagen; bitte an den Service eskalieren." if p.lang == "de"
                    else "I can't find a reliable statement in the documentation; please escalate to service.")
            return {"answer": Answer("abstain", text, problems=s.get("problems", []), **base)}
        chunk = self.index.chunks[d.chunk] if d.chunk is not None else None
        stock = s.get("stock")
        from_tool = stock is not None
        if stock is None and d.stock_claim is not None:
            stock = d.stock_claim
        text = d.value or ""
        if d.part:
            text += f" — {d.part}" + (f", {stock} on hand in {p.warehouse}" if stock is not None and p.warehouse else "")
        return {"answer": Answer("answer", text, d.value, chunk.id if chunk else None, d.part, stock, from_tool,
                                 passages=[self.index.chunks[i].id for i in s.get("hits", [])], line=d.line, **base)}
