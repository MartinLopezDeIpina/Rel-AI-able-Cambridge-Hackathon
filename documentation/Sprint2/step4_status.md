# Sprint 2 — Step 4 (Distortion Detection / `analyze`) Status

**Date:** 2026-06-27
**Stage:** Step 4 — content-faithfulness layer. Runs *after* citation resolution:
given the citing document's wording about a case (`relevant_text`) and the
resolved source judgment text (`source_text`), decide whether the wording fairly
represents what the case actually decided.

Code: `app/services/distortion_service.py` (orchestration) +
`app/services/distortion_backend.py` (pluggable model) +
`app/services/distortion_prompts.py` (strict-JSON templates).

---

## What step 4 does

`analyze(relevant_text, source_text, backend, ...) -> (report, id)`

Internal stages:
1. **chunk** source into word-window paragraphs
2. **rerank** paragraphs against the citation (lexical cosine)
3. **select** R_top (k best paragraphs)
4. gather **following** paragraphs (meso context)
5. **decompose** the citation into statements → premises
6. **judge** (3-level charity: micro/meso/macro) → per-premise labels
7. **score** → `mischaracterised_pct`, `out_of_context_pct`, classification

Output classes → eval labels: `correct→faithful`, `mischaracterised→misleading`,
`out_of_context→out_of_scope`. Threshold `TAU_LOW = 25%` (both axes below → correct).

---

## Current status: **wired & runnable on a real LLM (Gemini via Vertex AI + ADC)**

| Piece | Status |
|-------|--------|
| `analyze` orchestration (chunk→rerank→select→meso→decompose→judge→score) | ✅ working |
| Scoring + classification + thresholds | ✅ working |
| `MockBackend` (lexical heuristics, stdlib-only) | ✅ working |
| LLM-judge backend (`OpenRouterBackend` class, via `build_llm`) | ✅ **runnable** — drives **Gemini 2.5 Flash** |
| `vertex` provider via ADC (browser auth, no API key) | ✅ in use — project `llm-law-cambridge26cbx-518` |
| `gemini` provider in `build_llm` (Developer API, API-key only) | ✅ added as optional fallback (not used) |
| Real-LLM validation against hand-labelled cases | 🟡 smoke-tested on 3 cases; no eval set yet |
| Batch helpers (`analyze_relevant_texts`, `build_relevant_text_map`) | ✅ working, untested on real resolver output |

How the real LLM is wired: auth is **Application Default Credentials** (gcloud
browser auth) — *no API key*. ADC has access to one project,
`llm-law-cambridge26cbx-518` ("Hack the Law"), discovered via the Resource Manager
API. `.env` sets `LLM_PROVIDER=vertex` + `GOOGLE_PROJECT=llm-law-cambridge26cbx-518`;
`build_llm` returns `ChatVertexAI`. The distortion LLM backend reuses `build_llm`,
so it routes through Vertex unchanged. (A `gemini` Developer-API provider was also
added for portability but is **not** the configured path.)

Run: `.venv/bin/python example_mismatched/test_analyze.py openrouter`
(uses `.env`; the `openrouter` arg just selects the LLM-judge backend, which drives Vertex).

---

## Test run on `example_mismatched/Mismatched.pdf` (3 hand-built cases)

Harness: `example_mismatched/test_analyze.py` (`mock` for offline, `openrouter` for the LLM judge).

| # | Case | PDF defect | mock | **Vertex/Gemini** | mischar%/ooc% |
|---|------|-----------|------|-------------------|---------------|
| 1 | Anglia Television v Reed [1972] 1 QB 60 | opposite of source cited | `out_of_context` | `out_of_context` | 16.7 / 66.7 |
| 2 | D.C. Thomson v Deakin [1952] Ch 646 | rule made up | ✅ `mischaracterised` | ✅ `mischaracterised` | 34.6 / 30.8 |
| 3 | Hadley v Baxendale (1854) 9 Ex 341 | applied in reverse | `out_of_context` | `out_of_context` | 25 / 50 |

**Headline:** with both backends, all 3 mismatches are caught as defective —
**none classified `correct`/faithful**. The detector reliably separates "problem"
from "fine"; the open question is the *subtype* (mischaracterised vs out_of_context).

