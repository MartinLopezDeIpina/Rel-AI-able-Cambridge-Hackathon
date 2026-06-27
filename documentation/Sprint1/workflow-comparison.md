# Workflow Comparison — proposed simplified workflow vs current implementation

Compares the **proposed target workflow** against what the **current integrated
code** (`app/services/`) actually does, documents the **intended simplification**,
and for each differing step gives a **recommended simplifications** list and a
**keep (with reasons)** list. Ends with the **Monte-Carlo confidence** step (a
future, undefined task).

> Note on language: all integrated pipeline code is now **English**
> (`app/services/distortion_service.py`, `distortion_backend.py`,
> `distortion_prompts.py`, `pdf_ocr.py`, `citelib.py`, `indexer.py`,
> `resolver_service.py`). Leo's original German modules are superseded by these
> for the analysis + resolution paths; only the (not-yet-integrated) eval harness
> still contains German. See `implementation-status.md`.

## The proposed workflow (as given)

1. **Prep:** vectorize the document; generate + store a *Global Document Summary*.
2. **Retrieve:** vector-search the citation → top 50 paragraphs.
3. **Rerank:** *Nemotron Rerank 1B v2* scores the 50 → code deterministically slices the top 5 (R_top).
4. **Expand context:** for each of the 5 R_top, fetch 3 preceding + 3 succeeding paragraphs → 5 *Context Windows*.
5. **Extract & Formulate (LLM):** extract statements S + formulate necessary premises.
6. **Evaluate (Gemini via OpenRouter):** feed the Global Summary + 5 Context Windows + premises; run Micro/Meso/Macro.
7. **Output (JSON):** boolean flags for premise violations, summary of uncharitable interpretations, discrete class (Out of Scope, Mischaracterized, Valid).
8. **Monte-Carlo n-sampling → confidence score** (before the frontend; undefined; Martin's task).

## How it differs from the current code

| # | Proposed | Current code (`app/services`) | Difference |
|---|---|---|---|
| 1 | Vectorize + Global Summary | `indexer.build` vectorizes the corpus into `index/`; **no global summary** (a `{global_summary}` slot is threaded to the judge but always empty) | Global summary missing; vectorization is per-corpus, built once (now **auto-built** if absent) |
| 2 | Vector search → top 50 | The detector reranks **all** paragraphs of the *already-resolved* source, then slices `top=50` | No second corpus-wide vector search inside the detector; retrieval is within the resolved doc |
| 3 | **Nemotron Rerank 1B v2** → top 5 | `backend.rerank` (lexical in mock; OpenRouter inherits lexical) + `select` top `k=5` | **No dedicated reranker model** — and per the "remove all Nemotron" decision, none is planned |
| 4 | 3 preceding + 3 succeeding → 5 windows | Only **succeeding** paragraphs (`id+1..3`); not packaged as symmetric windows | Preceding context missing; not windowed |
| 5 | Extract statements + premises | `backend.decompose` (mock heuristic / `DECOMPOSE_PROMPT`) | **Matches** |
| 6 | Evaluate via **Gemini/OpenRouter**, Micro/Meso/Macro | `backend.judge` via OpenRouter (`LLM_MODEL`, now defaults to Gemini), Micro/Meso/Macro | **Matches** (model now Gemini by default) |
| 7 | JSON: flags + summary + discrete class | `analyze` returns flags (premise labels), `premise_summary`, two %-axes + discrete class; typed by `AnalysisDict` | **Matches**; naming differs (`correct/mischaracterised/out_of_context` ↔ Valid/Mischaracterized/Out of Scope) |
| 8 | Monte-Carlo confidence | **Not implemented** | Missing (see below) |

## Intended simplification

The integration deliberately **collapses the proposed multi-model stack into one
LLM client**:

- **One model, reused.** The judge reuses Martin's OpenRouter client
  (`build_llm`) instead of standing up a second model service. The default model
  is Gemini (`LLM_MODEL`); the deterministic `MockBackend` is the offline default
  so the whole pipeline runs with no key.
- **No dedicated reranker.** The proposed *Nemotron Rerank 1B v2* is dropped (it
  also conflicts with "remove all Nemotron references"); the 50→5 funnel is done
  by cheap lexical/embedding scoring + the LLM `SELECT` step.
- **Retrieve within the resolved document**, not a fresh corpus-wide vector
  search at judge time — resolution already picked the source.
- **Graceful degradation.** Every LLM stage falls back to the mock heuristic on a
  parse error or missing key, so the demo never hard-fails.
- **Auto-build.** If the embeddings don't exist, the resolver builds the index on
  first use (`ResolverService._ensure_loaded` → `indexer.build`).

## Reliability: proposed vs current, per differing step

**Overall.** The current `MockBackend` path is a *deterministic plumbing baseline*
— reliable as wiring, **not** a validation of judgment quality. The proposed
LLM-judge path is more accurate but trades determinism for cost, latency, and
external-dependency risk (API downtime, rate limits, malformed JSON) — which we
mitigate with the fallback-to-mock and tolerant JSON parsing.

### Step 1 — Prep / Global Summary
- **Recommended simplifications:** build the index once (done, + auto-build);
  generate the Global Summary **once per source and cache it** (don't regenerate
  per citation); for MVP it can stay empty (mock ignores it).
- **Keep (why):** the macro-level summary materially helps the *macro* check
  (is the cite consistent with the case's ratio?). Worth keeping the threaded
  slot so it can be switched on without code change.

### Step 2 — Retrieve top 50
- **Recommended simplifications:** retrieve **within the resolved document** only
  (current behaviour) — avoids a second embedding pass; at paragraph scale lexical
  rerank is enough to funnel to 50.
- **Keep (why):** the top-N funnel bounds downstream LLM context and cost.

### Step 3 — Rerank (Nemotron Rerank 1B v2)
- **Recommended simplifications:** **do not add a dedicated reranker model.** Use
  bge embedding similarity (already available via `citelib`) or let the LLM
  `SELECT` prompt pick R_top. Reason: a separate served model is extra infra for
  marginal gain on 50→5 within one document, and it reintroduces Nemotron.
- **Keep (why):** keep the **deterministic top-5 slice** after scoring — it makes
  R_top reproducible and caps the judge's context window.

### Step 4 — Expand context (3 preceding + 3 succeeding)
- **Recommended simplifications:** ±2 paragraphs is likely enough; full ±3 windows
  for 5 paragraphs can duplicate text and inflate tokens — dedupe overlapping
  windows.
- **Keep / enhance (why):** **add the preceding paragraphs** (current code only
  looks ahead). A qualification the citation ignores often appears *before* the
  on-point sentence; one-sided context misses it. This is the one place the
  proposal is stricter than the current code and should be adopted.

### Step 6 — Evaluate (LLM calls)
- **Recommended simplifications:** consider merging `SELECT`+`DECOMPOSE` (or
  `DECOMPOSE`+`JUDGE`) into fewer LLM calls — today it is 3 calls/citation (×12 ≈
  36). Fewer calls = lower latency/cost and fewer JSON-parse failure points.
- **Keep (why):** keep the **3-level (micro/meso/macro) charity rubric** and
  **strict-JSON** contract — they are what make the verdict explainable and
  auditable for the partner. Keep stages separable for debuggability even if
  co-batched in one request.

### Step 7 — Output
- **Recommended simplifications:** expose the single discrete class to the UI
  (`ClassificationType`); keep the two %-axes + `premise_summary` only in the
  "why" panel, not the headline.
- **Keep (why):** keep per-premise flags + the uncharitable-interpretation
  summary — they are the evidence behind the verdict.

## Step 8 — Confidence via Monte-Carlo n-sampling (future; Martin's task)

**Status: not defined, not implemented.** Documented here so the contract is clear.

- **Where it slots:** *after* `analyze` produces each report and *before* building
  the `DocumentReport` for the frontend. The result populates
  `Classification.confidence` (already in the schema).
- **Idea:** re-run the analysis `n` times under **varied parameters** and derive a
  confidence from how stable the verdict is (e.g. the fraction of runs that agree
  on the class, or the variance of `mischaracterised_pct` / `out_of_context_pct`).
- **Parameters that *could* be varied (not yet decided):** LLM `temperature`,
  the `top`/`k` funnel sizes, `chunk size`/`overlap`, the context-window radius,
  the model id, prompt phrasing, or the R_top selection. At least one source of
  variation (temperature > 0 or parameter jitter) is required, since the mock
  path and `temperature=0` are deterministic and would yield trivial confidence.
- **Open questions for Martin:** value of `n` (cost vs stability); which
  parameters to jitter; how to aggregate (agreement rate vs distributional); and
  the latency budget (n× the per-citation cost).
