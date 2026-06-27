"""STEP 1 — citing-side citation extraction + LLM enrichment.

Unit: regex extraction over monkeypatched text (every Step1Case).
Integration: real PDF (case_demo.pdf) and, if creds present, LLM enrichment.
"""
from __future__ import annotations

import pytest

from app.services import citation_service as cs
from app.services import citation_llm_service as llm
from tests.conftest import requires_live_llm
from tests.contracts import Step1Case, assert_citation


def _extract(monkeypatch, text):
    monkeypatch.setattr(cs, "read_pdf_text", lambda _p: text)
    return cs.extract_citations("ignored.pdf")


# -------------------------- unit: extraction cases -------------------------
@pytest.mark.unit
def test_neutral_citation(agent, monkeypatch):
    text = "The court in OBG Ltd v Allan [2007] UKHL 21 held that ..."
    cites = _extract(monkeypatch, text)
    c = cites[0]
    agent.case(Step1Case.NEUTRAL, "extract_citations").input(text=text).expect(
        n=1, raw="[2007] UKHL 21", type="neutral").check(
        n=len(cites), raw=c.raw, type=c.citation_type.value)
    assert_citation(c)


@pytest.mark.unit
def test_law_report_and_case_name(agent, monkeypatch):
    text = "Reliance is placed on Anglia Television Ltd v Reed [1972] 1 QB 60."
    cites = _extract(monkeypatch, text)
    c = cites[0]
    agent.case(Step1Case.LAW_REPORT, "extract_citations").input(text=text).expect(
        raw="[1972] 1 QB 60", type="law_report", reporter="QB").check(
        raw=c.raw, type=c.citation_type.value, reporter=c.reporter)
    agent.case(Step1Case.WITH_CASE_NAME, "extract_citations").expect(
        case_name="Anglia Television Ltd v Reed").check(case_name=c.case_name)


@pytest.mark.unit
def test_nominate_citation(agent, monkeypatch):
    text = "The principle in Lumley v Gye (1853) 2 E&B 216 is settled."
    cites = _extract(monkeypatch, text)
    c = cites[0]
    agent.case(Step1Case.NOMINATE, "extract_citations").input(text=text).expect(
        raw="(1853) 2 E&B 216", type="nominate", reporter="E&B").check(
        raw=c.raw, type=c.citation_type.value, reporter=c.reporter)


@pytest.mark.unit
def test_no_citation_returns_empty(agent, monkeypatch):
    text = "This paragraph is plain prose and contains no legal citations at all."
    cites = _extract(monkeypatch, text)
    agent.case(Step1Case.NONE_FOUND, "extract_citations").input(text=text).expect(
        n=0).check(n=len(cites))


@pytest.mark.unit
def test_duplicate_raw_deduped(agent, monkeypatch):
    text = "See [2007] UKHL 21 and again [2007] UKHL 21 later."
    cites = _extract(monkeypatch, text)
    agent.case(Step1Case.DUPLICATE, "extract_citations").input(text=text).expect(
        n=1).check(n=len(cites))


# -------------------------- integration ------------------------------------
@pytest.mark.integration
def test_extract_from_real_pdf(agent, sample_pdf):
    cites = cs.extract_citations(sample_pdf)
    agent.case("real_pdf", "extract_citations").input(pdf=sample_pdf.name).expect(
        at_least_one=True).check(at_least_one=len(cites) > 0)
    for c in cites:
        assert_citation(c)
    agent.case("real_pdf", "extract_citations").note(
        f"{len(cites)} unique citations: {[c.raw for c in cites][:8]}")


@pytest.mark.integration
@requires_live_llm
def test_llm_enrichment_relevant_text(agent, sample_pdf):
    enriched = llm.extract_enriched_citations(sample_pdf)
    has_rt = any((e.relevant_text or "").strip() for e in enriched)
    agent.case("real_pdf", "extract_enriched_citations").input(
        pdf=sample_pdf.name).expect(any_relevant_text=True).check(
        n=len(enriched), any_relevant_text=has_rt)
