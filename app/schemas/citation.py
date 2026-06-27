from enum import Enum

from pydantic import BaseModel


class CitationType(str, Enum):
    neutral = "neutral"  # court-assigned, e.g. [2007] UKHL 21
    law_report = "law_report"  # modern series report, e.g. [1952] Ch 646
    nominate = "nominate"  # old round-bracket report, e.g. (1853) 2 E&B 216


class Citation(BaseModel):
    id: int  # 1-based, in document order; anchors LLM enrichment back to this cite
    raw: str  # full matched text, e.g. "[2007] UKHL 21"
    case_name: str | None = None  # e.g. "OBG Ltd v Allan" (None if not found)
    year: int  # 2007
    court: str | None = None  # neutral court code: UKHL, EWHC, EWCA Civ ...
    division: str | None = None  # bracketed division for EWHC: Comm, Ch, TCC ...
    reporter: str | None = None  # law-report series: Ch, QB, AC, WLR, All ER ...
    volume: int | None = None  # optional volume, e.g. 1 in "[1972] 1 QB 60"
    number: int | None = None  # neutral case number, e.g. 21
    page: int | None = None  # law-report page, e.g. 646
    citation_type: CitationType


class CitationMetadata(BaseModel):
    """LLM-filled metadata for one anchored citation, keyed by ``id``."""

    id: int  # matches Citation.id
    full_case_name: str | None = None  # repaired full name
    court_name: str | None = None  # inferred court, e.g. "House of Lords"
    judges: list[str] = []  # e.g. ["Lord Hoffmann"]
    proposition: str | None = None  # what the case is cited for
    ground: str | None = None  # "Ground 1/2/3" from the Citation Index table
    # the document's OWN words on how the cite is used (quoted/closely paraphrased)
    relevant_text: str | None = None


class CitationExtraction(BaseModel):
    """Root container for structured LLM output (one item per anchored cite)."""

    items: list[CitationMetadata]


class EnrichedCitation(Citation, CitationMetadata):
    """A regex :class:`Citation` merged with its LLM :class:`CitationMetadata`.

    ``id`` is shared by both parents and reconciles the two halves.
    """


class FieldMismatch(BaseModel):
    """One citing-side attribute whose value disagrees with the matched source.

    Only fields present (non-null) on the citing side are ever compared, so a
    mismatch always means the document asserts something the real authority does
    not — the partner should be alerted. Source-only fields are not flagged.
    """

    field: str  # the attribute name, e.g. "reporter", "division", "case_name"
    citing_value: object | None = None  # value as written in the citing document
    source_value: object | None = None  # value from the matched source metadata


class MetadataMatchResult(BaseModel):
    """Existence + metadata-equality verdict for one citation, produced by the
    metadata-match layer that sits between extraction and the faithfulness check.

    ``exists`` answers "is this a real case we could confirm?"; ``field_mismatches``
    answers "does the document describe it with the real authority's metadata?".
    Neither is the final user-facing verdict — that merges with the downstream
    distortion detector — but together they catch fabricated and mislabelled cites.
    """

    id: int  # matches EnrichedCitation.id
    exists: bool  # source found AND confirmed to be this case
    matched_source: str | None = None  # identifier of the matched source (id/filename)
    match_method: str | None = None  # "direct" | "fuzzy" | "semantic" | None
    # True when the deterministic triple missed and the semantic resolver decided.
    used_semantic_fallback: bool = False
    # True when the year+court+number triple was satisfied (directly or confirmed).
    required_params_matched: bool = False
    field_mismatches: list[FieldMismatch] = []
    # True when existence could not be confirmed either way (resolver wanted a web
    # check, or the agent was unsure) — keeps "unknown" out of a false "doesn't exist".
    needs_review: bool = False
    reason: str | None = None  # one-line, plain-language rationale for the partner


class ClassificationType(str, Enum):
    """The user-facing verdict for one citation — the three buckets the challenge
    asks for. Mischaracterised and out-of-context collapse into one bucket because,
    to the reviewing partner, both mean "the case is real but used unfairly"."""

    EXISTS_CORRECTLY_APPLIED = "EXISTS_CORRECTLY_APPLIED"
    EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT = (
        "EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT"
    )
    DOESNT_EXIST = "DOESNT_EXIST"


class Classification(BaseModel):
    """The final verdict object for one citation, derived from the resolver
    (does the case exist in / resolve to the dataset?) and the faithfulness
    detector (is it applied correctly?)."""

    type: ClassificationType
    # 0..1 — how sure we are of the verdict (resolver confidence × detector margin).
    confidence: float | None = None
    # True when the citation could not be confirmed real (resolver wanted a web
    # check but none was configured). Keeps "unknown" out of a false DOESNT_EXIST.
    needs_review: bool = False
    # True when the deterministic metadata match missed and Leo's semantic vector
    # search resolved the source instead — surfaced for transparency in the report.
    used_semantic_fallback: bool = False
    # one-line, plain-language rationale for the partner.
    reason: str | None = None


class AnalysisDict(BaseModel):
    """Typed mirror of the dict returned by ``detect_distortion.analyze`` (the
    faithfulness detector). Curated to the five fields the API/UI consumes.

    Field types:
    - ``classification``: ``str`` — the detector's raw class, one of
      ``"correct" | "mischaracterised" | "out_of_context"`` (distinct from the
      user-facing :class:`ClassificationType`, which also covers DOESNT_EXIST).
    - ``mischaracterised_pct``: ``float`` — 0..100, share of premises VIOLATED,
      severity-weighted by level (micro/meso/macro).
    - ``out_of_context_pct``: ``float`` — 0..100, share of premises UNADDRESSED
      (the source does not speak to what the citation claims).
    - ``plain_language_holding``: ``str`` — 1–2 sentences on what the case
      actually decided.
    - ``evaluations``: ``list[dict]`` — per-premise judge results; each item has
      ``statement, premise, level('micro'|'meso'|'macro'),
      label('SATISFIED'|'CHARITABLE'|'VIOLATED'|'UNADDRESSED'),
      evidence_paragraph_id(int|None), reason(str)``.
    """

    classification: str
    mischaracterised_pct: float
    out_of_context_pct: float
    plain_language_holding: str
    evaluations: list[dict] = []
