# Leo's contribution — provenance & integration changes

This documents which files in this repo originate from **Leo's** verification
pipeline (originally a separate CPU-only, offline project at
`/home/leo/hackthelaw`) and the bigger-picture changes applied to make them fit
into **Martin's** FastAPI repo. The UI is **Louisa & Kim's** (incoming).

## Files that came from Leo

All integrated into Martin's existing `app/services/` package (English; **no
separate package**). Left column = Leo's original module, right = where it lives now.

| Leo's original | Now in this repo | What it does |
|---|---|---|
| `detect_distortion.py` | `app/services/distortion_service.py` | The faithfulness detector — `analyze()` (the 6-stage charity-judge pipeline) + `score()` + the `relevant_text` helpers. |
| `llm_backend.py` | `app/services/distortion_backend.py` | Pluggable model layer: `MockBackend` (offline) + `VertexBackend` (real LLM, Gemini via Vertex AI). |
| `prompts.py` | `app/services/distortion_prompts.py` | Strict-JSON prompt contracts for the SELECT / DECOMPOSE / JUDGE stages. |
| `pdf_to_text.py` | `app/services/pdf_ocr.py` | PDF→text with OCR fallback (PyMuPDF + RapidOCR) for scanned sources. |
| `citelib.py` | `app/services/citelib.py` | Shared embedding / chunking / fuzzy name-match helpers (fastembed + rapidfuzz). |
| `build_index.py` | `app/services/indexer.py` | Builds the semantic index (`embeddings.npy`/`chunks.json`/`sources.json`); exposes `build()`. |
| `resolve_citations.py` | `app/services/resolver_service.py` | Resolves a citation to a source (semantic + name fusion); `ResolverService` with auto-build. |

New schema work added to Martin's `app/schemas/citation.py`: `ClassificationType`
(3-value verdict enum), `Classification` (verdict object), `AnalysisDict` (typed
mirror of `analyze()`'s output). Tests: `tests/test_pipeline.py` (22 passing).

**Not integrated (still Leo's, German):** `web_fallback.py` (Perplexity, optional)
and the eval harness `evallib.py` / `gen_eval.py` / `score_eval.py` (dev-only —
our accuracy evidence, referenced from tests, not shipped).

## Bigger-picture changes to make them fit together

1. **One repo, no separate package.** Leo's standalone scripts were folded into
   Martin's `app/services/` layout (an earlier interim `app/pipeline/` package was
   removed) so the team builds one deployable FastAPI app.

2. **One LLM client, reused.** Leo's offline `NemotronBackend` stub was deleted.
   The new `VertexBackend` reuses Martin's `citation_llm_service.build_llm`, so
   citation enrichment *and* the distortion judge talk to a single configured
   model. **All Nemotron references removed**; the default `LLM_MODEL` is now
   Gemini (`google/gemini-3.5-flash`), overridable in `.env`. `MockBackend` stays
   the offline default, and each LLM stage degrades to it on error / missing key.

3. **Interface clean-up for the hand-off.** `analyze()`'s first parameter was
   renamed `citation → relevant_text` (it takes the citing document's *claim*, not
   the formal cite string — which is what the resolver takes). It also gained a
   pass-through `id` and now returns `(report, id)`; `build_relevant_text_map` +
   `analyze_relevant_texts` bridge Martin's `EnrichedCitation` rows to it.

4. **Resolution re-ordered + auto-build.** Deterministic exact metadata matching
   is the *primary* existence check; Leo's semantic vector search is the
   *fallback*, flagged via `used_semantic_fallback` and surfaced in the report.
   If the index doesn't exist yet, the resolver builds it on first use
   (`ResolverService._ensure_loaded` → `indexer.build`).

5. **Verdict mapping.** Resolver + detector outputs map onto the 3 challenge
   buckets via `ClassificationType`; an `UNVERIFIED` case carries `needs_review`
   rather than being mis-labelled `DOESNT_EXIST` (see `Sprint1/integration-plan.md` §3).

6. **Dependencies + language.** `requirements.txt` gained `numpy`, `fastembed`,
   `rapidfuzz` (OCR's `pymupdf`/`rapidocr` optional). All integrated code is in
   **English**; it supersedes Leo's German originals for the analysis + resolution
   paths.

See `documentation/Sprint1/` for the full comparison, integration plan,
implementation status, and workflow comparison.
