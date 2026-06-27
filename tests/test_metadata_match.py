"""Tests for the metadata-match layer (app/services/metadata_match_service).

All offline: the semantic resolver is a stub and the LLM confirmation agent is
monkeypatched, so no embeddings/credentials are needed.
"""

import json
from types import SimpleNamespace

import pytest

from app.schemas.citation import EnrichedCitation, MetadataMatchResult
from app.services import metadata_match_service as mm


# --------------------------------------------------------------------------
# Fixtures / helpers
# --------------------------------------------------------------------------

def cite(**kw) -> EnrichedCitation:
    """Build an EnrichedCitation with sensible defaults for the required fields."""
    base = dict(
        id=1, raw="[2007] UKHL 21", case_name="OBG Ltd v Allan", year=2007,
        court="UKHL", division=None, reporter=None, volume=None, number=21,
        page=None, citation_type="neutral",
    )
    base.update(kw)
    return EnrichedCitation(**base)


SOURCES = {
    "1": {
        "case_name": "OBG Ltd v Allan", "year": 2007, "court": "UKHL",
        "division": None, "reporter": "AC", "volume": 1, "number": 21,
        "page": 1, "citation_type": "neutral", "raw": "[2007] UKHL 21",
        "court_name": "House of Lords", "judges": ["Lord Hoffmann", "Lord Nicholls"],
        "source": "obg-ltd-v-allan.pdf",
    },
    "2": {
        "case_name": "Hadley v Baxendale", "year": 1854, "court": "EWHC",
        "division": "Exch", "reporter": "Ex", "volume": 9, "number": 70,
        "page": 341, "citation_type": "neutral", "raw": "[1854] EWHC Exch J70",
        "court_name": "Court of Exchequer", "judges": ["Alderson B"],
        "source": "hadley-v-baxendale.pdf",
    },
}


class FakeResolver:
    def __init__(self, result):
        self.result = result

    def resolve(self, _query):
        return self.result


def fake_llm(reply: dict):
    obj = SimpleNamespace(content=json.dumps(reply))
    return SimpleNamespace(invoke=lambda _messages: obj)


def patch_llm(monkeypatch, reply: dict):
    monkeypatch.setattr(
        "app.services.citation_llm_service.build_llm",
        lambda settings=None: fake_llm(reply),
    )


def index():
    return mm._filename_index(SOURCES)


# --------------------------------------------------------------------------
# Primary triple match
# --------------------------------------------------------------------------

def test_direct_match_exists_no_mismatch():
    c = cite(reporter="AC", volume=1, page=1)  # all match source 1
    res = mm.verify_one(c, SOURCES, index(), resolver=None)
    assert isinstance(res, MetadataMatchResult)
    assert res.exists is True
    assert res.match_method == "direct"
    assert res.required_params_matched is True
    assert res.used_semantic_fallback is False
    assert res.field_mismatches == []


def test_fuzzy_court_abbreviation_match():
    c = cite(court="HL")  # HL is an alias of UKHL -> fuzzy, not direct
    res = mm.verify_one(c, SOURCES, index(), resolver=None)
    assert res.exists is True
    assert res.match_method == "fuzzy"
    assert res.matched_source == "1"


def test_field_mismatch_is_flagged():
    # Right case (triple matches source 1) but the document mislabels the reporter
    # and invents a division -> both must be flagged; case still exists.
    c = cite(reporter="QB", division="Comm")
    res = mm.verify_one(c, SOURCES, index(), resolver=None)
    assert res.exists is True
    flagged = {m.field for m in res.field_mismatches}
    assert "reporter" in flagged
    assert "division" in flagged


def test_wrong_case_name_flagged_even_when_triple_matches():
    c = cite(case_name="Totally Different v Party")
    res = mm.verify_one(c, SOURCES, index(), resolver=None)
    assert res.exists is True
    assert any(m.field == "case_name" for m in res.field_mismatches)


def test_judges_not_in_source_flagged():
    c = cite(judges=["Lord Hoffmann", "Lord Madeup"])
    res = mm.verify_one(c, SOURCES, index(), resolver=None)
    mismatch = [m for m in res.field_mismatches if m.field == "judges"]
    assert mismatch and "Lord Madeup" in mismatch[0].citing_value
    assert "Lord Hoffmann" not in mismatch[0].citing_value  # present in source


