"""Vision-model OCR for source judgments: PDF -> full plain text.

This is the **full-text** preprocessing pipeline (a sibling of, and shared toolbox
for, :mod:`app.services.source_metadata_builder`). It rasterises **every** page of a
source PDF and asks a multimodal model to transcribe it, then writes one
``<stem>.txt`` per source under ``data/text_source/`` for later pipeline steps to use.

It also exposes the low-level primitives the metadata builder reuses: the
vision-capable LLM, page rendering, and a rate-limit-aware invoke.

Both pipelines run each document inside a single ``@traceable`` span, so LangSmith
shows one grouped trace per document (all the per-page vision calls nested under it)
rather than dozens of disconnected calls.

CLI::

    python -m app.services.vision_ocr [source_dir] [texts_dir]
"""

from __future__ import annotations

import base64
import contextvars
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree, tracing_context

from app.core.config import _ENV_FILE, Settings, get_settings

# Load .env so LANGSMITH_* (tracing) and provider creds are in os.environ.
load_dotenv(_ENV_FILE)

from app.services.citation_llm_service import build_llm

_OCR_INSTRUCTION = (
    "Transcribe ALL text visible in the following page image(s) of a UK court "
    "judgment, verbatim and in natural reading order. Include headers, footnotes, "
    "party names, citations, judges and dates. If several images are given, "
    "transcribe them in order. Output ONLY the transcribed plain text — do not "
    "summarise, translate, comment, or add anything of your own."
)


# Hard cap on a single vision call's output. Three dense law-report pages are well
# under this; the cap exists to stop pathological runaway generations (e.g. the model
# emitting tens of thousands of space characters) from burning tokens.
_MAX_OUTPUT_TOKENS = 8192


def build_vision_llm(settings: Settings | None = None):
    """Build the multimodal LLM for OCR (output-token-capped).

    Stage-1 OCR needs vision, so we force the builder's own provider
    (``source_llm_provider``, default Gemini via Vertex) regardless of the runtime
    ``llm_provider`` (which may be a text-only model like Nemotron).
    """
    settings = settings or get_settings()
    llm = build_llm(settings.model_copy(
        update={"llm_provider": settings.source_llm_provider}))
    return llm.bind(max_output_tokens=_MAX_OUTPUT_TOKENS)


# A phrase of >=12 chars immediately repeated 3+ times — the signature of a degenerate
# greedy decode (the model looping on a span). Collapse such runs to one occurrence.
# This is a backtracking regex (O(n^2) worst case), so it is applied ONLY to bounded
# vision-OCR output, never to whole large documents.
_REPEAT_RUN = re.compile(r"(.{12,}?)\1{2,}", re.DOTALL)
_REPEAT_GUARD_MAX = 64_000  # don't run the backtracking collapse above this length


