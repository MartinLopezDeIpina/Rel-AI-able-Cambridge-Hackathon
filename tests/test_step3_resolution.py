"""STEP 3 — resolution / existence (name + semantic fusion).

DEFERRED: skipped for now at the user's request; bodies are written so they can be
enabled shortly. Unit tests pin the fusion branches (every Step3Case) with a
monkeypatched query embedding; integration resolves against a real tiny index.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.services import citelib, resolver_service as rs
from tests.conftest import requires_fastembed
from tests.contracts import Step3Case, assert_resolver_result

pytestmark = pytest.mark.skip(reason="STEP 3 tests deferred — to be enabled shortly in this task")

# A 3-chunk fake index over 3 sources, unit basis vectors so we can steer cosine.
_SOURCES = ["Lumley v Gye (1853) 2 E&B 216.txt", "Hadley v Baxendale.txt", "Foo v Bar.txt"]
_CHUNKS = [{"source": s, "text": f"chunk for {s}"} for s in _SOURCES]
_EMB = np.eye(3, dtype=np.float32)


def _resolve(monkeypatch, citation, qvec):
    monkeypatch.setattr(citelib, "embed_queries", lambda _q: np.array([qvec], dtype=np.float32))
    return rs.resolve_one(citation, _EMB, _CHUNKS, _SOURCES)


@pytest.mark.unit
def test_name_hit_wins(agent, monkeypatch):
    d = _resolve(monkeypatch, "Lumley v Gye (1853) 2 E&B 216", [0, 0, 0])
    assert_resolver_result(d)
    agent.case(Step3Case.NAME_HIT, "resolve_one").expect(
        method="name", needs_web=False, used_semantic_fallback=False).check(
        method=d["method"], needs_web=d["needs_web"],
        used_semantic_fallback=d["used_semantic_fallback"])


@pytest.mark.unit
def test_semantic_fallback(agent, monkeypatch):
    # Paraphrase (no 'X v Y' name) -> low name score; query == chunk0 -> sem=1.0.
    d = _resolve(monkeypatch, "a malicious inducement to break a contract", [1, 0, 0])
    agent.case(Step3Case.SEMANTIC_HIT, "resolve_one").expect(
        method="semantic", used_semantic_fallback=True, needs_web=False).check(
        method=d["method"], used_semantic_fallback=d["used_semantic_fallback"],
        needs_web=d["needs_web"])


@pytest.mark.unit
def test_not_in_corpus_needs_web(agent, monkeypatch):
    # Paraphrase + weak semantic (0.3 < 0.5) -> needs_web (FABRICATED candidate).
    d = _resolve(monkeypatch, "an unrelated point about tax registration overseas", [0.3, 0, 0])
    agent.case(Step3Case.NEEDS_WEB, "resolve_one").expect(
        needs_web=True, uncertain=True).check(
        needs_web=d["needs_web"], uncertain=d["uncertain"])


@pytest.mark.integration
@requires_fastembed
def test_resolve_on_real_index(agent, tiny_index, monkeypatch):
    monkeypatch.setattr(rs, "load_index", lambda _d: rs.load_index.__wrapped__(tiny_index)
                        if hasattr(rs.load_index, "__wrapped__") else rs.load_index(tiny_index))
    emb, chunks, sources = rs.load_index(tiny_index)
    d = rs.resolve_one("Lumley v Gye (1853) 2 E&B 216", emb, chunks, sources)
    assert_resolver_result(d)
    agent.case(Step3Case.NAME_HIT, "resolve_one[real]").expect(
        chosen_contains="Lumley").check(
        method=d["method"], chosen_contains="Lumley" in d["chosen_source"])
