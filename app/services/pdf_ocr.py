"""PDF -> text, hybrid: embedded text layer first, OCR only when needed.

For each page the embedded text layer is read first (fast). If a page has
(almost) no text it is a scan/image and is recognised with RapidOCR (PP-OCR
models, ONNX, CPU). So only actual scanned pages go through OCR. No API key and
no GPU required.

This is the OCR-capable counterpart to ``citation_service.read_pdf_text`` (pypdf):
use this when a source PDF is scanned and pypdf returns little or no text.

Requires (heavy, optional): ``pymupdf`` and ``rapidocr-onnxruntime``. Imports are
lazy so this module can be imported without those installed; they are only needed
when :func:`extract_text` actually runs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Render resolution for OCR pages. 200 DPI is a good CPU trade-off.
RENDER_DPI = 200
# A page with fewer than this many text chars is treated as a scan.
MIN_TEXT_CHARS = 100

_ENGINE = None


def _get_engine():
    """Load the RapidOCR engine once (lazy) and only when OCR is needed."""
    global _ENGINE
    if _ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR
        _ENGINE = RapidOCR()
    return _ENGINE


def order_text(result: list | None) -> str:
    """Put RapidOCR detections into line-by-line reading order.

    ``result`` is a list of [box, text, score]; ``box`` is 4 corner points
    [[x, y], ...]. Sort by vertical position, group boxes of similar height into
    lines, and sort within a line by x.
    """
    if not result:
        return ""

    boxes = []  # (top, left, height, text)
    for box, text, _score in result:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        boxes.append((min(ys), min(xs), max(ys) - min(ys), text))

    heights = sorted(b[2] for b in boxes)
    tol = max(heights[len(heights) // 2] * 0.5, 1.0)

    boxes.sort(key=lambda b: b[0])
    lines: list[str] = []
    current: list[tuple[float, str]] = []
    line_top: float | None = None
    for top, left, _h, text in boxes:
        if line_top is None or top - line_top <= tol:
            current.append((left, text))
            if line_top is None:
                line_top = top
        else:
            current.sort(key=lambda c: c[0])
            lines.append(" ".join(c[1] for c in current))
            current = [(left, text)]
            line_top = top
    if current:
        current.sort(key=lambda c: c[0])
        lines.append(" ".join(c[1] for c in current))

    return "\n".join(lines)


def ocr_page(page, dpi: int = RENDER_DPI) -> str:
    """OCR a single page (render to PNG, RapidOCR decodes via OpenCV)."""
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    result, _elapse = _get_engine()(pix.tobytes("png"))
    return order_text(result)


def extract_text(pdf_path: Path | str, dpi: int = RENDER_DPI,
                 min_chars: int = MIN_TEXT_CHARS) -> str:
    """Extract all text of a PDF (text layer, OCR per page otherwise)."""
    import fitz  # PyMuPDF — imported lazily so the module loads without it.

    parts: list[str] = []
    with fitz.open(pdf_path) as doc:
        if doc.page_count == 0:
            raise ValueError(f"PDF has no pages: {pdf_path}")
        for page in doc:
            try:
                embedded = page.get_text().strip()
                if len(embedded) >= min_chars:
                    parts.append(embedded)
                else:
                    parts.append(ocr_page(page, dpi))
            except Exception as exc:  # broken page -> skip instead of aborting
                print(f"  Warning: page skipped ({exc})", file=sys.stderr)
                parts.append("")
    return "\n\n".join(p for p in parts if p).strip()


def convert(pdf_path: Path, out_path: Path) -> None:
    """Convert a PDF and write the result to out_path."""
    print(f"Processing {pdf_path.name} ...", file=sys.stderr)
    text = extract_text(pdf_path)
    out_path.write_text(text + "\n", encoding="utf-8")
    print(f"Done: text saved to {out_path}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert PDF to text (text layer + RapidOCR fallback, CPU).")
    parser.add_argument("pdf", nargs="?", default="example.pdf", type=Path,
                        help="Input PDF (default: example.pdf)")
    parser.add_argument("out", nargs="?", default="example.txt", type=Path,
                        help="Output text file (default: example.txt)")
    args = parser.parse_args(argv)

    if not args.pdf.is_file():
        print(f"Error: PDF not found: {args.pdf}", file=sys.stderr)
        return 2
    try:
        convert(args.pdf, args.out)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
