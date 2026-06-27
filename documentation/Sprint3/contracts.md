# Sprint 3 — Data Contracts & Per-Step State Machine

The machine-checkable version lives in `tests/contracts.py` (`assert_*` validators +
`StepNCase` enums). This is the narrative: for each step, the **input contract**, the
**output contract**, and **every case the step can land in** with the expected
externally-observable behaviour. Tests reference the enums so each case is covered.

---

## Step 1 — Citing-side extraction & enrichment
- **In:** a brief PDF path (or text via monkeypatched `read_pdf_text`).
- **Out:** `list[Citation]` (regex) → `list[EnrichedCitation]` (LLM). `assert_citation`
  requires `id:int>=1, raw:str, year:int`; enrichment adds nullable
  `full_case_name, proposition, ground, relevant_text`.

| Case | Trigger | Expected behaviour |
|------|---------|--------------------|
| `neutral_citation` | `[2007] UKHL 21` | one Citation, `citation_type=neutral` |
| `law_report_citation` | `[1972] 1 QB 60` | `citation_type=law_report`, `reporter=QB` |
| `nominate_citation` | `(1853) 2 E&B 216` | `citation_type=nominate`, `reporter=E&B` |
| `preceding_case_name` | `"X v Y [..]"` | `case_name` captured |
| `no_citation_in_text` | plain prose | `[]` |
| `duplicate_raw` | same raw twice | deduped to one, 1-based ids preserved |

## Step 2 — Source corpus → text + index
- **In:** a corpus dir of `.pdf`/`.txt`; **Out:** `embeddings.npy` (L2-normalised
  `n×dim`), `chunks.json` (`{source,filename,chunk_id,text}`), `sources.json`.

| Case | Trigger | Expected behaviour |
|------|---------|--------------------|
| pdf-with-sibling-txt | `a.pdf` + `a.txt` | txt dropped (pdf wins), no double-index |
| scanned page | text layer < 100 chars | OCR fallback (PyMuPDF+RapidOCR) |
| empty corpus | no sources | `ValueError` |
| build | N docs | normalised embeddings, `len(sources)==N` |

## Step 3 — Resolution / existence (`resolve_one` → dict)
- **In:** citation string + index (`embeddings, chunks, sources`).
- **Out:** dict — `assert_resolver_result` requires `chosen_source, method∈{name,semantic},
  confidence∈[0,1], uncertain, needs_web, used_semantic_fallback, signals_agree,
  name_top, semantic_top, name_ranking, semantic_ranking`.

| Case | Trigger | Expected behaviour |
|------|---------|--------------------|
| `name_hit_wins` | fuzzy ≥ 75 | `method=name`, `needs_web=False`, `used_semantic_fallback=False` |
| `semantic_fallback` | name < 75, sem ≥ 0.5 | `method=semantic`, `used_semantic_fallback=True` |
| `not_in_corpus` | name < 75 **and** sem < 0.5 | `needs_web=True`, `uncertain=True` → **FABRICATED candidate** |
| `name_and_semantic_agree` | name confident & same source as semantic | `signals_agree=True` |

## Step 4 — Faithfulness detector (`analyze` → report dict)
- **In:** `relevant_text` (claim) + `source_text` + backend.
- **Out:** `assert_analysis_report` requires `classification∈{correct,mischaracterised,
  out_of_context}`, `mischaracterised_pct/out_of_context_pct∈[0,100]`,
  `plain_language_holding`, `evaluations`.

| Case | Trigger | Expected behaviour |
|------|---------|--------------------|
| `faithful_correct` | both axes < `TAU_LOW`(25) | `correct` |
| `violated_misrepresentation` | VIOLATED dominates | `mischaracterised` |
| `unaddressed_off_topic` | UNADDRESSED dominates | `out_of_context` |
| `empty_source` | `source_text=""` | `out_of_context`, `out_of_context_pct=100` |

## Step 5 — Final verdict / frontend contract (NOT BUILT YET)
- **Target Out:** per citation — `assert_verify_response` requires `citation_name,
  status, confidence_score∈[0,1], associate_claim, actual_holding, explanation`.
- User-facing `status` from `ClassificationType`:
  `EXISTS_CORRECTLY_APPLIED | EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT | DOESNT_EXIST`.

| Case | Trigger | Expected behaviour |
|------|---------|--------------------|
| `verified` | exists + Step 4 `correct` | `EXISTS_CORRECTLY_APPLIED`, high `confidence_score` |
| `mischaracterised` | exists + Step 4 flagged | `EXISTS_MISCHARACTERISED…`, 2–3 sentence `explanation` |
| `fabricated` | Step 3 `needs_web` | `DOESNT_EXIST`, `confidence_score=0`, **skip Step 4** |
| `needs_review` | unconfirmed | `needs_review=True` badge |

> Step 5 tests are **XFAIL** until `POST /api/citations/verify` + the orchestrator exist.
