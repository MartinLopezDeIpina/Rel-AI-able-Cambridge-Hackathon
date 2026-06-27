"""Extract UK-standard legal citations from a PDF.

Handles the two common conventions (both share the ``[YEAR] ...`` shape):

- **Neutral citations** — court-assigned, e.g. ``[2007] UKHL 21``,
  ``[2023] EWHC 892 (TCC)``.
- **Law-report citations** — series reports, e.g. ``[1952] Ch 646``,
  ``[1974] 1 WLR 798``.

Each is returned as a :class:`~app.schemas.citation.Citation`, with the
preceding case name captured when present (e.g. ``OBG Ltd v Allan``).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from pypdf import PdfReader

from app.schemas.citation import Citation, CitationType

# Directories searched when a bare PDF name (not a path) is supplied.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SEARCH_DIRS = (_PROJECT_ROOT, _PROJECT_ROOT / "data")

# Neutral citation: [YEAR] COURT NUMBER (DIVISION)?  e.g. [2023] EWHC 892 (TCC)
_NEUTRAL_RE = re.compile(
    r"\[(?P<year>\d{4})\]\s+"
    r"(?P<court>UKHL|UKSC|UKPC|EWCA Civ|EWCA Crim|EWHC|EWCOP|EWFC)\s+"
    r"(?P<number>\d+)"
    r"(?:\s*\((?P<division>[A-Za-z]+)\))?"
)

# Law report: [YEAR] (VOL)? REPORTER PAGE  e.g. [1972] 1 QB 60
_REPORT_RE = re.compile(
    r"\[(?P<year>\d{4})\]\s+"
    r"(?P<volume>\d+\s+)?"
    r"(?P<reporter>AC|QB|KB|Ch|WLR|All ER|Lloyd's Rep|FSR|RPC|ECC)\s+"
    r"(?P<page>\d+)"
)

# Old nominate report: (YEAR) VOL REPORTER PAGE  e.g. (1853) 2 E&B 216
# Round brackets (pre-1865 style) and short nominate reporter codes (E&B, Ex...).
_NOMINATE_RE = re.compile(
    r"\((?P<year>\d{4})\)\s+"
    r"(?P<volume>\d+\s+)?"
    r"(?P<reporter>[A-Z][A-Za-z&'.]{0,9})\s+"
    r"(?P<page>\d+)"
)

# Optional case name immediately preceding a citation, e.g. "OBG Ltd v Allan".
# Matched against the text *before* the citation, anchored to its end.
_CASE_NAME_RE = re.compile(
    r"(?P<case_name>(?:[A-Z][\w'&.()-]*\s+)*v\.?\s+(?:[A-Z][\w'&.()-]*\s*)+)\s*$"
)


def _resolve_pdf_path(pdf_path: str | Path) -> Path:
    """Resolve a path or bare filename to an existing PDF on disk."""
    candidate = Path(pdf_path)
    if candidate.is_file():
        return candidate
    if not candidate.is_absolute():
        for base in _SEARCH_DIRS:
            resolved = base / candidate
            if resolved.is_file():
                return resolved
    raise FileNotFoundError(f"PDF not found: {pdf_path}")


def read_pdf_text(pdf_path: str | Path) -> str:
    """Extract all text from a PDF, with newlines collapsed to spaces.

    Collapsing whitespace lets citations that wrap across lines still match.
    """
    reader = PdfReader(str(_resolve_pdf_path(pdf_path)))
    pages = (page.extract_text() or "" for page in reader.pages)
    text = " ".join(pages)
    return re.sub(r"\s+", " ", text)


def _find_case_name(text: str, start: int) -> str | None:
    """Return the case name ending just before ``start``, if any."""
    match = _CASE_NAME_RE.search(text[:start])
    if match is None:
        return None
    return match.group("case_name").strip()


def _to_int(value: str | None) -> int | None:
    return int(value) if value and value.strip() else None


def extract_citations(pdf_path: str | Path) -> list[Citation]:
    """Extract UK legal citations from ``pdf_path`` as structured objects.

    Accepts either a full path or a bare filename (resolved against the
    project root and ``data/``). Duplicates (by raw text) are removed, and the
    result is ordered by position in the document with a 1-based ``id`` so each
    citation can be anchored back to during LLM enrichment.
    """
    text = read_pdf_text(pdf_path)

    # Collect (document_position, fields) for every match across the three styles.
    found: list[tuple[int, dict]] = []

    for match in _NEUTRAL_RE.finditer(text):
        found.append((
            match.start(),
            dict(
                raw=match.group(0),
                case_name=_find_case_name(text, match.start()),
                year=int(match.group("year")),
                court=match.group("court"),
                division=match.group("division"),
                number=_to_int(match.group("number")),
                citation_type=CitationType.neutral,
            ),
        ))

    for match in _REPORT_RE.finditer(text):
        found.append((
            match.start(),
            dict(
                raw=match.group(0),
                case_name=_find_case_name(text, match.start()),
                year=int(match.group("year")),
                reporter=match.group("reporter"),
                volume=_to_int(match.group("volume")),
                page=_to_int(match.group("page")),
                citation_type=CitationType.law_report,
            ),
        ))

    for match in _NOMINATE_RE.finditer(text):
        found.append((
            match.start(),
            dict(
                raw=match.group(0),
                case_name=_find_case_name(text, match.start()),
                year=int(match.group("year")),
                reporter=match.group("reporter"),
                volume=_to_int(match.group("volume")),
                page=_to_int(match.group("page")),
                citation_type=CitationType.nominate,
            ),
        ))

    # Order by document position, dedupe by raw text, then assign 1-based ids.
    found.sort(key=lambda item: item[0])
    citations: list[Citation] = []
    seen: set[str] = set()
    for _, fields in found:
        if fields["raw"] in seen:
            continue
        seen.add(fields["raw"])
        citations.append(Citation(id=len(citations) + 1, **fields))

    return citations


class CitationService:
    """Service wrapper around :func:`extract_citations` for DI in endpoints."""

    def extract(self, pdf_path: str | Path) -> list[Citation]:
        return extract_citations(pdf_path)


_service = CitationService()


def get_citation_service() -> CitationService:
    return _service


if __name__ == "__main__":
    import json

    target = sys.argv[1] if len(sys.argv) > 1 else "case_demo.pdf"
    results = extract_citations(target)
    print(json.dumps([c.model_dump() for c in results], indent=2))
