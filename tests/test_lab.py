from __future__ import annotations

import json

import pytest

from sra import cli
from sra.lab import report as rep
from sra.lab.study import grade, load_designs, same_value
from sra.world.catalog import ROOT


def test_designs_inherit_and_differ_from_the_platform_in_one_setting():
    ds = {d.id: d for d in load_designs()}
    p = ds["platform"]
    for d in ds.values():
        if d.kind != "ablation":
            continue
        diff = [k for k in vars(p) if k not in ("id", "label", "kind") and getattr(p, k) != getattr(d, k)]
        assert 1 <= len(diff) <= 2, (d.id, diff)


def test_value_matching():
    assert same_value("45 °C", 45.0)
    assert same_value("12,5 kg", 12.5)
    assert not same_value("40 °C", 45.0)
    assert same_value("ip55", "IP55")


def test_heldout_runs_once(tmp_path, monkeypatch):
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "heldout.lock").write_text("config abc seeds 1\n")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    with pytest.raises(SystemExit) as e:
        cli.main(["lab", "heldout"])
    assert e.value.code == 3


def test_gates():
    gates = [{"id": "a", "metric": "x", "min": 0.9, "label": "x"}, {"id": "b", "metric": "y", "maxShareOfStatusQuo": 0.1, "label": "y"}]
    out = rep.check_gates(gates, {"x": 0.95, "y": 5.0}, {"y": 100.0})
    assert [g["pass"] for g in out] == [True, True]
    out = rep.check_gates(gates, {"x": 0.85, "y": 20.0}, {"y": 100.0})
    assert [g["pass"] for g in out] == [False, False]


@pytest.mark.skipif(not (ROOT / "reports" / "dev.json").exists(), reason="no dev report yet")
def test_readme_results_are_generated_from_the_reports():
    dev = json.loads((ROOT / "reports" / "dev.json").read_text())
    held = rep.read("heldout")
    block = rep.results_block(dev, held, rep.read("bench"))
    readme = (ROOT / "README.md").read_text()
    assert block in readme, "README results block is stale: run `sra lab report`"


@pytest.mark.skipif(not (ROOT / "reports" / "dev.json").exists(), reason="no dev report yet")
def test_dev_gates_pass():
    dev = json.loads((ROOT / "reports" / "dev.json").read_text())
    assert all(g["pass"] for g in dev["gates"]), [g for g in dev["gates"] if not g["pass"]]


def test_grading_never_counts_a_refusal_as_wrong(world):
    from sra.agent.graph import Answer

    x = next(x for x in world.queries if x.kind == "attribute")
    g = grade(x, Answer("abstain", "Ich finde das nicht."), None)
    assert not g["wrong"] and not g["correct"]
