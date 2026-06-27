"""Frontend-ready report schema (`report.json`) — the Step 5 deliverable.

`ReportCitation` mirrors the frontend `Citation` interface (`src/lib/mock-citations.ts`):
the 3 challenge categories (`status`), integer `confidence` 0–100, and the fields the UI
renders. The frontend
validates only 7 of these per citation (`id, caseName, court, year, citation, status,
confidence`); the backend fills the full set. `extra="forbid"` + `min_length=1` make the
contract fail-loud: an empty/extra field raises instead of shipping a broken report.

Spec + acceptance criteria: documentation/Sprint4/STEP-5.md.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Non-empty string field (the frontend treats "" as a missing value).
_NonEmptyStr = Field(min_length=1)


class ReportCitation(BaseModel):
    """One citation's verdict in the shape the frontend renders."""

    model_config = ConfigDict(extra="forbid")

    # --- frontend-required (7) ---
    id: str = Field(pattern=r"^c\d+$")
    caseName: str = _NonEmptyStr
    court: str = _NonEmptyStr
    year: int
    citation: str = _NonEmptyStr
    status: Literal["verified", "mischar", "risk"]  # the 3 challenge categories
    confidence: int = Field(ge=0, le=100)
    # --- backend-populated extras (UI renders, frontend does not validate) ---
    summary: str = _NonEmptyStr
    holding: str = _NonEmptyStr
    howUsed: str = _NonEmptyStr
    reasoning: str = _NonEmptyStr
    recommendation: str = _NonEmptyStr
    issue: str = _NonEmptyStr
    action: str = _NonEmptyStr
    ground: str = _NonEmptyStr
    paragraph: int = Field(ge=0)
    supporting: str | None = None


class ReportDocument(BaseModel):
    """Top-level `report.json`. `status="complete"` once a run finishes; the frontend
    treats a missing file (404) as "pending", and `complete` + empty `citations` as an
    error (see STEP-5.md)."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["pending", "complete"]
    generated_at: str  # ISO-8601 UTC
    summary: dict[str, int]  # verified / mischar / risk / total
    citations: list[ReportCitation]
