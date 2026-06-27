# Sprint 4 — Consolidated Status

**Date:** 2026-06-27
**Supersedes:** `Sprint3/consolidated_status.md`, `Sprint3/reality_check.md`,
root `STEP-4.md`, `Sprint2/step4_status.md` (all folded in here).
**Companions (kept separate):** `contracts.md` (per-step data contracts / state machine),
`STEP-5.md` (active Step-5 report spec).

> Pipeline (CLAUDE.md approach): **(1)** extract metadata + citing context from the
> brief → **(2)** convert source case PDFs to text + index → **(3)** resolve source /
> existence → **(4)** verify the argument is supported, with probabilities →
> **(5)** emit a structured report for the frontend.
> Verdict buckets: **VERIFIED** / **MISCHARACTERISED** / **FABRICATED**.

---

## 1. Executive summary

- **One LLM client** (`build_llm`) shared by enrichment and the faithfulness judge;
  **Gemini via Vertex AI + ADC** (no API key), project `llm-law-cambridge26cbx-518`.
- **Step 4 (faithfulness) is mature** — runs on mock *and* real LLM, passes the
  supplied matched/mismatched examples, unit-tested.
- **Step 5 orchestrator + endpoint now EXIST** (new this sprint): `pipeline_service.py`
  joins M1→M3→M4→verdict and `POST /api/citations/verify` is mounted
  (`router.py` → `endpoints/citations.py`), returning a `VerifyResponse`.
- **Step-5 `report.json` DONE** (Sprint 5): serializer + atomic write to
  `app/frontend/public/report.json`, 3 challenge categories (`verified/mischar/risk`),
  validated. See `../Sprint5/`. `config.json` (document metadata) remains **Step #2/#3's**
  responsibility and is deferred.
- **Steps 1–5 all have running tests** (Steps 2/3 un-skipped this audit); the e2e test
  now drives the **real** Step 1→5 chain instead of stubs.
- **Pipeline fix:** `corpus_dir` pointed at `index/texts` (empty) → Step 3 could never
  build its index → the orchestrator silently degraded every citation to
  `mischar`+`needs_review`. Repointed to `pdfs/`; the live full-pipeline test now passes.
- **Test suite:** **57 passing** (`pytest` ~56s, includes live Vertex calls).

Readiness by step: **1** 🟡 · **2** 🟡 · **3** 🟡 · **4** ✅ · **5** 🟢 (orchestrator ✅, `report.json` ✅).

---

## 2. Status by pipeline step

### Step 1 — Citing-side extraction & enrichment (M1) — 🟡 implemented + tested
- `citation_service.py` — regex `extract_citations()` → `Citation`
  (id, raw, case_name, year, court, reporter, …) + `read_pdf_text`.
- `citation_llm_service.py` — `extract_enriched_citations()`: LLM fills
  `full_case_name, court_name, judges, proposition, ground, relevant_text`; `_verify`
  drops judge names absent from source (anti-hallucination guard).
- Schemas: `Citation`, `CitationMetadata`, `EnrichedCitation`.
- **Tests:** `test_step1_extraction.py` (5 unit + 2 integ, incl. live enrichment).

### Step 2 — Source corpus: PDF→text + semantic index (M2) — 🟡 code ok, index unbuilt
- `pdf_ocr.py` (PyMuPDF + RapidOCR fallback), `indexer.py`
  (`embeddings.npy`/`chunks.json`/`sources.json`), `citelib.py` (chunk/embed/fuzzy name).
- Index is **not built in the repo**; `ResolverService` auto-builds from `CORPUS_DIR`
  on first use. ~60 source PDFs in `pdfs/` (gitignored).
- **Tests:** `test_step2_corpus.py` (3) — **module-skipped** (enable by dropping `pytestmark`).

### Step 3 — Resolution / existence (M3) — 🟡 fusion ok, exact-match tier missing
- `resolver_service.py` — fuses **semantic** (embedding sim) + **fuzzy name**
  (filename) → chosen source, confidence, `needs_web`, `used_semantic_fallback`.