def _light_clean(text: str) -> str:
    """Cheap, linear whitespace normalisation: runs of spaces/tabs to one, trailing
    space stripped, 3+ blank lines collapsed to one. Safe on whole large documents."""
    lines = [re.sub(r"[ \t]{2,}", " ", ln).rstrip() for ln in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _clean_vision_text(text: str) -> str:
    """Sanitise one vision-OCR result: collapse pathological repeated-phrase runs (a
    known vision-decode failure mode) then normalise whitespace. Only used on bounded
    per-call output, where the backtracking collapse is cheap."""
    if len(text) <= _REPEAT_GUARD_MAX:
        text = _REPEAT_RUN.sub(r"\1", text)
    return _light_clean(text)


def render_pages(pdf_path: Path, start: int, count: int, dpi: int) -> list[bytes]:
    """Rasterise ``count`` pages starting at 0-based ``start`` to PNG bytes."""
    import fitz  # PyMuPDF — lazy import so the module loads without it installed.

    images: list[bytes] = []
    with fitz.open(pdf_path) as doc:
        end = min(start + count, doc.page_count)
        for i in range(start, end):
            pix = doc[i].get_pixmap(dpi=dpi, alpha=False)
            images.append(pix.tobytes("png"))
    return images


def page_count(pdf_path: Path) -> int:
    import fitz

    with fitz.open(pdf_path) as doc:
        return doc.page_count


class RateLimitExhausted(Exception):
    """Raised when an LLM call keeps hitting rate limits after all retries — the
    signal the concurrent corpus builder uses to requeue a file at lower concurrency.
    """

    def __init__(self, original: Exception):
        self.original = original
        super().__init__(str(original))


def _is_rate_limit(error: Exception) -> bool:
    """Heuristic: does this exception look like a 429 / quota exhaustion?"""
    text = f"{type(error).__name__} {error}".lower()
    return any(
        token in text
        for token in ("rate limit", "ratelimit", "429", "resourceexhausted",
                      "resource exhausted", "quota", "too many requests")
    )


def invoke_with_backoff(llm, messages, *, max_tries: int = 4, base_sleep: float = 5.0):
    """Invoke the LLM, retrying with exponential backoff on rate-limit errors.

    Raises :class:`RateLimitExhausted` if every retry is rate-limited; other errors
    propagate unchanged.
    """
    last: Exception | None = None
    for attempt in range(max_tries):
        try:
            return llm.invoke(messages)
        except Exception as error:  # noqa: BLE001 - inspect message to decide retry
            if not _is_rate_limit(error):
                raise
            last = error
            if attempt == max_tries - 1:
                break
            wait = base_sleep * (2**attempt)
            print(f"    rate-limited; sleeping {wait:.0f}s "
                  f"(retry {attempt + 1}/{max_tries - 1})", file=sys.stderr, flush=True)
            time.sleep(wait)
    raise RateLimitExhausted(last) if last else RuntimeError("invoke failed")


# Global cap on simultaneous vision API calls across ALL files and page-batches.
# Set by ``build_text_corpus`` before fan-out; ``None`` means no cap (single-call use).
_VISION_SEMAPHORE: threading.Semaphore | None = None


def count_vision(pdf_path: Path, settings: Settings) -> tuple[int, int]:
    """Return ``(scanned_pages, vision_batches)`` a PDF will need, computed from the
    text layer only (no rendering) — used to size progress bars up front. A fully
    digital PDF returns ``(0, 0)``."""
    import fitz

    min_chars = settings.text_layer_min_chars
    batch = max(1, settings.vision_ocr_batch_pages)
    try:
        with fitz.open(pdf_path) as doc:
            run = pages = batches = 0
            for pno in range(doc.page_count):
                if len(doc[pno].get_text().strip()) >= min_chars:
                    batches += (run + batch - 1) // batch  # flush current scan run
                    run = 0
                else:
                    run += 1
                    pages += 1
            batches += (run + batch - 1) // batch
            return pages, batches
    except Exception:  # noqa: BLE001 - bar sizing is best-effort
        return 0, 0


class _Progress:
    """Live multi-bar progress for a corpus OCR run: a global vision-pages bar plus a
    per-file bar (pages done / total) for each scanned file, on rotating screen rows.

    Set as the module-global ``_PROGRESS`` by ``build_text_corpus`` so the worker
    threads in :func:`transcribe_full_document` can report per-page progress.
    """

    def __init__(self, total_scanned_pages: int, slots: int):
        import queue

        from tqdm import tqdm

        self._tqdm = tqdm
        self._lock = threading.Lock()
        self.pages_bar = tqdm(total=total_scanned_pages, desc="vision pages (all files)",
                              position=1, unit="pg", smoothing=0.1)
        self._free: "queue.Queue[int]" = queue.Queue()
        for pos in range(2, 2 + max(1, slots)):  # one screen row per concurrent file
            self._free.put(pos)

    def open_file(self, name: str, total_pages: int) -> list:
        """Create a per-file page bar; returns an opaque handle for advance/close."""
        pos = self._free.get()
        bar = self._tqdm(total=total_pages, desc=f"  {name[:38]}", position=pos,
                         unit="pg", leave=False)
        return [pos, bar]

    def advance(self, handle: list, n_pages: int) -> None:
        handle[1].update(n_pages)
        with self._lock:
            self.pages_bar.update(n_pages)

    def close_file(self, handle: list) -> None:
        handle[1].close()
        self._free.put(handle[0])

    def close(self) -> None:
        self.pages_bar.close()


_PROGRESS: _Progress | None = None


def transcribe_images(llm, images: list[bytes]) -> str:
    """Vision-OCR a batch of page images to plain text (one LLM call).

    Respects the global ``_VISION_SEMAPHORE`` so that, however many files and
    page-batches are fanned out concurrently, only a bounded number of vision calls
    are in flight at once.
    """
    from langchain_core.messages import HumanMessage

    content: list[dict] = [{"type": "text", "text": _OCR_INSTRUCTION}]
    for png in images:
        b64 = base64.b64encode(png).decode("ascii")
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"},
        })
    message = [HumanMessage(content=content)]
    sem = _VISION_SEMAPHORE
    # Don't trace the raw model call: its inputs carry the base64 page images (tens of
    # MB), which exceed LangSmith's per-run size limit and make the whole run fail to
    # ingest. The enclosing ``_ocr_page_batch`` span still records the page label and
    # the transcribed text, so progress stays visible without the image payload.
    with tracing_context(enabled=False):
        if sem is None:
            response = invoke_with_backoff(llm, message)
        else:
            with sem:
                response = invoke_with_backoff(llm, message)
    return _clean_vision_text(str(response.content))


