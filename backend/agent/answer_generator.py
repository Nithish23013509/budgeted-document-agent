"""
answer_generator.py -- Final Answer Generator (Step 4).

Takes the VerificationResult and generates a final natural-language
answer, including source citations. DOES NOT make document tool calls.
"""

from models.verification import VerificationResult, FinalAnswer, STATUS_INSUFFICIENT
from agent.prompts import FINAL_ANSWER_PROMPT, build_final_answer_context
from services.llm import LLMClient, LLMError


class AnswerGenerator:
    """
    Generates the final natural-language answer with citations.
    """

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def generate(self, question: str, verification_result: VerificationResult) -> FinalAnswer:
        """
        Produce the final answer text.

        Args:
            question: The user's original question.
            verification_result: The parsed output of the Verifier.

        Returns:
            A FinalAnswer object containing the string answer and citations.
        """
        # If insufficient, skip the LLM call entirely to save time/budget
        if verification_result.status == STATUS_INSUFFICIENT:
            answer_text = "Insufficient information."
            if verification_result.answer and verification_result.answer != "Insufficient information.":
                answer_text += f" {verification_result.answer}"
        else:
            context = build_final_answer_context(question, verification_result.to_dict())
            try:
                # Call LLM without JSON mode
                answer_text = self.llm.generate(context, require_json=False).strip()
            except Exception as exc:
                answer_text = f"Error generating answer: {exc}"

        sources_str = self._format_sources(verification_result.supporting_pages)
        
        # Append sources to final output text
        if sources_str:
            final_output = f"{answer_text}\n\nSources: {sources_str}"
        else:
            final_output = answer_text

        return FinalAnswer(
            question=question,
            answer=final_output,
            sources=sources_str,
            verification=verification_result
        )

    @staticmethod
    def _format_sources(pages: list[int]) -> str:
        """Format a list of page numbers into a citation string."""
        if not pages:
            return ""
            
        unique_pages = sorted(list(set(pages)))
        
        if len(unique_pages) == 1:
            return f"page {unique_pages[0]}"
        elif len(unique_pages) == 2:
            return f"pages {unique_pages[0]} and {unique_pages[1]}"
        else:
            p_strs = [str(p) for p in unique_pages]
            return f"pages {', '.join(p_strs[:-1])}, and {p_strs[-1]}"
