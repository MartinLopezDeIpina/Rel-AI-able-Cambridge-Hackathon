"""Data-type contracts + the set of cases each pipeline step can land in.

Two jobs:
  1. `assert_*` validators check the *shape* (keys + types) of each step's I/O, so a
     test can pin the contract independently of the values.
  2. The `*_CASES` enums enumerate every state a step can resolve to, each with the
     expected externally-observable behaviour. Tests reference these so "every case a
     step could land in" is covered explicitly.

Narrative version: documentation/Sprint3/contracts.md.
"""
from __future__ import annotations

from enum import Enum


def _is(value, types) -> bool:
    return isinstance(value, types)


# ==========================================================================
# STEP 1 — citing-side extraction / enrichment
# ==========================================================================
CITATION_KEYS = {  # app.schemas.citation.Citation (required-ish fields)
    "id": int, "raw": str, "year": int,
}
ENRICHED_EXTRA_KEYS = {  # added by CitationMetadata (nullable)
    "full_case_name": (str, type(None)),
    "proposition": (str, type(None)),
    "ground": (str, type(None)),
    "relevant_text": (str, type(None)),
}


def assert_citation(obj) -> None:
    d = obj.model_dump() if hasattr(obj, "model_dump") else obj
    for k, t in CITATION_KEYS.items():
        assert k in d, f"citation missing {k}"
        assert _is(d[k], t), f"citation.{k} should be {t}, got {type(d[k])}"
    assert d["id"] >= 1, "citation id is 1-based"


class Step1Case(str, Enum):
    NEUTRAL = "neutral_citation"          # [2007] UKHL 21  -> type=neutral
    LAW_REPORT = "law_report_citation"    # [1972] 1 QB 60  -> type=law_report
    NOMINATE = "nominate_citation"        # (1853) 2 E&B 216 -> type=nominate
    WITH_CASE_NAME = "preceding_case_name"  # "X v Y [..]" -> case_name captured
    NONE_FOUND = "no_citation_in_text"    # plain prose -> [] (empty list)
    DUPLICATE = "duplicate_raw"           # same raw twice -> deduped to one


# ==========================================================================
# STEP 3 — resolution / existence (resolver_service.resolve_one returns a dict)
# ==========================================================================
RESOLVER_KEYS = {
    "citation": str, "chosen_source": str, "method": str, "confidence": float,
    "uncertain": bool, "needs_web": bool, "used_semantic_fallback": bool,
    "signals_agree": bool, "name_top": dict, "semantic_top": dict,
    "name_ranking": list, "semantic_ranking": list,
}


def assert_resolver_result(d: dict) -> None:
    for k, t in RESOLVER_KEYS.items():
        assert k in d, f"resolver result missing {k}"
        assert _is(d[k], t), f"resolver.{k} should be {t}, got {type(d[k])}"
    assert d["method"] in ("name", "semantic"), d["method"]
    assert 0.0 <= d["confidence"] <= 1.0, d["confidence"]


class Step3Case(str, Enum):
    NAME_HIT = "name_hit_wins"             # fuzzy>=75 -> method=name, needs_web=False
    SEMANTIC_HIT = "semantic_fallback"     # name<75, sem>=0.5 -> method=semantic, used_semantic_fallback=True
    NEEDS_WEB = "not_in_corpus"            # name<75 AND sem<0.5 -> needs_web=True (FABRICATED candidate)
    SIGNALS_AGREE = "name_and_semantic_agree"  # name confident AND name_src==sem_src


# ==========================================================================
# STEP 4 — faithfulness detector (distortion_service.analyze -> report dict)
# ==========================================================================
ANALYSIS_KEYS = {
    "relevant_text": str, "classification": str,
    "mischaracterised_pct": float, "out_of_context_pct": float,
    "plain_language_holding": str, "evaluations": list,
}
DETECTOR_CLASSES = {"correct", "mischaracterised", "out_of_context"}


def assert_analysis_report(d: dict) -> None:
    for k, t in ANALYSIS_KEYS.items():
        assert k in d, f"analysis report missing {k}"
        assert _is(d[k], t), f"report.{k} should be {t}, got {type(d[k])}"
    assert d["classification"] in DETECTOR_CLASSES, d["classification"]
    for axis in ("mischaracterised_pct", "out_of_context_pct"):
        assert 0.0 <= d[axis] <= 100.0, f"{axis}={d[axis]}"


class Step4Case(str, Enum):
    CORRECT = "faithful_correct"           # both axes < TAU_LOW -> correct
    MISCHARACTERISED = "violated_misrepresentation"  # VIOLATED dominates -> mischaracterised
    OUT_OF_CONTEXT = "unaddressed_off_topic"         # UNADDRESSED dominates -> out_of_context
    EMPTY_SOURCE = "empty_source"          # no source text -> out_of_context, 100%


# ==========================================================================
# STEP 5 — final per-citation verdict (the frontend contract)
# ==========================================================================
# user-facing buckets (app.schemas.citation.ClassificationType)
VERDICTS = {
    "EXISTS_CORRECTLY_APPLIED",
    "EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT",
    "DOESNT_EXIST",
}

# Target JSON the UI consumes (blueprint). NOTE: the endpoint that produces this does
# not exist yet — Step 5 tests assert this contract as XFAIL until it's built.
VERIFY_RESPONSE_KEYS = {
    "citation_name": str, "status": str, "confidence_score": float,
    "associate_claim": str, "actual_holding": str, "explanation": str,
}


def assert_verify_response(d: dict) -> None:
    for k, t in VERIFY_RESPONSE_KEYS.items():
        assert k in d, f"verify response missing {k}"
        assert _is(d[k], t), f"verify.{k} should be {t}, got {type(d[k])}"
    assert 0.0 <= d["confidence_score"] <= 1.0, d["confidence_score"]


class Step5Case(str, Enum):
    VERIFIED = "verified"                  # exists + correct
    MISCHARACTERISED = "mischaracterised"  # exists + wrong context
    FABRICATED = "fabricated"              # M3 needs_web -> DOESNT_EXIST, confidence 0, skip detector
    NEEDS_REVIEW = "needs_review"          # couldn't confirm; needs_review=True