# --------------------------------------------------------------------------
# Semantic fallback + LLM confirmation agent
# --------------------------------------------------------------------------

def test_missing_number_routes_to_semantic_and_confirms(monkeypatch):
    patch_llm(monkeypatch, {"same_case": True, "reason": "same case"})
    resolver = FakeResolver({"chosen_source": "obg-ltd-v-allan.pdf", "needs_web": False})
    # year 2010 is >1 from any SOURCES year, so the index-free name+year tier misses and the
    # citation falls through to the semantic resolver.
    c = cite(year=2010, number=None, citation_type="law_report", raw="[2010] 1 AC 1")
    res = mm.verify_one(c, SOURCES, index(), resolver=resolver)
    assert res.exists is True
    assert res.match_method == "semantic"
    assert res.used_semantic_fallback is True
    assert res.matched_source == "1"


def test_name_year_fallback_matches_without_resolver():
    # No neutral number and no resolver: the case name + year alone resolve it against
    # the JSON DB (the index-free fallback that makes the check standalone).
    c = cite(case_name="OBG Limited v Allan", number=None, citation_type="law_report",
             raw="[2007] 1 AC 1")
    res = mm.verify_one(c, SOURCES, index(), resolver=None)
    assert res.exists is True
    assert res.match_method == "name_year"
    assert res.matched_source == "1"
    assert res.used_semantic_fallback is False


def test_needs_web_is_non_existent(monkeypatch):
    patch_llm(monkeypatch, {"same_case": True})  # never reached
    resolver = FakeResolver({"chosen_source": None, "needs_web": True})
    c = cite(case_name="Fakecase v Nobody", number=None, raw="[2099] UKSC 999")
    res = mm.verify_one(c, SOURCES, index(), resolver=resolver)
    assert res.exists is False
    assert res.needs_review is False
    assert "not found" in res.reason


def test_agent_rejects_candidate_is_non_existent(monkeypatch):
    patch_llm(monkeypatch, {"same_case": False, "reason": "different case"})
    resolver = FakeResolver({"chosen_source": "obg-ltd-v-allan.pdf", "needs_web": False})
    c = cite(case_name="Imposter v Sham", number=None, raw="[2010] UKHL 5")
    res = mm.verify_one(c, SOURCES, index(), resolver=resolver)
    assert res.exists is False
    assert res.matched_source is None


def test_agent_unavailable_sets_needs_review(monkeypatch):
    def boom(settings=None):
        raise RuntimeError("no credentials")
    monkeypatch.setattr("app.services.citation_llm_service.build_llm", boom)
    resolver = FakeResolver({"chosen_source": "obg-ltd-v-allan.pdf", "needs_web": False})
    # year 2010 (>1 from any source) -> skip the name+year tier and reach the agent.
    c = cite(year=2010, number=None, raw="[2010] AC 1")
    res = mm.verify_one(c, SOURCES, index(), resolver=resolver)
    assert res.exists is False
    assert res.needs_review is True


# --------------------------------------------------------------------------
# Loader normalisation
# --------------------------------------------------------------------------

def test_loader_dict_shape(tmp_path):
    p = tmp_path / "sources.json"
    p.write_text(json.dumps(SOURCES), encoding="utf-8")
    loaded = mm.load_sources_metadata(p)
    assert set(loaded) == {"1", "2"}
    assert loaded["1"]["case_name"] == "OBG Ltd v Allan"


def test_loader_list_shape(tmp_path):
    rows = [
        {"id": 1, "case_name": "A v B", "year": 2000, "court": "UKHL", "number": 1},
        {"id": 2, "case_name": "C v D", "year": 2001, "court": "EWHC", "number": 2},
    ]
    p = tmp_path / "sources_list.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    loaded = mm.load_sources_metadata(p)
    assert set(loaded) == {"1", "2"}
    assert loaded["2"]["case_name"] == "C v D"


def test_loader_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        mm.load_sources_metadata(tmp_path / "nope.json")


# --------------------------------------------------------------------------
# Court normalisation unit
# --------------------------------------------------------------------------

def test_norm_court_aliases_and_divisions():
    assert mm._norm_court("HL") == "UKHL"
    assert mm._norm_court("EWHC (Comm)") == "EWHC"
    assert mm._courts_equal("HL", "UKHL")
    assert mm._courts_equal("EWHC (Ch)", "EWHC")
    assert not mm._courts_equal("UKHL", "EWCA Civ")
