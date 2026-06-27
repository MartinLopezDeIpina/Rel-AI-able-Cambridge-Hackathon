"""Step 5 orchestrator: an uploaded document -> a per-citation verdict for the UI.

Chains the whole pipeline:
  1. citing-side extraction + LLM enrichment (Step 1),
  2. existence + metadata-equality match against the sources DB (the metadata-match
     layer), then
  3. for every citation whose **source document exists** (matched to a source id), the
     Step-4 faithfulness detector — fed the citing claim (``relevant_text``) and the
     matched source's transcript text (``data/text_source/<stem>.txt``).

The three buckets are collapsed into :class:`ClassificationType` plus the fields the
frontend consumes (see ``documentation/Sprint3/contracts.md`` / ``assert_verify_response``).
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from app.core.config import _ENV_FILE, Settings, get_settings

load_dotenv(_ENV_FILE)

from app.schemas.citation import ClassificationType, MetadataMatchResult
from app.services import distortion_service
from app.services.distortion_backend import get_backend
from app.services.metadata_match_service import verify_citations_metadata


def _source_text(matched_source: str | None, settings: Settings) -> str:
    """The transcript text for a matched source filename ("" if it isn't on disk).

    The metadata-match returns the source's PDF filename; its vision-OCR transcript is
    ``source_texts_dir/<stem>.txt`` (produced once by the vision_ocr pipeline)."""
    if not matched_source:
        return ""
    path = Path(settings.source_texts_dir) / f"{Path(matched_source).stem}.txt"
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def _verdict(r: MetadataMatchResult, report: dict | None) -> ClassificationType:
    if not r.exists:
        return ClassificationType.DOESNT_EXIST
    if report is not None and report["classification"] in ("mischaracterised", "out_of_context"):
        return ClassificationType.EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT
    return ClassificationType.EXISTS_CORRECTLY_APPLIED


def _confidence(status: ClassificationType, report: dict | None) -> float:
    """0..1 confidence the citation is sound. Fabricated -> 0; otherwise driven by the
    faithfulness margin when Step 4 ran, else a moderate 'exists but unchecked'."""
    if status == ClassificationType.DOESNT_EXIST:
        return 0.0
    if report is not None:
        worst = max(report["mischaracterised_pct"], report["out_of_context_pct"])
        return round(max(0.0, min(1.0, 1.0 - worst / 100.0)), 3)
    return 0.6


def _explanation(status: ClassificationType, r: MetadataMatchResult,
                 report: dict | None) -> str:
    if status == ClassificationType.DOESNT_EXIST:
        if r.needs_review:
            return r.reason or "Existence could not be confirmed; manual review advised."
        return ("This citation could not be matched to any case in the sources "
                "database — it may be fabricated or mis-cited.")
    if report is not None and report["classification"] == "mischaracterised":
        msg = "The brief appears to mischaracterise what this case actually decided."
    elif report is not None and report["classification"] == "out_of_context":
        msg = ("The brief appears to cite this case out of context — the source does "
               "not address the proposition it is cited for.")
    elif report is not None:
        msg = "The brief's use of this case is consistent with what it actually decided."
    else:
        msg = "The case exists in the sources; its in-context use was not assessed."
    if r.field_mismatches:
        fields = ", ".join(m.field for m in r.field_mismatches)
        msg += f" Note: the citation's {fields} differ from the source record."
    return msg


def _to_item(c, r: MetadataMatchResult, report: dict | None) -> dict:
    status = _verdict(r, report)
    return {
        "id": c.id,
        # --- frontend contract (assert_verify_response) ---
        "citation_name": c.full_case_name or c.case_name or c.raw,
        "year": c.year,
        "court": c.court_name or c.court,
        "status": status.value,
        "confidence_score": _confidence(status, report),
        "associate_claim": c.relevant_text or c.proposition or "",
        "actual_holding": report["plain_language_holding"] if report else "",
        "explanation": _explanation(status, r, report),
        # --- extras for the dashboard / drawer ---
        "raw": c.raw,
        "needs_review": r.needs_review,
        "matched_source": r.matched_source,
        "match_method": r.match_method,
        "used_semantic_fallback": r.used_semantic_fallback,
        "field_mismatches": [m.model_dump() for m in r.field_mismatches],
        "distortion": report,  # full Step-4 report (or None when not run)
    }


def verify_document(*, pdf_path: str | Path | None = None, text: str | None = None,
                    settings: Settings | None = None) -> dict:
    """Run the full pipeline on a PDF path **or** raw pasted text; return the per-citation
    report the frontend consumes (``{"citations": [...], "summary": {...}}``)."""
    settings = settings or get_settings()

    if pdf_path is not None:
        from app.services.citation_llm_service import extract_enriched_citations
        enriched = extract_enriched_citations(pdf_path)
    else:
        from app.services.citation_llm_service import extract_enriched_citations_from_text
        enriched = extract_enriched_citations_from_text(text or "")

    matches = verify_citations_metadata(enriched, settings=settings)
    by_id = {m.id: m for m in matches}
    backend = get_backend(settings.distortion_backend)

    items: list[dict] = []
    for c in enriched:
        r = by_id[c.id]
        report = None
        # When the cited case EXISTS, plug its source text + the citing claim into Step 4.
        if r.exists and r.matched_source:
            source_text = _source_text(r.matched_source, settings)
            if source_text:  # only when the source document's transcript is on disk
                try:
                    report, _ = distortion_service.analyze(
                        c.relevant_text or c.proposition or "", source_text, backend, id=c.id)
                except Exception:  # noqa: BLE001 - one Step-4 hiccup must not fail the doc
                    report = None  # exists, but faithfulness left unassessed
        items.append(_to_item(c, r, report))

    n_exist = sum(1 for it in items if it["status"] != ClassificationType.DOESNT_EXIST.value)
    return {
        "citations": items,
        "summary": {
            "total": len(items),
            "exists": n_exist,
            "doesnt_exist": len(items) - n_exist,
            "needs_review": sum(1 for it in items if it["needs_review"]),
            "mischaracterised": sum(
                1 for it in items
                if it["status"] == ClassificationType.EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT.value),
        },
    }
