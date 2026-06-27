# Integration Plan — plug Martin's extraction into Leo's verification, behind one API for the UI

**Decision of record:** we are plugging the two codebases together **now**. Martin's
FastAPI app is the shell; Martin's extractor is the front; Leo's resolver +
distortion detector are the back; Louisa & Kim's UI consumes a single
document-level verification endpoint. This document fixes the interfaces and the
REST contract so all three streams can work in parallel.

## 1. Target pipeline

```
 upload PDF / paste text
        │
        ▼
 [Martin] extract + enrich           extract_enriched_citations(pdf) -> list[EnrichedCitation]
        │   (id, raw, case_name, full_case_name, court, judges, proposition, ground, relevant_text)
        ▼
 [Martin] deterministic match        PRIMARY existence check: exact metadata match of the extracted
        │   (case name + year + neutral/report cite) against the legal dataset. Deterministic + explainable.
        ├── hit ──────────────────►  chosen_source (method="exact")
        │
        ├── miss ─► [Leo] semantic search (FALLBACK)   resolve_one(cite_str, embeddings, chunks, sources) -> dict
        │              │   (chosen_source, method='name'|'semantic', confidence, uncertain, needs_web, signals_agree)
        │              │   LOGGED + surfaced in the report: used_semantic_fallback = True
        │              └── needs_web ─► web_fallback (Perplexity) → "exists online but not in corpus" vs "non-existent"
        ▼
 [Leo] judge faithful use            analyze(relevant_text, source_text, backend, id=…) -> (report, id)
        │   report: (classification, mischaracterised_pct, out_of_context_pct, plain_language_holding, evaluations)
        ▼
 [merge] one CitationReport per cite → DocumentReport (counts + per-citation Classification)
        │
        ▼
 [Louisa & Kim] colour-coded dashboard
```

> **Resolution ordering (corrected per Leo's note).** Deterministic, exact
> metadata matching is the **primary** existence check; the semantic vector search
> is **only the fallback** when the exact match misses. Whenever the fallback
> decides the source, set `used_semantic_fallback = True` so it is **logged and
> shown in the analysis report** (semantic hits are less certain and a reviewer
> should know one was used). Leo's `resolve_one` already encodes this preference
> internally (a confident fuzzy **name** match wins; **semantic** is the fallback,
> exposed as `method`), so `used_semantic_fallback = (method == "semantic")`. The
> stronger *exact* metadata tier (structured field equality, owned by Martin) sits
> in front of `resolve_one` and short-circuits it on a hit.

## 2. Verified interfaces (read from source, not assumed)

### Martin — `app/services/citation_llm_service.py` / `citation_service.py`
```python
extract_citations(pdf_path: str | Path) -> list[Citation]
extract_enriched_citations(pdf_path: str | Path) -> list[EnrichedCitation]
read_pdf_text(pdf_path: str | Path) -> str          # collapses whitespace
```
`EnrichedCitation` fields (from `app/schemas/citation.py`): `id, raw, case_name,
year, court, division, reporter, volume, number, page, citation_type,
full_case_name, court_name, judges, proposition, ground, relevant_text`.

### Leo — `resolve_citations.py`
```python
load_index(index_dir: Path) -> (embeddings: np.ndarray, chunks: list[dict], sources: list[str])
resolve_one(citation: str, embeddings, chunks, sources) -> dict
# dict: chosen_source, method('name'|'semantic'), confidence, uncertain,
#       needs_web, signals_agree, name_top, semantic_top, name_ranking, semantic_ranking
```

### Leo — `detect_distortion.py` / integrated as `app/services/distortion_service.py` *(updated)*
```python
analyze(relevant_text: str, source_text: str, backend,
        top=50, k=5, size=60, overlap=0, id=None, global_summary="") -> tuple[dict, int | None]
# returns (report, id); report: classification('correct'|'mischaracterised'|'out_of_context'),
#       mischaracterised_pct, out_of_context_pct, r_top_ids,
#       premise_summary, evaluations, plain_language_holding
build_relevant_text_map(rows) -> dict[int, str]            # id -> relevant_text from EnrichedCitation rows
analyze_relevant_texts(rt_map, source_for, backend, ...) -> list[tuple[dict, int]]
get_backend(name)  # 'mock' (default, offline) | 'openrouter' (real LLM via Martin's integration)
```

> ✅ **Interface gotcha — resolved.** The two parameters used to both be called
> `citation` but mean different things, so the detector parameter was **renamed to
> `relevant_text`**:
> - `resolve_one(citation=…)` wants the **formal citation string** (e.g.
>   `"OBG Ltd v Allan [2007] UKHL 21"`) to match a source.
> - `analyze(relevant_text=…)` wants the **claim being checked** — *what the
>   document asserts the case stands for* — i.e. Martin's `relevant_text`
>   (fallback `proposition`), **not** the formal cite.
>
> `analyze` now also takes a pass-through `id` and returns `(report, id)` so a
> report can be re-associated with its citation row; `build_relevant_text_map`
> turns `list[EnrichedCitation]` into the `{id: relevant_text}` the batch helper
> `analyze_relevant_texts` consumes.

## 3. Adapters needed (small, well-bounded)

1. **Cite-string builder** (resolver input): `f"{c.full_case_name or c.case_name or ''} {c.raw}".strip()`.
2. **Source-text loader** (detector input): the resolver returns a *filename*
   (`chosen_source`); load `index/texts/<chosen_source>` and `E.normalize_ws(...)`
   it (same as `detect_distortion.run_eval`).
3. **Pasted-text path:** Martin's `extract_citations` is PDF-only (calls
   `read_pdf_text` internally). For the "paste text" ingestion mode, refactor the
   regex core into `extract_citations_from_text(text: str) -> list[Citation]` and
   have both `extract_citations(pdf)` and the paste path call it. **(Owner: Martin.)**
