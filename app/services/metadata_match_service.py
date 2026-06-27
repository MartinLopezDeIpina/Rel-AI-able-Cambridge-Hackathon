"""Citation existence + metadata-equality check (the metadata-match layer).

This is the middle tier of the citation-integrity pipeline. It runs *after*
extraction (``extract_enriched_citations`` produces the citing-side
:class:`EnrichedCitation` objects) and *before* the downstream semantic-
correctness / distortion check. For each citation it answers two questions:

  1. **Does the cited case actually exist?** Look it up in the sources database by
     its three identifying parameters — ``year + court + number`` — exact first,
     then with court-abbreviation fuzzing. If that misses, fall back to the
     existing semantic searcher (:mod:`app.services.resolver_service`) and use an
     LLM agent to confirm the candidate really is the cited case. If nothing
     confirms, the citation is flagged as hallucinated / non-existent.

  2. **Is it described faithfully?** Once a source is matched, every *non-null*
     citing-side attribute must equal the matched source's value. Disagreements
     are returned as :class:`FieldMismatch` flags. Attributes present only on the
     source side (citing value is null) are allowed and never flagged.

The citing :class:`EnrichedCitation` and the source metadata entries share the
same field names, so the comparison is a direct field-by-field one.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from app.core.config import Settings, get_settings
from app.schemas.citation import (
    EnrichedCitation,
    FieldMismatch,
    MetadataMatchResult,
)
from app.services import citelib

# Above this fuzzy score (0..100) two case names count as the same case despite
# abbreviations (Ltd/Limited, Co/Company, "v"/"v.", party-order noise).
NAME_MATCH_THRESHOLD = 80.0

# Court neutral-citation aliases. Keys/values are uppercased, division-stripped
# court codes; both directions are treated as equal during the triple match.
_COURT_ALIASES: dict[str, str] = {
    "HL": "UKHL",
    "HOUSE OF LORDS": "UKHL",
    "SC": "UKSC",
    "SUPREME COURT": "UKSC",
    "PC": "UKPC",
    "CA": "EWCA CIV",
    "EWCA": "EWCA CIV",
    "COURT OF APPEAL": "EWCA CIV",
    "HC": "EWHC",
    "HIGH COURT": "EWHC",
}


# --------------------------------------------------------------------------
# Loading the sources database
# --------------------------------------------------------------------------

def load_sources_metadata(path: str | Path | None = None) -> dict[str, dict]:
    """Load the sources metadata database, normalised to ``{identifier: meta}``.

    Tolerant of two on-disk shapes so it works whether the file is keyed by
    identifier or is a flat list:
      - a JSON object ``{"1": {...}, "2": {...}}`` (id- or filename-keyed), or
      - a JSON array ``[{"id": 1, ...}, ...]`` (each item carrying its own id).

    The identifier is preserved as a string key; each entry's metadata dict is
    returned unchanged (so its native field names line up with EnrichedCitation).
    """
    p = Path(path or get_settings().sources_metadata_path)
    if not p.is_file():
        raise FileNotFoundError(f"sources metadata not found: {p}")
    raw = json.loads(p.read_text(encoding="utf-8"))

    sources: dict[str, dict] = {}
    if isinstance(raw, dict):
        for key, meta in raw.items():
            if isinstance(meta, dict):
                sources[str(key)] = meta
    elif isinstance(raw, list):
        for i, meta in enumerate(raw, start=1):
            if isinstance(meta, dict):
                key = str(meta.get("id", meta.get("source", i)))
                sources[key] = meta
    return sources


def _filename_index(sources: dict[str, dict]) -> dict[str, str]:
    """Map a source *filename* to its identifier, for resolver bridging.

    The semantic resolver returns a ``chosen_source`` filename; the sources DB is
    keyed by identifier. Each entry's ``source`` field carries the filename, so we
    invert it here. Entries without a ``source`` simply do not appear (the caller
    then falls back to fuzzy filename matching).
    """
    index: dict[str, str] = {}
    for ident, meta in sources.items():
        src = meta.get("source")
        if isinstance(src, str) and src:
            index[src] = ident
    return index


# --------------------------------------------------------------------------
# Primary match: the three required params (year + court + number)
# --------------------------------------------------------------------------

def _norm_court(court: str | None) -> str | None:
    """Normalise a court code for equality: uppercase, strip bracketed divisions
    and punctuation, then apply the abbreviation alias map."""
    if not court:
        return None
    c = court.upper()
    # Drop a trailing/embedded division in parentheses, e.g. "EWHC (Comm)".
    c = c.split("(")[0]
    c = " ".join(ch for ch in c.replace(".", " ").split() if ch).strip()
    if not c:
        return None
    return _COURT_ALIASES.get(c, c)


def _courts_equal(a: str | None, b: str | None) -> bool:
    na, nb = _norm_court(a), _norm_court(b)
    if na is None or nb is None:
        return False
    return na == nb or _COURT_ALIASES.get(na, na) == _COURT_ALIASES.get(nb, nb)


def _match_required(cite: EnrichedCitation, sources: dict[str, dict]):
    """Find the source matching the citing ``year + court + number`` triple.

    Returns ``(identifier, "direct"|"fuzzy")`` or ``None``. ``direct`` requires an
    exact (case-insensitive) court match; ``fuzzy`` accepts the
    abbreviation-aliased court. Year and number must always match exactly (ints).
    A missing neutral ``number`` (law-report/nominate cites) makes the triple
    incomplete -> ``None`` -> caller routes to the semantic fallback.
    """
    if cite.number is None or cite.year is None:
        return None

    fuzzy_hit: str | None = None
    for ident, meta in sources.items():
        if meta.get("year") != cite.year or meta.get("number") != cite.number:
            continue
        s_court = meta.get("court")
        # Exact (case-insensitive) court match -> the strongest "direct" tier.
        if cite.court and s_court and cite.court.strip().upper() == s_court.strip().upper():
            return ident, "direct"
        # Otherwise an alias-equal court counts as a fuzzy match (e.g. HL vs UKHL).
        if _courts_equal(cite.court, s_court) and fuzzy_hit is None:
            fuzzy_hit = ident
    if fuzzy_hit is not None:
        return fuzzy_hit, "fuzzy"
    return None


# --------------------------------------------------------------------------
# Semantic fallback + LLM confirmation agent
# --------------------------------------------------------------------------

def _cite_string(cite: EnrichedCitation) -> str:
    """Resolver query string: best available case name plus the raw citation."""
    name = cite.full_case_name or cite.case_name or ""
    return f"{name} {cite.raw}".strip()


_AGENT_SYSTEM = """You are a UK legal citation verifier. You are given the \
identifying details of a case citation taken from a court document, and the \
metadata of a candidate source document retrieved from a legal database. Decide \
whether they refer to the SAME case. Compare on case name (allow abbreviations \
like Ltd/Limited, Co/Company and party-order differences), year, court, and \
citation number. Minor formatting differences are fine; a different case is not.

