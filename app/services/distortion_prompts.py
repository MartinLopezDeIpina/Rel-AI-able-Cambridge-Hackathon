"""Prompt templates for the citation-integrity detector (LLM stages).

These templates are the contract between the orchestrator
(:mod:`app.services.distortion_service`) and the LLM for the SELECT (stage 3),
DECOMPOSE (stage 4) and JUDGE (stages 5-6) steps. The MockBackend ignores them
and uses transparent heuristics; the VertexBackend sends exactly these. All
of them require strict JSON replies.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Stage 3: the LLM selects R_top from the (paragraph, rerank-score) tuples.
# IMPORTANT: keep contradicting but on-topic paragraphs.
# --------------------------------------------------------------------------
SELECT_PROMPT = """\
You are auditing how a legal document cites a source judgment.

CITATION (an indirect/paraphrased reference made by the citing document):
\"\"\"{citation}\"\"\"

Below are candidate paragraphs from the cited judgment, each with a relevance
score. Select up to {k} paragraphs that actually concern the SAME point the
citation is about — the ones a lawyer would check to verify the citation.

CRUCIAL: include paragraphs that are on-topic even if they CONTRADICT or qualify
the citation. A contradicting paragraph is the most important evidence; do not
drop it for being "off message".

CANDIDATES:
{candidates}

Return strict JSON: {{"r_top": [<paragraph_id>, ...]}} ordered most to least
on-point. Do not include paragraphs that merely share vocabulary but address a
different question.
"""

# --------------------------------------------------------------------------
# Stage 4: extract statements S + premises per statement.
# --------------------------------------------------------------------------
DECOMPOSE_PROMPT = """\
Decompose the following indirect legal citation into atomic STATEMENTS, and for
each statement list the PREMISES that must hold for the statement to be a fair
characterisation of the cited judgment, given its scope and topic.

For each premise mark its kind:
  - "necessary": must hold or the statement is false/unfair.
  - "sufficient": if it holds (in this context) the statement is supported.
Include premises about epistemic strength (is a tentative/modal point in the
source being stated as settled fact?), about omitted conditions/qualifications,
and about whether the point is the court's holding vs dictum/argument/dissent.

CITATION:
\"\"\"{citation}\"\"\"

Return strict JSON:
{{"statements": [
   {{"statement": "<text>",
     "premises": [{{"premise": "<text>", "kind": "necessary|sufficient"}}]}}
]}}
"""

# --------------------------------------------------------------------------
# Stages 5+6: 3-level charity judge over R_top -> premise labels.
# --------------------------------------------------------------------------
JUDGE_PROMPT = """\
You evaluate whether an indirect legal citation fairly represents a cited
judgment. Apply the PRINCIPLE OF CHARITY: label a premise VIOLATED only if NO
reasonable charitable reading of the citation satisfies it given the evidence.
If a charitable-but-defensible reading is needed, use CHARITABLE.

Labels per premise:
  - SATISFIED   : directly supported by the evidence paragraphs.
  - CHARITABLE  : holds only under a charitable interpretation.
  - VIOLATED    : contradicted, or distorts the source (e.g. modal->factual
                  inflation, an omitted condition, dictum cited as holding,
                  dissent cited as the court's position).
  - UNADDRESSED : the evidence does not speak to this premise at all.

Evaluate on three levels and record which level drove each label:
  - micro : the single most relevant paragraph (does s align with it? modal->fact?)
  - meso  : the surrounding context — do the following paragraphs add a
            counter-argument or relativisation that the citation ignores?
  - macro : is the citation consistent with the core holding/ratio of the case,
            or in direct contradiction to it?

GLOBAL DOCUMENT SUMMARY (what the cited judgment is about, for macro context):
{global_summary}

CITATION:
\"\"\"{citation}\"\"\"

STATEMENTS AND PREMISES (JSON):
{statements_json}

EVIDENCE PARAGRAPHS R_top (id -> text):
{r_top}

FOLLOWING CONTEXT (for meso; id -> text):
{following}

Return strict JSON:
{{"evaluations": [
   {{"statement": "<text>", "premise": "<text>",
     "level": "micro|meso|macro", "label": "SATISFIED|CHARITABLE|VIOLATED|UNADDRESSED",
     "evidence_paragraph_id": <id or null>, "reason": "<one sentence>"}}
],
 "plain_language_holding": "<what the case actually decided, 1-2 sentences>"}}
"""
