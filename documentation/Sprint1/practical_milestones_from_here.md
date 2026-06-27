Use milestones that follow the product’s actual verification path: **parse -> verify existence -> verify support -> classify -> explain**. That keeps the team focused on the challenge’s narrow success condition, and it matches current legal citation-verification practice where systems first confirm the authority is real and then test whether it supports the cited proposition. [phala](https://phala.com/posts/legalcitebench-ai4law-icml-2026)

## Milestone 1

**Document ingestion and citation extraction** should prove that the system can take the skeleton argument and recover all twelve citations as structured objects. Success here means the tool extracts exactly twelve candidate citations with stable IDs, source spans, and normalized citation strings from the document. [journals.sagepub](https://journals.sagepub.com/doi/10.1177/0266382112458203?icid=int.sj-abstract.similar-articles.7)

Acceptance criteria:
- Upload or paste the skeleton argument works. [scitepress](https://www.scitepress.org/Papers/2019/80527/80527.pdf)
- Exactly 12 citations are extracted from the test document.  
- Each citation has `id`, raw text, normalized citation string, surrounding paragraph, and claimed proposition fields. [phala](https://phala.com/posts/legalcitebench-ai4law-icml-2026)

## Milestone 2

**Dataset matching and existence verification** should prove that each extracted citation can be checked against the mock legal dataset before any reasoning step. This follows the recommended pipeline pattern: treat citations as verifiable objects, normalize them, and match them against a source registry instead of asking a model to invent or remember the answer. [cite](https://cite.review)

Acceptance criteria:
- Each of the 12 citations is looked up against the mock dataset. [phala](https://phala.com/posts/legalcitebench-ai4law-icml-2026)
- Output for each citation is one of: exact match, fuzzy/candidate match, or no match. [cite](https://cite.review)
- No citation is marked “verified” without a supporting dataset match. [cite](https://cite.review)

## Milestone 3

**Contextual support checking** should prove that the system can compare what the skeleton argument claims with what the matched authority actually says. This is the second half of the problem: a citation can be real and still be misapplied, so support review must happen after identity verification rather than being merged into the same step. [arxiv](https://arxiv.org/html/2511.16198v1)

Acceptance criteria:
- For every citation with a dataset match, the system retrieves the relevant case summary, holding, or supporting passage. [arxiv](https://arxiv.org/html/2511.16198v1)
- The system compares the argument’s proposition to that source evidence. [cite](https://cite.review)
- Each matched citation is marked as supported, weakly supported, contradicted, or insufficient evidence internally, even if the user-facing label is simpler. [arxiv](https://arxiv.org/html/2511.16198v1)

## Milestone 4

**Verdict classification and explanation** should prove that the system can convert verification outputs into the three challenge categories with plain-language reasons. The important design principle is that explanation comes from grounded evidence, not free-form model intuition. [phala](https://phala.com/posts/legalcitebench-ai4law-icml-2026)

Acceptance criteria:
- Each of the 12 citations is labeled as **verified**, **misapplied**, or **non-existent**. [cite](https://cite.review)
- Each label includes a one- to three-sentence explanation in plain English. [phala](https://phala.com/posts/legalcitebench-ai4law-icml-2026)
- The explanation cites either “matched and supports,” “matched but does not support,” or “no reliable match found in dataset” as its basis. [cite](https://cite.review)

## Milestone 5

**End-to-end review output** should prove that a partner could act on the result immediately. Legal citation workflows benefit when the output is reviewable, traceable, and clearly separated into existence checking and support checking rather than hidden inside one opaque score. [phala](https://phala.com/posts/legalcitebench-ai4law-icml-2026)

Acceptance criteria:
- One report shows all 12 citations in a table.  
- The table includes citation text, dataset match, verdict, and plain-language explanation. [cite](https://cite.review)
- The report can be read in under two minutes and supports immediate filing review. [phala](https://phala.com/posts/legalcitebench-ai4law-icml-2026)

A practical milestone tracker could look like this:

| Milestone | Goal | Done when |
|---|---|---|
| M1 Extraction | Find the 12 citations | Exactly 12 extracted with metadata and context  [scitepress](https://www.scitepress.org/Papers/2019/80527/80527.pdf) |
| M2 Existence check | Match citations to dataset | Each citation has exact/fuzzy/no-match status  [phala](https://phala.com/posts/legalcitebench-ai4law-icml-2026) |
| M3 Support check | Test legal proposition | Matched citations compared to case evidence  [cite](https://cite.review) |
| M4 Verdicting | Produce the 3 required labels | Every citation labeled verified, misapplied, or non-existent  [cite](https://cite.review) |
| M5 Report | Make output actionable | One readable partner-facing report for all 12 citations  [journals.sagepub](https://journals.sagepub.com/doi/10.1177/0266382112458203?icid=int.sj-abstract.similar-articles.7) |

One useful anti-drift rule: do not start confidence scoring, Monte Carlo sampling, or web fallback until **M4** is stable, because the challenge’s main value is correct extraction, grounded verification, and clear verdicting on the twelve citations, not advanced scoring machinery. [phala](https://phala.com/posts/legalcitebench-ai4law-icml-2026)

Would you like these milestones rewritten as a sprint board with owners and test cases?
