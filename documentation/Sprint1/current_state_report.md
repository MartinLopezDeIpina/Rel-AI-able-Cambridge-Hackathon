# HackTheLaw — File, I/O & Data-Flow Report

Status snapshot of the codebase: which files exist, what each expects as input,
what it promises as output, and the high-level intermediate steps.

## End-to-end data flow

```
                 ┌─ CORPUS BUILD ──────────────┐   ┌─ RESOLUTION ────────┐   ┌─ FAITHFULNESS (new) ─────────┐
 pdfs/*.pdf ──►  pdf_to_text ──► build_index ──► index/ ──► resolve_citations ──► chosen_source ──► detect_distortion ──► integrity report
                      │              │              │              │                                      │
                  (OCR cache)   embeddings.npy  chunks.json   web_fallback (opt.)                    llm_backend + prompts
                  index/texts/  sources.json                  (Perplexity)                          (Mock | Nemotron-stub)

                 ┌─ EVAL HARNESS (new) ───────────────────────────────────────────────────────────────┐
 index/texts/ ──► gen_eval ──► eval/eval_set.jsonl ──► (detect_distortion --eval) ──► eval/preds.jsonl ──► score_eval ──► metrics
                            (citelib = shared embedding/chunking/name-match library, used across all stages)
```

14 Python modules: **9 pre-existing** (corpus + resolution) and **6 new** (detector + eval). `citelib.py` is shared by both halves.

---

## Stage 1 — Corpus building (source side)

### `pdf_to_text.py` · *PDF → plain text* · **status: working**
- **Input:** a PDF path (CLI `pdf [out]`, default `example.pdf` → `example.txt`); also called as `extract_text(pdf_path)`.
- **Output:** a `.txt` file / returns the document text (pages joined by blank lines).
- **Steps:** open with PyMuPDF → per page read the **embedded text layer**; if a page has `< 100` chars it's treated as a scan → render at **200 DPI** and OCR with RapidOCR → `order_text()` reorders detected boxes into reading order. No GPU/API.

