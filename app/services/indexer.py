"""Build a semantic index over a corpus of source documents.

For each source (.pdf or .txt) text is obtained (PDF via OCR if no sibling .txt
exists), split into overlapping chunks, embedded with fastembed (CPU/ONNX) and
persisted with metadata.

Output in ``out_dir``:
    embeddings.npy   float32 matrix (n_chunks x dim), L2-normalised
    chunks.json      list of {source, filename, chunk_id, text}
    sources.json     list of source filenames (for name matching)

Usable as a library (``build(...)``, called by the resolver's auto-build) or as a
CLI (``python -m app.services.indexer --source-dir ./data --out-dir ./index``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from app.services import citelib


def load_source_text(path: Path) -> str:
    """Return a source's text: an existing .txt, otherwise hybrid extraction.

    For PDFs, ``pdf_ocr.extract_text`` uses the text layer and only falls back to
    OCR for scanned pages.
    """
    if path.suffix.lower() == ".txt":
        return path.read_text(encoding="utf-8", errors="replace")

    sibling_txt = path.with_suffix(".txt")
    if sibling_txt.is_file():
        return sibling_txt.read_text(encoding="utf-8", errors="replace")

    from app.services.pdf_ocr import extract_text
    return extract_text(path)


def collect_sources(source_dir: Path) -> list[Path]:
    """Collect source files: every .pdf, plus .txt without a same-named .pdf."""
    pdfs = sorted(source_dir.glob("*.pdf"))
    pdf_stems = {p.stem for p in pdfs}
    txts = sorted(t for t in source_dir.glob("*.txt") if t.stem not in pdf_stems)
    return pdfs + txts


def build(source_dir: Path, out_dir: Path, size: int = 80, overlap: int = 20) -> None:
    """Build the index from ``source_dir`` into ``out_dir`` (creates it)."""
    source_dir, out_dir = Path(source_dir), Path(out_dir)
    sources = collect_sources(source_dir)
    if not sources:
        raise ValueError(f"No .pdf/.txt sources found in {source_dir}.")

    # Cache extracted text (incl. expensive OCR) so re-builds / aborted runs do
    # not OCR again.
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = out_dir / "texts"
    cache_dir.mkdir(exist_ok=True)

    chunk_meta: list[dict] = []
    chunk_texts: list[str] = []

    for i, src in enumerate(sources, start=1):
        cache_file = cache_dir / f"{src.name}.txt"
        if cache_file.is_file():
            text = cache_file.read_text(encoding="utf-8", errors="replace")
            note = "(cache)"
        else:
            text = load_source_text(src)
            cache_file.write_text(text, encoding="utf-8")
            note = ""
        chunks = citelib.chunk_text(text, size=size, overlap=overlap)
        print(f"  [{i}/{len(sources)}] {src.name}: {len(chunks)} chunk(s) {note}",
              file=sys.stderr, flush=True)
        for cid, chunk in enumerate(chunks):
            chunk_meta.append({"source": src.name, "filename": src.name,
                               "chunk_id": cid, "text": chunk})
            chunk_texts.append(chunk)

    if not chunk_texts:
        raise ValueError("No chunks produced (empty sources?).")

    print(f"Embedding {len(chunk_texts)} chunks with {citelib.EMBED_MODEL} ...", file=sys.stderr)
    embeddings = citelib.embed_passages(chunk_texts)

    np.save(out_dir / "embeddings.npy", embeddings)
    (out_dir / "chunks.json").write_text(json.dumps(chunk_meta, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    (out_dir / "sources.json").write_text(json.dumps([s.name for s in sources],
                                                      ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    print(f"Index saved to {out_dir} "
          f"({embeddings.shape[0]} chunks, dim={embeddings.shape[1]}).", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a semantic index over source documents.")
    parser.add_argument("--source-dir", type=Path, required=True,
                        help="Directory with source PDFs and/or .txt files")
    parser.add_argument("--out-dir", type=Path, default=Path("index"),
                        help="Target directory for the index (default: ./index)")
    parser.add_argument("--chunk-size", type=int, default=80, help="Chunk size in words")
    parser.add_argument("--chunk-overlap", type=int, default=20, help="Overlap in words")
    args = parser.parse_args(argv)

    if not args.source_dir.is_dir():
        print(f"Error: source directory not found: {args.source_dir}", file=sys.stderr)
        return 2
    try:
        build(args.source_dir, args.out_dir, args.chunk_size, args.chunk_overlap)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
