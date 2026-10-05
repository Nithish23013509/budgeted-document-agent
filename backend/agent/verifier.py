"""
verifier.py -- The Evidence Verifier (Step 4).

Takes the evidence collected by the planner loop and determines
if it is sufficient, consistent, and answers the question.
"""

import json
import re

from models.verification import Conflict, VerificationResult, STATUS_ANSWERED, STATUS_INSUFFICIENT, STATUS_CONFLICT
from agent.prompts import VERIFIER_SYSTEM_PROMPT, build_verifier_context
from services.llm import LLMClient, LLMError


class Verifier:
    """
    Verifies evidence against the user's question.
    """

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        # The llm instance must be initialized with VERIFIER_SYSTEM_PROMPT.
        # This is handled in the agent loop or factory.

    def verify(self, question: str, evidence: list[dict], session_evidence: list[dict] = None) -> VerificationResult:
        """
        Ask the LLM to verify the collected evidence.

        Args:
            question: The user's original question.
            evidence: List of dictionaries representing EvidenceItem objects.
            session_evidence: List of dictionaries representing evidence from earlier in the session.

        Returns:
            A populated VerificationResult object.
        """
        context = build_verifier_context(question, evidence, session_evidence)
        
        try:
            raw_response = self.llm.generate(context)
            parsed = self._extract_json(raw_response)
            return self._parse_to_model(parsed)
        except (json.JSONDecodeError, LLMError) as exc:
            # Safe fallback if verification completely fails
            return VerificationResult(
                status=STATUS_INSUFFICIENT,
                answer="Insufficient information.",
                reason=f"Verification failed: {exc}",
                supporting_pages=[],
                conflicts=[],
                confidence="low"
            )

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Extract a JSON object from the LLM response."""
        text = text.strip()
        
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        raise json.JSONDecodeError("No valid JSON object found in verifier response", text, 0)

    @staticmethod
    def _parse_to_model(data: dict) -> VerificationResult:
        """Convert the raw JSON dict into a VerificationResult object."""
        status = data.get("status", STATUS_INSUFFICIENT)
        if status not in (STATUS_ANSWERED, STATUS_INSUFFICIENT, STATUS_CONFLICT):
            status = STATUS_INSUFFICIENT

        answer = str(data.get("answer", ""))
        if status == STATUS_INSUFFICIENT and not answer:
            answer = "Insufficient information."

        reason = str(data.get("reason", ""))
        
        # Ensure pages are ints
        raw_pages = data.get("supporting_pages", [])
        if not isinstance(raw_pages, list):
            raw_pages = []
        supporting_pages = []
        for p in raw_pages:
            try:
                supporting_pages.append(int(float(p)))
            except (ValueError, TypeError):
                pass
                
        # Parse conflicts
        raw_conflicts = data.get("conflicts", [])
        if not isinstance(raw_conflicts, list):
            raw_conflicts = []
        conflicts = []
        for c in raw_conflicts:
            if isinstance(c, dict):
                try:
                    conflicts.append(Conflict(
                        page_a=int(c.get("page_a", 0)),
                        statement_a=str(c.get("statement_a", "")),
                        page_b=int(c.get("page_b", 0)),
                        statement_b=str(c.get("statement_b", "")),
                        resolution=str(c.get("resolution", "unresolved"))
                    ))
                except (ValueError, TypeError):
                    pass
                    
        confidence = str(data.get("confidence", "low"))

        return VerificationResult(
            status=status,
            answer=answer,
            reason=reason,
            supporting_pages=supporting_pages,
            conflicts=conflicts,
            confidence=confidence
        )
