"""Citation-integrity detector: out-of-context vs mischaracterised vs correct.

Content-faithfulness stage AFTER resolution: given the citing document's own
wording about a case (``relevant_text``) and the resolved source judgment's text,
check whether that wording fairly represents what the case actually decided.

Stages: chunk source into paragraphs -> rerank -> select R_top -> gather following
paragraphs (meso context) -> decompose into statements/premises -> 3-level charity
judge -> two %-scores + classification. The model steps run via a pluggable
backend (:mod:`app.services.distortion_backend`); the default is the deterministic
offline MockBackend, ``vertex`` is the real one (Gemini via Vertex AI).
"""

from __future__ import annotations

from app.services.distortion_backend import get_backend  # noqa: F401 (re-export)

# Classification thresholds (calibrate on the eval set).
TAU_LOW = 25.0                          # both axes below -> correct
LEVEL_W = {"micro": 0.5, "meso": 0.7, "macro": 1.0}   # severity per level

# Detector classes -> eval labels (kept for parity with the eval harness).
CLASS_TO_LABEL = {
    "correct": "faithful",
    "mischaracterised": "misleading",
    "out_of_context": "out_of_scope",
}


def chunk_paragraphs(text: str, size: int = 60, overlap: int = 0) -> list[str]:
    """Word-window chunking (dependency-free; non-overlapping by default so that
    'following paragraphs' stay disjoint)."""
    words = text.split()
    if not words:
        return []
    step = max(1, size - overlap)
    out, n = [], len(words)
    for start in range(0, n, step):
        piece = words[start:start + size]
        if not piece:
            break
        out.append(" ".join(piece))
        if start + size >= n:
            break
    return out


def score(evals: list[dict]) -> tuple[float, float, str]:
    """Premise labels -> (mischar%, out_of_context%, classification)."""
    n = len(evals)
    if n == 0:
        return 0.0, 0.0, "correct"
    violated = sum(LEVEL_W.get(e["level"], 0.5) for e in evals if e["label"] == "VIOLATED")
    unaddressed = sum(1 for e in evals if e["label"] == "UNADDRESSED")
    mischar = 100.0 * violated / n
    ooc = 100.0 * unaddressed / n
    if max(mischar, ooc) < TAU_LOW:
        cls = "correct"
    elif mischar >= ooc:
        cls = "mischaracterised"
    else:
        cls = "out_of_context"
    return round(mischar, 1), round(ooc, 1), cls


def analyze(relevant_text: str, source_text: str, backend,
            top: int = 50, k: int = 5,
            size: int = 60, overlap: int = 0,
            id: int | None = None, global_summary: str = "") -> tuple[dict, int | None]:
    """Check whether ``relevant_text`` (the citing document's claim about the case)
    fairly represents the source.

    ``id`` is NOT processed, only passed through: the result is a tuple
    ``(report, id)`` so the caller can re-associate the report with its citation
    row. ``global_summary`` is forwarded to the judge for macro context (the mock
    backend ignores it; the Vertex backend uses it).
    """
    paragraphs = chunk_paragraphs(source_text, size, overlap)
    if not paragraphs:
        return _report(relevant_text, "out_of_context", 0.0, 100.0, [], [],
                       "(empty source)"), id

    scores = backend.rerank(relevant_text, paragraphs)                  # Stage 2
    scored = sorted(((i, paragraphs[i], scores[i]) for i in range(len(paragraphs))),
                    key=lambda t: t[2], reverse=True)[:top]              # Stage 1+2
    r_ids = backend.select(relevant_text, scored, k)                    # Stage 3
    r_top = [{"id": i, "text": paragraphs[i]} for i in r_ids]

    follow_ids: list[int] = []
    rset = set(r_ids)
    for i in r_ids:                                                     # meso context
        for j in (i + 1, i + 2, i + 3):
            if j < len(paragraphs) and j not in rset and j not in follow_ids:
                follow_ids.append(j)
    following = [{"id": j, "text": paragraphs[j]} for j in follow_ids]

    statements = backend.decompose(relevant_text)                      # Stage 4
    judged = backend.judge(relevant_text, statements, r_top, following,
                           global_summary=global_summary)              # Stages 5+6
    evals = judged.get("evaluations", [])
    mischar, ooc, cls = score(evals)                                   # Stage 6
    return _report(relevant_text, cls, mischar, ooc, r_ids, evals,
                   judged.get("plain_language_holding", "")), id


def _report(relevant_text, cls, mischar, ooc, r_ids, evals, holding) -> dict:
    return {
        "relevant_text": relevant_text,
        "classification": cls,
        "mischaracterised_pct": mischar,
        "out_of_context_pct": ooc,
        "r_top_ids": r_ids,
        "premise_summary": [e for e in evals if e["label"] in ("VIOLATED", "UNADDRESSED")],
        "evaluations": evals,
        "plain_language_holding": holding,
    }


def build_relevant_text_map(rows) -> dict[int, str]:
    """Read the 'id' and 'relevant_text' columns and store id -> relevant_text.

    Accepts dict rows ({'id':..., 'relevant_text':...}) OR objects with
    ``.id``/``.relevant_text`` attributes (e.g. Martin's ``EnrichedCitation``).
    """
    mapping: dict[int, str] = {}
    for row in rows:
        if isinstance(row, dict):
            _id, rt = row.get("id"), row.get("relevant_text")
        else:
            _id, rt = getattr(row, "id", None), getattr(row, "relevant_text", None)
        if _id is not None:
            mapping[_id] = rt or ""
    return mapping


def analyze_relevant_texts(rt_map: dict[int, str], source_for, backend,
                           top: int = 50, k: int = 5,
                           size: int = 60, overlap: int = 0,
                           global_summary_for=None) -> list[tuple[dict, int | None]]:
    """Run :func:`analyze` for each ``(id, relevant_text)`` pair.

    ``source_for(id) -> str`` yields the resolved source text for that citation.
    ``global_summary_for(id) -> str`` (optional) yields its global summary.
    Returns a list of ``(report, id)`` — exactly what :func:`analyze` produces.
    """
    return [
        analyze(rt, source_for(_id), backend, top=top, k=k, size=size, overlap=overlap,
                id=_id, global_summary=(global_summary_for(_id) if global_summary_for else ""))
        for _id, rt in rt_map.items()
    ]
