"""
pdf_parser.py — Internal PDF parsing layer.

This module is INTERNAL. The future LLM agent must NEVER receive
PDFDocument instances or raw page text directly. All agent access
goes through the four tool functions in document_tools.py.
"""

import os
import pymupdf  # PyMuPDF


class PDFParsingError(Exception):
    """Raised when a PDF cannot be opened or parsed."""
    pass


class PDFDocument:
    """
    Internal representation of a parsed PDF document.

    Attributes:
        doc_id:    Unique identifier for this document.
        title:     Human-readable title (typically the filename).
        file_path: Absolute path to the PDF file on disk.
        pages:     Dict mapping 1-based page numbers to extracted text.
        headings:  List of heading dicts from the PDF's built-in TOC.
    """

    def __init__(self, doc_id: str, title: str, file_path: str) -> None:
        self.doc_id = doc_id
        self.title = title
        self.file_path = file_path
        self.pages: dict[int, str] = {}       # {1: "text…", 2: "text…", …}
        self.headings: list[dict] = []         # [{"level": 1, "title": "…", "page": 1}, …]

        self._load(file_path)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load(self, file_path: str) -> None:
        """Open the PDF, extract pages and TOC."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF not found: {file_path}")

        try:
            doc = pymupdf.open(file_path)
        except Exception as exc:
            raise PDFParsingError(
                f"Failed to open PDF '{file_path}': {exc}"
            ) from exc

        if doc.page_count == 0:
            doc.close()
            raise PDFParsingError(f"PDF has zero pages: {file_path}")

        # --- Extract text page-by-page (1-based) ---------------------
        for i in range(doc.page_count):
            page = doc[i]
            self.pages[i + 1] = page.get_text("text")

        # --- Extract built-in Table of Contents ----------------------
        toc = doc.get_toc()  # list of [level, title, page_number]
        for entry in toc:
            self.headings.append({
                "level": entry[0],
                "title": entry[1],
                "page":  entry[2],
            })

        doc.close()

    # ------------------------------------------------------------------
    # Public query methods (used by document_tools.py)
    # ------------------------------------------------------------------

    @property
    def page_count(self) -> int:
        """Total number of pages."""
        return len(self.pages)

    def get_page(self, page_number: int) -> str:
        """
        Return the text of exactly one page.

        Args:
            page_number: 1-based page number.

        Raises:
            ValueError: If the page number is out of range.
        """
        if not isinstance(page_number, int) or page_number < 1 or page_number > self.page_count:
            raise ValueError(
                f"Invalid page number {page_number}. "
                f"Document '{self.doc_id}' has pages 1–{self.page_count}."
            )
        return self.pages[page_number]

    def get_headings(self) -> list[dict]:
        """
        Return the PDF's built-in TOC as a list of heading dicts.

        Returns an empty list if the PDF has no TOC.
        """
        return list(self.headings)  # defensive copy

    def search_keyword(self, keyword: str) -> list[int]:
        """
        Case-insensitive keyword search across all pages.

        Args:
            keyword: The search term (whitespace is trimmed).

        Returns:
            Sorted list of 1-based page numbers where the keyword appears.

        Raises:
            ValueError: If the keyword is empty after trimming.
        """
        keyword = keyword.strip()
        if not keyword:
            raise ValueError("Keyword must not be empty.")

        keyword_lower = keyword.lower()
        matching_pages: list[int] = []

        for page_num, text in self.pages.items():
            if keyword_lower in text.lower():
                matching_pages.append(page_num)

        return sorted(matching_pages)
