"""Writes reports/*.json, REPORT.md, the README results block and the console's data file."""

from __future__ import annotations

import json
import math
from pathlib import Path

from sra.world.catalog import ROOT


def clean(x):
    if isinstance(x, float):
        return None if math.isnan(x) else round(x, 6)
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, list):
        return [clean(v) for v in x]
    return x


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(data), indent=2, ensure_ascii=False) + "\n")


def read(name: str) -> dict | None:
    p = ROOT / "reports" / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def mean_metrics(per_seed: list[dict]) -> dict:
    out: dict = {}
    for key, v in per_seed[0].items():
        if key == "byKind":
            kinds = {}
            for kind in v:
                rows = [m["byKind"][kind] for m in per_seed if kind in m["byKind"]]
                kinds[kind] = {k: sum(r[k] for r in rows) / len(rows) for k in ("correct", "wrong")} | {"n": sum(r["n"] for r in rows)}
            out[key] = kinds
            continue
        vals = [m[key] for m in per_seed if isinstance(m[key], int | float) and not (isinstance(m[key], float) and math.isnan(m[key]))]
        out[key] = sum(vals) / len(vals) if vals else float("nan")
    return out


def check_gates(gates: list[dict], platform: dict, status_quo: dict) -> list[dict]:
    out = []
    for g in gates:
        v = platform.get(g["metric"])
        sq = status_quo.get(g["metric"])
        ok = v is not None and not (isinstance(v, float) and math.isnan(v))
        limit = ""
        if "min" in g:
            ok = ok and v >= g["min"]
            limit = f"≥ {g['min']}"
        if "max" in g:
            ok = ok and v <= g["max"]
            limit = f"≤ {g['max']}"
        if "maxShareOfStatusQuo" in g:
            ok = ok and v <= g["maxShareOfStatusQuo"] * sq
            limit = f"≤ {g['maxShareOfStatusQuo']} × naive RAG ({sq:.1f})"
        out.append({"id": g["id"], "label": g["label"], "value": v, "limit": limit, "pass": bool(ok)})
    return out


def pct(x, d=1):
    return "–" if x is None else f"{x * 100:.{d}f}%"


def num(x, d=1):
    return "–" if x is None else f"{x:.{d}f}"


COLS = [("Correct", "correctRate", pct), ("Wrong per 1,000", "wrongPer1000", num), ("Declined unanswerable", "unanswerableHandled", pct),
        ("Unsafe refused", "unsafeRefused", pct), ("Wrong edition", "revisionErrors", pct), ("Recall@5", "recallAt5", pct),
        ("Citations right", "citationPrecision", pct), ("€ per 1,000", "costPer1000Eur", lambda x: num(x, 2))]


def table(report: dict, ids: list[str] | None = None) -> str:
    rows = [d for d in report["designs"] if ids is None or d["id"] in ids]
    head = "| Design | " + " | ".join(c[0] for c in COLS) + " |"
    sep = "|---|" + "---:|" * len(COLS)
    lines = []
    for d in rows:
        b = "**" if d["kind"] == "platform" else ""
        lines.append(f"| {b}{d['label']}{b} | " + " | ".join(f(d["mean"].get(k)) for _, k, f in COLS) + " |")
    return "\n".join([head, sep, *lines])


def gates_table(gates: list[dict]) -> str:
    rows = [f"| {g['label']} | {'–' if g['value'] is None else round(g['value'], 4)} | {g['limit']} | {'pass' if g['pass'] else '**fail**'} |" for g in gates]
    return "\n".join(["| Gate | Value | Limit | |", "|---|---:|---|---|", *rows])


def kind_table(report: dict, design: str) -> str:
    d = next(x for x in report["designs"] if x["id"] == design)
    rows = [f"| {k} | {v['n']} | {pct(v['correct'])} | {pct(v['wrong'])} |" for k, v in d["mean"]["byKind"].items()]
    return "\n".join(["| Question type | Questions | Correct | Wrong |", "|---|---:|---:|---:|", *rows])