@traceable(run_type="chain", process_inputs=lambda inputs: {"label": inputs.get("label")})
def _ocr_page_batch(llm, images: list[bytes], label: str) -> str:
    """Vision-OCR one page-batch as its own named LangSmith span (``label`` becomes the
    run name). The image bytes are redacted from this span's inputs (the nested model
    call logs them) so progress is readable; the span name carries the page range and
    "(k/total)" so you can watch batches complete within a document."""
    return transcribe_images(llm, images)


def _batch_label(first: int, last: int, k: int, total: int) -> str:
    a, b = first + 1, last + 1  # 1-based for humans
    pages = f"page {a}" if a == b else f"pages {a}-{b}"
    return f"{pages} ({k}/{total})"


@traceable(run_type="chain", name="vision_ocr_document")
def transcribe_full_document(llm, pdf_path: Path, settings: Settings) -> str:
    """Return the full text of a PDF, **hybrid** per page and **parallel** per batch.

    Hybrid: a page with a real text layer is read for free (digital PDF); only
    scanned/image pages are rasterised and sent to the vision model — so digital
    judgments (most of the corpus) skip the LLM entirely.

    Streamed + parallel: pages are walked once, and each batch of scanned pages is
    **submitted to the vision model as soon as it is rendered** (not after the whole
    document), so work starts in seconds and the progress bar moves immediately. The
    batches run concurrently (up to ``vision_intra_concurrency`` per file); each is its
    own named child span (e.g. "pages 7-9 (3/8)") that inherits this function's trace
    context via a copied :mod:`contextvars` snapshot, so a document's vision calls stay
    in one LangSmith trace. The global ``_VISION_SEMAPHORE`` bounds total in-flight
    calls across all files.
    """
    import fitz  # PyMuPDF — lazy import so the module loads without it installed.

    min_chars = settings.text_layer_min_chars
    batch = max(1, settings.vision_ocr_batch_pages)
    scanned_total, total = count_vision(pdf_path, settings)  # pages, batches
    intra = settings.vision_intra_concurrency or (total or 1)
    intra = max(1, min(intra, total or 1))

    # Per-file live page bar (pages done / total) when running under a corpus build.
    prog = _PROGRESS
    handle = prog.open_file(pdf_path.name, scanned_total) if (prog and scanned_total) else None

    segments: list[dict] = []  # ordered; each is text (has result) or vision (has future)
    n_text = n_scan = 0
    k = 0  # 1-based index of the vision batch being submitted

    pool = ThreadPoolExecutor(max_workers=intra)
    try:
        pending: list[tuple[int, bytes]] = []  # (page_index, png) buffered scanned pages

        def submit(chunk: list[tuple[int, bytes]]) -> None:
            nonlocal k
            k += 1
            first, last = chunk[0][0], chunk[-1][0]
            label = _batch_label(first, last, k, total)
            images = [png for _, png in chunk]
            seg = {"kind": "vision", "result": None}
            segments.append(seg)

            n_pages = len(images)

            def work() -> None:
                seg["result"] = _ocr_page_batch(llm, images, label)
                if handle is not None:  # advance this file's bar + the global pages bar
                    prog.advance(handle, n_pages)

            ctx = contextvars.copy_context()  # carry the trace context into the worker
            seg["future"] = pool.submit(ctx.run, work)

        def flush_pending() -> None:
            nonlocal pending
            for i in range(0, len(pending), batch):
                submit(pending[i : i + batch])
            pending = []

        with fitz.open(pdf_path) as doc:
            for pno in range(doc.page_count):
                embedded = doc[pno].get_text().strip()
                if len(embedded) >= min_chars:
                    flush_pending()  # keep order: emit buffered scans before this text
                    segments.append({"kind": "text", "result": embedded})
                    n_text += 1
                else:
                    png = doc[pno].get_pixmap(dpi=settings.vision_dpi,
                                              alpha=False).tobytes("png")
                    pending.append((pno, png))
                    n_scan += 1
            flush_pending()

        run = get_current_run_tree()  # record totals on the parent run for LangSmith
        if run is not None:
            try:
                run.add_metadata({"file": pdf_path.name, "total_pages": n_text + n_scan,
                                  "text_layer_pages": n_text, "scanned_pages": n_scan,
                                  "vision_batches": total})
            except Exception:  # noqa: BLE001 - metadata is best-effort, never fatal
                pass

        for seg in segments:  # wait for all vision batches (propagate any error)
            if "future" in seg:
                seg["result"] = seg["future"].result() or seg["result"]
    finally:
        pool.shutdown(wait=True)
        if handle is not None:
            prog.close_file(handle)

    try:
        from tqdm import tqdm
        tqdm.write(f"  done {pdf_path.name[:50]}: {n_text} text page(s), "
                   f"{n_scan} scanned in {total} batch(es)")
    except Exception:  # noqa: BLE001 - logging only
        pass
    return _light_clean("\n\n".join(seg["result"] for seg in segments if seg["result"]))