Respond with ONLY a JSON object: {"same_case": true|false, "reason": "<short>"}."""

_AGENT_HUMAN = """Citing document says:
- case_name: {c_name}
- year: {c_year}
- court: {c_court}
- number: {c_number}
- raw citation: {c_raw}

Candidate source metadata:
- case_name: {s_name}
- year: {s_year}
- court: {s_court}
- number: {s_number}
- raw citation: {s_raw}
- court_name: {s_court_name}

Do these refer to the same case?"""


def _parse_agent_json(content: str) -> dict:
    """Parse the agent reply, tolerating markdown fences / surrounding prose."""
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


def _confirm_same_case(cite: EnrichedCitation, meta: dict,
                       settings: Settings | None = None) -> tuple[bool | None, str]:
    """Ask the LLM agent whether ``meta`` is the same case as ``cite``.

    Returns ``(same_case, reason)``. ``same_case`` is ``None`` when the agent
    could not be reached (no credentials / repeated bad JSON) so the caller can
    mark the citation ``needs_review`` rather than wrongly declaring it fake.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.services.citation_llm_service import build_llm

    try:
        llm = build_llm(settings)
    except Exception as error:  # missing key / credentials -> can't confirm
        return None, f"verification agent unavailable: {error}"

    human = _AGENT_HUMAN.format(
        c_name=cite.full_case_name or cite.case_name, c_year=cite.year,
        c_court=cite.court, c_number=cite.number, c_raw=cite.raw,
        s_name=meta.get("case_name"), s_year=meta.get("year"),
        s_court=meta.get("court"), s_number=meta.get("number"),
        s_raw=meta.get("raw"), s_court_name=meta.get("court_name"),
    )
    messages = [SystemMessage(content=_AGENT_SYSTEM), HumanMessage(content=human)]
    for _ in range(2):
        try:
            response = llm.invoke(messages)
            data = _parse_agent_json(str(response.content))
            return bool(data.get("same_case")), str(data.get("reason", ""))
        except Exception:
            messages.append(HumanMessage(
                content='Reply with ONLY {"same_case": true|false, "reason": "..."}.'))
    return None, "verification agent did not return valid JSON"


