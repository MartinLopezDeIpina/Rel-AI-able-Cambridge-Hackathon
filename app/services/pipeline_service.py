"""End-to-end orchestrator: brief -> per-citation verdict (M1 -> M3 -> M4 -> M5).

Joins the existing services into the object the frontend renders
(:class:`app.schemas.citation.VerifyResponse`):

  M1  extract + enrich citations            (citation_llm_service)
  M3  resolve each to a source / existence  (resolver_service)
  M4  faithfulness of the brief's claim     (distortion_service)
  M5  map to a 3-way verdict + blueprint    (here)

Design: the resolver and detector backend are injected, so this is unit-testable
without a built index or live LLM. The FABRICATED short-circuit (``needs_web`` ->
``DOESNT_EXIST``) skips the detector entirely, per the challenge spec.
"""
from __future__ import annotations

from collections import Counter

from app.schemas.citation import (
    CitationVerdict,
    ClassificationType,
    EnrichedCitation,
    VerifyResponse,
)
from app.services.distortion_service import analyze

# --------------------------------------------------------------------------
# Verdict helpers (M5)
# --------------------------------------------------------------------------
_STATUS = {
    "correct": ClassificationType.EXISTS_CORRECTLY_APPLIED,
    "mischaracterised": ClassificationType.EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT,
    "out_of_context": ClassificationType.EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT,
}


def _confidence(resolver_conf: float, report: dict | None) -> float:
    """How robustly the source supports the claim: resolver certainty x detector support."""
    if report is None:
        return 0.0
    support = 1.0 - max(report["mischaracterised_pct"], report["out_of_context_pct"]) / 100.0
    return round(max(0.0, min(1.0, resolver_conf * support)), 3)


def _explanation(status: ClassificationType, report: dict | None) -> str:
    """A concise, partner-readable 'why it's wrong' (empty when verified)."""
    if status == ClassificationType.DOESNT_EXIST:
        return ("No matching source judgment was found in the corpus, so this citation "
                "could not be verified and may be fabricated or mis-cited.")
    if status == ClassificationType.EXISTS_CORRECTLY_APPLIED or report is None:
        return ""
    flagged = report.get("premise_summary", [])
    reasons = [e["reason"] for e in flagged if e.get("label") == "VIOLATED"][:2]
    if not reasons:
        reasons = [e["reason"] for e in flagged][:2]
    if reasons:
        return " ".join(reasons)[:400]
    if report["classification"] == "out_of_context":
        return "The cited source does not address the proposition the brief relies on it for."
    return "The brief's characterisation is not supported by the cited source."


def _citation_string(c: EnrichedCitation) -> str:
    """What we hand the resolver: full name (for name match) + raw (for the year/series)."""
    name = c.full_case_name or c.case_name or ""
    return f"{name} {c.raw}".strip()


def _name(c: EnrichedCitation) -> str:
    return c.full_case_name or c.case_name or c.raw


def verdict_for(c: EnrichedCitation, resolver, backend,
                global_summary: str = "") -> CitationVerdict:
    """Resolve one enriched citation (M3), check faithfulness (M4), map to a verdict (M5)."""
    claim = c.relevant_text or c.proposition or ""

    # ---- M3: resolve / existence (resilient: index may not be built yet) ----
    try:
        res = resolver.resolve(_citation_string(c))
    except Exception as exc:  # noqa: BLE001 - resolver/index unavailable -> needs review
        return CitationVerdict(
            id=c.id, citation_name=_name(c), raw=c.raw,
            status=ClassificationType.EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT,
            confidence_score=0.0, associate_claim=claim, actual_holding="",
            explanation=f"Could not resolve the source ({type(exc).__name__}); manual review needed.",
            ground=c.ground, needs_review=True)

    # ---- M5a: FABRICATED short-circuit (skip the detector) ----
    if res.get("needs_web"):
        return CitationVerdict(
            id=c.id, citation_name=_name(c), raw=c.raw,
            status=ClassificationType.DOESNT_EXIST, confidence_score=0.0,
            associate_claim=claim, actual_holding="",
            explanation=_explanation(ClassificationType.DOESNT_EXIST, None),
            ground=c.ground, needs_review=True,
            used_semantic_fallback=res.get("used_semantic_fallback", False),
            chosen_source=None)

    # ---- M4: faithfulness of the claim against the resolved source ----
    source_text = ""
    try:
        source_text = resolver.source_text(res["chosen_source"])
    except Exception:  # noqa: BLE001
        source_text = ""
    report, _ = analyze(claim, source_text, backend, id=c.id, global_summary=global_summary)

    # ---- M5b: verdict ----
    status = _STATUS.get(report["classification"],
                         ClassificationType.EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT)
    return CitationVerdict(
        id=c.id, citation_name=_name(c), raw=c.raw, status=status,
        confidence_score=_confidence(res.get("confidence", 0.0), report),
        associate_claim=claim,
        actual_holding=report.get("plain_language_holding", ""),
        explanation=_explanation(status, report),
        ground=c.ground,
        needs_review=bool(res.get("uncertain", False)),
        used_semantic_fallback=res.get("used_semantic_fallback", False),
        chosen_source=res.get("chosen_source"),
        detector_classification=report["classification"],
        mischaracterised_pct=report["mischaracterised_pct"],
        out_of_context_pct=report["out_of_context_pct"])


def _summary(verdicts: list[CitationVerdict]) -> dict[str, int]:
    c = Counter(v.status.value for v in verdicts)
    return {
        "verified": c[ClassificationType.EXISTS_CORRECTLY_APPLIED.value],
        "mischaracterised": c[ClassificationType.EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT.value],
        "fabricated": c[ClassificationType.DOESNT_EXIST.value],
        "needs_review": sum(1 for v in verdicts if v.needs_review),
        "total": len(verdicts),
    }


def verify_enriched(enriched: list[EnrichedCitation], resolver, backend,
                    document_name: str | None = None) -> VerifyResponse:
    """Core orchestration over already-enriched citations (DI-friendly, no I/O)."""
    verdicts = [verdict_for(c, resolver, backend) for c in enriched]
    return VerifyResponse(document_name=document_name, citations=verdicts,
                          summary=_summary(verdicts))


# --------------------------------------------------------------------------
# Entry points wiring in the real services (used by the API)
# --------------------------------------------------------------------------
def _default_backend():
    from app.core.config import get_settings
    from app.services.distortion_backend import get_backend
    return get_backend(get_settings().distortion_backend)


def _default_resolver():
    from app.services.resolver_service import get_resolver_service
    return get_resolver_service()


def verify_document(pdf_path, resolver=None, backend=None,
                    document_name: str | None = None) -> VerifyResponse:
    """M1 from a PDF, then orchestrate. Uses the real resolver/backend by default."""
    from app.services.citation_llm_service import extract_enriched_citations
    enriched = extract_enriched_citations(pdf_path)
    return verify_enriched(enriched, resolver or _default_resolver(),
                           backend or _default_backend(), document_name)


def verify_text(text: str, resolver=None, backend=None,
                document_name: str | None = None) -> VerifyResponse:
    """M1 from pasted text, then orchestrate."""
    from app.services.citation_llm_service import enrich_from_text
    enriched = enrich_from_text(text)
    return verify_enriched(enriched, resolver or _default_resolver(),
                           backend or _default_backend(), document_name)
