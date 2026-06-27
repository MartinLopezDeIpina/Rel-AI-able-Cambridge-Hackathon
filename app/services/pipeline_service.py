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

import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.citation import (
    CitationVerdict,
    ClassificationType,
    EnrichedCitation,
    VerifyResponse,
)
from app.schemas.report import ReportCitation, ReportDocument
from app.services.distortion_service import analyze

logger = logging.getLogger(__name__)
_REPO_ROOT = Path(__file__).resolve().parents[2]

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
# report.json serialization (Step 5 deliverable)  — see documentation/Sprint4/STEP-5.md
# --------------------------------------------------------------------------
# Per-status fallbacks so every field is non-empty even when the detector was skipped
# (FABRICATED) or the LLM returned blanks. LLM-produced text always takes precedence.
_STATUS_DEFAULTS: dict[str, dict[str, str]] = {
    "verified": {
        "issue": "None", "action": "Retain", "recommendation": "No action required.",
        "summary": "This authority exists and is correctly applied.",
        "holding": "The cited source supports the proposition it is relied on for.",
        "howUsed": "Cited in support of the argument.",
        "reasoning": "The proposition aligns with the source; the citation is correctly applied.",
    },
    "mischar": {
        "issue": "Authority mischaracterised", "action": "Revise paragraph",
        "recommendation": "Reformulate to match the actual holding.",
        "summary": "This authority is real but materially mischaracterised.",
        "holding": "The cited source does not support the proposition as stated.",
        "howUsed": "Cited in support of the argument.",
        "reasoning": "The brief's characterisation is not supported by the cited source.",
    },
    "risk": {
        "issue": "Authority cannot be verified", "action": "Remove / verify",
        "recommendation": "Remove the citation or verify it against a legal database.",
        "summary": "This authority could not be verified and may be fabricated.",
        "holding": "No matching source judgment was found; the holding could not be confirmed.",
        "howUsed": "Cited in support of the argument.",
        "reasoning": "No matching source was found in the corpus, so the citation could not be verified.",
    },
}


def _frontend_status(v: CitationVerdict) -> str:
    """Map the 3 user-facing verdicts to the 3 challenge categories the frontend renders.

    These are the only three buckets the challenge defines:
      DOESNT_EXIST                            -> risk      (fabricated)
      EXISTS_MISCHARACTERISED…/out_of_context -> mischar   (real but misused)
      EXISTS_CORRECTLY_APPLIED                -> verified  (real + correctly applied)
    """
    if v.status == ClassificationType.DOESNT_EXIST:
        return "risk"
    if v.status == ClassificationType.EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT:
        return "mischar"
    return "verified"  # EXISTS_CORRECTLY_APPLIED


def _first_sentence(text: str) -> str:
    text = (text or "").strip()
    m = re.search(r"\.(?:\s|$)", text)
    return text[: m.end()].strip() if m else text


def _report_citation(v: CitationVerdict, e: EnrichedCitation | None) -> ReportCitation:
    """Map one verdict (+ its enriched citation for year/court/ground) to the UI shape."""
    status = _frontend_status(v)
    d = _STATUS_DEFAULTS[status]

    court = ((e.court_name or e.court) if e else None) or "Unknown court"
    holding = (v.actual_holding or "").strip() or d["holding"]
    how_used = (v.associate_claim or "").strip() or (e.proposition if e else None) or d["howUsed"]
    reasoning = (v.explanation or "").strip() or d["reasoning"]
    return ReportCitation(
        id=f"c{v.id}",
        caseName=(v.citation_name or "").strip() or v.raw,
        court=court.strip() or "Unknown court",
        year=e.year if e else 0,
        citation=v.raw,
        status=status,  # type: ignore[arg-type]
        confidence=max(0, min(100, round((v.confidence_score or 0.0) * 100))),
        summary=_first_sentence(holding) or d["summary"],
        holding=holding,
        howUsed=how_used,
        reasoning=reasoning,
        recommendation=d["recommendation"],
        issue=d["issue"],
        action=d["action"],
        ground=(v.ground or (e.ground if e else None) or "Unassigned"),
        paragraph=max(0, v.id - 1),
    )


def to_report(response: VerifyResponse, enriched: list[EnrichedCitation],
              *, status: str = "complete") -> ReportDocument:
    """Build the validated `report.json` model from a VerifyResponse + its enriched cites.

    Enriched citations carry year/court/ground that the verdict drops; they're matched
    back by ``id``. Validation is fail-loud (an empty/invalid field raises here)."""
    by_id = {e.id: e for e in enriched}
    cits = [_report_citation(v, by_id.get(v.id)) for v in response.citations]
    counts = Counter(c.status for c in cits)
    summary = {k: counts[k] for k in ("verified", "mischar", "risk")}
    summary["total"] = len(cits)
    return ReportDocument(
        status=status,  # type: ignore[arg-type]
        generated_at=datetime.now(timezone.utc).isoformat(),
        summary=summary,
        citations=cits,
    )


def write_report(report: ReportDocument, path: str | os.PathLike | None = None) -> Path:
    """Atomically write `report.json` (temp file + os.replace) so a polling frontend
    never reads a half-written file. Relative paths resolve against the repo root."""
    from app.core.config import get_settings

    target = Path(path or get_settings().report_output_path)
    if not target.is_absolute():
        target = _REPO_ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, target)
    return target


def _persist_report(response: VerifyResponse, enriched: list[EnrichedCitation]) -> None:
    """Serialize + write report.json as a side effect. Validation errors propagate
    (fail-loud, inconsistent report); IO errors are logged and swallowed."""
    report = to_report(response, enriched)
    try:
        write_report(report)
    except OSError:
        logger.exception("Failed to write report.json")


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
    response = verify_enriched(enriched, resolver or _default_resolver(),
                               backend or _default_backend(), document_name)
    _persist_report(response, enriched)
    return response


def verify_text(text: str, resolver=None, backend=None,
                document_name: str | None = None) -> VerifyResponse:
    """M1 from pasted text, then orchestrate."""
    from app.services.citation_llm_service import extract_enriched_citations_from_text
    enriched = extract_enriched_citations_from_text(text)
    response = verify_enriched(enriched, resolver or _default_resolver(),
                               backend or _default_backend(), document_name)
    _persist_report(response, enriched)
    return response
