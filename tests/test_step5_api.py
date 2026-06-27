"""STEP 5 — report API for the frontend.

Pins what exists today (/health) and the *target contract* for the not-yet-built
`POST /api/citations/verify`. The contract tests are XFAIL until the endpoint +
orchestrator land, so the gap is tracked by the suite instead of being invisible.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.contracts import Step5Case, VERDICTS, assert_verify_response

client = TestClient(app)


@pytest.mark.unit
def test_health_ok(agent):
    resp = client.get("/health")
    agent.case("health", "GET /health").expect(status=200, body={"status": "ok"}).check(
        status=resp.status_code, body=resp.json())


@pytest.mark.unit
@pytest.mark.contract
def test_verify_endpoint_not_yet_implemented(agent):
    # Documents current reality: the route the frontend needs does not exist yet.
    resp = client.post("/api/citations/verify", json={"text": "x"})
    agent.case("verify_absent", "POST /api/citations/verify").expect(
        status=404).check(status=resp.status_code)
    agent.case("verify_absent", "POST /api/citations/verify").note(
        "ACTION: build the endpoint + M1->M3->M4 orchestrator (Step 5).")


@pytest.mark.contract
@pytest.mark.xfail(reason="verify endpoint + orchestrator not implemented yet", strict=False)
def test_verify_response_contract(agent):
    resp = client.post("/api/citations/verify", json={"text": "Lumley v Gye (1853) 2 E&B 216 ..."})
    assert resp.status_code == 200
    body = resp.json()
    citations = body["citations"] if isinstance(body, dict) else body
    for item in citations:
        assert_verify_response(item)
        assert item["status"] in VERDICTS or item["status"] in {
            "verified", "mischar", "risk", "review"}
    agent.case(Step5Case.VERIFIED, "POST /api/citations/verify").note(
        "contract satisfied once implemented")
