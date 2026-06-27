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
