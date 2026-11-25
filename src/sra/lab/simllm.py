"""A stand-in for the language model, for the lab. It understands questions well (it is given the
question's intent, with a small misreading rate) and reads passages the way LLMs do: it takes the
first line that seems to answer, often without checking that the passage is about the right unit,
can be fooled by a change-log line or a table without its header, and invents an answer when the
passages hold none. Its behaviour depends only on the question and the passages, never on the design.
"""

from __future__ import annotations

import re

from sra.agent.llm import Draft
from sra.rng import Rng
from sra.world.catalog import ATTR, ATTRIBUTES, UNDOCUMENTED
from sra.world.queries import Query

VALUE_RE = re.compile(r":\s*([^()]+?)\s*(?:\(|$)")
NUM_RE = re.compile(r"\d+(?:[.,]\d+)?\s?(?:°C|Nm|h|s|%|A|kg)?")
PART_RE = re.compile(r"\b[A-Z]{2}\d{4}-[A-C]\b")
REMEDY_RE = re.compile(r"(?:Abhilfe|Remedy):\s*(.+?)(?:\s\((?:Ersatzteil|Spare part)[^)]*\))?\.$")


def model_mentioned(text: str, model: str) -> bool:
    prefix, num = model.split("-")
    return re.search(rf"\b{prefix}[\s-]?{num}\b", text, re.IGNORECASE) is not None


