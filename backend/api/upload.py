"""
upload.py -- PDF upload endpoint.

POST /api/upload
  - Accepts multipart/form-data with a PDF file.
  - Validates extension, MIME type, and readability.
  - Saves to storage/uploads/ with a unique ID.
  - Registers the document via register_document().
  - Returns metadata (doc_id, title, pages).
"""

import os
import uuid

from fastapi import APIRouter, File, UploadFile, HTTPException

from tools.document_tools import register_document


router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage", "uploads")


@router.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """Upload a PDF and register it as a document."""

    # -- Validate file exists ------------------------------------------
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    # -- Validate extension --------------------------------------------
    filename = file.filename.strip()
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are accepted. Please upload a .pdf file."
        )

    # -- Validate MIME type (basic check) ------------------------------
    if file.content_type and "pdf" not in file.content_type.lower():
        raise HTTPException(
            status_code=400,
            detail=f"Invalid content type: {file.content_type}. Expected a PDF."
        )

    # -- Read file content ---------------------------------------------
    try:
        content = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unable to read file: {exc}"
        )

    if not content or len(content) < 100:
        raise HTTPException(
            status_code=400,
            detail="File appears to be empty or too small to be a valid PDF."
        )

    # -- Save to disk --------------------------------------------------
    doc_id = str(uuid.uuid4())
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    save_path = os.path.join(UPLOAD_DIR, f"{doc_id}.pdf")

    try:
        with open(save_path, "wb") as f:
            f.write(content)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save file: {exc}"
        )

    # -- Register document using existing tool -------------------------
    try:
        meta = register_document(
            doc_id=doc_id,
            title=filename,
            file_path=save_path,
        )
    except Exception as exc:
        # Clean up saved file on failure
        if os.path.exists(save_path):
            os.remove(save_path)
        raise HTTPException(
            status_code=400,
            detail=f"Unable to read this PDF. Please try another PDF. Error: {exc}"
        )

    return {
        "doc_id": meta["doc_id"],
        "title": meta["title"],
        "pages": meta["pages"],
    }