- **Caveat:** the "deterministic exact metadata match" in docstrings is **not** a
  separate module; only semantic+name fallback exists. No field-by-field metadata
  equality between citing and cited; source side = filename + embeddings only.
- `needs_web` (existence) **is now consumed** by Step 5 → `DOESNT_EXIST` short-circuit.
- **Tests:** `test_step3_resolution.py` (4) — **module-skipped**.

### Step 4 — Faithfulness / argument verifier (M4) — ✅ real LLM + unit-tested
- `distortion_service.py` / `distortion_backend.py` / `distortion_prompts.py`.
  `analyze()` = chunk → rerank → select → meso → decompose → 3-level charity judge →
  score → `mischaracterised_pct` / `out_of_context_pct` / class.
- Backends (`get_backend`): `mock` (offline lexical), `vertex` (real LLM);
  `openrouter` is a back-compat alias for `vertex`.
- **Tests:** `test_pipeline.py` (19, mock) + `test_step4_faithfulness.py` (6, incl. live).
- Details + results: §4 below.

### Step 5 — Orchestrator + report (M5) — 🟡 orchestrator ✅, `report.json` ❌
- **Orchestrator built:** `pipeline_service.py` — `verdict_for` runs M3→M4→verdict per
  citation (FABRICATED short-circuit on `needs_web`, skips the detector);
  `verify_document` / `verify_text` wire the real resolver + backend; output is a
  `VerifyResponse` (`CitationVerdict[]` + summary).
- **Endpoint built:** `POST /api/citations/verify` (`endpoints/citations.py`) accepts a
  PDF `file` or `text`, returns `VerifyResponse`. Mounted in `router.py`.
- **Open gap:** write **`app/frontend/report.json`** (frontend-ready `Citation` shape,
  4-way status, `confidence` 0–100, fully populated + schema-validated) — see `STEP-5.md`.
- **Frontend:** `app/frontend` (TanStack Start, React 19 + Vite + Tailwind) is built but
  renders **mock data** (`src/lib/mock-citations.ts`); polls for `report.json` once
  emitted. Needs **Node ≥ 22.12** (local Node 20 → dev/build fails until upgraded).
- **Tests:** `test_step5_orchestrator.py` (6) + `test_step5_api.py` (2).

---

## 3. Test inventory (51 collected)

| File | Count | Covers | Step |
|------|-------|--------|------|
| `test_step1_extraction.py` | 7 | regex extraction + live enrichment | 1 |
| `test_step2_corpus.py` | 3 | corpus → index | 2 *(skipped)* |
| `test_step3_resolution.py` | 4 | name/semantic fusion, `needs_web` | 3 *(skipped)* |
| `test_pipeline.py` | 19 | `analyze()` contract, scoring, schemas, backend fallback | 4 |
| `test_step4_faithfulness.py` | 6 | faithfulness on mock + live LLM | 4 |
| `test_step5_orchestrator.py` | 6 | `verdict_for` M3→M4→verdict, FABRICATED short-circuit, summary | 5 |
| `test_step5_api.py` | 2 | `/health`, `/verify` mounted + validates | 5 |
| `test_integration_e2e.py` | 1 | step1→step4→verdict end-to-end | e2e |
| `test_items.py` | 3 | FastAPI-template leftovers | template (obsolete) |

Machine-checkable contracts live in `tests/contracts.py` (`assert_*` + `StepNCase` enums);
narrative in `contracts.md`. Steps 2/3 are written but **module-skipped** by request.

**Gap list:** Step-5 `report.json` serializer test (per `STEP-5.md` acceptance criteria);
enable Step 2/3 once the index is built; promote matched/mismatched into `eval/anchors.jsonl`.

---

## 4. Step 4 deep-dive (faithfulness detector)