def _ocr_to_file(llm, pdf: Path, texts_dir: Path, settings: Settings) -> int:
    """OCR one PDF to ``texts_dir/<stem>.txt``; return char count. Raises on failure
    (``RateLimitExhausted`` for sustained rate limits)."""
    text = transcribe_full_document(llm, pdf, settings)
    (texts_dir / f"{pdf.stem}.txt").write_text(text + "\n", encoding="utf-8")
    return len(text)


def build_text_corpus(source_dir: Path, texts_dir: Path,
                      settings: Settings | None = None,
                      concurrency: int | None = None) -> dict[str, str]:
    """Vision-OCR every source PDF in ``source_dir`` to ``texts_dir/<stem>.txt``.

    Files are processed **concurrently** (one thread per file, each its own LangSmith
    trace). Concurrency starts at ``concurrency`` (or ``vision_ocr_concurrency``, or
    "all files at once" when 0) and **halves** whenever some files exhaust their
    rate-limit retries — those files are requeued at the lower concurrency, so the run
    adapts from "all at once" down to small batches only as far as the quota forces.

    Skips a PDF whose ``<stem>.txt`` already exists (idempotent / resumable).
    Returns ``{filename: status}`` where status is "ok", "cached", or an error string.
    """
    settings = settings or get_settings()
    source_dir, texts_dir = Path(source_dir), Path(texts_dir)
    texts_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(source_dir.glob("*.pdf"), key=lambda p: p.name)
    others = sorted(p for p in source_dir.iterdir()
                    if p.suffix.lower() not in (".pdf",))
    if not pdfs:
        raise ValueError(f"No .pdf sources found in {source_dir}.")

    from tqdm import tqdm

    # Bound total in-flight vision calls across the two layers of fan-out (files ×
    # page-batches). Set the module-global the workers consult.
    global _VISION_SEMAPHORE, _PROGRESS
    _VISION_SEMAPHORE = threading.Semaphore(max(1, settings.vision_max_concurrent_calls))

    llm = build_vision_llm(settings)
    statuses: dict[str, str] = {}
    lock = threading.Lock()

    pending = [p for p in pdfs if not (texts_dir / f"{p.stem}.txt").is_file()]
    n_cached = len(pdfs) - len(pending)
    for p in pdfs:
        if p not in pending:
            statuses[p.name] = "cached"

    # Classify the to-do files: digital (text layer only, no vision) vs scanned (needs
    # vision), and tally scanned pages/batches — so the run starts with a clear picture.
    work = {p: count_vision(p, settings) for p in pending}  # path -> (pages, batches)
    digital = [p for p, (pg, _b) in work.items() if pg == 0]
    vision_files = [p for p, (pg, _b) in work.items() if pg > 0]
    total_scanned_pages = sum(pg for pg, _b in work.values())
    total_batches = sum(b for _pg, b in work.values())

    requested = concurrency if concurrency is not None else settings.vision_ocr_concurrency
    conc = requested if requested and requested > 0 else len(pending)

    tqdm.write(
        f"Sources: {len(pdfs)} files | cached/skip: {n_cached} | to do: {len(pending)}\n"
        f"  - digital (text layer, no vision): {len(digital)}\n"
        f"  - need vision OCR: {len(vision_files)} files, "
        f"{total_scanned_pages} pages, {total_batches} batches\n"
        f"  - {min(conc, max(1, len(pending)))} file(s) at a time, "
        f"up to {settings.vision_max_concurrent_calls} vision calls in flight")

    # Live bars: files completed; global vision pages; and one per-file page bar per
    # concurrent scanned file (created/freed by transcribe_full_document via _PROGRESS).
    file_bar = tqdm(total=len(pdfs), initial=n_cached, desc="files done",
                    position=0, unit="file")
    _PROGRESS = _Progress(total_scanned_pages, slots=max(1, min(conc, len(pending) or 1)))

    try:
        while pending:
            conc = max(1, min(conc, len(pending)))
            tqdm.write(f"-- OCR wave: {len(pending)} file(s), concurrency={conc} --")
            rate_limited: list[Path] = []
            with ThreadPoolExecutor(max_workers=conc) as pool:
                futures = {pool.submit(_ocr_to_file, llm, pdf, texts_dir, settings): pdf
                           for pdf in pending}
                for future in as_completed(futures):
                    pdf = futures[future]
                    try:
                        n = future.result()
                        with lock:
                            statuses[pdf.name] = "ok"
                        file_bar.update(1)
                        tqdm.write(f"  ok: {pdf.name} ({n} chars)")
                    except RateLimitExhausted:
                        rate_limited.append(pdf)
                        tqdm.write(f"  rate-limited (requeue): {pdf.name}")
                    except Exception as error:  # noqa: BLE001 - record and move on
                        with lock:
                            statuses[pdf.name] = f"error: {error}"
                        file_bar.update(1)
                        tqdm.write(f"  ERROR: {pdf.name}: {error}")

            if rate_limited and conc == 1:
                wait = max(5.0, settings.source_request_sleep)
                tqdm.write(f"  still rate-limited at concurrency=1; sleeping {wait:.0f}s")
                time.sleep(wait)
            elif rate_limited:
                conc = max(1, conc // 2)  # adaptive batching: shrink and retry
            pending = rate_limited
    finally:
        _PROGRESS.close()
        file_bar.close()
        _PROGRESS = None

    for other in others:
        statuses[other.name] = "skipped: not a PDF"

    ok = sum(1 for s in statuses.values() if s in ("ok", "cached"))
    print(f"\nDone: {ok}/{len(pdfs)} PDFs transcribed -> {texts_dir}", file=sys.stderr)
    return statuses


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    argv = sys.argv[1:] if argv is None else argv
    source_dir = Path(argv[0]) if len(argv) > 0 else Path(settings.source_dir)
    texts_dir = Path(argv[1]) if len(argv) > 1 else Path(settings.source_texts_dir)

    if not source_dir.is_dir():
        print(f"Error: source directory not found: {source_dir}", file=sys.stderr)
        return 2
    try:
        build_text_corpus(source_dir, texts_dir, settings)
    except Exception as exc:  # noqa: BLE001 - surface a clean CLI error
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