def _norm_for_match(name: str) -> str:
    """Normalised case name for fuzzy matching, with runs of single-letter initials
    collapsed ("d c thomson" -> "dc thomson") so "DC Thomson" matches "D. C. Thomson"."""
    n = citelib.normalize_name(name)
    return re.sub(r"\b([a-z])\s+(?=[a-z]\b)", r"\1", n)


def _match_by_name_year(cite: EnrichedCitation, sources: dict[str, dict]):
    """Index-free fallback for cites without a neutral ``number`` (law-report /
    nominate): match directly against the sources DB on **year (±1) + fuzzy case
    name**. Returns ``(identifier, "name_year")`` or ``None``.

    The ±1-year tolerance absorbs report-year vs decision-year differences (e.g. a case
    decided in 1971 but reported in 1972). This is what makes the "check against the
    JSON" work standalone — no vector index — for authorities cited by name.
    """
    if cite.year is None:
        return None
    name = cite.full_case_name or cite.case_name
    if not name:
        return None
    from rapidfuzz import fuzz

    target = _norm_for_match(name)
    best, best_score = None, 0.0
    for ident, meta in sources.items():
        s_year = meta.get("year")
        if s_year is None or abs(int(s_year) - cite.year) > 1:
            continue
        score = fuzz.token_set_ratio(
            target, _norm_for_match(str(meta.get("case_name") or "")))
        if score > best_score:
            best, best_score = ident, score
    if best is not None and best_score >= NAME_MATCH_THRESHOLD:
        return best, "name_year"
    return None


def _semantic_confirm(cite: EnrichedCitation, sources: dict[str, dict],
                      fname_index: dict[str, str], resolver,
                      settings: Settings | None = None):
    """Fallback existence check: semantic resolve, then LLM-confirm the candidate.

    Returns ``(identifier, "semantic")`` when confirmed, or one of the sentinel
    tuples ``("__none__", reason)`` / ``("__review__", reason)`` for
    non-existent and unsure outcomes respectively.
    """
    try:
        res = resolver.resolve(_cite_string(cite))
    except Exception as error:  # noqa: BLE001 - no/broken vector index -> can't confirm
        return "__review__", f"semantic resolver unavailable: {error}"
    if res.get("needs_web"):
        return "__none__", "not found in the sources database (no confident match)"

    chosen = res.get("chosen_source")
    ident = fname_index.get(chosen) if chosen else None
    if ident is None and chosen:
        # The DB entry carries no `source` field (or a different filename) -> map
        # by fuzzy filename similarity against each entry's own source/identifier.
        best, best_score = None, 0.0
        for k, meta in sources.items():
            target = meta.get("source") or k
            score = citelib.name_match_score(chosen, target)
            if score > best_score:
                best, best_score = k, score
        if best is not None and best_score >= NAME_MATCH_THRESHOLD:
            ident = best
    if ident is None:
        return "__none__", "resolver candidate is not in the sources database"

    same, reason = _confirm_same_case(cite, sources[ident], settings)
    if same is True:
        return ident, "semantic"
    if same is None:
        return "__review__", reason or "could not confirm the candidate case"
    return "__none__", reason or "resolver candidate is a different case"