4. **Verdict mapper** (the 3 buckets the challenge asks for). Verified against the
   pipeline's actual outputs and mapped to the `ClassificationType` enum now in
   `app/schemas/citation.py`:

   | Condition (resolver + detector) | internal verdict | `ClassificationType` | extra flags |
   |---|---|---|---|
   | `needs_web` **and** web-fallback finds nothing | `NON_EXISTENT` | `DOESNT_EXIST` | — |
   | `needs_web` **and** web-fallback not configured (no key) | `UNVERIFIED` | *(see gap)* | `needs_review=True` |
   | resolved **and** detector `correct` | `VERIFIED` | `EXISTS_CORRECTLY_APPLIED` | `used_semantic_fallback=method=="semantic"` |
   | resolved **and** detector `mischaracterised` | `MISCHARACTERISED` | `EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT` | ″ |
   | resolved **and** detector `out_of_context` | `OUT_OF_CONTEXT` | `EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT` | ″ |

   **Coverage check — does this cover all conditions? Mostly, with two gaps to close:**
   - ⚠️ **`UNVERIFIED` has no home in the 3-value enum.** "Couldn't confirm" must
     **not** be silently folded into `DOESNT_EXIST` — that would falsely accuse a
     real case of being fabricated (a reputational-risk error for the partner).
     The `Classification` schema therefore carries a `needs_review: bool` flag;
     the UI shows these as a distinct "unverified / check manually" state rather
     than red. (Alternative: add a 4th enum value `UNVERIFIED`. We chose the flag
     to keep the three challenge buckets clean.)
   - ⚠️ **Empty/failed source text** makes `analyze` return `out_of_context` with
     `out_of_context_pct=100` (early return). If the source resolved but its text
     is missing/garbled (OCR failure), that would wrongly read as a content
     problem. Guard: if `chosen_source` resolved but `source_text` is empty, set
     `needs_review=True` instead of `OUT_OF_CONTEXT`.
   - Everything else (the three substantive buckets) is fully covered; the
     mischaracterised/out-of-context split is preserved internally for the
     explanation panel even though both collapse to one user-facing bucket.

## 4. Response schema for the UI (stable contract for Louisa & Kim)

