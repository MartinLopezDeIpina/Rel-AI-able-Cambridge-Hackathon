# Implementation Status — what's built vs the proposed workflow

Snapshot after integrating Leo's analysis pipeline into Martin's repo. Two views:
(1) the **proposed 8-step workflow**, step by step; (2) the **integration artifacts**.
Tests: `tests/test_pipeline.py` — **22 passed** (`.venv/bin/python -m pytest -q`).

## A. Proposed workflow — step-by-step status

| # | Proposed step | Status | Where / note |
|---|---|---|---|
| 1 | **Prep:** vectorize the document + store a *Global Document Summary* | 🟡 Partial | Vectorizing exists offline (`build_index.py` + `citelib`) but **has not been run** (only the OCR text cache exists, 9/58 docs) and isn't wired into the request path. **Global Summary is not implemented** — a `{global_summary}` slot is threaded through `analyze → judge` but is always empty today. |
| 2 | **Retrieve:** vector search the citation → top 50 paragraphs | 🟡 Partial | The detector chunks the source and reranks **all** paragraphs, then slices `top=50` (`detector.analyze`). True embedding retrieval lives in `resolve_citations`/`citelib` (needs the built index); the detector currently uses the backend's `rerank`, not a vector DB. |
| 3 | **Rerank:** Nemotron Rerank 1B v2 → code slices top 5 (R_top) | 🟡 Partial | The rerank→select→slice **structure** is implemented (`backend.rerank` + `backend.select`, `k=5`). The model is the **lexical MockBackend** (and OpenRouter inherits that lexical rerank). **A dedicated Nemotron Rerank 1B v2 is not wired.** |
| 4 | **Expand context:** 3 preceding + 3 succeeding → 5 context windows | 🟡 Partial | Detector gathers **succeeding** paragraphs (`id+1..3`) for meso context. **Preceding paragraphs are not gathered**, and context isn't packaged as 5 symmetric windows. |
| 5 | **Extract & Formulate (LLM):** statements S + necessary premises | ✅ Implemented | `backend.decompose` (Mock heuristic, or OpenRouter via `DECOMPOSE_PROMPT`). |
| 6 | **Evaluate (LLM):** Global Summary + windows + premises → micro/meso/macro | ✅ Implemented (model-agnostic) | `backend.judge` runs micro/meso/macro (Mock heuristic, or OpenRouter via `JUDGE_PROMPT`). **Gemini specifically is not set** — it runs whatever `LLM_MODEL` is configured (default a Nemotron-nano tier). Switching to Gemini is a one-line `.env` change. |
| 7 | **Output JSON:** premise-violation flags + uncharitable summary + discrete class | ✅ Implemented | `analyze` returns the structured report; `score` maps to a discrete class. **Naming differs** from the proposal: `correct`↔Valid, `mischaracterised`↔Mischaracterized, `out_of_context`↔Out of Scope. Per-premise labels (SATISFIED/CHARITABLE/VIOLATED/UNADDRESSED) are the "boolean flags"; `premise_summary` is the uncharitable-interpretation summary. Typed by `AnalysisDict`. |
| 8 | **Monte Carlo n-sampling → confidence score** | ❌ Not implemented | Documented as **Martin's task** (undefined parameters). See `workflow-comparison.md` §Confidence. |

Legend: ✅ done · 🟡 partial · ❌ not started.

## B. Integration artifacts — status

| Artifact | Status |
|---|---|
| Integrated into `app/services/` (distortion_service, distortion_backend, distortion_prompts, pdf_ocr, citelib, indexer, resolver_service), English comments — **no separate package** | ✅ Created |
| Resolver auto-builds the index when embeddings are missing (`ResolverService._ensure_loaded` → `indexer.build`) | ✅ Done |
| `requirements.txt` += `numpy`, `fastembed`, `rapidfuzz`; config/.env → Gemini default; all Nemotron references removed | ✅ Done |
| `OpenRouterBackend` (LLM stages via Martin's OpenRouter); `NemotronBackend` stub removed | ✅ Done |
| `analyze` renamed param `citation`→`relevant_text`, added pass-through `id`, returns `(report, id)` | ✅ Done |
| `build_relevant_text_map` / `analyze_relevant_texts` helpers | ✅ Done |
| Schemas: `ClassificationType`, `Classification`, `AnalysisDict` in `app/schemas/citation.py` | ✅ Done |
| Tests `tests/test_pipeline.py` | ✅ 22 passing |
| FastAPI routes `/api/citations/extract` + `/verify` | ❌ Proposed only (integration-plan §5) |
| `verification_service.py` orchestrator | ❌ Proposed only (integration-plan §6) |
| Deterministic **exact metadata** resolver (primary existence check) | ❌ Martin's to build |
| `extract_citations_from_text` (paste-text path) | ❌ Martin's to build |
| Built index + restored corpus (`build_index` run) | ❌ Blocked on data |
| Monte-Carlo confidence | ❌ Martin's task |

## C. Language / quality

- All **integrated** code under `app/services/*` is written in **English**.
- These English modules **supersede** Leo's original German files for the analysis
  and resolution paths (`detect_distortion.py`, `llm_backend.py`, `prompts.py`,
  `pdf_to_text.py`, `citelib.py`, `build_index.py`, `resolve_citations.py`), which
  remain only in Leo's separate working directory as historical reference.
- The **only** modules still containing German are the not-yet-integrated eval
  harness (`evallib.py`, `gen_eval.py`, `score_eval.py`) and `web_fallback.py` —
  a tracked follow-up (see `file-integration-assessment.md`).