# --------------------------------------------------------------------------
# Other-attribute comparison (everything beyond the required triple)
# --------------------------------------------------------------------------

# Fields compared once a source is matched. year/court/number are excluded (the match
# established them); citation_type and raw are excluded too — a case has several valid
# citation formats (neutral vs law-report), so comparing them is noise, not a
# misrepresentation.
_COMPARE_FIELDS = ("case_name", "division", "reporter", "volume", "page")

# Law-report coordinates: when the source has no value (it recorded the case under a
# different citation system, e.g. a neutral cite), we can't contradict the document, so
# a null source here is skipped rather than flagged. (division stays compared — a null
# division on a no-division court genuinely contradicts a claimed one.)
_SKIP_IF_SOURCE_NULL = {"reporter", "volume", "page"}


def _coerce(value):
    """Unwrap enums (e.g. CitationType) to their underlying value for comparison."""
    return getattr(value, "value", value)


def _scalar_equal(field: str, citing, source) -> bool:
    if source is None:
        return False  # citing asserts a value the source does not have -> mismatch
    citing, source = _coerce(citing), _coerce(source)
    if field in ("case_name", "raw", "division", "reporter", "citation_type"):
        return citelib.normalize_name(str(citing)) == citelib.normalize_name(str(source))
    return str(citing).strip().lower() == str(source).strip().lower()


def _judges_mismatch(citing: list[str], source) -> list[str]:
    """Return citing judge names not found in the source's judge list.

    Matching is lenient: a citing judge counts as present if its normalised form is a
    substring of (or a close fuzzy match to) any source judge — so "Baroness Hale"
    matches "Baroness Hale of Richmond" and only genuinely absent judges are flagged.
    """
    from rapidfuzz import fuzz

    src_norm = [citelib.normalize_name(j) for j in (source or []) if j]
    missing = []
    for j in citing:
        if not j:
            continue
        cj = citelib.normalize_name(j)
        present = any(
            cj in s or s in cj or fuzz.token_set_ratio(cj, s) >= 88 for s in src_norm)
        if not present:
            missing.append(j)
    return missing


