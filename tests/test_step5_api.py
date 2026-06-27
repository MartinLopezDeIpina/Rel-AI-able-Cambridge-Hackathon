"""STEP 5 — report API for the frontend.

Pins /health and that `POST /api/citations/verify` is mounted and validates input.
The full pipeline behind it (M1 enrichment + resolver index + LLM) is covered by the
orchestrator unit tests (test_step5_orchestrator.py) and the live integration tests;
here we only check the HTTP contract that doesn't need network/index.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.mark.unit
def test_health_ok(agent):
    resp = client.get("/health")
    agent.case("health", "GET /health").expect(status=200, body={"status": "ok"}).check(
        status=resp.status_code, body=resp.json())


@pytest.mark.unit
@pytest.mark.contract
def test_verify_route_mounted_and_validates(agent):
    # Route exists now (not 404) and rejects an empty request with 400.
    resp = client.post("/api/citations/verify", data={})
    agent.case("verify_validates", "POST /api/citations/verify").expect(
        mounted=True, status=400).check(
        mounted=resp.status_code != 404, status=resp.status_code)