### `build_index.py` · *corpus → semantic index* · **status: not yet run** (only the OCR cache exists)
- **Input:** `--source-dir` (PDFs and/or `.txt`), `--out-dir` (default `index/`), `--chunk-size 80`, `--chunk-overlap 20`.
- **Output (in `index/`):** `embeddings.npy` (float32, L2-normalised, `n_chunks×384`), `chunks.json` (list of `{source, filename, chunk_id, text}`), `sources.json` (filenames), and `index/texts/<name>.txt` (cached extracted text).
- **Steps:** collect sources → per source load text (reuse cache, else `pdf_to_text.extract_text`) → `citelib.chunk_text` (overlapping 80-word windows) → `citelib.embed_passages` (fastembed/bge-small) → persist.
- **Note:** `index/` currently holds **only `texts/` (9 of 58 PDFs OCR'd)** — no `embeddings.npy`/`chunks.json`. So `resolve_citations.py` can't run until this is built; the detector/eval work directly off `index/texts/`.

---

## Stage 2 — Citation resolution (which case is meant)

### `resolve_citations.py` · *citation → source document* · **status: working, needs built index**
- **Input:** `--index`, citations via `--citations FILE` (one per line) / repeated `--citation` / default `citations.txt`; thresholds `--name-threshold 75`, `--sem-uncertain 0.5`; optional `--web-fallback`, `--out`.
- **Output:** stdout summary + (with `--out`) a JSON list. Per citation: `{citation, chosen_source, method (name|semantic|web), confidence, uncertain, needs_web, signals_agree, name_top, semantic_top{source,score,evidence}, name_ranking, semantic_ranking}`.
- **Steps:** load index → for each citation run two signals: **semantic** (`embed_queries` → cosine vs all chunks → best chunk per source) and **name** (`name_match_score`, fuzzy "X v Y" vs filename) → **fusion** (name ≥75 wins, else semantic; both low ⇒ `needs_web`) → optional web fallback.
- **This is the upstream contract for the detector:** it produces the `chosen_source` the detector consumes.

### `web_fallback.py` · *unresolved citation → online lookup* · **status: scaffold (safe no-op without key)**
- **Input:** list of `(citation, metadata)`; env `PERPLEXITY_API_KEY`; `--pplx-model`.
- **Output:** per citation `{citation, status (ok|not_configured|error), answer, sources, metadata}`.
- **Steps:** `extract_citation_metadata` (case name via regex, year, neutral citation, court codes) → `build_search_prompt` → **async** Perplexity calls (concurrency 4). Handles the "case does not exist / not in corpus" branch of the challenge.

---

## Stage 3 — Content faithfulness (the new detector)

### `detect_distortion.py` · *citation + source → integrity verdict* · **status: working (Mock backend)**
- **Input (two modes):**
  - batch: `--eval eval/eval_set.jsonl` (+`--out`, `--texts-dir`)
  - single: `--citation "..." --source "<name>.pdf.txt"` (+`--texts-dir`)
  - knobs: `--backend mock|nemotron`, `--top 50`, `--k 5`, `--chunk-size 60`, `--chunk-overlap 0`.
- **Output:**
  - batch → `eval/preds.jsonl`: `{id, predicted_label}` (out_of_context→`out_of_scope`, mischaracterised→`misleading`, correct→`faithful`).
  - single → full JSON report: `{citation, classification, mischaracterised_pct, out_of_context_pct, r_top_ids, premise_summary[], evaluations[], plain_language_holding}`.
- **Steps (the 6-stage pipeline):** chunk source into paragraphs → **rerank** (`backend.rerank`) → **select R_top ≤5** (`backend.select`) → gather **following** paragraphs (`id+1..3`) for the meso level → **decompose** citation into statements + premises (`backend.decompose`) → **3-level charity judge** (`backend.judge`: micro modal→factual / meso dropped-qualifier / macro coverage) labelling each premise SATISFIED·CHARITABLE·VIOLATED·UNADDRESSED → **score** (`mischar%` from level-weighted VIOLATED, `out_of_context%` from UNADDRESSED) → classify against `τ_low=25`.

### `llm_backend.py` · *pluggable model layer* · **status: Mock working, Nemotron stub**
- **Input/Output:** a `Backend` with `rerank(citation, paragraphs)→scores`, `select(...)→ids`, `decompose(citation)→statements`, `judge(...)→{evaluations, plain_language_holding}`. `get_backend(name)` factory.
- **`MockBackend`:** deterministic, stdlib-only — lexical-cosine rerank; heuristic judge using `content_coverage` (IDF-style, for out-of-context), `best_sentence` matching, modal/qualifier/negation signals. **Plumbing baseline only — not a validation of the method (same heuristic family as the eval generator).**
- **`NemotronBackend`:** stub that raises `NotImplementedError` — the 1:1 drop-in point for Nemotron Rerank 1B v2 + Ultra once the Pkt-9 serving decision is made.
- **Utilities (shared with detector):** `tokenize`, `lexical_sim`, `content_tokens/coverage`, `best_sentence`.

### `prompts.py` · *Nemotron prompt contracts* · **status: ready, unused until backend lands**
- **Input/Output:** three `.format()` templates — `SELECT_PROMPT` (→`{"r_top":[ids]}`), `DECOMPOSE_PROMPT` (→`{"statements":[{statement,premises[]}]}`), `JUDGE_PROMPT` (→`{"evaluations":[…], "plain_language_holding"}`). Each demands strict JSON and encodes the charity rule + the keep-contradicting-paragraphs instruction.

---

## Stage 4 — Evaluation harness (new)

### `evallib.py` · *eval building blocks* · **status: working (library)**
- **Provides:** `EvalExample` dataclass (`id, indirect_quote, source_doc, gold_label, distortion_type, source_sentence, source_char_offset, qualifier_span, qualifier_text, generation_method, difficulty`); JSONL I/O; `read_text_docs`/`normalize_ws`; `text_quality`/`is_clean` (OCR-quality gate); `split_sentences`/`is_proposition`; the **perturbation operators** (`op_conditional_drop`, `op_scope_strip`, `op_negation_flip`, `op_faithful_compress`); `_ok_quote`/`lexical_gate`/`absent_from_doc` (validation gate).

### `gen_eval.py` · *corpus → labelled eval set* · **status: working (82 examples)**
- **Input:** `--texts-dir index/texts`, `--out eval/eval_set.jsonl`, `--per-type 4`, `--embed-check` (optional), `--seed`.
- **Output:** `eval/eval_set.jsonl` (gold examples) + a stderr summary (counts per class/type).
- **Steps:** load docs → keep clean ones → extract propositions → apply templated operators → **misleading** (+faithful controls); inject sentences from other docs → **out_of_scope**; validate each via the gate; balance & shuffle.

### `score_eval.py` · *predictions vs gold → metrics* · **status: working**
- **Input:** `--gold`, and `--pred preds.jsonl` **or** `--baseline {perfect|majority|random}`.
- **Output:** stdout report — per-class **P/R/F1**, **macro-F1**, **confusion matrix**, **recall per distortion type**, **evidence-span accuracy**; headline = **recall on `misleading`**.
- **Steps:** load both → tally TP/FP/FN per class + confusion → per-type recall → span-overlap (IoU≥0.5) for flagged misleading.

---

## Shared library & data artifacts

| File | Role |
|------|------|
| `citelib.py` | **Shared library** (no CLI): `EMBED_MODEL=bge-small-en-v1.5`; `get_model`, `embed_passages`, `embed_queries`, `chunk_text(80/20)`, `normalize_name`, `extract_case_name`, `filename_to_name`, `name_match_score`. Used by build/resolve/web; the detector deliberately avoids it (numpy) for offline runs. |
| `index/texts/*.txt` | OCR/text cache — **9 docs** (the de-facto corpus for detector + eval today). |
| `eval/eval_set.jsonl` | 82 gold examples (41 misleading / 32 out_of_scope / 9 faithful). |
| `eval/preds.jsonl` | Latest detector predictions (Mock backend). |
| `example.pdf` / `example.txt` | The example input document (skeleton-argument side). |
| `requirements.txt` | `pymupdf`, `rapidocr-onnxruntime`, `fastembed`, `rapidfuzz`, `numpy` — CPU-only. *(Not installed in base `python3`; the detector + eval run without them.)* |
| `TODO.md` | Notes (web-fallback flagged "scaffold, not finalized"). |

---

## Status at a glance

- **Runs today, offline, no deps:** `detect_distortion`, `llm_backend` (Mock), `prompts`, `evallib`, `gen_eval`, `score_eval`, `pdf_to_text`.
- **Needs `numpy`/`fastembed` + a build step:** `build_index` → then `resolve_citations`.
- **Needs a decision/key:** `NemotronBackend` (Pkt-9 serving), `web_fallback` (Perplexity key).

## Current Mock-backend metrics (synthetic eval, 82 examples)

macro-F1 **0.752** · out_of_scope **R 1.00 / P 0.97** · misleading **R 0.83 / P 0.87** · faithful 0.44.
Per distortion type: foreign_claim 32/32, scope_stripped 7/7, polarity_flip 21/25, conditional_dropped 6/9.
These prove the pipeline + two-axis scoring; real accuracy needs the Nemotron backend (+ a small hand-labelled anchor set).
