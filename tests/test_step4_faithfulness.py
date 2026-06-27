"""STEP 4 — faithfulness detector (contract + every Step4Case + live LLM).

Complements tests/test_pipeline.py (which covers scoring/helpers in depth). Here we
pin the report contract per case and, with creds, run the real LLM on a faithful and
an unfaithful citation.
"""
from __future__ import annotations

import pytest

from app.services.distortion_service import analyze
from tests.conftest import requires_live_llm
from tests.contracts import Step4Case, assert_analysis_report

SOURCE = (
    "The court held that damages for lost profits are recoverable provided that the "
    "loss was within the reasonable contemplation of the parties at the time of "
    "contracting. This is the established measure of expectation damages."
)


@pytest.mark.unit
@pytest.mark.contract
@pytest.mark.parametrize("case,claim,source,expected", [
    (Step4Case.CORRECT,
     "Damages for lost profits are recoverable provided that the loss was within the "
     "reasonable contemplation of the parties.", SOURCE, "correct"),
    (Step4Case.MISCHARACTERISED,
     "Damages for lost profits are always recoverable.", SOURCE, "mischaracterised"),
    (Step4Case.OUT_OF_CONTEXT,
     "The defendant must register the trademark before exporting goods overseas.",
     SOURCE, "out_of_context"),
    (Step4Case.EMPTY_SOURCE, "Any claim at all.", "", "out_of_context"),
])
def test_detector_cases(agent, mock_backend, case, claim, source, expected):
    report, _ = analyze(claim, source, mock_backend)
    assert_analysis_report(report)
    agent.case(case, "analyze[mock]").input(claim=claim[:60]).expect(
        classification=expected).check(
        classification=report["classification"],
        mischar=report["mischaracterised_pct"], ooc=report["out_of_context_pct"])


@pytest.mark.integration
@requires_live_llm
def test_live_faithful_not_flagged(agent, mock_backend):
    from app.services.distortion_backend import get_backend
    claim = ("For an interlocutory injunction the applicant need not establish a "
             "strong prima facie case on the merits.")
    source = ("The court must be satisfied only that the claim is not frivolous or "
              "vexatious; that there is a serious question to be tried. The use of "
              "'a strong prima facie case' leads to confusion and is not required.")
    report, _ = analyze(claim, source, get_backend("vertex"))
    agent.case("live_faithful", "analyze[vertex]").expect(flagged=False).check(
        classification=report["classification"],
        flagged=report["classification"] != "correct")


@pytest.mark.integration
@requires_live_llm
def test_live_misrepresentation_flagged(agent):
    from app.services.distortion_backend import get_backend
    claim = ("The court held that lost profits must always be awarded in full as "
             "expectation damages, regardless of contemplation.")
    source = ("The claimant did not claim lost profits; they claimed wasted "
              "expenditure. Lost profits were not awarded on these facts.")
    report, _ = analyze(claim, source, get_backend("vertex"))
    agent.case("live_misrep", "analyze[vertex]").expect(flagged=True).check(
        classification=report["classification"],
        flagged=report["classification"] != "correct")
