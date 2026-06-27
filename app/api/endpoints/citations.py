"""Citation-integrity API: upload a brief (or paste text) -> structured verdict report.

`POST /api/citations/verify` accepts either a multipart `file` (PDF) or a `text`
form field, runs the M1->M3->M4->M5 pipeline, and returns a
:class:`~app.schemas.citation.VerifyResponse`.
"""
from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas.citation import VerifyResponse
from app.services import pipeline_service

router = APIRouter()


@router.post("/verify", response_model=VerifyResponse)
async def verify(
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
) -> VerifyResponse:
    if file is None and not (text and text.strip()):
        raise HTTPException(status_code=400, detail="Provide a PDF 'file' or non-empty 'text'.")

    if file is not None:
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            tf.write(data)
            tmp_path = tf.name
        try:
            return pipeline_service.verify_document(tmp_path, document_name=file.filename)
        finally:
            os.unlink(tmp_path)

    return pipeline_service.verify_text(text, document_name="pasted text")
