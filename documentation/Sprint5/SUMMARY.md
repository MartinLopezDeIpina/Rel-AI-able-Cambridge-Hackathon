# Sprint 5 — Summary: Step 5 `report.json` serializer

**Date:** 2026-06-27
**Goal:** Close the last Step-5 gap — turn the orchestrator's `VerifyResponse` into a
validated, frontend-ready **`report.json`** and drop it where the frontend polls.
**Spec:** `STEP-5.md` (this folder). **Baseline status / contracts:** `../Sprint4/`.

---

## What shipped this sprint

- **`app/schemas/report.py`** — `ReportCitation` + `ReportDocument` (`extra="forbid"`,
  non-empty constraints). Mirrors the frontend `Citation` shape (4-way `status`,
  integer `confidence` 0–100) and the agreed validation contract.
- **`app/services/pipeline_service.py`** — serializer + sink:
  - `to_report(response, enriched)` maps each `CitationVerdict` (+ its `EnrichedCitation`
    for `year`/`court`/`ground`, matched by `id`) to a `ReportCitation`; computes the
    frontend summary (`verified/mischar/risk/total`).
  - `write_report(report, path?)` writes atomically (`tmp` + `os.replace`).
  - `_persist_report(...)` wired into `verify_document` **and** `verify_text` (covers PDF
    and pasted-text paths); validation is fail-loud, IO errors are logged.
- **`app/core/config.py`** — `report_output_path` (default `app/frontend/public/report.json`).
- **`tests/test_step5_report.py`** — 4 unit tests; **all 12 Step-5 tests pass**.

## Decisions locked in (with the frontend AI)

- **Two files:** `report.json` (Step 5) + `config.json` (document metadata — Step #2/#3,
  **deferred**). Both served from Vite `public/`.
- **`report.json`:** top-level `status: "pending" | "complete"` (backend writes
  `"complete"`); 7 required citation fields (`id, caseName, court, year, citation, status,
  confidence`); backend fills the full superset.
- **Exactly 3 categories** for the per-citation `status` (the challenge buckets):
  `verified` / `mischar` / `risk`. No 4th "review" bucket — `needs_review` is an internal
  verdict note and does not change the frontend category.
- **`isMissing`:** `null`/`undefined`/`""`/`[]` = missing; `0` (and `false`) are valid —
  important for `confidence: 0` on fabricated cites.
- **Polling:** missing file (404) = "not ready" (no error). **Zero-citations:** backend
  writes `complete` + `[]`; the frontend surfaces that as a visible error.

## Status-Mapping (backend → frontend) — 3 categories

| `CitationVerdict.status` | → frontend `status` |
|--------------------------|---------------------|
| `DOESNT_EXIST` | `risk` (confidence 0) |
| `EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT` | `mischar` |
| `EXISTS_CORRECTLY_APPLIED` | `verified` |

Step #4's `mischaracterised` and `out_of_context` both collapse into `mischar`;
`correct` → `verified`; Step #3 `needs_web` → `risk`.

## Acceptance criteria — met

Schema-valid (`extra="forbid"`), all citations fully populated (7 required non-empty,
`confidence` an `int`, `0` valid), deterministic status mapping, consistent summary,
atomic write, ISO-8601 `generated_at`, reload-revalidation. (See `STEP-5.md` §Akzeptanz.)

## Remaining / next

1. **`config.json`** (document metadata) — Step #2/#3, still deferred.
2. **`tests/contracts.py`** — optional `assert_report_document` + `Step5ReportCase` enum.
3. **Frontend wiring** — `validation.ts` / `live-data.ts` / settings download button
   (frontend AI); poll `report.json`, error on `complete`+empty, Node ≥ 22.
4. **Build the real index** + enable Step 2/3 tests; Step 4 subtype-scoring fix
   (see `../Sprint4/STATUS.md`).

## Pipeline integration audit (Step 1→5)

Replaced the fake "e2e" test (stubbed resolver, monkeypatched source, hand-written
verdict map) with a **real** chain test, and un-skipped Steps 2/3. This surfaced a real
break:

- **Root cause:** `corpus_dir = "index/texts"` (empty) — the resolver's index auto-build
  found no sources → `ValueError` at Step 3. `verdict_for`'s broad `except` then turned
  that into `mischar`+`needs_review` for **every** citation, so `/verify` returned 200
  with an entirely wrong report. **Fix:** `corpus_dir = "pdfs"`.
- **Verified:** `tests/test_integration_e2e.py::test_full_pipeline_live` now runs
  Step 1 (LLM enrich) → 3 (real resolve) → 4 (Vertex judge) → 5 → `report.json` green.
- **Residual risk (not changed):** the orchestrator still masks a *total* resolver/index
  failure as per-citation `mischar`. Recommend a document-level error when all citations
  fail to resolve, so a broken index can't masquerade as a valid report.

## Handing to the human intermediary (open checks)

- **Mapping alignment:** `to_report` matches enriched↔verdict by `id`; confirm ids stay
  stable end-to-end (largest correctness risk).
- **3 categories only:** `needs_review` no longer creates a 4th bucket; a correct-but-
  uncertain cite ships as `verified`. The frontend's `Citation` type still lists a
  `review` value (mock) — it simply won't be emitted; the frontend AI can drop it.
- **`paragraph`** = citation order (`id-1`), not true document position — doc highlighting
  is approximate.
