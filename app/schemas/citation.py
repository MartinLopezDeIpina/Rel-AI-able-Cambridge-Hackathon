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


class CitationVerdict(BaseModel):
    """One citation's end-to-end verdict — the object the frontend renders.

    Carries the challenge blueprint fields (``citation_name``, ``status``,
    ``confidence_score``, ``associate_claim``, ``actual_holding``, ``explanation``)
    plus provenance for transparency (resolver/detector internals)."""

    id: int
    citation_name: str
    raw: str
    status: ClassificationType
    confidence_score: float                 # 0..1, how robustly the source supports the claim
    associate_claim: str                    # the brief's own wording (relevant_text)
    actual_holding: str                     # what the case actually decided ("" if fabricated)
    explanation: str                        # 2-3 sentence "why it's wrong" ("" if verified)
    ground: str | None = None               # Ground 1/2/3 of the dispute
    needs_review: bool = False
    used_semantic_fallback: bool = False
    chosen_source: str | None = None
    detector_classification: str | None = None   # correct|mischaracterised|out_of_context
    mischaracterised_pct: float | None = None
    out_of_context_pct: float | None = None


class VerifyResponse(BaseModel):
    """Full document report returned by ``POST /api/citations/verify``."""

    document_name: str | None = None
    citations: list[CitationVerdict] = []
    summary: dict[str, int] = {}            # counts per status (verified / mischar / fabricated)
