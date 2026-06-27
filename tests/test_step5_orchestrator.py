"""STEP 5 — orchestrator (M3 -> M4 -> verdict), the core of the /verify pipeline.

Unit-tested with a stub resolver + mock detector backend, so every Step5Case is
covered without a built index or live LLM. This is the "step 3 -> 4" handoff.
"""
from __future__ import annotations

import pytest

from app.schemas.citation import CitationType, ClassificationType, EnrichedCitation
from app.services import pipeline_service as pl
from tests.contracts import Step5Case, VERDICTS, assert_verify_response

pytestmark = pytest.mark.unit

SOURCE = (
    "The court held that damages for lost profits are recoverable provided that the "
    "loss was within the reasonable contemplation of the parties at the time of "
    "contracting. This is the established measure of expectation damages."
)


def _cite(claim: str, cid: int = 1) -> EnrichedCitation:
    return EnrichedCitation(
        id=cid, raw="(1854) 9 Ex 341", year=1854, citation_type=CitationType.nominate,
        full_case_name="Hadley v Baxendale", relevant_text=claim, ground="Ground 2")


class StubResolver:
    """Returns a canned resolver result + source text (mimics resolver_service)."""

    def __init__(self, *, needs_web=False, uncertain=False, confidence=0.9,
                 semantic=False, source=SOURCE):
        self._res = {
            "citation": "x", "chosen_source": "Hadley v Baxendale.txt",
            "method": "semantic" if semantic else "name", "confidence": confidence,
            "uncertain": uncertain, "needs_web": needs_web,
            "used_semantic_fallback": semantic, "signals_agree": not semantic,
            "name_top": {}, "semantic_top": {}, "name_ranking": [], "semantic_ranking": [],
        }
        self._source = source

    def resolve(self, _citation):
        return self._res

    def source_text(self, _src):
        return self._source


def _run(agent, case, claim, resolver, expect_status, expect_review=None):
    from app.services.distortion_backend import get_backend
    v = pl.verdict_for(_cite(claim), resolver, get_backend("mock"))
    d = v.model_dump(mode="json")
    assert_verify_response(d)                      # blueprint contract holds
    c = agent.case(case, "verdict_for").expect(status=expect_status.value)
    actual = {"status": d["status"], "confidence_score": d["confidence_score"],
              "detector": d["detector_classification"], "needs_review": d["needs_review"]}
    if expect_review is not None:
        c.expect(needs_review=expect_review)
    c.check(**actual)
    return v


def test_verified(agent):
    claim = ("Damages for lost profits are recoverable provided that the loss was "
             "within the reasonable contemplation of the parties.")
    v = _run(agent, Step5Case.VERIFIED, claim, StubResolver(),
             ClassificationType.EXISTS_CORRECTLY_APPLIED)
    assert v.explanation == ""                     # blueprint: empty when verified
    assert v.confidence_score > 0.5


def test_mischaracterised(agent):
    claim = "Damages for lost profits are always recoverable."
    v = _run(agent, Step5Case.MISCHARACTERISED, claim, StubResolver(),
             ClassificationType.EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT)
    assert v.explanation                            # non-empty 'why it's wrong'
    assert v.ground == "Ground 2"                   # ground surfaced


def test_fabricated_short_circuits(agent):
    # needs_web -> DOESNT_EXIST, confidence 0, detector skipped.
    v = _run(agent, Step5Case.FABRICATED, "anything", StubResolver(needs_web=True),
             ClassificationType.DOESNT_EXIST, expect_review=True)
    assert v.confidence_score == 0.0
    assert v.detector_classification is None        # detector was not run
    assert v.actual_holding == ""


def test_needs_review_on_uncertain(agent):
    claim = ("Damages for lost profits are recoverable provided that the loss was "
             "within the reasonable contemplation of the parties.")
    _run(agent, Step5Case.NEEDS_REVIEW, claim, StubResolver(semantic=True, uncertain=True),
         ClassificationType.EXISTS_CORRECTLY_APPLIED, expect_review=True)


def test_resolver_failure_is_needs_review(agent):
    class Boom:
        def resolve(self, _c):
            raise RuntimeError("index not built")

    v = pl.verdict_for(_cite("x"), Boom(), None)
    agent.case("resolver_down", "verdict_for").expect(needs_review=True).check(
        needs_review=v.needs_review, status=v.status.value)


def test_summary_counts(agent):
    from app.services.distortion_backend import get_backend
    cites = [_cite("Damages for lost profits are recoverable provided that the loss was "
                   "within the reasonable contemplation of the parties.", 1),
             _cite("Damages for lost profits are always recoverable.", 2)]
    resp = pl.verify_enriched(cites, StubResolver(), get_backend("mock"), "brief.pdf")
    agent.case("summary", "verify_enriched").expect(total=2).check(
        total=resp.summary["total"], verified=resp.summary["verified"],
        mischaracterised=resp.summary["mischaracterised"])
