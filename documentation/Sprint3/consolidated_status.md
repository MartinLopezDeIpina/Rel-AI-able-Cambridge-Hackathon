# Sprint 3 — Consolidated Status Report

**Date:** 2026-06-27
**Scope:** end-to-end status of every pipeline step in `CLAUDE.md`, the test suite
that actually exists, and the files that have become obsolete.

> Pipeline (CLAUDE.md approach): **(1)** extract metadata + citing context from the
> brief → **(2)** convert source case PDFs to text → **(3)** extract source metadata
> and check it matches the citing side (existence) → **(4)** verify the argument is
> supported, with probabilities → **(5)** output a report to a frontend.
> Challenge verdict buckets: **VERIFIED** / **MISCHARACTERISED** / **FABRICATED**.

---

## 1. Executive summary

- **One LLM client** (`build_llm`) shared by enrichment and the faithfulness judge;
  configured for **Gemini via Vertex AI + ADC** (no API key). Project
  `llm-law-cambridge26cbx-518`.
- **Step 4 (faithfulness) is the mature part** — runs on mock *and* the real LLM,
  passes the supplied matched/mismatched examples, and is the only step with unit
  tests.
- **Steps 1–3 exist as services but are unorchestrated and untested.**
- **Step 5 is the critical gap:** there is **no `/api/citations/verify` endpoint and
  no orchestrator** joining steps 1→3→4 into a `Classification`. The React frontend
  is built but runs on mock data.
- **The test suite was broken at collection** (two `test_analyze.py` harnesses
  collided). **Fixed this sprint** (`pytest.ini` `testpaths=tests`, harnesses renamed
  to `run_analyze.py`): **22 tests now pass.**

Overall readiness by step: **1** 🟡 · **2** 🟡 · **3** 🟡 · **4** ✅ · **5** ❌.

---

## 2. Status by pipeline step

### Step 1 — Citing-side extraction & enrichment (M1) — 🟡 implemented, untested
- `app/services/citation_service.py` — regex `extract_citations()` → `Citation`
  (id, raw, case_name, year, court, reporter, …) + `read_pdf_text`.
- `app/services/citation_llm_service.py` — `extract_enriched_citations()`: LLM fills
  `full_case_name, court_name, judges, proposition, ground, relevant_text`; `_verify`
  drops judge names not present in the source (anti-hallucination guard).
- Schemas: `Citation`, `CitationMetadata`, `EnrichedCitation`.
- **Tests: none.** Regex coverage and LLM-JSON parsing are unverified.

### Step 2 — Source corpus: PDF→text + semantic index (M2) — 🟡 implemented, not built, untested
- `app/services/pdf_ocr.py` — PyMuPDF text + RapidOCR fallback for scans.
- `app/services/indexer.py` — builds `embeddings.npy` / `chunks.json` / `sources.json`.
- `app/services/citelib.py` — shared chunk / embed (fastembed bge-small) / fuzzy name.
- **State:** index is **not built in the repo**; `ResolverService` auto-builds from
  `CORPUS_DIR` on first use. ~60 source PDFs live in `pdfs/` (gitignored).
- **Tests: none.**

### Step 3 — Source metadata + existence match (M3) — 🟡 partial
- `app/services/resolver_service.py` — fuses **semantic** (embedding similarity) and
  **fuzzy name** (filename) signals → which source, confidence, `needs_web`,
  `used_semantic_fallback`.
- **Caveat:** the "deterministic exact metadata match" referenced in docstrings is
  **not a separate module** — only the semantic+name fallback exists. There is no
  structured, field-by-field metadata-equality check between citing and cited, and no
  per-source `CitationMetadata` extraction (source side = filename + embeddings only).
- **Existence/Not-Found (`needs_web`) is produced but NOT wired** to a FABRICATED
  verdict (that wiring is Step 5).
- **Tests: none.**

### Step 4 — Faithfulness / argument verifier (M4) — ✅ implemented + real LLM, ✅ unit-tested (mock)
- `distortion_service.py` / `distortion_backend.py` / `distortion_prompts.py`.
  `analyze()` = chunk → rerank → select → meso → decompose → 3-level charity judge →
  score → `mischaracterised_pct` / `out_of_context_pct` / class.
- **Real LLM works** (Vertex/Gemini): matched examples **PASS** (not flagged),
  mismatched examples **all flagged**. Full detail in root `STEP-4.md` and
  `documentation/Sprint2/step4_status.md`.
- **Tests: 19** in `tests/test_pipeline.py` (mock backend only).
- **Known weakness:** mischaracterised-vs-out_of_context **subtype is unstable**
  (decompose emits party-specific premises that go UNADDRESSED and inflate
  out_of_context). Fix: decompose on the legal proposition / reweight `score()`.

### Step 5 — Report + frontend (M5) — ❌ backend wiring missing
- **Frontend built:** `app/frontend` (TanStack Start, React 19 + Vite + Tailwind);
  `relaiable/*` components + 46 shadcn `ui/*`, routes `index`/`dashboard`/`report`.
  Currently renders **mock data** (`src/lib/mock-citations.ts`). `npm install` done
  (needs **Node ≥ 22.12**; local Node is 20 → dev/build will fail until upgraded).
