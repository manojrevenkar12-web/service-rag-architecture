from __future__ import annotations

from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from sra.service.app import create_app
from sra.service.redact import redact

DEMO = {"x-api-key": "demo-key"}
ACME = {"x-api-key": "acme-key"}


@pytest.fixture(scope="module")
def client(monkeypatch_module):
    monkeypatch_module.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch_module.delenv("SRA_DATABASE_URL", raising=False)
    monkeypatch_module.setenv("SRA_API_KEYS", "demo:demo-key,acme:acme-key")
    return TestClient(create_app())


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


def test_unknown_key_is_rejected(client):
    assert client.post("/v1/ask", json={"question": "Schutzart VD-340?"}).status_code == 401
    assert client.post("/v1/ask", json={"question": "Schutzart VD-340?"}, headers={"x-api-key": "nope"}).status_code == 401


def test_tenant_comes_from_the_key_and_sees_only_its_manuals(client):
    r = client.post("/v1/ask", json={"question": "Schutzart VD-340?"}, headers=ACME)
    assert r.status_code == 404 and "acme" in r.json()["detail"]


def test_ask_answers_with_a_citation_and_steps(client):
    qs = client.get("/v1/questions", headers=DEMO).json()
    attr = next(q for q in qs if q["kind"] == "attribute")
    r = client.post("/v1/ask", json={"question": attr["text"]}, headers=DEMO).json()
    assert r["steps"][0] == "guard"
    if r["status"] == "answer":
        assert r["citation"]["text"] and r["value"] in r["citation"]["text"]


def test_unsafe_is_refused(client):
    qs = client.get("/v1/questions", headers=DEMO).json()
    unsafe = next(q for q in qs if q["kind"] == "unsafe")
    assert client.post("/v1/ask", json={"question": unsafe["text"]}, headers=DEMO).json()["status"] == "refuse"


def test_a_retried_request_is_answered_once_and_audited_once(client):
    before = len(client.get("/v1/audit", headers=DEMO).json())
    h = {**DEMO, "x-request-id": "req-42"}
    a = client.post("/v1/ask", json={"question": "Schutzart VD-340? Rückruf an max.mustermann@example.com, Frau Weber"}, headers=h).json()
    b = client.post("/v1/ask", json={"question": "Schutzart VD-340? Rückruf an max.mustermann@example.com, Frau Weber"}, headers=h).json()
    assert a == b
    log = client.get("/v1/audit", headers=DEMO).json()
    assert len(log) == before + 1
    assert "example.com" not in log[0]["question"] and "Weber" not in log[0]["question"]


def test_search_respects_filters(client):
    hits = client.post("/v1/search", json={"query": "Schutzart", "revision": "A", "k": 5}, headers=DEMO).json()
    assert hits
    for h in hits:
        assert client.get(f"/v1/passages/{quote(h['id'], safe='')}", headers=DEMO).json()["revision"] == "A"


def test_redaction():
    out = redact("Ruf mich an: +49 176 1234567, mail a.b@c.de, Herr Schmidt", ["email", "phone", "person"])
    assert out == "Ruf mich an: [phone], mail [email], Herr [name]"