**Subtype split is unstable, and the root cause is now clear.** The DECOMPOSE step
breaks the citing claim into premises that include **party-specific application
facts** (Crestholm, £47m, the Supply Agreement, saved costs, risk adjustments).
Those facts can never appear in a 19th/20th-century source judgment, so the judge
labels them `UNADDRESSED`, which inflates `out_of_context_pct` and can overtake the
genuine `VIOLATED` (contradiction) signal — even though the LLM's reasoning
correctly identifies the contradiction. Gemini's per-premise reasons are right on
all 3 (e.g. Hadley → *"'such loss would neither have flowed naturally'… directly
contradicting the claim"*); only the **numeric class** flips.

**Fix direction (the actual lever):** decompose against the *legal proposition the
case is cited for* (use the upstream `proposition`/`ground`), not the party-specific
facts; and/or weight `VIOLATED` over `UNADDRESSED` in `score()` so a clear
contradiction isn't drowned by off-topic application detail.

---

## What needs to be done now

### P0 — DONE: real backend running (Gemini via Vertex + ADC)
- [x] Vertex/ADC path working: `.env` `LLM_PROVIDER=vertex` + `GOOGLE_PROJECT`; no API key.
- [x] Added optional `gemini` Developer-API provider to `build_llm` for portability.
- [x] Re-ran the 3 cases on the real LLM — all flagged defective, reasoning correct on all 3.
- [ ] Fix subtype instability (decompose on the proposition / reweight `score()`).

### P0b — M4 gaps vs the "Definition of Done" checklist (newly identified)
- [ ] **3-way classification not assembled.** `analyze()` only emits the *exists* side
  (`correct|mischaracterised|out_of_context`). No code maps M3 "Not Found" →
  `DOESNT_EXIST` (FABRICATED) and short-circuits to 0% before the LLM. The
  `Classification` schema exists but nothing populates it.
- [ ] **No M3→M4 orchestrator.** Nothing reads `/data/text_source/{id}.txt`, feeds the
  resolved source as `source_text`, or merges resolver existence + detector verdict.
- [ ] **Ground not used.** `CitationMetadata.ground` is extracted upstream but is not
  passed into the judge prompt or surfaced in the verdict (checklist requires it).
- [ ] **Structured output mismatch.** Detector asks for "strict JSON" in prose and
  parses leniently; it does not use Pydantic `with_structured_output`. Report keys
  (`mischaracterised_pct`, `plain_language_holding`, …) differ from the blueprint's
  (`citation_name, status, confidence_score, associate_claim, actual_holding,
  explanation`). No single 0..1 `confidence_score`; `Classification.confidence` unset.
- [ ] **Mismatch explanation field missing.** We emit per-premise `reason`s + a
  `plain_language_holding`, but not the single 2-3 sentence "why it's wrong" the
  partner needs.
- [ ] **Overturn / Perplexity check is OPTIONAL and not implemented in `app/`**
  (`web_fallback.py` lives only in the prototype root). Document as a fallback TODO.

### P1 — validation
- [ ] Promote the 3 `Mismatched.pdf` cases into a small hand-labelled anchor set
  (with expected class) under `eval/` and assert on it in `tests/test_pipeline.py`.
- [ ] Add a "faithful" control case (a correct citation) so we measure false-positives.
- [ ] Run the existing synthetic eval harness (`gen_eval` → `score_eval`) against
  the real backend, not just mock, and record precision/recall per class.

### P2 — robustness / integration
- [ ] Feed real resolver output (`source_for(id)`) — current cases use short hand-typed
  source snippets; full judgment text changes chunking/rerank behaviour.
- [ ] Tune `TAU_LOW`, `tau_coverage`, and `LEVEL_W` on the anchor set once the real
  backend exists (current values are placeholders).
- [ ] Decide handling for the "case doesn't exist / wrong citation" path — step 4
  assumes resolution already found a real source.

### Housekeeping
- [ ] Rotate the API keys committed in `.env` (Gemini PAT, GitHub PAT, Claude key) —
  ensure `.env` stays gitignored.
