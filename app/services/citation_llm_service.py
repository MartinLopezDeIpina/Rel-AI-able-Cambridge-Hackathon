"""LLM enrichment for regex-anchored UK legal citations.

The regex layer (:mod:`app.services.citation_service`) reliably extracts the
formal citation strings and assigns each a 1-based ``id`` in document order.
This module feeds those anchors *plus the whole document* to the configured LLM
(``build_llm`` — Google Gemini via Vertex AI by default, or Nemotron via
OpenRouter) and gets back structured JSON keyed by ``id`` — filling the metadata
regex cannot: full case names, court, judges, the proposition the case is cited
for, the supporting Ground, and the document's own wording on how it is used.

Provider/model selection is config-driven (:class:`app.core.config.Settings`)
via ``LLM_PROVIDER`` with no code change. ``build_llm`` is also reused by the
distortion judge (:mod:`app.services.distortion_backend`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.core.config import _ENV_FILE, Settings, get_settings

# Load .env into the process environment so LangChain/LangSmith tracing picks up
# LANGSMITH_* vars (pydantic Settings only reads .env into the Settings object).
load_dotenv(_ENV_FILE)
from app.schemas.citation import (
    Citation,
    CitationExtraction,
    CitationMetadata,
    EnrichedCitation,
)
from app.services.citation_service import extract_citations, read_pdf_text

_SYSTEM_PROMPT = """You are a UK legal citation analyst. You are given the full \
text of a court document (a skeleton argument) and a numbered list of case \
citations already extracted from it. For each citation id, extract metadata \
STRICTLY from the document text.

Rules:
- Return exactly one item per supplied id; never add or drop ids.
- Use ONLY information present in the document. Never invent or use outside \
knowledge. If a field is not stated in the document, set it to null.
- full_case_name: the full party names as written (repair truncations).
- court_name: the deciding court in words, e.g. "House of Lords", "Court of \
Appeal", "Chancery Division", "Commercial Court" — only if stated or \
unambiguous from the document.
- judges: list of judges named in connection with the case, exactly as written \
(e.g. "Lord Hoffmann", "Cockerill J"). Empty list if none.
- proposition: a short phrase for the legal point the case is cited for.
- ground: the Ground the citation supports (e.g. "Ground 1"), e.g. from the \
Citation Index table if present; null if not stated.
- relevant_text: the document's OWN words describing how this citation is used \
or what it establishes — quote or closely paraphrase the document, do not \
summarise in your own voice.

Respond with ONLY a JSON object of the form:
{"items": [{"id": 1, "full_case_name": ..., "court_name": ..., "judges": [...], \
"proposition": ..., "ground": ..., "relevant_text": ...}, ...]}
No prose, no markdown fences."""

_HUMAN_TEMPLATE = """CITATIONS TO ENRICH (one JSON item per id):
{anchors}

FULL DOCUMENT TEXT:
\"\"\"
{document}
\"\"\""""


def build_llm(settings: Settings | None = None):
    """Construct the chat model for the configured provider.

    Modular: ``LLM_PROVIDER`` selects the backend and the rest of the pipeline is
    unchanged. "openrouter" -> Nemotron via OpenAI-compatible API; "vertex" ->
    Google Gemini via Vertex AI (Application Default Credentials).
    """
    settings = settings or get_settings()

    if settings.llm_provider == "vertex":
        from langchain_google_vertexai import ChatVertexAI

        if not settings.google_project:
            raise RuntimeError(
                "GOOGLE_PROJECT is not set; required for the vertex provider."
            )
        return ChatVertexAI(
            model=settings.google_model,
            project=settings.google_project,
            location=settings.google_location,
            temperature=settings.llm_temperature,
            thinking_budget=settings.google_thinking_budget,
        )

    if settings.llm_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not settings.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set; required for the gemini provider."
            )
        return ChatGoogleGenerativeAI(
            model=settings.google_model,
            google_api_key=settings.gemini_api_key,
            temperature=settings.llm_temperature,
        )

    from langchain_openai import ChatOpenAI

    if not settings.openrouter_api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Add it to .env (or the environment) "
            "to run LLM enrichment."
        )
    return ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.openrouter_api_key,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
    )


def _anchor_block(citations: list[Citation]) -> str:
    return "\n".join(
        f'{c.id}. raw="{c.raw}" regex_case_name="{c.case_name or ""}"'
        for c in citations
    )


def _parse_extraction(content: str) -> CitationExtraction:
    """Parse the model reply into :class:`CitationExtraction`.

    Tolerates markdown fences / surrounding prose by isolating the JSON object.
    """
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return CitationExtraction.model_validate_json(text)


def _enrich(
    citations: list[Citation], document: str, settings: Settings | None = None
) -> dict[int, CitationMetadata]:
    """Single LLM call (with one retry) returning metadata keyed by citation id."""
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = build_llm(settings)
    human = _HUMAN_TEMPLATE.format(
        anchors=_anchor_block(citations), document=document
    )
    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=human)]

    last_error: Exception | None = None
    for _ in range(2):
        response = llm.invoke(messages)
        try:
            extraction = _parse_extraction(str(response.content))
            return {item.id: item for item in extraction.items}
        except Exception as error:  # noqa: BLE001 - retry on any parse/validation issue
            last_error = error
            messages.append(
                HumanMessage(
                    content="Your previous reply was not valid JSON matching the "
                    'schema. Reply with ONLY {"items": [...]} and nothing else.'
                )
            )
    raise RuntimeError(f"LLM did not return valid JSON: {last_error}")


def _verify(metadata: CitationMetadata, document: str) -> CitationMetadata:
    """Drop any judge name the model returned that is not present in the source.

    Cheap anti-hallucination guard: judge names are short exact tokens, so a
    substring check reliably catches fabrications without another LLM call.
    """
    low = document.lower()
    verified_judges = [j for j in metadata.judges if j.lower() in low]
    return metadata.model_copy(update={"judges": verified_judges})


def _merge(citation: Citation, metadata: CitationMetadata | None) -> EnrichedCitation:
    data = citation.model_dump()
    if metadata is not None:
        meta = metadata.model_dump()
        meta.pop("id", None)  # id comes from the regex citation
        data.update(meta)
    return EnrichedCitation(**data)


def extract_enriched_citations(pdf_path: str | Path) -> list[EnrichedCitation]:
    """Extract citations (regex) then enrich their metadata with the LLM."""
    return enrich_from_text(read_pdf_text(pdf_path))


def enrich_from_text(document: str) -> list[EnrichedCitation]:
    """Extract + enrich citations from already-extracted document text (paste path)."""
    from app.services.citation_service import extract_citations_from_text

    citations = extract_citations_from_text(document)
    if not citations:
        return []
    metadata = _enrich(citations, document)
    return [
        _merge(c, _verify(metadata[c.id], document) if c.id in metadata else None)
        for c in citations
    ]


class CitationLLMService:
    """Service wrapper for DI in endpoints, mirroring ``CitationService``."""

    def extract(self, pdf_path: str | Path) -> list[EnrichedCitation]:
        return extract_enriched_citations(pdf_path)


_service = CitationLLMService()


def get_citation_llm_service() -> CitationLLMService:
    return _service


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "case_demo.pdf"
    results = extract_enriched_citations(target)
    print(json.dumps([c.model_dump() for c in results], indent=2))
