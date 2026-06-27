# Sprint 3 — Reality Check: what works, what's mock/stub, and progress

Companion to `consolidated_status.md` and `contracts.md`. Backed by the combined
unit+integration suite (`tests/`), run on real Vertex/Gemini credentials.

## Test suite snapshot
`pytest` → **38 passed · 7 skipped · 1 xfail** (~42s, includes live LLM calls).

| Step | Tests | Runs today |
|------|-------|-----------|
| 1 Extraction/enrichment | `test_step1_extraction.py` (5 unit + 2 integ) | ✅ incl. live enrichment |
| 2 Corpus/index | `test_step2_corpus.py` (3) | ⏸️ **deferred (skipped)** |
| 3 Resolution | `test_step3_resolution.py` (4) | ⏸️ **deferred (skipped)** |
| 4 Faithfulness | `test_pipeline.py` (19) + `test_step4_faithfulness.py` (6) | ✅ incl. live LLM |
| 5 Report API | `test_step5_api.py` (2 + 1 xfail) | ✅ /health; verify = xfail |
| e2e | `test_integration_e2e.py` (1) | ✅ step1→step4→verdict |

> Step 2/3 tests are written and ready (real bodies); they're module-skipped at the
> user's request and should be enabled shortly (drop the `pytestmark = skip`).

## What actually works (verified by tests / live runs)
- **Step 1:** regex extraction (neutral/law-report/nominate, case-name, dedupe) and
  LLM enrichment (`relevant_text`) on a real PDF.
- **Step 4:** the faithfulness detector on **mock and real Gemini** — matched examples
  not flagged, mismatched all flagged.
- **/health**, schemas, backend selection + offline fallback.
- **Deps fixed this task:** `rapidfuzz` and `fastembed` were missing from `.venv`
  (Steps 2/3 couldn't run); now installed.

## Where mocks / stubs still are → and how to replace them

| Mock / stub | Where | Replace with | Effort |
|-------------|-------|--------------|--------|
| **`MockBackend`** lexical judge (default `DISTORTION_BACKEND=mock`) | `distortion_backend.py` | already have real `VertexBackend`; flip default / pass `get_backend("vertex")` in the orchestrator | XS |
| **Index not built** (auto-builds on first call) | `index/` absent | run `indexer.build` over the real corpus once; unzip `pdfs/*.zip`, drop `(1)` dupes | S |
| **"deterministic exact metadata match" tier** | referenced in `resolver_service` docstring, not implemented | implement field-level citing↔source metadata equality in front of the semantic fallback | M |
| **Source-side metadata extraction** | only filename + embeddings today | extract per-source `CitationMetadata` (mirror Step 1) | M |
| **`needs_web` → verdict** wiring | produced, never consumed | orchestrator: `needs_web` → `DOESNT_EXIST`, confidence 0, skip Step 4 | S |
| **Perplexity / overturn fallback** | only in prototype root `web_fallback.py` | port as optional Step 3.5 | M (optional) |
| **`POST /api/citations/verify` + orchestrator** | **does not exist** (`router.py` = items only) | build endpoint that runs M1→M3→M4 → `Classification` → blueprint JSON | L |
| **Frontend `mock-citations.ts` / fake `AnalysisProgress` timer** | `app/frontend/src` | wire real `/verify` (react-query), drop mock import, real pending state; Node 22 | L (after UI update) |

## Progress (assuming Step 2 & 3 ≈ 70%, frontend update incoming)

```
Step 1  Extraction + enrichment   ████████████████░░░░  85%  works + tested
Step 2  Corpus → text + index     ██████████████░░░░░░  70%  code ok, index unbuilt, tests deferred
Step 3  Resolution / existence    ██████████████░░░░░░  70%  fusion ok, verdict-wiring + exact-match missing
Step 4  Faithfulness verifier     █████████████████░░░  85%  real LLM, tested; subtype scoring weak
Step 5  Orchestrator + /verify    ██░░░░░░░░░░░░░░░░░░░  10%  schema only, no endpoint
Step 5  Frontend UI               ██████████████░░░░░░  70%  built, runs on mock data
Tests + contracts                 ███████████████░░░░░  75%  steps 1/4/5 live; 2/3 deferred
                                   ─────────────────────────
Overall                           █████████████░░░░░░░  ~65%
```

## Time-to-finish estimate (engineering effort)

Critical path is **index build → backend orchestrator/endpoint → frontend wiring**
(the last gated on the incoming UI update). Step 4 polish and cleanup parallelize.

| Work item | Est. |
|-----------|------|
| Build real index + enable Step 2/3 tests | 0.5 d |
| Finish Step 3 (verdict wiring; optional exact-match tier) | 0.5–1 d |
| **Step 5 backend:** `/verify` + M1→M3→M4 orchestrator + structured blueprint JSON + ground + explanation | 1.5–2 d |
| **Frontend wiring** after UI update (drop mock, real `/verify`, Node 22) | 1–1.5 d |
| Step 4 subtype scoring fix + small eval set | 0.5–1 d |
| Cleanup obsolete template files | 0.5 d |
| **Total (serial, one dev)** | **~5–6.5 dev-days** |

**Elapsed estimate:**
- **~3–4 working days** if backend + frontend run in parallel and the frontend update
  lands on schedule (target: end-to-end with **no mock data**).
- **~1.5 weeks** solo/sequential including the scoring fix, eval set, and cleanup.

Biggest risk/unknown: arrival + shape of the **frontend update** (drives the wiring
item) and the one-time **index build** over the full ~60-PDF corpus.
