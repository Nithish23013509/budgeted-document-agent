"""
document_tools.py — The ONLY document interface the future agent may use.

This module exposes exactly four tool functions:

    1. list_documents()              → metadata only
    2. list_headings(doc_id)         → TOC only
    3. search_keyword(doc_id, kw)    → page numbers only
    4. get_page(doc_id, page_number) → text of ONE page

Plus one admin function (register_document) used by the backend
to load PDFs — NOT available to the agent.

IMPORTANT ARCHITECTURAL RULE
─────────────────────────────
The future LLM agent must NEVER receive:
  • The DOCUMENTS registry
  • PDFDocument instances
  • Raw page text outside of get_page()

All document access MUST go through the four functions above.
"""

from tools.pdf_parser import PDFDocument, PDFParsingError


# ── Internal registry (hidden from agent) ────────────────────────────
DOCUMENTS: dict[str, PDFDocument] = {}


# ── Admin function (NOT an agent tool) ───────────────────────────────

def register_document(doc_id: str, title: str, file_path: str) -> dict:
    """
    Load a PDF from disk and register it in the document store.

    This is an admin/backend function. The agent does NOT call this.

    Args:
        doc_id:    Unique identifier to assign.
        title:     Human-readable title (e.g. the filename).
        file_path: Path to the PDF file.

    Returns:
        Metadata dict with doc_id, title, and page count.

    Raises:
        FileNotFoundError: If the file does not exist.
        PDFParsingError:   If the PDF cannot be parsed.
        ValueError:        If doc_id is empty.
    """
    if not doc_id or not doc_id.strip():
        raise ValueError("doc_id must not be empty.")

    pdf = PDFDocument(doc_id=doc_id, title=title, file_path=file_path)
    DOCUMENTS[doc_id] = pdf

    return {
        "doc_id": pdf.doc_id,
        "title":  pdf.title,
        "pages":  pdf.page_count,
    }


# ── Agent tool 1 ─────────────────────────────────────────────────────

def list_documents() -> list[dict]:
    """
    Return metadata for every registered document.

    Returns ONLY doc_id, title, and page count.
    NEVER returns page text.
    """
    return [
        {
            "doc_id": doc.doc_id,
            "title":  doc.title,
            "pages":  doc.page_count,
        }
        for doc in DOCUMENTS.values()
    ]


# ── Agent tool 2 ─────────────────────────────────────────────────────

def list_headings(doc_id: str) -> list[dict]:
    """
    Return the table-of-contents / heading structure of a document.

    Returns a list of {"level", "title", "page"} dicts.
    Returns an empty list if the PDF has no built-in TOC.
    NEVER returns page text.

    Raises:
        KeyError: If doc_id is not registered.
    """
    if doc_id not in DOCUMENTS:
        raise KeyError(f"Document not found: '{doc_id}'")

    return DOCUMENTS[doc_id].get_headings()


# ── Agent tool 3 ─────────────────────────────────────────────────────

def search_keyword(doc_id: str, keyword: str) -> list[int]:
    """
    Search for a keyword across all pages of a document.

    Returns ONLY a sorted list of 1-based page numbers.
    NEVER returns page text.

    Args:
        doc_id:  Registered document identifier.
        keyword: Search term (case-insensitive, trimmed).

    Raises:
        KeyError:    If doc_id is not registered.
        ValueError:  If keyword is empty.
    """
    if doc_id not in DOCUMENTS:
        raise KeyError(f"Document not found: '{doc_id}'")

    return DOCUMENTS[doc_id].search_keyword(keyword)


# ── Agent tool 4 ─────────────────────────────────────────────────────

def get_page(doc_id: str, page_number: int) -> dict:
    """
    Return the text of exactly ONE page.

    Args:
        doc_id:      Registered document identifier.
        page_number: 1-based page number (must be a single integer).

    Returns:
        Dict with doc_id, page number, and the page text.

    Raises:
        KeyError:    If doc_id is not registered.
        TypeError:   If page_number is not an integer.
        ValueError:  If page_number is out of range.
    """
    if doc_id not in DOCUMENTS:
        raise KeyError(f"Document not found: '{doc_id}'")

    if not isinstance(page_number, int):
        raise TypeError(
            f"page_number must be a single integer, got {type(page_number).__name__}."
        )

    text = DOCUMENTS[doc_id].get_page(page_number)

    return {
        "doc_id": doc_id,
        "page":   page_number,
        "text":   text,
    }
