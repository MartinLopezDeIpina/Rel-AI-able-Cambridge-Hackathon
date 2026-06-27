"""Shared helpers for citation resolution (chunking, embeddings, names).

Used by :mod:`app.services.indexer` and :mod:`app.services.resolver_service`.
Everything runs on CPU: fastembed (ONNX, no PyTorch) for embeddings, rapidfuzz
for name matching. Both are imported lazily so importing this module is cheap.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

# Lightweight CPU/ONNX embedding model (no PyTorch). bge-small is small and good
# for English (legal) text; swap for a multilingual model if needed.
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

_MODEL = None


def get_model(name: str = EMBED_MODEL):
    """Load the embedding model once (lazy, cached)."""
    global _MODEL
    if _MODEL is None:
        from fastembed import TextEmbedding
        _MODEL = TextEmbedding(model_name=name)
    return _MODEL


def _normalize(mat: np.ndarray) -> np.ndarray:
    """L2-normalise row vectors so the dot product equals cosine similarity."""
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


def embed_passages(texts: list[str]) -> np.ndarray:
    """Embed source chunks (passages)."""
    model = get_model()
    vecs = list(model.embed(list(texts)))
    return _normalize(np.asarray(vecs, dtype=np.float32))


def embed_queries(texts: list[str]) -> np.ndarray:
    """Embed search queries (citations). Use the query variant if available.

    bge models prepend an instruction to queries; fastembed offers query_embed()
    for that. Falls back to embed() otherwise.
    """
    model = get_model()
    qfn = getattr(model, "query_embed", None)
    vecs = list(qfn(list(texts))) if qfn is not None else list(model.embed(list(texts)))
    return _normalize(np.asarray(vecs, dtype=np.float32))


def chunk_text(text: str, size: int = 80, overlap: int = 20) -> list[str]:
    """Split text into overlapping word windows.

    OCR text is line- not paragraph-oriented, so we use word windows rather than
    blank-line paragraphs. size/overlap are in words.
    """
    words = text.split()
    if not words:
        return []
    step = max(1, size - overlap)
    chunks: list[str] = []
    for start in range(0, len(words), step):
        piece = words[start:start + size]
        if not piece:
            break
        chunks.append(" ".join(piece))
        if start + size >= len(words):
            break
    return chunks


def normalize_name(s: str) -> str:
    """Normalise a string for name matching: lower, only a-z0-9 + space."""
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# Case-name pattern "X v Y" (e.g. "Donoghue v Stevenson"). Captures runs of
# capitalised words around a " v "/" v. ".
_CASE_RE = re.compile(
    r"\b([A-Z][A-Za-z.'&-]+(?:\s+[A-Z][A-Za-z.'&-]+){0,6})"
    r"\s+v\.?\s+"
    r"([A-Z][A-Za-z.'&-]+(?:\s+[A-Z][A-Za-z.'&-]+){0,6})"
)


def extract_case_name(citation: str) -> str | None:
    """Extract the case name 'X v Y' from a citation (normalised) or None.

    Separates named (direct) citations from pure paraphrases: without an
    'X v Y' pattern there is no name, so name matching does not fire on paraphrases.
    """
    m = _CASE_RE.search(citation)
    if not m:
        return None
    return normalize_name(f"{m.group(1)} v {m.group(2)}")


def filename_to_name(path: str | Path) -> str:
    """Turn a filename stem (slug) into normalised name text.

    e.g. 'allen-v-flood-and-another-uk-nondevolved-case-law' -> 'allen v flood ...'
    """
    return normalize_name(Path(path).stem)


def name_match_score(citation: str, filename: str | Path) -> float:
    """Fuzzy similarity (0..100) between a citation and a filename.

    Prefers the extracted case name 'X v Y' (precise; named citations score ~100
    against the right file), otherwise falls back to the whole citation.
    token_set_ratio is robust against extra tokens in the filename (e.g.
    jurisdiction suffixes).
    """
    from rapidfuzz import fuzz
    fn = filename_to_name(filename)
    if not fn:
        return 0.0
    candidates = []
    span = extract_case_name(citation)
    if span:
        candidates.append(span)
    whole = normalize_name(citation)
    if whole:
        candidates.append(whole)
    if not candidates:
        return 0.0
    return float(max(
        max(fuzz.token_set_ratio(c, fn), fuzz.partial_ratio(c, fn))
        for c in candidates
    ))
