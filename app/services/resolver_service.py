"""Resolve citations to source documents (semantic search + name match).

This is the FALLBACK existence/resolution tier behind the deterministic exact
metadata match: it uses two complementary signals to find which source judgment a
citation refers to.

  1. Semantic - embed the citation and compare against the chunk embeddings;
                resolves indirect/paraphrased citations (meaning).
  2. Name     - fuzzy-match the citation against the source filenames; resolves
                direct/named citations whose name may only appear in the filename.

Fusion: a confident name hit wins; otherwise the semantic top hit. If neither is
confident the source is probably not in the corpus (``needs_web``). Whenever the
semantic signal decides, ``used_semantic_fallback`` is set so the report can flag
that a less-certain fallback was used.

Auto-build: if the index does not exist yet, :meth:`ResolverService._ensure_loaded`
runs the indexer (``app.services.indexer.build``) over the configured corpus dir
before loading — i.e. "if the embeddings don't exist yet, build them".
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from app.services import citelib

# Above this fuzzy score (0..100) a name hit counts as confident. Because we match
# the extracted case name, real named citations reach ~90-100 while paraphrases
# stay well below.
NAME_THRESHOLD = 75.0
# Below this cosine similarity a purely semantic decision is treated as uncertain.
SEM_UNCERTAIN = 0.5
# Number of semantic evidences returned per citation.
TOP_EVIDENCE = 3


def load_index(index_dir: Path):
    embeddings = np.load(index_dir / "embeddings.npy")
    chunks = json.loads((index_dir / "chunks.json").read_text(encoding="utf-8"))
    sources = json.loads((index_dir / "sources.json").read_text(encoding="utf-8"))
    return embeddings, chunks, sources


def semantic_rank(query: str, embeddings: np.ndarray, chunks: list[dict]):
    """Rank sources by maximum chunk similarity to the citation."""
    q = citelib.embed_queries([query])[0]
    scores = embeddings @ q  # cosine (everything L2-normalised)
    best: dict[str, tuple[float, int]] = {}
    for i, s in enumerate(scores):
        src = chunks[i]["source"]
        if src not in best or s > best[src][0]:
            best[src] = (float(s), i)
    ranked = sorted(best.items(), key=lambda kv: kv[1][0], reverse=True)
    return ranked, scores


def resolve_one(citation: str, embeddings, chunks, sources,
                name_threshold: float = NAME_THRESHOLD,
                sem_uncertain: float = SEM_UNCERTAIN) -> dict:
    sem_ranked, _ = semantic_rank(citation, embeddings, chunks)
    sem_src, (sem_score, sem_idx) = sem_ranked[0]

    name_scores = sorted(
        ((src, citelib.name_match_score(citation, src)) for src in sources),
        key=lambda kv: kv[1], reverse=True,
    )
    name_src, name_score = name_scores[0]

    if name_score >= name_threshold:
        chosen, method, confidence = name_src, "name", round(name_score / 100.0, 3)
        uncertain = False
    else:
        chosen, method, confidence = sem_src, "semantic", round(sem_score, 3)
        uncertain = sem_score < sem_uncertain

    # Neither a confident name/filename hit nor a meaningful semantic hit -> the
    # source is probably not in the corpus -> candidate for the web fallback.
    needs_web = (name_score < name_threshold) and (sem_score < sem_uncertain)

    agree = (name_score >= name_threshold) and (name_src == sem_src)
    return {
        "citation": citation,
        "chosen_source": chosen,
        "method": method,
        "confidence": confidence,
        "uncertain": uncertain,
        "needs_web": needs_web,
        # True when the less-certain semantic signal decided (logged in the report).
        "used_semantic_fallback": method == "semantic",
        "signals_agree": agree,
        "name_top": {"source": name_src, "score": round(name_score, 1)},
        "semantic_top": {"source": sem_src, "score": round(sem_score, 3),
                         "evidence": chunks[sem_idx]["text"][:300]},
        "name_ranking": [{"source": s, "score": round(sc, 1)} for s, sc in name_scores[:TOP_EVIDENCE]],
        "semantic_ranking": [{"source": s, "score": round(sc, 3)}
                             for s, (sc, _i) in sem_ranked[:TOP_EVIDENCE]],
    }


class ResolverService:
    """Loads the index once (building it first if missing) and resolves citations.

    Mirrors the DI style of Martin's services. The index is loaded lazily on the
    first resolve so app startup never blocks on building embeddings.
    """

    def __init__(self, index_dir: str | Path | None = None,
                 corpus_dir: str | Path | None = None,
                 chunk_size: int = 80, chunk_overlap: int = 20) -> None:
        from app.core.config import get_settings
        s = get_settings()
        self.index_dir = Path(index_dir or s.index_dir)
        self.corpus_dir = Path(corpus_dir or s.corpus_dir)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._loaded = False
        self._embeddings = self._chunks = self._sources = None

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        if not (self.index_dir / "embeddings.npy").is_file():
            # Embeddings don't exist yet -> build the index from the corpus first.
            from app.services import indexer
            indexer.build(self.corpus_dir, self.index_dir,
                          self.chunk_size, self.chunk_overlap)
        self._embeddings, self._chunks, self._sources = load_index(self.index_dir)
        self._loaded = True

    def resolve(self, citation: str) -> dict:
        self._ensure_loaded()
        return resolve_one(citation, self._embeddings, self._chunks, self._sources)

    def resolve_many(self, citations: list[str]) -> list[dict]:
        self._ensure_loaded()
        return [resolve_one(c, self._embeddings, self._chunks, self._sources)
                for c in citations]

    def source_text(self, chosen_source: str) -> str:
        """Return the cached source text for a resolved filename (for the detector)."""
        path = self.index_dir / "texts" / f"{chosen_source}.txt"
        if not path.is_file():
            path = self.index_dir / "texts" / chosen_source
        return path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""


_service: ResolverService | None = None


def get_resolver_service() -> ResolverService:
    global _service
    if _service is None:
        _service = ResolverService()
    return _service
