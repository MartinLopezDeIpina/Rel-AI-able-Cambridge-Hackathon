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
def test_verify_endpoint_exists_and_handles_no_citations(agent):
    # The route the frontend needs now exists; text with no citations -> empty report,
    # no LLM call (so this stays an offline unit test).
    resp = client.post("/api/citations/verify", json={"text": "no citations in here"})
    agent.case("verify_present", "POST /api/citations/verify").expect(
        status=200).check(status=resp.status_code)
    body = resp.json()
    assert isinstance(body.get("citations"), list) and body["citations"] == []


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
