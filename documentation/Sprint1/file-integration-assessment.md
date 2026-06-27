# Per-file Integration Assessment — Leo's modules into Martin's repo

For each of Leo's modules: **one reason** it should be integrated and **where**,
whether it is **redundant** with something Martin already has, and **one
counterargument** (why it may not be necessary or not cleanly compatible).

**Layout decision:** everything is integrated into Martin's **existing**
`app/services/` package — **no separate `app/pipeline` package** (that interim
package was removed). Dependencies added: `numpy`, `fastembed`, `rapidfuzz`
(OCR's `pymupdf`/`rapidocr` stay optional). All Nemotron references were removed;
the LLM stages reuse Martin's OpenRouter client (`build_llm`).

| Leo's file | Integrated as | Reason to integrate | Redundant with Martin's? | Counterargument (skip / incompatible) |
|---|---|---|---|---|
| **pdf_to_text.py** | ✅ `app/services/pdf_ocr.py` | OCR fallback for **scanned** source PDFs that `pypdf` returns empty for. | **Partly** — overlaps `citation_service.read_pdf_text` (pypdf) for born-digital PDFs. | Heavy deps (`pymupdf` + `rapidocr`, ~100s MB) kept **optional/lazy**. If every PDF has a text layer, pypdf suffices and this is dead weight → call it only when pypdf yields < N chars. |
| **detect_distortion.py** | ✅ `app/services/distortion_service.py` | The faithfulness judge — the core of reqs #3–#4 Martin's repo has nothing for. | **No** — Martin has no faithfulness/verdict logic. | Pure-stdlib, self-contained; essentially free. Only cost is keeping one canonical copy (Leo's eval copy is now superseded). |
| **llm_backend.py** | ✅ `app/services/distortion_backend.py` (Nemotron removed; `OpenRouterBackend` reuses `build_llm`) | Gives the detector a real model path on **Martin's existing OpenRouter client** — no new infra. | **No** — but it imports Martin's `build_llm`, so there is one client, not two. | `MockBackend` heuristics share a family with the eval generator → Mock metrics aren't accuracy validation; fine as offline default only. |
| **prompts.py** | ✅ `app/services/distortion_prompts.py` | Strict-JSON contracts the `OpenRouterBackend` sends. | **No.** | Unused on `MockBackend`; earns its keep once the Gemini/OpenRouter judge is on. |
| **citelib.py** | ✅ `app/services/citelib.py` | Shared embedding / chunking / name-match for the fallback resolver. | **No** (Martin has no embeddings). | Pulls in `fastembed`/`numpy`/`rapidfuzz`. If the deterministic exact matcher is enough for the 12 cites, the embedding stack is optional for the demo. |
| **build_index.py** | ✅ `app/services/indexer.py` (also `build()` library fn) | One-time corpus → `index/`; the resolver **auto-builds** via this if embeddings are missing. | **No.** | A build step, not request-path logic — exposed as a library `build()` + CLI; blocked on restoring the deleted corpus. |
| **resolve_citations.py** | ✅ `app/services/resolver_service.py` (`ResolverService`, auto-build) | Semantic + fuzzy-name matching catches paraphrased cites and "not in corpus" (`needs_web`). | **Partial conflict** — its fuzzy-name signal overlaps the deterministic exact match Martin should own; semantic is the **fallback** (`used_semantic_fallback` is surfaced). | Needs `numpy` + an index. Auto-build covers the index; still blocked on having a corpus. |
| **web_fallback.py** | ⏳ Not yet (optional, behind `needs_web`) | Distinguishes "real case, not in our corpus" from "fabricated" → sharpens `DOESNT_EXIST`. | **No.** | Needs `PERPLEXITY_API_KEY` + external calls. Safe no-op without a key; `needs_web → needs_review` is acceptable for the demo. |
| **evallib.py** | 🧪 Dev-only (stays in Leo's repo) | Builds the synthetic gold set + quality gates → measurable accuracy. | **No.** | Not a runtime concern; reference from tests, don't ship. |
| **gen_eval.py** | 🧪 Dev-only (CLI) | Regenerates the labelled eval set. | **No.** | Offline harness; out of API scope. |
| **score_eval.py** | 🧪 Dev-only (CLI) + CI | Predictions → P/R/F1 / macro-F1 credibility metrics. | **No.** | Offline only; could become a CI gate later. |

## Summary

- **Integrated into `app/services/` (done):** `pdf_ocr`, `distortion_service`,
  `distortion_backend`, `distortion_prompts`, `citelib`, `indexer`,
  `resolver_service`. Analysis path is stdlib + langchain; resolution path adds
  `numpy`/`fastembed`/`rapidfuzz`; OCR deps optional/lazy.
- **Not yet integrated:** `web_fallback` (needs a key; optional).
- **Dev-only (not shipped):** `evallib`, `gen_eval`, `score_eval` — accuracy
  evidence, referenced from tests. These are the only modules still containing
  German comments (tracked follow-up).
