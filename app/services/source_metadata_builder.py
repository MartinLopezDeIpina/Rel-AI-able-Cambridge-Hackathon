"""One-off builder: extract citation metadata for every source judgment in ``data/``.

This is a **preprocessing step, not part of the runtime pipeline** — the moral
equivalent of :mod:`app.services.indexer` (which builds the vector index once). Run
it once whenever the source corpus changes; it writes a JSON metadata "database"
(``data/source_metadata.json``) that the runtime pipeline reads back later.

Per document it does the minimum it needs (just the first page or two), in two stages:

1. **Get the leading text.** If the full-document transcript produced by
   :mod:`app.services.vision_ocr` already exists under ``data/text_source/``, a prefix
   of it is used (no re-OCR). Otherwise the first page is vision-OCR'd on demand.
2. **Extract metadata.** A text LLM reads that text plus the filename title and returns
   the :class:`SourceMetadataFields` JSON, leaving any field not stated as ``null``
   (it never fabricates).

If the essential fields (case name + year) are missing, the builder escalates — more
of the cached text, or the next OCR'd page — up to ``vision_max_pages``. A document
still missing essentials after that is recorded with ``status="error"`` for manual
review rather than guessed.

Each document runs inside one ``@traceable`` span, so LangSmith shows a single grouped
trace per document. The provider is forced to the multimodal builder provider
(``source_llm_provider``, default Gemini via Vertex) — see
:func:`app.services.vision_ocr.build_vision_llm`.

CLI (mirrors the indexer's run-once invocation)::

    python -m app.services.source_metadata_builder [source_dir] [out_json]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from langsmith import traceable

from app.core.config import _ENV_FILE, Settings, get_settings

# Load .env so LANGSMITH_* (tracing) and provider creds are in os.environ.
load_dotenv(_ENV_FILE)

from app.schemas.citation import (
    SourceExtraction,
    SourceMetadata,
    SourceMetadataFields,
)
from app.services.vision_ocr import (
    build_vision_llm,
    invoke_with_backoff,
    render_pages,
    transcribe_images,
)

# Fields that must be present for an extraction to count as successful; missing them
# triggers escalation and, ultimately, an error entry for manual review.
_ESSENTIAL_FIELDS = ("case_name", "year")

# Rough chars-per-page, used to grow the slice of cached full text per escalation.
_CHARS_PER_PAGE = 4000

_META_SYSTEM_PROMPT = """You are a UK legal citation analyst. You are given the \
transcribed text of the FIRST page(s) of a single law-report/judgment, plus the \
source file's title. Extract metadata for THIS case STRICTLY from what is present.

Rules:
- Use ONLY information in the transcribed text or unambiguously in the title. Never \
invent or use outside knowledge. If a field is not stated, set it to null.
- case_name: the parties as written, e.g. "OBG Ltd v Allan".
- year: the decision/report year as an integer, e.g. 2007.
- court: the neutral court code ONLY for a genuine neutral citation actually printed \
in the text, e.g. UKHL, UKSC, EWHC, EWCA Civ. Do NOT infer a modern code for an old \
nominate report (e.g. an 1854 Exchequer case) — leave null and use court_name instead.
- division: bracketed EWHC division if shown, e.g. Comm, Ch, TCC.
- reporter: law-report series if shown, e.g. AC, QB, Ch, WLR, All ER, Ex.
- volume: report volume number if shown (integer).
- number: neutral citation case number if shown (integer), e.g. 21 in [2007] UKHL 21.
- page: law-report page if shown (integer).
- citation_type: one of "neutral" (court-assigned, e.g. [2007] UKHL 21), \
"law_report" (modern series, e.g. [1952] Ch 646), or "nominate" (old round-bracket \
report, e.g. (1853) 2 E&B 216); null if unclear.
- raw: the case's own primary citation exactly as printed, e.g. "[2007] UKHL 21".
- court_name: the deciding court in words, e.g. "House of Lords", "Court of Appeal".
- judges: list of judges named, exactly as written (e.g. "Lord Hoffmann"); [] if none.
- decision_date: the judgment date as printed, e.g. "2 May 2007"; null if absent.

Respond with ONLY a JSON object of the form:
{"item": {"case_name": ..., "year": ..., "court": ..., "division": ..., \
"reporter": ..., "volume": ..., "number": ..., "page": ..., "citation_type": ..., \
"raw": ..., "court_name": ..., "judges": [...], "decision_date": ...}}
No prose, no markdown fences."""

_META_HUMAN_TEMPLATE = """SOURCE FILE TITLE: {title}

TRANSCRIBED PAGE TEXT:
\"\"\"
{text}
\"\"\""""


def _parse_extraction(content: str) -> SourceExtraction:
    """Parse the stage-2 reply, tolerating markdown fences / surrounding prose.

    Mirrors ``citation_llm_service._parse_extraction``.
    """
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return SourceExtraction.model_validate_json(text)


def _extract_metadata(llm, text: str, title: str) -> SourceMetadataFields:
    """Stage 2: extract citation metadata from the transcribed text (one retry)."""
    from langchain_core.messages import HumanMessage, SystemMessage

    human = _META_HUMAN_TEMPLATE.format(title=title, text=text)
    messages = [SystemMessage(content=_META_SYSTEM_PROMPT), HumanMessage(content=human)]

    last_error: Exception | None = None
    for _ in range(2):
        response = invoke_with_backoff(llm, messages)
        try:
            return _parse_extraction(str(response.content)).item
        except Exception as error:  # noqa: BLE001 - retry on any parse/validation issue
            last_error = error
            messages.append(HumanMessage(
                content='Your previous reply was not valid JSON matching the schema. '
                        'Reply with ONLY {"item": {...}} and nothing else.'))
    raise RuntimeError(f"stage-2 LLM did not return valid JSON: {last_error}")