def _compare_fields(cite: EnrichedCitation, meta: dict) -> list[FieldMismatch]:
    """Flag every non-null citing attribute that disagrees with the source."""
    mismatches: list[FieldMismatch] = []

    # case_name is fuzzy (tolerates Ltd/Limited, Co/Company, "v"/"v.", initials). Use
    # the repaired full_case_name when available — the regex case_name is often a
    # truncated fragment that would misfire here.
    citing_name = cite.full_case_name or cite.case_name
    if citing_name:
        from rapidfuzz import fuzz
        s_name = meta.get("case_name")
        score = fuzz.token_set_ratio(
            _norm_for_match(citing_name), _norm_for_match(str(s_name or "")))
        if not s_name or score < NAME_MATCH_THRESHOLD:
            mismatches.append(FieldMismatch(
                field="case_name", citing_value=citing_name, source_value=s_name))

    for field in _COMPARE_FIELDS:
        if field == "case_name":
            continue
        citing_value = getattr(cite, field, None)
        if citing_value is None:
            continue
        source_value = meta.get(field)
        if source_value is None and field in _SKIP_IF_SOURCE_NULL:
            continue  # source used a different citation system -> can't contradict
        if not _scalar_equal(field, citing_value, source_value):
            mismatches.append(FieldMismatch(
                field=field, citing_value=citing_value, source_value=source_value))

    if cite.judges:
        missing = _judges_mismatch(cite.judges, meta.get("judges"))
        if missing:
            mismatches.append(FieldMismatch(
                field="judges", citing_value=missing, source_value=meta.get("judges")))

    return mismatches


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def verify_one(cite: EnrichedCitation, sources: dict[str, dict],
               fname_index: dict[str, str], resolver,
               settings: Settings | None = None) -> MetadataMatchResult:
    """Existence + metadata-equality verdict for a single citation.

    Match tiers, in order: (1) the neutral ``year+court+number`` triple; (2) an
    index-free ``year + fuzzy name`` match against the JSON; (3) the semantic resolver
    (only if one was supplied and a vector index exists). The first two need only the
    JSON DB, so the check works without an index.
    """
    primary = _match_required(cite, sources)
    if primary is not None:
        ident, method = primary
    else:
        name_year = _match_by_name_year(cite, sources)
        if name_year is not None:
            ident, method = name_year
        elif resolver is not None:
            ident, method = _semantic_confirm(cite, sources, fname_index, resolver, settings)
        else:
            ident, method = "__none__", "not found in the sources database (no metadata match)"

    if ident == "__none__":
        return MetadataMatchResult(
            id=cite.id, exists=False, match_method=None,
            used_semantic_fallback=False, required_params_matched=False,
            reason=method or "case does not appear to exist",
        )
    if ident == "__review__":
        return MetadataMatchResult(
            id=cite.id, exists=False, match_method=None,
            used_semantic_fallback=True, required_params_matched=False,
            needs_review=True, reason=method or "existence could not be confirmed",
        )

    # Confirmed to exist: compare every other citing attribute against the source.
    meta = sources[ident]
    mismatches = _compare_fields(cite, meta)
    if mismatches:
        flagged = ", ".join(m.field for m in mismatches)
        reason = f"case exists; metadata mismatch on: {flagged}"
    else:
        reason = "case exists and metadata matches the source"
    return MetadataMatchResult(
        id=cite.id, exists=True, matched_source=ident, match_method=method,
        used_semantic_fallback=(method == "semantic"),
        required_params_matched=method in ("direct", "fuzzy"),
        field_mismatches=mismatches, reason=reason,
    )


def verify_citations_metadata(
    enriched: list[EnrichedCitation],
    sources: dict[str, dict] | None = None,
    resolver=None,
    settings: Settings | None = None,
) -> list[MetadataMatchResult]:
    """Run the metadata-match check over a list of enriched citations."""
    settings = settings or get_settings()
    sources = sources if sources is not None else load_sources_metadata()
    fname_index = _filename_index(sources)
    # The resolver (semantic, needs a vector index) is an OPTIONAL deepest fallback; by
    # default we run JSON-only (triple + name+year). Pass a resolver to enable it.
    return [verify_one(c, sources, fname_index, resolver, settings) for c in enriched]


def run_metadata_verification(pdf_path: str | Path) -> list[MetadataMatchResult]:
    """End-to-end: extract enriched citations from ``pdf_path`` then verify them."""
    from app.services.citation_llm_service import extract_enriched_citations

    enriched = extract_enriched_citations(pdf_path)
    return verify_citations_metadata(enriched)