**Already implemented** in `app/schemas/citation.py`: `ClassificationType` (the
3-value string enum), `Classification` (verdict object: `type, confidence,
needs_review, used_semantic_fallback, reason`) and `AnalysisDict` (typed mirror of
`analyze()`'s output). The remaining `CitationReport` / `DocumentReport` below are
the still-to-add wrappers the `/verify` route returns — they embed the existing
`Classification` and `AnalysisDict`:

```python
class CitationReport(EnrichedCitation):
    # resolution (Leo)
    chosen_source: str | None = None
    resolution_method: str | None = None        # name | semantic | web | none
    resolution_confidence: float | None = None
    signals_agree: bool | None = None
    # faithfulness (Leo)
    mischaracterised_pct: float | None = None
    out_of_context_pct: float | None = None
    plain_language_holding: str | None = None
    explanation: list[dict] = []                 # detector premise_summary
    # unified
    verdict: str                                 # VERIFIED|MISCHARACTERISED|OUT_OF_CONTEXT|NON_EXISTENT|UNVERIFIED
    confidence: float                            # 0..1 for the UI badge

class DocumentReport(BaseModel):
    source: str
    summary: dict                                # {total, verified, mischaracterised, out_of_context, non_existent}
    citations: list[CitationReport]
```

The UI colour-codes off `verdict`; the badge percentage is `confidence`; the
"why" panel renders `plain_language_holding` + `explanation`.

## 5. Proposed FastAPI routes

New file `app/api/endpoints/citations.py`, registered in `app/api/router.py`
(currently it only includes `items`):

```python
api_router.include_router(citations.router, prefix="/citations", tags=["citations"])
```

| Method & path | Body | Returns | Purpose |
|---|---|---|---|
| `POST /api/citations/extract` | `file` (PDF) **or** `{ "text": "…" }` | `list[EnrichedCitation]` | Martin's existing logic, just exposed. Fast, demo-able on its own. |
| `POST /api/citations/verify` | `file` (PDF) **or** `{ "text": "…" }` | `DocumentReport` | **Headline endpoint** — full pipeline: extract → resolve → detect → categorise. This is what the UI calls. |
| `GET /health` | — | `{ "status": "ok" }` | Already exists. |

Notes:
- Accept `multipart/form-data` (file) and `application/json` (`{text}`) on the
  same two endpoints so the UI can offer both "upload" and "paste".
- `/verify` is the only route the UI strictly needs; `/extract` stays as a fast
  fallback / debugging surface and keeps Martin's task-1 deliverable demoable.
- Wire it via DI mirroring Martin's `get_citation_llm_service()` — add a
  `get_verification_service()` that holds the loaded index in memory (load
  `embeddings/chunks/sources` once at startup in `main.py`'s `lifespan`).

## 6. New service: `app/services/verification_service.py`

Orchestrates the chain (owner: Leo + Martin pairing). Sketch:

```python
class VerificationService:
    def __init__(self, index_dir, backend_name="mock", texts_dir="index/texts"):
        self.embeddings, self.chunks, self.sources = load_index(Path(index_dir))
        self.backend = get_backend(backend_name)
        self.texts_dir = Path(texts_dir)

    def verify_document(self, enriched: list[EnrichedCitation]) -> DocumentReport:
        reports = []
        for c in enriched:
            res = resolve_one(cite_string(c), self.embeddings, self.chunks, self.sources)
            if res["needs_web"]:
                report = self._non_existent(c, res)              # → NON_EXISTENT / UNVERIFIED
            else:
                src_text = normalize_ws((self.texts_dir / res["chosen_source"]).read_text())
                claim = c.relevant_text or c.proposition or c.raw
                judged = analyze(claim, src_text, self.backend)
                report = self._merge(c, res, judged)             # → VERIFIED / MISCHAR… / OUT_OF_CONTEXT
            reports.append(report)
        return self._summarise(reports)
```

## 7. Prerequisites / open items

- [ ] **Run `build_index.py`** to produce `index/embeddings.npy` + `chunks.json` +
      `sources.json` (currently only `index/texts/` exists, 9 of 58 PDFs). The
      resolver cannot run without it. **(Owner: Leo.)** Requires `numpy`/`fastembed`.
- [ ] **Restore the corpus** Martin deleted from git ("too heavy") — share via a
      data drop, not the repo; both `index/` build and `index/texts/` depend on it.
- [ ] **Merge `requirements.txt`** — Martin's web stack (`fastapi`, `pypdf`,
      `langchain-openai`) + Leo's pipeline (`pymupdf`, `rapidocr-onnxruntime`,
      `fastembed`, `rapidfuzz`, `numpy`).
- [x] **Nemotron decision — done.** The offline `NemotronBackend` stub was removed
      from the integrated package; the LLM stages now run through Martin's
      OpenRouter integration via `app/services/distortion_backend.py::OpenRouterBackend`
      (`get_backend("openrouter")`). `MockBackend` stays the offline default, so
      `/verify` still runs with no key. *(Note: the proposed simplified workflow
      reintroduces a dedicated **Nemotron Rerank** model for the rerank stage —
      that is a separate reranker role, not the removed judge stub; see
      `workflow-comparison.md`.)*
- [ ] `extract_citations_from_text` refactor for the paste path. **(Owner: Martin.)**
- [x] **Repo home — done.** Leo's modules are integrated into Martin's existing
      `app/services/` (`distortion_service`, `distortion_backend`,
      `distortion_prompts`, `pdf_ocr`, `citelib`, `indexer`, `resolver_service`) —
      **no separate package** — English throughout, one deployable repo.
- [ ] **Confidence score** — Monte-Carlo n-sampling step before returning to the
      frontend (re-run the analysis under varied parameters, aggregate to a
      confidence). Undefined / not yet implemented. **(Owner: Martin.)** See
      `workflow-comparison.md`.

## 8. Why we're doing this now

The deadline scenario (skeleton argument, 12 citations, file by 4 PM) needs the
**whole** chain — extract, prove a case is real or fake, prove it is used
honestly, and show it at a glance. Neither codebase delivers that alone; merged,
they do, with the eval harness as our credibility evidence. Locking the interfaces
and the `/verify` contract now lets Martin finish the paste path, Leo build the
index + verification service, and Louisa & Kim build the dashboard **in
parallel** against a fixed `DocumentReport` shape.
