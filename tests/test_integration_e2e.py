"""END-TO-END (integration) — the REAL Step 1->5 pipeline, chained, no stubs.

Earlier this file faked the chain (monkeypatched source text, a stubbed resolver, a
hand-written verdict map). It now drives the actual services so a broken hand-off
surfaces here instead of hiding behind a mock:

    STEP 1  extract_citations            (real regex over the brief text)
    STEP 3  ResolverService.resolve      (real semantic+name fusion over a real index)
    STEP 4  distortion_service.analyze   (real detector; mock judge offline, Vertex live)
    STEP 5  pipeline_service.verdict_for + to_report  (real verdict + report.json)

`assert_*` from tests.contracts pin each hand-off's shape. The point is to prove the
steps work *together* (and to fail loudly / locate the stuck step if they do not).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.schemas.citation import ClassificationType, EnrichedCitation
from app.schemas.report import ReportDocument
from app.services import citation_service as cs
from app.services import pipeline_service as pl
from app.services import resolver_service as rs
from app.services.distortion_service import analyze
from tests.conftest import requires_fastembed, requires_live_llm
from tests.contracts import assert_analysis_report, assert_citation, assert_resolver_result

# A brief whose single citation (Hadley) IS in the tiny corpus, with a faithful claim.
BRIEF = ("Crestholm relies on Hadley v Baxendale (1854) 9 Ex 341 for the proposition "
         "that damages are limited to losses arising naturally from the breach or such "
         "as were in the reasonable contemplation of both parties at the time of "
         "contracting.")
CLAIM = ("Damages are limited to losses arising naturally from the breach, or such as "
         "were within the reasonable contemplation of both parties when contracting.")

THREE_CATEGORIES = {c.value for c in ClassificationType}


@pytest.mark.unit
def test_default_corpus_dir_has_sources(agent):
    """Config guard: the index auto-builds from `corpus_dir`, so it must point at a
    real corpus. (Regression test for corpus_dir=index/texts, which left Step 3 unable
    to build an index and silently degraded every verdict.)"""
    from app.core.config import get_settings

    corpus = Path(get_settings().corpus_dir)
    if not corpus.is_absolute():
        corpus = Path(__file__).resolve().parents[1] / corpus
    sources = list(corpus.glob("*.pdf")) + list(corpus.glob("*.txt"))
    agent.case("config", "corpus_dir").input(corpus_dir=str(corpus)).expect(
        exists=True, has_sources=True).check(
        exists=corpus.is_dir(), has_sources=len(sources) > 0)


@pytest.mark.integration
@requires_fastembed
def test_step1_to_5_real_chain(agent, monkeypatch, tiny_index, tiny_corpus, mock_backend):
    """The full chain on real services (offline judge): every hand-off's contract holds
    and the citation flows Step 1 -> 5 without a step silently dropping it."""
    # ---- STEP 1: real regex extraction (only the input text is injected) ----
    monkeypatch.setattr(cs, "read_pdf_text", lambda _p: BRIEF)
    cites = cs.extract_citations("brief.pdf")
    assert len(cites) == 1, "Step 1 should find exactly the Hadley citation"
    c = cites[0]
    assert_citation(c)
    agent.case("e2e", "step1.extract").expect(raw="(1854) 9 Ex 341").check(raw=c.raw)

    # citing-side enrichment (LLM half) stands in as the brief's own wording
    enriched = EnrichedCitation(**c.model_dump(), full_case_name="Hadley v Baxendale",
                                relevant_text=CLAIM, ground="Ground 2")

    # ---- STEP 3: REAL resolution against a REAL index (no stub) ----
    resolver = rs.ResolverService(index_dir=tiny_index, corpus_dir=tiny_corpus)
    res = resolver.resolve(f"{enriched.full_case_name} {enriched.raw}")
    assert_resolver_result(res)
    assert not res["needs_web"], "Hadley is in the corpus -> must resolve, not needs_web"
    agent.case("e2e", "step3.resolve").expect(in_corpus=True, hits_hadley=True).check(
        method=res["method"], in_corpus=not res["needs_web"],
        hits_hadley="Hadley" in res["chosen_source"])

    # ---- STEP 4: REAL detector over the REAL resolved source text ----
    source_text = resolver.source_text(res["chosen_source"])
    assert source_text.strip(), "Step 4 got empty source text -> resolver/index cache broken"
    report, _ = analyze(CLAIM, source_text, mock_backend)
    assert_analysis_report(report)
    agent.case("e2e", "step4.analyze").expect(has_class=True).check(
        classification=report["classification"], has_class=report["classification"] in
        {"correct", "mischaracterised", "out_of_context"})

    # ---- STEP 5: REAL verdict + report.json (no resolver-failure degradation) ----
    verdict = pl.verdict_for(enriched, resolver, mock_backend)
    assert verdict.status.value in THREE_CATEGORIES
    assert not verdict.needs_review, "resolver succeeded -> should not be flagged for review"
    assert not verdict.explanation.startswith("Could not resolve"), \
        "Step 3 silently failed inside the orchestrator"
    report_doc = pl.to_report(pl.verify_enriched([enriched], resolver, mock_backend), [enriched])
    assert isinstance(report_doc, ReportDocument) and len(report_doc.citations) == 1
    agent.case("e2e", "step5.verdict+report").expect(
        category_in_3=True, frontend_status_in_3=True).check(
        status=verdict.status.value, category_in_3=verdict.status.value in THREE_CATEGORIES,
        frontend_status=report_doc.citations[0].status,
        frontend_status_in_3=report_doc.citations[0].status in {"verified", "mischar", "risk"})


@pytest.mark.integration
@requires_fastembed
@requires_live_llm
def test_full_pipeline_live(agent, tiny_index, tiny_corpus):
    """Fullest real path: LLM enrichment (Step 1) + real resolve (Step 3) + Vertex judge
    (Step 4) + orchestrator (Step 5), then validate report.json end-to-end."""
    from app.services.citation_llm_service import enrich_from_text
    from app.services.distortion_backend import get_backend

    enriched = enrich_from_text(BRIEF)
    assert enriched, "Step 1 LLM enrichment returned no citations"
    resolver = rs.ResolverService(index_dir=tiny_index, corpus_dir=tiny_corpus)
    resp = pl.verify_enriched(enriched, resolver, get_backend("vertex"), "brief.pdf")
    report = pl.to_report(resp, enriched)

    # every citation completed the chain into one of the 3 categories; report validates
    ReportDocument.model_validate(report.model_dump())
    statuses = {c.status for c in report.citations}
    agent.case("e2e", "full_live").expect(all_in_3=True, n_ok=True).check(
        n=len(report.citations), statuses=sorted(statuses), n_ok=len(report.citations) >= 1,
        all_in_3=statuses <= {"verified", "mischar", "risk"})
