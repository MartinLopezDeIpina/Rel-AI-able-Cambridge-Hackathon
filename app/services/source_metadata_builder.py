"""One-off builder: source transcripts -> ``data/source_metadata.json``.

Run **once** to create the source-metadata database the verify layer
(:mod:`app.services.metadata_match_service`) reads. It is NOT part of the request
path, and it does NOT touch the PDFs or re-run OCR — the PDF->text pipeline
(:mod:`app.services.vision_ocr`) is a separate, already-completed step that produced
one transcript per source at ``data/text_source/<stem>.txt``.

For each transcript it feeds the **filename (title) + a generous leading-text window**
(``source_metadata_chars``; the identifying metadata sits in the first ~1-2k chars, so
the default is a wide safety margin) to Gemini, which returns the standard
Citation-shaped object (:class:`SourceMetadataFields`) via **structured output** — never
fabricating, leaving any field not present as ``null``.

Files are processed **concurrently with batch control**
(``source_metadata_concurrency`` worker threads) with a ``tqdm`` progress bar; each
extraction is one LangSmith trace.

CLI::

    python -m app.services.source_metadata_builder [texts_dir] [out_json]
"""

from __future__ import annotations

import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv
from langsmith import traceable

from app.core.config import _ENV_FILE, Settings, get_settings

# Load .env so LANGSMITH_* (tracing) and provider creds are in os.environ.
load_dotenv(_ENV_FILE)

from app.schemas.citation import SourceMetadata, SourceMetadataFields
from app.services.citation_llm_service import build_llm
from app.services.vision_ocr import invoke_with_backoff

_SYSTEM_PROMPT = """You are a UK legal citation analyst. You are given the leading text \
of a single law report / judgment, plus the source file's title. Extract metadata for \
THIS case STRICTLY from what is present.

Rules:
- Use ONLY information in the provided text or unambiguously in the title. Never invent \
or use outside knowledge. If a field is not stated, leave it null.
- case_name: the parties as written, e.g. "OBG Ltd v Allan".
- year: the decision/report year as an integer, e.g. 2007.
- court: the neutral court code ONLY for a genuine neutral citation actually printed in \
the text, e.g. UKHL, UKSC, EWHC, EWCA Civ. Do NOT infer a modern code for an old \
nominate report (e.g. an 1854 Exchequer case) — leave null and use court_name instead.
- division: bracketed EWHC division if shown, e.g. Comm, Ch, TCC.
- reporter: law-report series if shown, e.g. AC, QB, Ch, WLR, All ER, Ex.
- volume: report volume number if shown (integer).
- number: neutral citation case number if shown (integer), e.g. 21 in [2007] UKHL 21.
- page: law-report page if shown (integer).
- citation_type: one of "neutral" (court-assigned, e.g. [2007] UKHL 21), "law_report" \
(modern series, e.g. [1952] Ch 646), or "nominate" (old round-bracket report, e.g. \
(1853) 2 E&B 216); null if unclear.
- raw: the case's own primary citation exactly as printed, e.g. "[2007] UKHL 21".
- court_name: the deciding court in words, e.g. "House of Lords", "Court of Appeal".
- judges: list of judges named, exactly as written (e.g. "Lord Hoffmann"); [] if none.
- decision_date: the judgment date as printed, e.g. "2 May 2007"; null if absent."""

_HUMAN_TEMPLATE = """SOURCE FILE TITLE: {title}

LEADING TEXT OF THE JUDGMENT:
\"\"\"
{text}
\"\"\""""


def _build_structured_llm(settings: Settings):
    """Gemini (forced multimodal/Vertex provider) bound to return the standard
    Citation-shaped object directly via structured output."""
    model = build_llm(settings.model_copy(
        update={"llm_provider": settings.source_llm_provider}))
    return model.with_structured_output(SourceMetadataFields)


@traceable(run_type="chain", name="source_metadata_document",
           process_inputs=lambda i: {k: v for k, v in i.items() if k != "structured_llm"})
def extract_one(structured_llm, source_id: str, title: str, text: str) -> SourceMetadata:
    """Extract one source's metadata from its leading text (one structured call)."""
    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=_HUMAN_TEMPLATE.format(title=title, text=text))]
    fields = invoke_with_backoff(structured_llm, messages)
    if not isinstance(fields, SourceMetadataFields):
        raise RuntimeError("model did not return structured metadata")
    return SourceMetadata(source=source_id, **fields.model_dump())


def collect_texts(texts_dir: Path) -> list[Path]:
    """Every transcript ``.txt`` in ``texts_dir``, sorted by name."""
    return sorted(Path(texts_dir).glob("*.txt"), key=lambda p: p.name)


def build(texts_dir: Path, out_path: Path, settings: Settings | None = None) -> dict:
    """Build the source-metadata database from the transcripts; write it and return it."""
    from tqdm import tqdm

    settings = settings or get_settings()
    texts_dir, out_path = Path(texts_dir), Path(out_path)

    txts = collect_texts(texts_dir)
    if not txts:
        raise ValueError(f"No .txt transcripts found in {texts_dir}.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    structured_llm = _build_structured_llm(settings)
    n_chars = settings.source_metadata_chars
    conc = max(1, settings.source_metadata_concurrency)

    results: dict[str, dict] = {}
    errors: list[str] = []
    lock = threading.Lock()

    def work(txt: Path) -> tuple[str, SourceMetadata]:
        source_id = f"{txt.stem}.pdf"  # the original source filename / identifier
        text = txt.read_text(encoding="utf-8", errors="replace")[:n_chars]
        try:
            meta = extract_one(structured_llm, source_id, source_id, text)
        except Exception as error:  # noqa: BLE001 - one bad file never aborts the batch
            meta = SourceMetadata(source=source_id, status="error", error=str(error))
        return source_id, meta

    print(f"Extracting metadata for {len(txts)} source(s) | "
          f"{n_chars} leading chars each | {conc} at a time", file=sys.stderr)
    bar = tqdm(total=len(txts), desc="source metadata", unit="doc")
    with ThreadPoolExecutor(max_workers=conc) as pool:
        futures = [pool.submit(work, t) for t in txts]
        for future in as_completed(futures):
            source_id, meta = future.result()
            with lock:
                results[source_id] = meta.model_dump()
                if meta.status == "error":
                    errors.append(source_id)
            bar.update(1)
            if meta.status == "error":
                tqdm.write(f"  ERR  {source_id}: {meta.error}")
            else:
                tqdm.write(f"  ok   {source_id}: {meta.case_name} ({meta.year})")
    bar.close()

    ordered = {k: results[k] for k in sorted(results)}  # stable, name-sorted DB
    out_path.write_text(json.dumps(ordered, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"\nDone: {len(results) - len(errors)} ok, {len(errors)} error(s) -> {out_path}",
          file=sys.stderr)
    if errors:
        print("  review manually: " + ", ".join(errors), file=sys.stderr)
    return ordered


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    argv = sys.argv[1:] if argv is None else argv
    texts_dir = Path(argv[0]) if len(argv) > 0 else Path(settings.source_texts_dir)
    out_path = Path(argv[1]) if len(argv) > 1 else Path(settings.source_metadata_out)

    if not texts_dir.is_dir():
        print(f"Error: transcripts directory not found: {texts_dir}", file=sys.stderr)
        return 2
    try:
        build(texts_dir, out_path, settings)
    except Exception as exc:  # noqa: BLE001 - surface a clean CLI error
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
