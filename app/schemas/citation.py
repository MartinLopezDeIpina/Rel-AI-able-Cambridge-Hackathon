from enum import Enum

from pydantic import BaseModel


class CitationType(str, Enum):
    neutral = "neutral"  # court-assigned, e.g. [2007] UKHL 21
    law_report = "law_report"  # modern series report, e.g. [1952] Ch 646
    nominate = "nominate"  # old round-bracket report, e.g. (1853) 2 E&B 216


class Citation(BaseModel):
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
