"""STEP 5 — report.json serializer (to_report + write_report).

Covers the STEP-5.md acceptance criteria without a live LLM or built index: builds a
mixed set of verdicts (all 4 frontend buckets), maps them, writes the file, then reloads
and validates against ReportDocument.
"""
from __future__ import annotations

import json

import pytest

from app.schemas.citation import (
    CitationType,
    CitationVerdict,
    ClassificationType,
    EnrichedCitation,
    VerifyResponse,
)
from app.schemas.report import ReportDocument
from app.services import pipeline_service as pl

pytestmark = pytest.mark.unit

REQUIRED = ("id", "caseName", "court", "year", "citation", "status", "confidence")


def _enr(cid: int, year: int = 2007) -> EnrichedCitation:
    return EnrichedCitation(
        id=cid, raw=f"[{year}] UKHL {cid}", year=year, citation_type=CitationType.neutral,
        full_case_name=f"Case {cid} v Crown", court_name="House of Lords",
        relevant_text="claim text", ground="Ground 1")


def _verdict(cid: int, status: ClassificationType, *, needs_review=False, conf=0.9,
             holding="The court held that loss must be in reasonable contemplation.",
             expl="") -> CitationVerdict:
    return CitationVerdict(
        id=cid, citation_name=f"Case {cid} v Crown", raw=f"[2007] UKHL {cid}",
        status=status, confidence_score=conf, associate_claim="the brief's claim",
        actual_holding=holding, explanation=expl, ground="Ground 1",
        needs_review=needs_review)


def _mixed():
    """Verdicts covering the 3 challenge categories (incl. a needs_review correct cite,
    which must still map to `verified` — there is no 4th bucket)."""
    verdicts = [
        _verdict(1, ClassificationType.EXISTS_CORRECTLY_APPLIED),                       # verified
        _verdict(2, ClassificationType.EXISTS_CORRECTLY_APPLIED, needs_review=True),    # still verified
        _verdict(3, ClassificationType.EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT,
                 expl="The Supreme Court moved away from this formulation."),           # mischar
        _verdict(4, ClassificationType.DOESNT_EXIST, conf=0.0, holding=""),             # risk
    ]
    enriched = [_enr(1), _enr(2), _enr(3), _enr(4)]
    resp = VerifyResponse(document_name="brief.pdf", citations=verdicts, summary={})
    return resp, enriched


def test_status_mapping_and_required_fields(agent):
    resp, enriched = _mixed()
    report = pl.to_report(resp, enriched)
    d = report.model_dump()

    statuses = [c["status"] for c in d["citations"]]
    confs = {c["id"]: c["confidence"] for c in d["citations"]}
    # only the 3 challenge categories; needs_review correct cite -> verified (not a 4th bucket)
    agent.case("status_mapping", "to_report").expect(
        statuses=["verified", "verified", "mischar", "risk"], risk_conf=0).check(
        statuses=statuses, risk_conf=confs["c4"])
    assert set(statuses) <= {"verified", "mischar", "risk"}

    # every citation: 7 required fields present, non-empty, correctly typed
    for c in d["citations"]:
        for k in REQUIRED:
            assert k in c and c[k] != "" and c[k] is not None, f"{c['id']}.{k} empty"
        assert isinstance(c["confidence"], int) and 0 <= c["confidence"] <= 100
        assert isinstance(c["year"], int)
    # 0 is a valid confidence, not "missing"
    assert confs["c4"] == 0


def test_summary_and_toplevel(agent):
    resp, enriched = _mixed()
    report = pl.to_report(resp, enriched)
    s = report.summary
    agent.case("summary", "to_report").expect(
        status="complete", total=4, sum_eq_total=True, no_review=True).check(
        status=report.status, total=s["total"],
        sum_eq_total=(s["verified"] + s["mischar"] + s["risk"] == s["total"]),
        no_review=("review" not in s))
    assert (s["verified"], s["mischar"], s["risk"]) == (2, 1, 1)


def test_write_is_atomic_and_revalidates(tmp_path, agent):
    resp, enriched = _mixed()
    report = pl.to_report(resp, enriched)
    out = tmp_path / "sub" / "report.json"

    written = pl.write_report(report, out)
    assert written == out and out.is_file()
    assert not (tmp_path / "sub" / "report.json.tmp").exists()  # temp cleaned up

    reloaded = ReportDocument.model_validate_json(out.read_text(encoding="utf-8"))
    agent.case("roundtrip", "write_report").expect(n=4, status="complete").check(
        n=len(reloaded.citations), status=reloaded.status)
    # extra="forbid" holds: an unknown field would have failed model_validate above
    raw = json.loads(out.read_text(encoding="utf-8"))
    assert set(raw["citations"][0]) >= set(REQUIRED)


def test_zero_citations_is_complete_but_empty(agent):
    # backend writes the normal report; frontend treats complete+empty as an error.
    resp = VerifyResponse(document_name="empty.pdf", citations=[], summary={})
    report = pl.to_report(resp, [])
    agent.case("zero_citations", "to_report").expect(
        status="complete", total=0, n=0).check(
        status=report.status, total=report.summary["total"], n=len(report.citations))