def _has_essentials(fields: SourceMetadataFields) -> bool:
    return all(getattr(fields, name) is not None for name in _ESSENTIAL_FIELDS)


def _leading_text(llm, pdf_path: Path, n: int, settings: Settings,
                  cached: str | None, _ocr_state: dict) -> str | None:
    """Return the text for escalation step ``n`` (1-based): a growing slice of the
    cached full transcript when available, otherwise the first ``n`` pages OCR'd
    on demand (each page transcribed once, accumulated in ``_ocr_state``)."""
    if cached is not None:
        if (n - 1) * _CHARS_PER_PAGE >= len(cached) and n > 1:
            return None  # no more text to add
        return cached[: n * _CHARS_PER_PAGE]

    images = render_pages(pdf_path, n - 1, 1, settings.vision_dpi)
    if not images:
        return None  # ran out of pages
    page_text = transcribe_images(llm, images)
    _ocr_state["text"] = f"{_ocr_state.get('text', '')}\n\n{page_text}".strip()
    return _ocr_state["text"]


@traceable(run_type="chain", name="source_metadata_document")
def process_pdf(llm, pdf_path: Path, settings: Settings) -> SourceMetadata:
    """Extract metadata for one source PDF, escalating pages until essentials appear.

    Runs in a single traced span so the OCR (if any) and the metadata call(s) for this
    document group under one LangSmith trace.
    """
    cache_file = Path(settings.source_texts_dir) / f"{pdf_path.stem}.txt"
    cached = (cache_file.read_text(encoding="utf-8", errors="replace")
              if cache_file.is_file() else None)

    best: SourceMetadataFields | None = None
    last_error: str | None = None
    ocr_state: dict = {}
    used = 0

    for n in range(1, settings.vision_max_pages + 1):
        try:
            text = _leading_text(llm, pdf_path, n, settings, cached, ocr_state)
        except Exception as error:  # noqa: BLE001 - render/OCR failure -> stop escalating
            last_error = str(error)
            break
        if not text:
            break
        used = n
        try:
            fields = _extract_metadata(llm, text, pdf_path.name)
        except Exception as error:  # noqa: BLE001 - record and try the next page slice
            last_error = str(error)
            continue
        best = fields
        if _has_essentials(fields):
            return SourceMetadata(source=pdf_path.name, pages_used=n,
                                  **fields.model_dump())

    # Exhausted the page/text budget without the essential fields.
    if best is None:
        return SourceMetadata(source=pdf_path.name, status="error",
                              pages_used=used, error=last_error or "extraction failed")
    missing = [f for f in _ESSENTIAL_FIELDS if getattr(best, f) is None]
    return SourceMetadata(source=pdf_path.name, status="error", pages_used=used,
                          error=f"missing essential field(s) {missing}",
                          **best.model_dump())


def _docx_entry(path: Path) -> SourceMetadata:
    """Flag a .docx source for manual review (the vision path can't render it)."""
    return SourceMetadata(source=path.name, status="error",
                          error="docx not supported by the vision OCR path")


def collect_sources(source_dir: Path) -> list[Path]:
    """Every .pdf and .docx in the source directory, sorted by name."""
    return sorted(
        [p for p in source_dir.iterdir() if p.suffix.lower() in (".pdf", ".docx")],
        key=lambda p: p.name,
    )


def build(source_dir: Path, out_path: Path, settings: Settings | None = None) -> dict:
    """Build the source-metadata database; write it to ``out_path`` and return it."""
    settings = settings or get_settings()
    source_dir, out_path = Path(source_dir), Path(out_path)

    sources = collect_sources(source_dir)
    if not sources:
        raise ValueError(f"No .pdf/.docx sources found in {source_dir}.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    llm = build_vision_llm(settings)
    results: dict[str, dict] = {}
    errors: list[str] = []

    for i, src in enumerate(sources, start=1):
        print(f"  [{i}/{len(sources)}] {src.name} ...", file=sys.stderr, flush=True)
        try:
            if src.suffix.lower() == ".docx":
                meta = _docx_entry(src)
            else:
                meta = process_pdf(llm, src, settings)
        except Exception as error:  # noqa: BLE001 - never let one doc abort the run
            meta = SourceMetadata(source=src.name, status="error", error=str(error))

        results[src.name] = meta.model_dump()
        if meta.status == "error":
            errors.append(src.name)
            print(f"      ERROR: {meta.error}", file=sys.stderr, flush=True)
        else:
            print(f"      ok: {meta.case_name} ({meta.year}) "
                  f"[{meta.pages_used} page(s)]", file=sys.stderr, flush=True)

        # Idempotent partial save so an aborted long run keeps its progress.
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        if i < len(sources) and settings.source_request_sleep > 0:
            time.sleep(settings.source_request_sleep)

    ok = len(results) - len(errors)
    print(f"\nDone: {ok} ok, {len(errors)} error(s) -> {out_path}", file=sys.stderr)
    if errors:
        print("  review manually: " + ", ".join(errors), file=sys.stderr)
    return results


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    argv = sys.argv[1:] if argv is None else argv
    source_dir = Path(argv[0]) if len(argv) > 0 else Path(settings.source_dir)
    out_path = Path(argv[1]) if len(argv) > 1 else Path(settings.source_metadata_out)

    if not source_dir.is_dir():
        print(f"Error: source directory not found: {source_dir}", file=sys.stderr)
        return 2
    try:
        build(source_dir, out_path, settings)
    except Exception as exc:  # noqa: BLE001 - surface a clean CLI error
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
