"""
verification.py -- Data models for the evidence verification pipeline.

These models are used by the verifier and answer generator (Step 4).
They are deliberately simple dataclasses -- no framework dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# =====================================================================
#  Evidence
# =====================================================================

@dataclass
class Evidence:
    """
    One piece of retrieved evidence with full provenance.

    Every claim the verifier considers must trace back to a specific
    page in a specific document, retrieved by a specific tool call.
    """
    doc_id: str
    page: int
    text: str
    source: str  # tool that retrieved it, e.g. "get_page"


# =====================================================================
#  Conflict
# =====================================================================

@dataclass
class Conflict:
    """
    Two statements from the document that contradict each other.

    The verifier records these so judges can see how contradictions
    were detected and resolved (or left unresolved).
    """
    page_a: int
    statement_a: str
    page_b: int
    statement_b: str
    resolution: str  # how the conflict was resolved, or "unresolved"


# =====================================================================
#  VerificationResult
# =====================================================================

# Allowed status values
STATUS_ANSWERED = "ANSWERED"
STATUS_INSUFFICIENT = "INSUFFICIENT_INFORMATION"
STATUS_CONFLICT = "CONFLICT_REQUIRES_REVIEW"


@dataclass
class VerificationResult:
    """
    The output of the evidence verifier.

    This is consumed by the AnswerGenerator to produce the final
    user-facing answer.

    Attributes:
        status:           One of ANSWERED, INSUFFICIENT_INFORMATION,
                          or CONFLICT_REQUIRES_REVIEW.
        answer:           The verified answer text (empty for insufficient).
        reason:           Why the verifier reached this conclusion.
        supporting_pages: Page numbers that support the answer.
        conflicts:        Any contradictions found in the evidence.
        confidence:       "high", "medium", or "low".
    """
    status: str
    answer: str = ""
    reason: str = ""
    supporting_pages: list[int] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    confidence: str = "high"

    def to_dict(self) -> dict:
        """Serialize for LLM context and trace logging."""
        return {
            "status": self.status,
            "answer": self.answer,
            "reason": self.reason,
            "supporting_pages": self.supporting_pages,
            "conflicts": [
                {
                    "page_a": c.page_a,
                    "statement_a": c.statement_a,
                    "page_b": c.page_b,
                    "statement_b": c.statement_b,
                    "resolution": c.resolution,
                }
                for c in self.conflicts
            ],
            "confidence": self.confidence,
        }


# =====================================================================
#  FinalAnswer
# =====================================================================

@dataclass
class FinalAnswer:
    """
    The complete, user-facing answer with source citations.

    This is the terminal output of the entire pipeline:
        Planner -> Harness -> Verifier -> AnswerGenerator -> FinalAnswer
    """
    question: str
    answer: str
    sources: str           # e.g. "page 15" or "pages 8 and 32"
    verification: VerificationResult | None = None
    run_id: str = ""
    calls_used: int = 0
    calls_remaining: int = 6
    trace: list[dict] = field(default_factory=list)