def results_block(dev: dict, heldout: dict | None, bench: dict | None) -> str:
    p = next(d for d in dev["designs"] if d["id"] == "platform")["mean"]
    n = next(d for d in dev["designs"] if d["id"] == "naive-rag")["mean"]
    a = next(d for d in dev["designs"] if d["id"] == "model-alone")["mean"]
    passed = sum(g["pass"] for g in dev["gates"])
    out = [
        f"Dev: {len(dev['seeds'])} simulated equipment makers, {dev['questionsPerSeed']} questions each, {dev['chunksPerSeed']:,} manual passages per maker. "
        f"Every design meets the same manuals, questions and model behaviour. **{passed} of {len(dev['gates'])} gates pass.**",
        "",
        "| | Model alone | Naive RAG | Platform |",
        "|---|---:|---:|---:|",
        f"| Answerable questions answered correctly | {pct(a['correctRate'])} | {pct(n['correctRate'])} | **{pct(p['correctRate'])}** |",
        f"| Wrong answers per 1,000 questions | {num(a['wrongPer1000'])} | {num(n['wrongPer1000'])} | **{num(p['wrongPer1000'])}** |",
        f"| Firmware questions answered from the wrong edition | {pct(a['revisionErrors'])} | {pct(n['revisionErrors'])} | **{pct(p['revisionErrors'])}** |",
        f"| Unknown products and undocumented values declined | {pct(a['unanswerableHandled'])} | {pct(n['unanswerableHandled'])} | **{pct(p['unanswerableHandled'])}** |",
        f"| Requests to bypass safety functions refused | {pct(a['unsafeRefused'])} | {pct(n['unsafeRefused'])} | **{pct(p['unsafeRefused'])}** |",
        f"| Model cost per 1,000 questions | €{num(a['costPer1000Eur'], 2)} | €{num(n['costPer1000Eur'], 2)} | **€{num(p['costPer1000Eur'], 2)}** |",
        "",
        "**All designs**",
        "",
        table(dev),
        "",
        "**Platform by question type**",
        "",
        kind_table(dev, "platform"),
        "",
        "**Gates (dev)**",
        "",
        gates_table(dev["gates"]),
        "",
    ]
    if heldout:
        hp = next(d for d in heldout["designs"] if d["id"] == "platform")["mean"]
        hn = next(d for d in heldout["designs"] if d["id"] == "naive-rag")["mean"]
        hpass = sum(g["pass"] for g in heldout["gates"])
        out += [f"**Held-out ({len(heldout['seeds'])} further makers, run once after the design was frozen): {hpass} of {len(heldout['gates'])} gates pass.** "
                f"Correct {pct(hn['correctRate'])} → {pct(hp['correctRate'])}; wrong per 1,000 {num(hn['wrongPer1000'])} → {num(hp['wrongPer1000'])}.", ""]
        failed = [g for g in heldout["gates"] if not g["pass"]]
        if failed:
            out += ["Failed on held-out: " + "; ".join(f"{g['label']} ({round(g['value'], 4)}, limit {g['limit']})" for g in failed) + ".", ""]
        out += [gates_table(heldout["gates"]), ""]
    else:
        out += ["_Held-out not run yet._", ""]
    if bench:
        line = (f"**Measured, not simulated** ({bench['machine']}): hybrid retrieval in process p50 {bench['retrievalMs']['p50']:.1f} ms, "
                f"p95 {bench['retrievalMs']['p95']:.1f} ms.")
        pg = bench.get("pgvector")
        if pg:
            line += (f" pgvector over {pg['rows']:,} passages, {pct(pg['nearTwinShare'], 0)} of which have a near-twin: HNSW top-{pg['k']} recall "
                     f"against exact search {pct(pg['recallUnfiltered'])} unfiltered and {pct(pg['recallFiltered'])} filtered by product, "
                     f"query p95 {pg['p95Ms']:.1f} ms (exact search {pg['exactP95Ms']:.1f} ms). See ADR 4 for why the HNSW settings changed.")
        out += [line]
    return "\n".join(out)


def write_readme_block(block: str) -> None:
    p = ROOT / "README.md"
    if not p.exists():
        return
    t = p.read_text()
    a, b = t.find("<!-- results:start -->"), t.find("<!-- results:end -->")
    if a < 0 or b < 0:
        return
    p.write_text(t[: a + len("<!-- results:start -->")] + "\n" + block + "\n" + t[b:])


def full_report(dev: dict, heldout: dict | None) -> str:
    out = ["# Study report", "", "Generated by `sra lab report`. Do not edit by hand.", ""]
    for r in (dev, heldout):
        if not r:
            continue
        out += [f"## {'Dev' if r['kind'] == 'dev' else 'Held-out'} seeds {', '.join(map(str, r['seeds']))}", "", table(r), "", gates_table(r["gates"]), ""]
        for d in r["designs"]:
            out += [f"### {d['label']}", "", kind_table(r, d["id"]), ""]
    out += ["## Reranker", "", "Logistic regression trained on the training seeds only.", "", "```", json.dumps(dev["reranker"], indent=2), "```", ""]
    return "\n".join(out)
