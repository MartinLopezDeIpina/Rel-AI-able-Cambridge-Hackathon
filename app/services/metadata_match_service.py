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


def _semantic_confirm(cite: EnrichedCitation, sources: dict[str, dict],
                      fname_index: dict[str, str], resolver,
                      settings: Settings | None = None):
    """Fallback existence check: semantic resolve, then LLM-confirm the candidate.

    Returns ``(identifier, "semantic")`` when confirmed, or one of the sentinel
    tuples ``("__none__", reason)`` / ``("__review__", reason)`` for
    non-existent and unsure outcomes respectively.
    """
    res = resolver.resolve(_cite_string(cite))
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

# Fields compared once a source is matched. year/court/number are excluded
# because the triple match already established them.
_COMPARE_FIELDS = (
    "case_name", "division", "reporter", "volume", "page", "citation_type", "raw",
)


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
    """Return citing judge names not found in the source's judge list."""
    src_norm = {citelib.normalize_name(j) for j in (source or []) if j}
    missing = []
    for j in citing:
        if not j:
            continue
        if citelib.normalize_name(j) not in src_norm:
            missing.append(j)
    return missing


def _compare_fields(cite: EnrichedCitation, meta: dict) -> list[FieldMismatch]:
    """Flag every non-null citing attribute that disagrees with the source."""
    mismatches: list[FieldMismatch] = []

    # case_name is fuzzy (tolerates Ltd/Limited, Co/Company, "v"/"v.").
    if cite.case_name:
        from rapidfuzz import fuzz
        s_name = meta.get("case_name")
        score = fuzz.token_set_ratio(
            citelib.normalize_name(cite.case_name),
            citelib.normalize_name(str(s_name or "")),
        )
        if not s_name or score < NAME_MATCH_THRESHOLD:
            mismatches.append(FieldMismatch(
                field="case_name", citing_value=cite.case_name, source_value=s_name))

    for field in _COMPARE_FIELDS:
        if field == "case_name":
            continue
        citing_value = getattr(cite, field, None)
        if citing_value is None:
            continue
        source_value = meta.get(field)
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
    """Existence + metadata-equality verdict for a single citation."""
    primary = _match_required(cite, sources)
    used_semantic = False

    if primary is not None:
        ident, method = primary
    else:
        ident, method = _semantic_confirm(cite, sources, fname_index, resolver, settings)
        used_semantic = True

    if ident == "__none__":
        return MetadataMatchResult(
            id=cite.id, exists=False, match_method=None,
            used_semantic_fallback=used_semantic, required_params_matched=False,
            reason=method or "case does not appear to exist",
        )
    if ident == "__review__":
        return MetadataMatchResult(
            id=cite.id, exists=False, match_method=None,
            used_semantic_fallback=used_semantic, required_params_matched=False,
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
        required_params_matched=True, field_mismatches=mismatches, reason=reason,
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
    if resolver is None:
        from app.services.resolver_service import get_resolver_service
        resolver = get_resolver_service()
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
