"""Pluggable LLM backend for the citation-integrity detector.

Separates orchestration (:mod:`app.services.distortion_service`) from the concrete
model binding. Two backends:

  * MockBackend       - deterministic, pure-Python (stdlib only), NO GPU/API/deps.
                        Uses transparent lexical heuristics instead of real LLM
                        inference. PLACEHOLDER: it proves the pipeline/wiring and
                        the scoring, NOT the substantive accuracy.
  * OpenRouterBackend - real binding that REUSES the project's OpenRouter client
                        (``app.services.citation_llm_service.build_llm``), so the
                        whole app talks to one configured model (``LLM_MODEL``).
                        Sends the strict-JSON templates from
                        :mod:`app.services.distortion_prompts`.

The real backend replaces the mock 1:1 (same method signatures). Each LLM stage
degrades to the mock heuristic if the reply cannot be parsed or no API key is
configured, so the pipeline never crashes offline.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter

from app.services.distortion_prompts import (
    DECOMPOSE_PROMPT,
    JUDGE_PROMPT,
    SELECT_PROMPT,
)

# --------------------------------------------------------------------------
# Text helpers (shared with the detector)
# --------------------------------------------------------------------------

def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def lexical_sim(a: str, b: str) -> float:
    """Cosine over token frequencies (0..1). Embedding-free stand-in."""
    ca, cb = Counter(tokenize(a)), Counter(tokenize(b))
    if not ca or not cb:
        return 0.0
    common = set(ca) & set(cb)
    dot = sum(ca[t] * cb[t] for t in common)
    na = math.sqrt(sum(v * v for v in ca.values()))
    nb = math.sqrt(sum(v * v for v in cb.values()))
    return dot / (na * nb) if na and nb else 0.0


# Signal lexica for the mock heuristic.
_NEG = re.compile(r"\b(not|no|cannot|never|nor|none|without|fails? to)\b", re.I)
_MODAL = re.compile(
    r"\b(may|might|could|would|appears?|seems?|suggests?|arguably|"
    r"prima facie|tend(?:s|ed)? to|likely|possibl[ey]|perhaps)\b", re.I)
# Qualifiers whose omission distorts a statement (condition OR scope).
_QUALIFIER = re.compile(
    r"\b(provided (?:always )?that|unless|subject to|save where|except where|"
    r"so long as|on condition that|for the purposes? of|within the meaning of|"
    r"in the context of)\b", re.I)


def _has(rx, text: str) -> bool:
    return rx.search(text) is not None


_STOP = {"which", "there", "their", "these", "those", "where", "while", "shall",
         "would", "could", "should", "being", "other", "under", "upon", "after",
         "before", "because", "whether", "against", "between", "within", "about",
         "without", "therefore", "however", "accordingly", "claim", "claims",
         "court", "case", "cases", "judgment", "appeal"}


def content_tokens(text: str) -> list[str]:
    """Distinctive content tokens (len>=5, no common function/legal words)."""
    return [t for t in tokenize(text) if len(t) >= 5 and t not in _STOP]


def content_coverage(citation: str, paragraph: str) -> float:
    """Share of the citation's distinctive tokens present in the paragraph (0..1).

    Low coverage = the paragraph does NOT talk about what the citation talks about
    (foreign claim / out of context). More robust than absolute similarity because
    legal texts share a lot of common vocabulary.
    """
    cts = content_tokens(citation)
    if not cts:
        return 1.0
    pset = set(tokenize(paragraph))
    return sum(1 for t in cts if t in pset) / len(cts)


def best_sentence(citation: str, paragraph: str) -> str:
    """The sentence within a paragraph most similar to the citation."""
    parts = [p for p in re.split(r"(?<=[.?!])\s+", paragraph) if p.strip()] or [paragraph]
    return max(parts, key=lambda s: lexical_sim(citation, s))


def _loads_json(content: str) -> dict:
    """Parse a model reply into a dict, tolerating markdown fences / stray prose."""
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)


# --------------------------------------------------------------------------
# MockBackend
# --------------------------------------------------------------------------

class MockBackend:
    """Deterministic placeholder with no external dependencies.

    NOTE: the heuristics deliberately mirror the same distortion types as the
    synthetic eval generator -> metrics with this backend are a plumbing/scoring
    test, NOT a validation of the method. Real validation needs the OpenRouter
    backend (+ a small hand-labelled anchor set).
    """

    name = "mock"

    # -- Stage 2: Rerank -------------------------------------------------
    def rerank(self, citation: str, paragraphs: list[str]) -> list[float]:
        return [lexical_sim(citation, p) for p in paragraphs]

    # -- Stage 3: Select R_top ------------------------------------------
    def select(self, citation, scored: list[tuple[int, str, float]], k: int) -> list[int]:
        ranked = sorted(scored, key=lambda t: t[2], reverse=True)
        return [pid for pid, _txt, _s in ranked[:k]]

    # -- Stage 4: Decompose ---------------------------------------------
    def decompose(self, citation: str) -> list[dict]:
        sents = [s.strip() for s in re.split(r"(?<=[.?!])\s+", citation) if s.strip()]
        if not sents:
            sents = [citation.strip()]
        statements = []
        for s in sents:
            statements.append({
                "statement": s,
                "premises": [
                    {"premise": "The cited judgment asserts this point.", "kind": "necessary"},
                    {"premise": "The epistemic strength matches the source.", "kind": "necessary"},
                    {"premise": "No qualifying condition or scope limit is omitted.", "kind": "necessary"},
                ],
            })
        return statements

    # -- Stages 5+6: 3-level charity judge ------------------------------
    def judge(self, citation: str, statements: list[dict],
              r_top: list[dict], following: list[dict],
              tau_coverage: float = 0.34, global_summary: str = "") -> dict:
        best = max(r_top, key=lambda p: lexical_sim(citation, p["text"]), default=None)
        # Bind signals to the best-matching SENTENCE (not the whole chunk),
        # otherwise ambient modals/qualifiers fire on everything.
        src = best_sentence(citation, best["text"]) if best else ""
        cov = content_coverage(citation, best["text"]) if best else 0.0
        sim = lexical_sim(citation, src) if best else 0.0
        # Following paragraphs: relativisation/condition the citation ignores.
        follow_txt = " ".join(p["text"] for p in following)

        evals: list[dict] = []
        for st in statements:
            s = st["statement"]
            if best is None or cov < tau_coverage:
                evals.append(_ev(s, "The cited judgment asserts this point.",
                                 "macro", "UNADDRESSED", None,
                                 f"Source does not cover the citation's content (coverage={cov:.2f})."))
                continue
            evals.append(_ev(s, "The cited judgment asserts this point.",
                             "macro", "SATISFIED", best["id"],
                             f"Paragraph {best['id']} is on point (coverage={cov:.2f})."))
            if _has(_MODAL, src) and not _has(_MODAL, citation):
                evals.append(_ev(s, "The epistemic strength matches the source.",
                                 "micro", "VIOLATED", best["id"],
                                 "Source is tentative/modal; citation states it as settled."))
            if _has(_QUALIFIER, src) and not _has(_QUALIFIER, citation):
                evals.append(_ev(s, "No qualifying condition or scope limit is omitted.",
                                 "meso", "VIOLATED", best["id"],
                                 "Matched sentence qualifies/conditions the point; citation drops it."))
            elif _has(_QUALIFIER, follow_txt) and not _has(_QUALIFIER, citation) \
                    and _has(re.compile(r"\b(however|but|provided|unless|qualif)", re.I), follow_txt):
                evals.append(_ev(s, "No qualifying condition or scope limit is omitted.",
                                 "meso", "VIOLATED", best["id"],
                                 "Following context relativises the point; citation ignores it."))
            if sim > 0.30 and (_has(_NEG, citation) != _has(_NEG, src)):
                evals.append(_ev(s, "The epistemic strength matches the source.",
                                 "micro", "VIOLATED", best["id"],
                                 "Negation polarity differs from the matched sentence."))
        holding = (src[:200] + "…") if best else "(no on-point paragraph found)"
        return {"evaluations": evals, "plain_language_holding": holding}


def _ev(statement, premise, level, label, pid, reason) -> dict:
    return {"statement": statement, "premise": premise, "level": level,
            "label": label, "evidence_paragraph_id": pid, "reason": reason}


# --------------------------------------------------------------------------
# OpenRouterBackend (real LLM stages, reusing the project's OpenRouter client)
# --------------------------------------------------------------------------

class OpenRouterBackend(MockBackend):
    """LLM backend that reuses ``citation_llm_service.build_llm`` (one client for
    the whole app). Inherits ``rerank`` from :class:`MockBackend` (cheap lexical
    pre-filter ahead of the LLM ``select``); overrides ``select``/``decompose``/
    ``judge`` to call the configured model with the strict-JSON prompts. Every
    overridden stage falls back to the mock heuristic if the model reply cannot be
    parsed or no API key is set, so the pipeline never crashes.
    """

    name = "openrouter"

    def __init__(self) -> None:
        self._llm = None

    def _model(self):
        if self._llm is None:
            from app.services.citation_llm_service import build_llm
            self._llm = build_llm()  # raises if OPENROUTER_API_KEY is missing
        return self._llm

    def _ask(self, prompt: str) -> dict:
        from langchain_core.messages import HumanMessage
        resp = self._model().invoke([HumanMessage(content=prompt)])
        return _loads_json(str(resp.content))

    def select(self, citation, scored, k):
        candidates = "\n".join(
            f"[{pid}] (score={s:.3f}) {txt}" for pid, txt, s in scored
        )
        try:
            data = self._ask(SELECT_PROMPT.format(citation=citation, k=k, candidates=candidates))
            ids = [i for i in data.get("r_top", []) if isinstance(i, int)][:k]
            if ids:
                return ids
        except Exception:  # noqa: BLE001 - degrade to the deterministic selector
            pass
        return super().select(citation, scored, k)

    def decompose(self, citation):
        try:
            data = self._ask(DECOMPOSE_PROMPT.format(citation=citation))
            statements = data.get("statements", [])
            if statements:
                return statements
        except Exception:  # noqa: BLE001
            pass
        return super().decompose(citation)

    def judge(self, citation, statements, r_top, following,
              tau_coverage: float = 0.34, global_summary: str = ""):
        r_top_s = "\n".join(f"[{p['id']}] {p['text']}" for p in r_top)
        following_s = "\n".join(f"[{p['id']}] {p['text']}" for p in following)
        try:
            data = self._ask(JUDGE_PROMPT.format(
                global_summary=global_summary or "(not provided)",
                citation=citation, statements_json=json.dumps(statements),
                r_top=r_top_s, following=following_s,
            ))
            if "evaluations" in data:
                return {
                    "evaluations": data.get("evaluations", []),
                    "plain_language_holding": data.get("plain_language_holding", ""),
                }
        except Exception:  # noqa: BLE001
            pass
        return super().judge(citation, statements, r_top, following, tau_coverage, global_summary)


def get_backend(name: str):
    return {"mock": MockBackend, "openrouter": OpenRouterBackend}[name]()
