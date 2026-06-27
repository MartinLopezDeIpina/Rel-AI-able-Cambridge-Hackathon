"""Tests for the integrated citation-integrity pipeline (app/pipeline) and the
new schemas (app/schemas/citation).

These cover the parts that are actually implemented today: the deterministic
MockBackend, the detector's scoring + classification thresholds, the
``analyze`` tuple/``id`` contract, the ``relevant_text`` mapping helpers, the
schema round-trips, and the OpenRouter backend's graceful offline fallback.

The OpenRouter LLM path itself is not exercised (needs OPENROUTER_API_KEY); we
only assert it degrades to the mock heuristic instead of crashing when no key is
present.
"""

from types import SimpleNamespace

from app.services.distortion_backend import get_backend
from app.services.distortion_service import (
    analyze,
    analyze_relevant_texts,
    build_relevant_text_map,
    chunk_paragraphs,
    score,
)
from app.schemas.citation import (
    AnalysisDict,
    Classification,
    ClassificationType,
)

# A short source "judgment" with a clear qualifier ("provided that ...").
SOURCE = (
    "The court held that damages for lost profits are recoverable provided that "
    "the loss was within the reasonable contemplation of the parties at the time "
    "of contracting. This is the established measure of expectation damages."
)


def mock():
    return get_backend("mock")


# --------------------------------------------------------------------------
# analyze() contract: (report, id) tuple + id passthrough
# --------------------------------------------------------------------------

def test_analyze_returns_report_and_id_tuple():
    result = analyze("Damages for lost profits are recoverable.", SOURCE, mock(), id=42)
    assert isinstance(result, tuple) and len(result) == 2
    report, returned_id = result
    assert returned_id == 42                       # id is passed through unprocessed
    assert isinstance(report, dict)
    for key in ("classification", "mischaracterised_pct", "out_of_context_pct",
                "plain_language_holding", "evaluations"):
        assert key in report


def test_analyze_id_defaults_to_none():
    _report, returned_id = analyze("Some claim.", SOURCE, mock())
    assert returned_id is None


def test_analyze_empty_source_is_out_of_context():
    report, _ = analyze("Any claim at all.", "", mock(), id=1)
    assert report["classification"] == "out_of_context"
    assert report["out_of_context_pct"] == 100.0


# --------------------------------------------------------------------------
# Detector classification behaviour (MockBackend heuristics)
# --------------------------------------------------------------------------

def test_faithful_claim_classified_correct():
    # Preserves the source's "provided that ... contemplation" qualifier verbatim,
    # so the charity judge finds no violation -> correct.
    claim = ("Damages for lost profits are recoverable provided that the loss was "
             "within the reasonable contemplation of the parties.")
    report, _ = analyze(claim, SOURCE, mock())
    assert report["classification"] == "correct"


def test_dropped_qualifier_is_mischaracterised():
    # Drops the "provided that ... contemplation" condition -> overstates the rule.
    claim = "Damages for lost profits are always recoverable."
    report, _ = analyze(claim, SOURCE, mock())
    assert report["classification"] == "mischaracterised"
    assert report["mischaracterised_pct"] > 0


def test_foreign_claim_is_out_of_context():
    claim = "The defendant must register the trademark before exporting goods overseas."
    report, _ = analyze(claim, SOURCE, mock())
    assert report["classification"] == "out_of_context"


# --------------------------------------------------------------------------
# score(): threshold logic in isolation
# --------------------------------------------------------------------------

def test_score_empty_is_correct():
    assert score([]) == (0.0, 0.0, "correct")


def test_score_violations_drive_mischaracterised():
    evals = [
        {"level": "macro", "label": "SATISFIED"},
        {"level": "macro", "label": "VIOLATED"},
        {"level": "meso", "label": "VIOLATED"},
    ]
    mischar, ooc, cls = score(evals)
    assert cls == "mischaracterised"
    assert mischar > ooc


def test_score_unaddressed_drives_out_of_context():
    evals = [
        {"level": "macro", "label": "UNADDRESSED"},
        {"level": "macro", "label": "UNADDRESSED"},
        {"level": "macro", "label": "SATISFIED"},
    ]
    _mischar, ooc, cls = score(evals)
    assert cls == "out_of_context"
    assert ooc > 0


# --------------------------------------------------------------------------
# relevant_text mapping helpers
# --------------------------------------------------------------------------

def test_build_relevant_text_map_from_dicts():
    rows = [{"id": 1, "relevant_text": "alpha"}, {"id": 2, "relevant_text": "beta"}]
    assert build_relevant_text_map(rows) == {1: "alpha", 2: "beta"}


def test_build_relevant_text_map_from_objects():
    rows = [SimpleNamespace(id=7, relevant_text="gamma"),
            SimpleNamespace(id=8, relevant_text=None)]
    # None relevant_text normalises to empty string; ids without value are skipped.
    assert build_relevant_text_map(rows) == {7: "gamma", 8: ""}


def test_analyze_relevant_texts_batches_and_preserves_ids():
    rt_map = {1: "Damages are always recoverable.",
              2: "Damages are recoverable if within contemplation."}
    out = analyze_relevant_texts(rt_map, source_for=lambda _id: SOURCE, backend=mock())
    ids = sorted(returned_id for _report, returned_id in out)
    assert ids == [1, 2]
    assert all(isinstance(rep, dict) for rep, _ in out)


# --------------------------------------------------------------------------
# chunk_paragraphs
# --------------------------------------------------------------------------

def test_chunk_paragraphs_windows():
    text = " ".join(str(i) for i in range(130))
    chunks = chunk_paragraphs(text, size=60, overlap=0)
    assert len(chunks) == 3                 # 60 + 60 + 10
    assert chunks[0].split()[0] == "0"
    assert chunks[1].split()[0] == "60"


def test_chunk_paragraphs_empty():
    assert chunk_paragraphs("") == []


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

def test_classification_enum_values():
    assert {c.value for c in ClassificationType} == {
        "EXISTS_CORRECTLY_APPLIED",
        "EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT",
        "DOESNT_EXIST",
    }


def test_classification_model_defaults():
    c = Classification(type=ClassificationType.DOESNT_EXIST)
    assert c.needs_review is False
    assert c.used_semantic_fallback is False
    assert c.confidence is None


def test_analysis_dict_mirrors_report():
    report, _ = analyze("Damages are always recoverable.", SOURCE, mock())
    ad = AnalysisDict(**{k: report[k] for k in (
        "classification", "mischaracterised_pct", "out_of_context_pct",
        "plain_language_holding", "evaluations")})
    assert ad.classification == report["classification"]
    assert isinstance(ad.evaluations, list)


# --------------------------------------------------------------------------
# Backends
# --------------------------------------------------------------------------

def test_get_backend_mock_and_openrouter():
    assert get_backend("mock").name == "mock"
    assert get_backend("openrouter").name == "openrouter"


def test_openrouter_select_falls_back_without_key(monkeypatch):
    # With no API key, the OpenRouter stages must degrade to the mock heuristic
    # rather than raise, so the pipeline still returns a result offline.
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    backend = get_backend("openrouter")
    scored = [(0, "para zero", 0.9), (1, "para one", 0.5)]
    selected = backend.select("a claim", scored, k=1)
    assert selected == [0]                   # same as MockBackend.select
    statements = backend.decompose("a claim about damages.")
    assert statements and "premises" in statements[0]