class SimulatedReader:
    name = "simulated-llm"

    def __init__(self, seed: int, intents: dict[str, Query], cfg: dict, stock_guess: list[int] | None = None) -> None:
        self.seed = seed
        self.intents = intents
        self.cfg = cfg
        self.stock_guess = stock_guess or [0, 1, 2, 3, 5]

    def read(self, question: str, passages: list[str], tools: bool) -> Draft:
        q = self.intents.get(question.split(" (= ")[0])
        if q is None:
            return Draft("none", notes=["question is not one of the simulated world's questions"])
        # Every decision is drawn from a stream keyed by the question and what is being decided
        # (for a line, the line itself), so a line meets the same behaviour in every design.
        r = Rng(self.seed, "llm", q.id)
        c = self.cfg
        if q.kind == "unsafe":
            return Draft("refuse") if self._u(q, "unsafe") < c["refusesUnsafeAlone"] else Draft("value", "procedure", notes=["complied"])
        attribute = q.attribute
        if attribute and self._u(q, "misread") < c["misreadQuestion"]:
            same_level = [a.key for a in ATTRIBUTES if a.level == ATTR[attribute].level and a.key != attribute]
            attribute = r.choice(same_level)
        if not passages:
            return self._from_memory(q, r)
        if q.kind in ("errorCode", "partAndStock"):
            return self._remedy(q, passages, r, tools)
        undocumented = next((u for u in UNDOCUMENTED if q.kind == "unanswerable" and (u[1] in question or u[2] in question)), None)
        if undocumented or attribute is None:
            return self._invent(q, r)
        # The model knows the product only if the question (or a registry hint) names it.
        model = self._asked_model(question)
        reads_history = self._u(q, "history") < c["readsHistoryLines"]
        for i, text in enumerate(passages):
            for line, value, line_model in self._candidates(text, attribute, q.variant, reads_history):
                if model is None or line_model is None:
                    ok = self._u(q, "trust", line) < c["answersWithoutEntityCheck"]
                elif line_model == model:
                    ok = True
                else:
                    ok = self._u(q, "confuse", line) < c["confusesModelInLine"]
                if ok and q.revision:
                    fw = "3" if q.revision == "A" else "4"
                    ok = f"Firmware {fw}" in text or self._u(q, "edition", line) < c["answersWithoutEntityCheck"]
                if ok:
                    return Draft("value", value, i, line)
        return self._invent(q, r)

    # -------------------------------------------------------------------------------------------
    def _u(self, q: Query, *keys: object) -> float:
        return Rng(self.seed, "llm", q.id, *keys).random()

    def _asked_model(self, question: str) -> str | None:
        m = re.search(r"\b([A-Za-z]{2})[\s-]?(\d{3})\b", question)
        return f"{m.group(1).upper()}-{m.group(2)}" if m else None

    def _candidates(self, text: str, attribute: str, variant: str | None, reads_history: bool):
        """Lines that seem to answer, in reading order, with the product the line names (if any)."""
        a = ATTR[attribute]
        labels = (a.de, a.en)
        lines = text.split("\n")
        header = next((ln for ln in lines if " | " in ln and any(lbl in ln for lbl in labels)), None)
        for ln in lines:
            if ln.startswith("["):  # the passage's breadcrumb, not content
                continue
            named = re.search(r"\b([A-Z]{2}-\d{3})\b", ln)
            line_model = named.group(1) if named else None
            history = "changed from" in ln or ("von" in ln and "geändert" in ln)
            if " | " in ln and ln is not header:
                cells = [x.strip() for x in ln.split(" | ")]
                if a.level == "variant":
                    if not variant or len(cells) < 3 or cells[1].replace(",", ".") != variant:
                        continue
                elif len(cells) < 2 or re.search(r"\bkW\b", cells[1]):
                    continue
                if header:
                    cols = [x.strip() for x in header.split(" | ")]
                    col = next((j for j, h in enumerate(cols) if h in labels), None)
                    if col is not None and col < len(cells):
                        yield ln, cells[col], line_model
                else:
                    # Without the header the model guesses the column by its unit.
                    guess = next((x for x in cells[1:] if a.unit and x.endswith(" " + a.unit) or (not a.unit and x.startswith("IP"))), None)
                    if guess:
                        yield ln, guess, line_model
            elif a.level == "model" and any(lbl in ln for lbl in labels):
                if history:
                    if reads_history:
                        m = NUM_RE.search(ln.split("von")[-1].split("from")[-1])
                        if m:
                            yield ln, m.group(0).strip(), line_model
                    continue
                m = VALUE_RE.search(ln)
                if m:
                    yield ln, m.group(1).strip(), line_model

    def _remedy(self, q: Query, passages: list[str], r: Rng, tools: bool) -> Draft:
        assert q.code and q.model
        prefix = q.model.split("-")[0]
        for i, text in enumerate(passages):
            for ln in text.split("\n"):
                if not ln.startswith(q.code):
                    continue
                m = REMEDY_RE.search(ln)
                if not m:
                    continue
                family_ok = re.search(rf"\b{prefix}-\d{{3}}\b", text) is not None
                if family_ok or self._u(q, "trust", ln) < self.cfg["answersWithoutEntityCheck"]:
                    part = PART_RE.search(ln)
                    d = Draft("remedy", m.group(1).strip(), i, ln, part.group(0) if part else None)
                    if q.warehouse and not tools and self._u(q, "stock") < self.cfg["inventsWhenNothingFound"]:
                        d.stock_claim = r.choice(self.stock_guess)
                    return d
        return self._invent(q, r)

    def _from_memory(self, q: Query, r: Rng) -> Draft:
        if q.kind in ("attribute", "variantAttribute", "revision") and self._u(q, "memory") < self.cfg["knowsFromPretraining"]:
            return Draft("value", str(q.answer_value), notes=["from pretraining"])
        return self._invent(q, r)

    def _invent(self, q: Query, r: Rng) -> Draft:
        if self._u(q, "invent") >= self.cfg["inventsWhenNothingFound"]:
            return Draft("none")
        if q.kind in ("errorCode", "partAndStock"):
            d = Draft("remedy", r.choice(["Gerät neu starten", "Restart the unit", "Replace the control unit"]), notes=["invented"])
            if q.warehouse:
                d.part = f"{(q.model or 'XX-000')[:2]}{r.randint(1000, 9999)}-A"
                d.stock_claim = r.choice(self.stock_guess)
            return d
        return Draft("value", r.choice(["45 °C", "IP54", "1.2 Nm", "40000 h", "10.0 s", "150 %", "16 A", "12.5 kg"]), notes=["invented"])
