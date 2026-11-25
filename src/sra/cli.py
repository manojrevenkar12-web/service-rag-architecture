"""sra lab dev|heldout|report|gate|bench   ·   sra serve   ·   sra ingest"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time

from sra.lab import report as rep
from sra.world.catalog import ROOT


def _seeds() -> dict:
    return json.loads((ROOT / "config" / "seeds.json").read_text())


def study(kind: str) -> dict:
    from sra.lab.study import build_world, load_designs, load_json, run_seed, train_reranker

    product = load_json("product.json")
    seeds = _seeds()
    reranker, info = train_reranker(seeds["train"], product)
    designs = load_designs()
    per_seed = []
    for seed in seeds[kind]:
        t = time.perf_counter()
        per_seed.append(run_seed(seed, kind, designs, reranker, product))
        print(f"{kind} seed {seed}: {time.perf_counter() - t:.0f} s", flush=True)
    w = build_world(seeds[kind][0], kind, product)
    summary: list[dict] = [{"id": d.id, "label": d.label, "kind": d.kind, "mean": rep.mean_metrics([s[d.id] for s in per_seed]),
                "perSeed": [s[d.id] for s in per_seed]} for d in designs]
    platform = next(d for d in summary if d["id"] == "platform")["mean"]
    naive = next(d for d in summary if d["kind"] == "status-quo")["mean"]
    gates = json.loads((ROOT / "config" / "gates.json").read_text())["gates"]
    return {"kind": kind, "seeds": seeds[kind], "questionsPerSeed": len(w.queries), "chunksPerSeed": len(w.indexes["structure"].chunks),
            "reranker": info, "_model": reranker.to_json(), "designs": summary, "gates": rep.check_gates(gates, platform, naive)}


def regenerate() -> None:
    dev = rep.read("dev")
    if not dev:
        sys.exit("run `sra lab dev` first")
    heldout = rep.read("heldout")
    bench = rep.read("bench")
    (ROOT / "REPORT.md").write_text(rep.full_report(dev, heldout) + "\n")
    rep.write_readme_block(rep.results_block(dev, heldout, bench))
    rep.write_json(ROOT / "web" / "public" / "data" / "study.json", {"dev": dev, "heldout": heldout, "bench": bench})


def config_hash() -> str:
    h = hashlib.sha256()
    for f in ("product.json", "world.json", "designs.json", "gates.json", "seeds.json"):
        h.update((ROOT / "config" / f).read_bytes())
    return h.hexdigest()[:16]


def compare(old: dict | None, new: dict, tol: float = 0.005) -> int:
    """Reproduction check: same metrics within `tol` (BLAS and CPU differences move the last digits)."""
    if not old:
        print("no reports/dev.json to compare with")
        return 1
    bad = []
    for o, n in zip(old["designs"], new["designs"], strict=True):
        for k, v in o["mean"].items():
            w = n["mean"][k]
            if isinstance(v, int | float) and isinstance(w, int | float):
                scale = 1000 if k == "wrongPer1000" else (10 if k.endswith("Eur") or k.endswith("Question") else 1)
                if abs(v - w) > tol * scale:
                    bad.append(f"{o['id']}.{k}: committed {v:.4f}, rerun {w:.4f}")
    print("\n".join(bad) if bad else f"reproduced: {len(old['designs'])} designs within tolerance")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="sra")
    sub = ap.add_subparsers(dest="cmd", required=True)
    lab = sub.add_parser("lab")
    lab.add_argument("what", choices=["dev", "heldout", "report", "gate", "bench"])
    lab.add_argument("--check", action="store_true", help="dev: rerun and compare with reports/dev.json instead of writing")
    sub.add_parser("serve")
    ing = sub.add_parser("ingest")
    ing.add_argument("--seed", type=int, default=4242)
    a = ap.parse_args(argv)
    if a.cmd == "serve":
        import uvicorn

        uvicorn.run("sra.service.app:app", host="0.0.0.0", port=8000)
        return
    if a.cmd == "ingest":
        from sra.service.store import ingest_demo

        print(ingest_demo(a.seed))
        return
    lock = ROOT / "reports" / "heldout.lock"
    if a.what == "dev" and a.check:
        sys.exit(compare(rep.read("dev"), study("dev")))
    if a.what == "dev":
        r = study("dev")
        rep.write_json(ROOT / "reports" / "reranker.json", r.pop("_model"))
        rep.write_json(ROOT / "reports" / "dev.json", r)
        regenerate()
    elif a.what == "heldout":
        if lock.exists():
            sys.stderr.write(f"Held-out seeds were already run ({lock.read_text().strip()}). They are run once; see AGENTS.md.\n")
            sys.exit(3)
        r = study("heldout")
        r.pop("_model")
        rep.write_json(ROOT / "reports" / "heldout.json", r)
        lock.write_text(f"config {config_hash()} seeds {','.join(map(str, _seeds()['heldout']))}\n")
        regenerate()
    elif a.what == "report":
        regenerate()
    elif a.what == "gate":
        dev = rep.read("dev")
        if not dev:
            sys.exit("no reports/dev.json")
        for g in dev["gates"]:
            print(("pass" if g["pass"] else "FAIL"), g["label"], g["value"], g["limit"])
        sys.exit(0 if all(g["pass"] for g in dev["gates"]) else 1)
    elif a.what == "bench":
        from sra.service.bench import bench

        rep.write_json(ROOT / "reports" / "bench.json", bench())
        regenerate()


if __name__ == "__main__":
    main()