- **Backend endpoint `POST /api/citations/verify`: does not exist** — `app/api/router.py`
  only wires the `items` template.
- **Orchestrator** (M1→M3→M4 → single `Classification`): **does not exist**.
- The wiring spec + open gaps are documented in `app/frontend/interactions.md`.
- **Tests: none.**

---

## 3. Test inventory — what is actually implemented

**Suite health:** previously **broken at collection** (duplicate `test_analyze.py`
basenames). Fixed this sprint. **`pytest -q` → 22 passed.**

| File | Count | What it actually covers | Step |
|------|-------|--------------------------|------|
| `tests/test_pipeline.py` | 19 | `analyze()` contract; mock classification (correct / mischar / ooc); `score()` thresholds; `relevant_text` helpers; `chunk_paragraphs`; schemas (`ClassificationType`, `Classification`, `AnalysisDict`); `get_backend` + offline fallback | **4** (+ schemas) |
| `tests/test_items.py` | 3 | `/health`; item create/get; missing item (404) | template (obsolete) |
| `example_matched/run_analyze.py` | manual | hits **live Vertex**; asserts both faithful cites → `correct` | 4 (integration) |
| `example_mismatched/run_analyze.py` | manual | hits **live Vertex**; asserts all 3 → flagged | 4 (integration) |

**Coverage by step:** 1 ❌ · 2 ❌ · 3 ❌ · 4 ✅ (mock only; real-LLM path is manual,
not in CI) · 5 ❌.

**Missing tests worth adding (gap list):**
- Step 1: `extract_citations` on a fixture brief (regex precision/recall);
  enrichment JSON-parse + `_verify` judge-drop.
- Step 3: `resolve_one` fusion (name-wins vs semantic vs `needs_web`) on a tiny index.
- Step 5: a `TestClient` test for `/api/citations/verify` once it exists; an
  orchestrator test mapping `needs_web` → `DOESNT_EXIST` short-circuit.
- Step 4: promote the matched/mismatched examples into an `eval/` anchor set with
  expected labels (currently only manual, network-bound).

---

## 4. Obsolete / removable files

### FastAPI-template scaffolding (unrelated to the product — safe to delete/replace)
- `app/api/endpoints/items.py`
- `app/services/item_service.py`
- `app/schemas/item.py`
- `tests/test_items.py` *(keep only the `/health` assertion — migrate it)*
- `app/models/` *(empty package)*
- `app/api/router.py` *(only wires `items`; must be rewritten to mount `/citations`)*
- Cosmetic: `app_name = "FastAPI Template"` in `config.py` / `.env.example`.

### Superseded documentation (keep as history, no longer current guidance)
- `documentation/Sprint1/*` — pre-merge planning: `comparison.md`,
  `workflow-comparison.md`, `file-integration-assessment.md`, `integration-plan.md`,
  `implementation-status.md`, `practical_milestones_from_here.md`,
  `current_state_report.md`, `TODO.md`, `README.md`, `HackTheLaw_Status_Report.docx`.
  Superseded by `Sprint2/step4_status.md`, root `STEP-4.md`, and this report.

### IDE / transient (should be gitignored, not tracked)
- `.idea/` — JetBrains project files (add to `.gitignore`).
- `__pycache__/`, `.pytest_cache/` — already covered by `.gitignore`.

### Stray / unusable assets
- `case_demo.pdf` (repo root) — orphan demo input, referenced only by the
  `citation_llm_service` `__main__` default.
- `pdfs/*.zip` (`meretz-…zip`, `starbucks-…zip`) — zipped, never extracted; the
  resolver reads `.pdf`/`.txt`, so these contribute nothing until unzipped.
- Duplicate sources: `caparo-…(1).pdf`, `three-rivers-…(1).pdf` — redundant copies.

### Prototype originals (outside this repo, in `/home/leo/hackthelaw/`)
- `detect_distortion.py`, `llm_backend.py`, `prompts.py`, `build_index.py`,
  `citelib.py`, `resolve_citations.py`, `pdf_to_text.py`, `web_fallback.py`,
  `evallib.py`, `gen_eval.py`, `score_eval.py` — Leo's standalone scripts, **folded
  into `app/services/`** (see `documentation/leo.md`). Obsolete as live code; retained
  only as the source prototype. `web_fallback.py` (Perplexity overturn check) was
  **not** ported and remains an optional TODO.

---

## 5. Priorities for the rest of Sprint 3

1. **M5 backend (unblocks everything):** build `POST /api/citations/verify` + an
   orchestrator that runs M1→M3→M4 and emits one `Classification` per citation,
   including the `needs_web → DOESNT_EXIST` (FABRICATED) short-circuit. Rewrite
   `router.py` to mount it.
2. **Frontend wiring:** close the `interactions.md` gaps (real `/verify` call, drop
   `mock-citations`, real pending state); move to **Node 22**.
3. **Tests for Steps 1–3** + a `TestClient` test for `/verify`.
4. **Step 4 subtype scoring fix** (decompose on proposition / reweight `score()`).
5. **Cleanup:** delete the template scaffolding (Section 4), gitignore `.idea/`,
   remove/extract the stray `pdfs/*.zip` and duplicates.
