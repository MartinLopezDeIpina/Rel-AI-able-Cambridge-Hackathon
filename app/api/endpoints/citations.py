"""Citation verification endpoint for the frontend.

``POST /api/citations/verify`` accepts either a multipart **file** upload (the
UploadZone) or a JSON body ``{"text": ...}`` (the paste box), runs the Step-5
orchestrator, and returns ``{"citations": [...], "summary": {...}}`` — the per-citation
verdict the dashboard/report render.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Request

from app.services.verify_service import verify_document

router = APIRouter()


@router.post("/verify")
async def verify(request: Request) -> dict:
    """Verify every citation in an uploaded document (file) or pasted text."""
    pdf_bytes: bytes | None = None
    text: str | None = None

    if "application/json" in request.headers.get("content-type", ""):
        data = await request.json()
        text = (data or {}).get("text")
    else:
        form = await request.form()
        upload = form.get("file")
        if upload is not None and hasattr(upload, "read"):
            raw = await upload.read()
            if (getattr(upload, "filename", "") or "").lower().endswith(".txt"):
                text = raw.decode("utf-8", "replace")  # plain-text upload
            else:
                pdf_bytes = raw
        else:
            value = form.get("text")
            text = value if isinstance(value, str) else None

    if pdf_bytes:
        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            tmp.write(pdf_bytes)
            tmp.flush()
            return verify_document(pdf_path=tmp.name)
    return verify_document(text=text or "")