`analyze(relevant_text, source_text, backend, ...) -> (report, id)`. Stages: chunk →
rerank (lexical) → select R_top (LLM) → meso context → decompose claim into premises
(LLM) → 3-level charity judge micro/meso/macro (LLM) → score → two %-axes + class.
`TAU_LOW = 25` (both axes below → `correct`); else the larger axis wins.
`mischaracterised_pct` = severity-weighted **VIOLATED** share; `out_of_context_pct` =
**UNADDRESSED** share. Auth = ADC (gcloud browser auth, no key).

### Results on supplied examples
**Matched (`example_matched/Matched.pdf`) — must NOT be flagged:**

| # | Case | class | mischar%/ooc% | Verdict |
|---|------|-------|---------------|---------|
| 1 | Lumley v Gye (1853) 2 E&B 216 | `correct` | 0 / 0 | ✅ not flagged |
| 2 | American Cyanamid v Ethicon [1975] AC 396 | `correct` | 0 / 14.3 | ✅ not flagged |

**Mismatched (`example_mismatched/Mismatched.pdf`) — must be flagged:**

| # | Case | PDF defect | mock | Vertex/Gemini | mischar%/ooc% |
|---|------|-----------|------|---------------|---------------|
| 1 | Anglia Television v Reed [1972] 1 QB 60 | opposite of source | `out_of_context` | `out_of_context` | 16.7 / 66.7 |
| 2 | D.C. Thomson v Deakin [1952] Ch 646 | rule made up | `mischaracterised` | `mischaracterised` | 34.6 / 30.8 |
| 3 | Hadley v Baxendale (1854) 9 Ex 341 | applied in reverse | `out_of_context` | `out_of_context` | 25 / 50 |

**Headline:** with both backends, all 3 mismatches are caught (none cleared `correct`)
and neither faithful citation is flagged. Defective/clean split is reliable.

### Known weakness — subtype instability (mischar vs out_of_context)
DECOMPOSE turns the claim into premises that include **party-specific application facts**
(Crestholm, £47m, the Supply Agreement). Those never appear in a 19th/20th-century
judgment, so the judge marks them `UNADDRESSED`, inflating `out_of_context_pct` until it
overtakes the genuine `VIOLATED` contradiction — even though the LLM's per-premise
*reasoning* is correct on all 3 (e.g. Hadley → *"'such loss would neither have flowed
naturally'… directly contradicting the claim"*). **Fix levers:** (1) decompose against
the *legal proposition the case is cited for* (use upstream `proposition`/`ground`), not
party facts; (2) weight `VIOLATED` over `UNADDRESSED` in `score()`. Also feed the **full**
resolved source, not snippets.

---

## 5. Obsolete / removable files

- **FastAPI-template scaffolding:** `endpoints/items.py`, `item_service.py`,
  `schemas/item.py`, `test_items.py` (migrate only the `/health` assertion),
  `app/models/` (empty), `app_name = "FastAPI Template"` in `config.py`, root
  `README.md` (still the template readme — rewrite for the product).
- **Superseded docs:** `Sprint1/*` (pre-merge planning) — kept as history.
- **IDE/transient:** `.idea/` (gitignore), `__pycache__/`, `.pytest_cache/`.
- **Stray assets:** `case_demo.pdf` (orphan); `pdfs/*.zip` (never extracted);
  duplicate sources `*(1).pdf`.
- **Prototype originals** in `/home/leo/hackthelaw/` — folded into `app/services/`;
  `web_fallback.py` (Perplexity overturn check) not ported (optional TODO).

---

## 6. Priorities

1. **Step 5 `report.json`** — implement the serializer + atomic write per `STEP-5.md`
   (frontend-ready shape, fully populated, schema-validated) + its acceptance tests.
2. **Build the real index** once over the ~60-PDF corpus; enable Step 2/3 tests
   (unzip `pdfs/*.zip`, drop `(1)` dupes).
3. **Step 4 subtype scoring fix** (decompose on proposition / reweight `score()`).
4. **Step 3 exact-match tier** + per-source metadata extraction (optional).
5. **Frontend wiring** after the UI update: drop `mock-citations`, poll `report.json`,
   move to Node 22.
6. **Cleanup** the template scaffolding (§5); rewrite root `README.md`.
