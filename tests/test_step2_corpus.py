"""STEP 2 — source corpus: PDF->text + chunking + semantic index.

Unit parts (chunking, source collection) need no heavy deps; the index-build
integration needs fastembed and is skipped cleanly when it is absent.
"""
from __future__ import annotations

import pytest

from app.services import citelib, indexer
from tests.conftest import requires_fastembed


@pytest.mark.unit
def test_chunk_text_windows(agent):
    text = " ".join(str(i) for i in range(180))
    chunks = citelib.chunk_text(text, size=80, overlap=20)  # step=60
    agent.case("chunking", "chunk_text").input(words=180, size=80, overlap=20).expect(
        first="0", second="60").check(
        n=len(chunks), first=chunks[0].split()[0], second=chunks[1].split()[0])


@pytest.mark.unit
def test_collect_sources_prefers_pdf(agent, tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "a.txt").write_text("dup")          # same stem as a.pdf -> dropped
    (tmp_path / "b.txt").write_text("standalone")
    got = [p.name for p in indexer.collect_sources(tmp_path)]
    agent.case("collect_sources", "collect_sources").expect(
        has_pdf=True, drops_dup_txt=True, keeps_standalone_txt=True).check(
        has_pdf="a.pdf" in got, drops_dup_txt="a.txt" not in got,
        keeps_standalone_txt="b.txt" in got)


@pytest.mark.integration
@requires_fastembed
def test_build_real_index(agent, tiny_index):
    import json
    import numpy as np
    emb = np.load(tiny_index / "embeddings.npy")
    sources = json.loads((tiny_index / "sources.json").read_text())
    agent.case("build_index", "indexer.build").expect(
        normalised=True, n_sources=3).check(
        n_chunks=emb.shape[0], dim=emb.shape[1], n_sources=len(sources),
        normalised=bool(np.allclose(np.linalg.norm(emb, axis=1), 1.0, atol=1e-3)))