class MetadataMatchService:
    """Loads the sources database once and verifies citations against it.

    Mirrors the DI style of the other services. The database and resolver are
    loaded lazily on first use so app startup never blocks.
    """

    def __init__(self, sources_path: str | Path | None = None) -> None:
        self._settings = get_settings()
        self._sources_path = sources_path
        self._sources: dict[str, dict] | None = None
        self._fname_index: dict[str, str] | None = None
        self._resolver = None

    def _ensure_loaded(self) -> None:
        if self._sources is None:
            self._sources = load_sources_metadata(self._sources_path)
            self._fname_index = _filename_index(self._sources)
        if self._resolver is None:
            from app.services.resolver_service import get_resolver_service
            self._resolver = get_resolver_service()

    def verify(self, enriched: list[EnrichedCitation]) -> list[MetadataMatchResult]:
        self._ensure_loaded()
        return [verify_one(c, self._sources, self._fname_index, self._resolver,
                           self._settings) for c in enriched]

    def verify_pdf(self, pdf_path: str | Path) -> list[MetadataMatchResult]:
        from app.services.citation_llm_service import extract_enriched_citations

        return self.verify(extract_enriched_citations(pdf_path))


_service: MetadataMatchService | None = None


def get_metadata_match_service() -> MetadataMatchService:
    global _service
    if _service is None:
        _service = MetadataMatchService()
    return _service


# --------------------------------------------------------------------------
# CLI: uploaded document -> extract citations -> check against the JSON DB
# --------------------------------------------------------------------------

def _verdict(r: MetadataMatchResult) -> str:
    if r.exists:
        return "EXISTS" if not r.field_mismatches else "EXISTS (metadata mismatch)"
    return "NEEDS REVIEW" if r.needs_review else "DOES NOT EXIST"


def run_report(pdf_path: str | Path) -> dict:
    """Full pipeline for one document: extract enriched citations, verify each against
    the sources DB, print a partner-readable report, and return the structured result."""
    from app.services.citation_llm_service import extract_enriched_citations

    enriched = extract_enriched_citations(pdf_path)
    results = verify_citations_metadata(enriched)
    by_id = {r.id: r for r in results}

    print(f"\nCitation integrity report — {pdf_path}", file=sys.stderr)
    print(f"{len(enriched)} citation(s) checked against the sources database\n"
          + "=" * 72, file=sys.stderr)
    counts = {"exist": 0, "mismatch": 0, "review": 0, "none": 0}
    for c in enriched:
        r = by_id[c.id]
        if r.exists:
            counts["exist"] += 1
            counts["mismatch"] += bool(r.field_mismatches)
        elif r.needs_review:
            counts["review"] += 1
        else:
            counts["none"] += 1
        name = c.full_case_name or c.case_name or "(name not extracted)"
        matched = f"  [matched {r.matched_source} via {r.match_method}]" if r.exists else ""
        print(f"\n[{c.id}] {name}  {c.raw or ''}", file=sys.stderr)
        print(f"     {_verdict(r)}{matched}", file=sys.stderr)
        for m in r.field_mismatches:
            print(f"       ! {m.field}: document={m.citing_value!r} "
                  f"vs source={m.source_value!r}", file=sys.stderr)
        if r.reason:
            print(f"     {r.reason}", file=sys.stderr)

    print("\n" + "=" * 72, file=sys.stderr)
    print(f"Summary: {counts['exist']} exist "
          f"({counts['mismatch']} with metadata mismatches), "
          f"{counts['none']} do not exist, {counts['review']} need review.",
          file=sys.stderr)

    report = {"document": str(pdf_path),
              "citations": [{**c.model_dump(), "verification": by_id[c.id].model_dump()}
                            for c in enriched]}
    return report


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    pdf_path = Path(argv[0]) if argv else Path("case_demo.pdf")
    out_path = Path(argv[1]) if len(argv) > 1 else Path("data/citation_report.json")

    if not Path(pdf_path).is_file():
        print(f"Error: document not found: {pdf_path}", file=sys.stderr)
        return 2
    try:
        report = run_report(pdf_path)
    except Exception as exc:  # noqa: BLE001 - surface a clean CLI error
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nJSON report -> {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
