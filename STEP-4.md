# STEP 4 — Citation-Integrity / Distortion Detection

Consolidated status + results for **Step 4 (M4)**: given a citation's claim and the
resolved source judgment, decide whether the claim *fairly represents* what the case
decided. This is the input to **Step 5** (report generation / frontend).

- Code: `app/services/distortion_service.py` (orchestration),
  `app/services/distortion_backend.py` (pluggable model),
  `app/services/distortion_prompts.py` (strict-JSON templates).
- Schemas: `app/schemas/citation.py` (`Classification`, `ClassificationType`, `AnalysisDict`).
- Detailed log: `documentation/Sprint2/step4_status.md`.
- Test harnesses: `example_matched/test_analyze.py`, `example_mismatched/test_analyze.py`.

---

## 1. What it does

`analyze(relevant_text, source_text, backend, ...) -> (report, id)`

Stages: **chunk** source → **rerank** (lexical) → **select** R_top (LLM) → gather
**following** paragraphs (meso context) → **decompose** claim into statements/premises
(LLM) → **3-level charity judge** micro/meso/macro (LLM) → **score** → two %-axes +
class.

Output class (detector-level): `correct | mischaracterised | out_of_context`.
Thresholds: `TAU_LOW = 25` (both axes below → `correct`); else the larger axis wins.
- `mischaracterised_pct` = severity-weighted share of **VIOLATED** premises (contradiction).
- `out_of_context_pct` = share of **UNADDRESSED** premises (source silent on the claim).

How the three challenge buckets map:
- **Direct Support** → premises **SATISFIED**, class `correct` → user-facing `EXISTS_CORRECTLY_APPLIED`.
- **Misapplication / Distinction** → **UNADDRESSED** → `out_of_context`.
- **Reversal / principle rejected in the case itself** → **VIOLATED** → `mischaracterised`.
- Both collapse to the user-facing `EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT`.

---

## 2. How the LLM is wired

Auth is **Application Default Credentials** (gcloud browser auth) — *no API key*.
ADC has access to one project, `llm-law-cambridge26cbx-518` ("Hack the Law"),
discovered via the Resource Manager API.

`.env`: `LLM_PROVIDER=vertex`, `GOOGLE_PROJECT=llm-law-cambridge26cbx-518`.
`build_llm` returns `ChatVertexAI` (Gemini 2.5 Flash). The distortion LLM backend
(`VertexBackend`, formerly `OpenRouterBackend`) reuses `build_llm`, so citation
enrichment and the distortion judge share one client.

Backends (`get_backend`): `"mock"` (offline, deterministic lexical heuristics),
`"vertex"` (real LLM). `"openrouter"` is kept as a **back-compat alias** for `"vertex"`.

Run: `.venv/bin/python example_matched/test_analyze.py vertex`
(or `example_mismatched/...`; `mock` for offline).

---

## 3. Results on the supplied examples

### Matched (`example_matched/Matched.pdf`) — must NOT be flagged

| # | Case | class | mischar% / ooc% | Verdict |
|---|------|-------|-----------------|---------|
| 1 | Lumley v Gye (1853) 2 E&B 216 | `correct` | 0 / 0 | ✅ not flagged |
| 2 | American Cyanamid v Ethicon [1975] AC 396 | `correct` | 0 / 14.3 | ✅ not flagged |

**PASS** — neither faithful citation was flagged. (No false positives.)

### Mismatched (`example_mismatched/Mismatched.pdf`) — must be flagged

| # | Case | PDF defect | mock | Vertex/Gemini | mischar%/ooc% |
|---|------|-----------|------|---------------|---------------|
| 1 | Anglia Television v Reed [1972] 1 QB 60 | opposite of source cited | `out_of_context` | `out_of_context` | 16.7 / 66.7 |
| 2 | D.C. Thomson v Deakin [1952] Ch 646 | rule made up | `mischaracterised` | `mischaracterised` | 34.6 / 30.8 |
| 3 | Hadley v Baxendale (1854) 9 Ex 341 | applied in reverse | `out_of_context` | `out_of_context` | 25 / 50 |

**All 3 flagged as defective — none cleared as `correct`.** The headline behaviour
(separating "problem" from "fine") is solid in both directions.

---

## 4. Known weakness: subtype instability (mischaracterised vs out_of_context)

On the mismatched set the *defective/clean* split is reliable, but the *subtype* is
not (Vertex: case 2 right, cases 1 & 3 land on `out_of_context`). Root cause,
confirmed: **DECOMPOSE** turns the claim into premises that include **party-specific
application facts** (Crestholm, £47m, the Supply Agreement, saved costs, risk
adjustments). Those can never appear in a 19th/20th-century judgment, so the judge
marks them `UNADDRESSED`, inflating `out_of_context_pct` until it overtakes the
genuine `VIOLATED` contradiction — even though the LLM's per-premise *reasoning* is
correct on all 3 (e.g. Hadley → *"'such loss would neither have flowed naturally'…
directly contradicting the claim"*). The matched set scores ~0 precisely because
its claims are clean legal propositions with a full faithful source.

**Fix direction (two levers):**
1. Decompose against the *legal proposition the case is cited for* (use the upstream
   `proposition` / `ground`), not the party-specific facts.
2. Weight `VIOLATED` over `UNADDRESSED` in `score()` so a clear contradiction is not
   drowned by off-topic application detail.

Also: feed the **full** resolved source document, not snippets — faithful and
unfaithful claims both score far more cleanly with full text (see matched results).

---

## 5. Gaps vs the M4 "Definition of Done" (what Step 5 still needs)

| Requirement | Status | Gap |
|---|---|---|
| Strict 3-way (VERIFIED / MISCHARACTERISED / FABRICATED) | 🟡 schema only | No code maps M3 "Not Found" → `DOESNT_EXIST` + 0% short-circuit; verdict object unset |
| Ground mapping | ❌ | `CitationMetadata.ground` extracted upstream but not fed to the judge or surfaced |
| Mismatch pass (no false-clear) | ✅ | matched not flagged; mismatched all flagged |
| Structured JSON for frontend | 🟡 | Pydantic exists; judge asks for "strict JSON" in prose (no `with_structured_output`); keys differ from blueprint; no single 0–1 `confidence_score` |
| Plain-language summaries | 🟡 | `plain_language_holding` present; no dedicated 2–3 sentence "why it's wrong" explanation |
| Overturn check (Perplexity) | ➖ optional | Not implemented in `app/` (prototype `web_fallback.py` only); documented as a fallback TODO |

### Recommended next steps (Step 5 enablement)
1. **M3→M4 orchestrator**: read `/data/text_source/{id}.txt`, short-circuit
   FABRICATED, run `analyze`, merge resolver existence + detector verdict into a
   single `Classification`.
2. **Frontend contract**: emit the blueprint JSON
   (`citation_name, status, confidence_score, associate_claim, actual_holding,
   explanation`) via Pydantic structured output; derive one `confidence_score`
   (0–1) from the two %-axes; add the 2–3 sentence mismatch explanation and `ground`.
3. **Fix subtype scoring** (Section 4) so MISCHARACTERISED is reliable.
4. **Eval set**: promote the matched + mismatched cases into `eval/` with expected
   labels and assert in `tests/test_pipeline.py`.
