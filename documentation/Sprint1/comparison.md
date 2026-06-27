# Codebase Comparison — Leo vs Martin (vs the incoming UI)

Two codebases address the same challenge. They turn out to be **two halves of the
same pipeline with almost no overlap**: Martin owns the *front* (ingest + extract
citations), Leo owns the *back* (verify existence + check faithful use + measure
accuracy). The UI (Louisa & Kim) is the third piece, about to sit on top.

- **Leo** — `/home/leo/hackthelaw` ("current version"); described by `current_state_report.md`.
- **Martin** — `github_project/Rel-AI-able-Cambridge-Hackathon` (all 6 commits dated 2026-06-27 — brand new).
- **Louisa & Kim** — UI, *about to be integrated* (no code yet).

---

## 1. What each codebase is

### Leo — verification pipeline (offline, CPU-only, script-based)
A four-stage pipeline plus a shared library (`citelib.py`):

1. **Corpus build** — `pdf_to_text.py` (PyMuPDF + RapidOCR), `build_index.py` (bge-small embeddings → `index/`).
2. **Resolution** — `resolve_citations.py`: matches a citation to its source case-law document by **two signals** (semantic embedding + fuzzy case-name match), with a `needs_web` flag and an optional `web_fallback.py` (Perplexity) for "not in corpus".
3. **Faithfulness** — `detect_distortion.py` + `llm_backend.py` + `prompts.py`: given a claim and its resolved source, classifies **faithful / misleading (mischaracterised) / out_of_scope (out-of-context)** via a charity-judge over decomposed premises, with two %-scores and a plain-language holding.
4. **Eval** — `gen_eval.py`, `evallib.py`, `score_eval.py`: an 82-example synthetic gold set + metrics (current Mock backend: macro-F1 0.752).

Maturity: strong on the *hard* part (verification + faithfulness + measurable eval), but **no API, no UI**, `build_index` not yet run, and the real Nemotron backend is a stub (`MockBackend` is the working default).

### Martin — extraction + enrichment + service shell (FastAPI, cloud LLM)
A layered FastAPI template with two real feature modules:

- **`citation_service.py`** — regex extraction from a PDF. Genuinely solid: three UK citation styles (neutral `[2007] UKHL 21`, law-report `[1952] Ch 646`, nominate `(1853) 2 E&B 216`), captures preceding case names, dedupes by raw text, orders by document position, assigns 1-based `id`s.
- **`citation_llm_service.py`** — feeds the anchors **plus the whole document** to Nemotron-3-nano via OpenRouter (LangChain), returning structured metadata per `id`: `full_case_name`, `court_name`, `judges`, `proposition`, `ground`, `relevant_text`. Includes a cheap judge-name anti-hallucination check.
- Pydantic schemas (`Citation` → `CitationMetadata` → `EnrichedCitation`), config-driven model selection, `.env` for the key.

Maturity: deployable web shape + excellent extraction, but **no verification, no flagging**, the citation feature is **not wired into the API** (router only exposes the template `items` endpoint — both citation modules run only via `python -m … __main__`), the corpus was deleted from git, and the only test is the template's `test_items.py`.

---

## 2. The most important finding

**Martin's LLM step is, by design, the opposite of a verifier.** Its system
prompt instructs:

> "Use ONLY information present in the document. Never invent or use outside
> knowledge. If a field is not stated in the document, set it to null."

So it answers *"what does the document say about this cite?"* — it **transcribes**,
it does not check. If the junior associate's skeleton cites a **hallucinated**
case, Martin's tool will faithfully extract that fake case's metadata from the
document and report it, with **no signal that it is fake**.

That existence-and-faithfulness check — challenge requirements #3 and #4, and the
whole demo moment ("this case does not exist") — lives **entirely on Leo's side**.
This is the strongest argument for merging rather than picking one.

---

## 3. Scored against the challenge MUST requirements

| Requirement | Martin | Leo | After merge |
|---|---|---|---|
| **1. Ingestion** (upload/paste a doc) | PDF via pypdf, **not exposed over HTTP** yet | PDF→text + OCR; takes citations as given input | ✅ one endpoint, PDF **or** pasted text |
| **2. Citation extraction** | ✅ **strong** (regex 3 styles + LLM enrichment) | ❌ absent — resolver takes citations as *input lines* | ✅ Martin's extractor |
| **3. Verification (is it real?)** | ❌ document-internal only; cannot detect a fake | ✅ resolver matches against corpus; `needs_web` + web-fallback = "not in corpus" | ✅ Leo's resolver |
| **4. Flagging into 3 buckets** | ❌ no verdict produced | ✅ faithful / misleading / out_of_scope; resolver confidence + non-existent signal | ✅ Leo's detector + resolver |

### Bonuses
| Bonus | Martin | Leo |
|---|---|---|
| Confidence score | ❌ | ✅ resolver `confidence`; detector `mischaracterised_pct` / `out_of_context_pct` |
| Explanation engine | ~ `proposition`/`relevant_text` (descriptive, not a flag rationale) | ✅ `premise_summary`, per-premise `evaluations`, `plain_language_holding` |
| Visual dashboard | FastAPI `/docs` only (structural) | ❌ | ← **this is Louisa & Kim's piece** |

---

## 4. Overlap, divergence, and the shared bet

- **Overlap:** minimal. Both define a `Citation` concept, and both intend to use **Nemotron** — but at different points and via different serving:
  - Martin: Nemotron-3-nano via **OpenRouter** (cloud, API key, *already integrated*) for **enrichment**.
  - Leo: `NemotronBackend` stub for Nemotron Rerank 1B v2 + Ultra (CPU/offline) for the **judge** — currently a `NotImplementedError`, with `MockBackend` standing in.
  - **Decision needed:** Leo's stub can be short-circuited by reusing Martin's OpenRouter path, so the faithfulness judge runs on a real model without solving local serving. (See integration plan.)
- **Divergence in framing:** Martin = "describe the cite from the doc"; Leo = "judge the cite against ground truth". These compose perfectly: Martin's `relevant_text`/`proposition` (the document's *claim* about the case) is exactly the input Leo's detector needs to judge.

---

## 5. Conclusion

Neither codebase is a full solution alone, and they barely overlap:

- **Martin alone** ingests and extracts beautifully but cannot tell real from fake or right from wrong — it fails the core of the challenge.
- **Leo alone** can verify and judge, and proves it with an eval, but has no extraction, no API, and no UI.
- **Together**, behind Martin's FastAPI with Louisa & Kim's dashboard on top, they cover every MUST requirement and three of three bonuses.

→ Proceed to [`integration-plan.md`](integration-plan.md).
