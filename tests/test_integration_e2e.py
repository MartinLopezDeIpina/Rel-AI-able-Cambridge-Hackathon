"""END-TO-END (integration) — the steps that run today, chained.

STEP 1 (extract) -> [STEP 3 resolve: DEFERRED] -> STEP 4 (faithfulness) -> STEP 5
(verdict mapping). Resolution is stubbed here (the index/resolver tests are deferred),
so the source text is supplied directly; this exercises the real extraction and real
detector and pins the detector->verdict mapping the orchestrator must implement.
"""
from __future__ import annotations

import pytest

from app.services import citation_service as cs
from app.services.distortion_service import analyze
from app.schemas.citation import ClassificationType

# detector class -> user-facing verdict (the mapping Step 5's orchestrator owes us)
DETECTOR_TO_VERDICT = {
    "correct": ClassificationType.EXISTS_CORRECTLY_APPLIED,
    "mischaracterised": ClassificationType.EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT,
    "out_of_context": ClassificationType.EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT,
}

BRIEF = ("Crestholm relies on Hadley v Baxendale (1854) 9 Ex 341 for the proposition "
         "that its lost profits are always recoverable in full as a natural consequence "
         "of the breach.")
SOURCE = ("Damages are recoverable only for losses arising naturally from the breach, "
          "or such as were in the reasonable contemplation of both parties. Such lost "
          "profits did not flow naturally and were not recoverable on these facts.")


@pytest.mark.integration
def test_extract_then_detect_then_map(agent, monkeypatch, mock_backend):
    # STEP 1 — extract the citation from the (monkeypatched) brief text.
    monkeypatch.setattr(cs, "read_pdf_text", lambda _p: BRIEF)
    cites = cs.extract_citations("brief.pdf")
    agent.case("e2e", "step1.extract").expect(found=True, raw="(1854) 9 Ex 341").check(
        found=len(cites) == 1, raw=cites[0].raw)

    # STEP 3 — DEFERRED (resolver/index tests skipped); source supplied directly.
    agent.case("e2e", "step3.resolve").note("DEFERRED stub: source text injected, not resolved")

    # STEP 4 — faithfulness check of the brief's claim against the source.
    report, _ = analyze(BRIEF, SOURCE, mock_backend)
    agent.case("e2e", "step4.analyze").expect(flagged=True).check(
        classification=report["classification"],
        flagged=report["classification"] != "correct")

    # STEP 5 — map detector class -> user-facing verdict.
    verdict = DETECTOR_TO_VERDICT[report["classification"]]
    agent.case("e2e", "step5.map_verdict").expect(
        verdict=ClassificationType.EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT.value).check(
        verdict=verdict.value)
