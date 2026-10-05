"""
planner.py -- LLM planner that decides the next tool action.

The planner:
    1. Sends the current context to the LLM.
    2. Parses the JSON response.
    3. Validates the action and arguments.
    4. Retries once if the output is malformed.
    5. Returns a PlannerDecision.

The planner NEVER executes tools. It only returns a decision.
Execution goes through the Step 2 harness.
"""

import json
import re
from dataclasses import dataclass, field

from services.llm import LLMClient, LLMError


# -- Exceptions --------------------------------------------------------

class PlannerValidationError(Exception):
    """Raised when the planner's JSON output fails validation."""
    pass


# -- Data classes ------------------------------------------------------

@dataclass
class PlannerDecision:
    """A single decision from the LLM planner."""
    action: str              # tool name or "FINAL"
    arguments: dict = field(default_factory=dict)
    reason: str = ""
    question_type: str = "GENERAL"
    strategy: str = ""


# -- Constants ---------------------------------------------------------

ALLOWED_ACTIONS = frozenset({
    "list_documents",
    "list_headings",
    "search_keyword",
    "get_page",
    "FINAL",
})

# Actions that should never be allowed -- common LLM hallucinations
BLOCKED_ACTIONS = frozenset({
    "shell", "python", "execute", "browse", "read_file",
    "open_pdf", "database_query", "eval", "exec", "os.system",
    "subprocess", "open", "import", "delete_file",
})


# -- Planner -----------------------------------------------------------

class Planner:
    """
    Calls the LLM to decide the next document-tool action.

    Usage:
        planner = Planner(llm_client)
        decision = planner.plan(context_string)
    """

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def plan(self, context: str) -> PlannerDecision:
        """
        Ask the LLM for the next action, parse, and validate.

        If the first response is malformed, retries once with a
        correction prompt. If the retry also fails, returns FINAL
        as a safe fallback (no tool is executed).

        Args:
            context: The fully assembled planner context string.

        Returns:
            A validated PlannerDecision.
        """
        # -- First attempt ---------------------------------------------
        try:
            raw = self.llm.generate(context)
            parsed = self._extract_json(raw)
            return self._validate(parsed)

        except (json.JSONDecodeError, PlannerValidationError, LLMError) as first_error:
            # -- Retry once with a correction prompt -------------------
            retry_prompt = (
                "Your previous response could not be parsed as a valid action.\n"
                f"Error: {first_error}\n\n"
                "Please return ONLY a valid JSON object with exactly these fields:\n"
                '{\n'
                '    "question_type": "DIRECT_FACT | BROAD_TOPIC | MULTI_PART | COMPARISON | FOLLOW_UP | CONTRADICTION | MISSING_INFORMATION | GENERAL",\n'
                '    "strategy": "Brief description of retrieval strategy",\n'
                '    "action": "list_documents | list_headings | search_keyword | get_page | FINAL",\n'
                '    "arguments": { ... },\n'
                '    "reason": "Brief explanation."\n'
                '}\n\n'
                "For search_keyword, arguments must include doc_id and keyword.\n"
                "For get_page, arguments must include doc_id and page_number (integer).\n"
                "For list_headings, arguments must include doc_id.\n"
                "For list_documents and FINAL, arguments should be {}.\n\n"
                f"Original context:\n{context}"
            )

            try:
                raw2 = self.llm.generate(retry_prompt)
                parsed2 = self._extract_json(raw2)
                return self._validate(parsed2)
            except Exception as retry_error:
                # Both attempts failed -- force FINAL (safe: no tool executes)
                return PlannerDecision(
                    action="FINAL",
                    arguments={},
                    reason=(
                        f"Planner could not produce valid output after retry. "
                        f"First error: {first_error}. "
                        f"Retry error: {retry_error}."
                    ),
                )

    # -- JSON extraction -----------------------------------------------

    @staticmethod
    def _extract_json(text: str) -> dict:
        """
        Extract a JSON object from the LLM response.

        Handles:
            - Clean JSON
            - JSON wrapped in markdown code blocks
            - JSON embedded in surrounding prose
        """
        text = text.strip()

        # 1. Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2. Try extracting from markdown code block
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 3. Try finding first { ... } block
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        raise json.JSONDecodeError(
            "No valid JSON object found in LLM response", text, 0
        )

    # -- Validation ----------------------------------------------------

    @staticmethod
    def _validate(data: dict) -> PlannerDecision:
        """
        Validate and sanitize the parsed LLM output.

        Checks:
            - 'action' field exists and is allowed
            - Required arguments per action type
            - page_number is an integer
            - No blocked/hallucinated actions

        Raises:
            PlannerValidationError on any violation.
        """
        if not isinstance(data, dict):
            raise PlannerValidationError(
                f"Expected a JSON object, got {type(data).__name__}"
            )

        action = data.get("action", "")
        if not action:
            raise PlannerValidationError("Missing 'action' field.")

        # Reject blocked actions
        if action.lower() in BLOCKED_ACTIONS:
            raise PlannerValidationError(
                f"Blocked action: '{action}'. "
                f"Only these are allowed: {sorted(ALLOWED_ACTIONS)}"
            )

        # Must be in allowed set
        if action not in ALLOWED_ACTIONS:
            raise PlannerValidationError(
                f"Unknown action: '{action}'. "
                f"Allowed: {sorted(ALLOWED_ACTIONS)}"
            )

        arguments = data.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}

        reason = str(data.get("reason", ""))

        # -- Per-action argument validation ----------------------------

        if action == "get_page":
            if "doc_id" not in arguments:
                raise PlannerValidationError(
                    "get_page requires 'doc_id' in arguments."
                )
            if "page_number" not in arguments:
                raise PlannerValidationError(
                    "get_page requires 'page_number' in arguments."
                )
            try:
                arguments["page_number"] = int(float(arguments["page_number"]))
            except (ValueError, TypeError):
                raise PlannerValidationError(
                    f"page_number must be an integer, "
                    f"got: {arguments['page_number']!r}"
                )

        elif action == "search_keyword":
            if "doc_id" not in arguments:
                raise PlannerValidationError(
                    "search_keyword requires 'doc_id' in arguments."
                )
            if "keyword" not in arguments:
                raise PlannerValidationError(
                    "search_keyword requires 'keyword' in arguments."
                )
            kw = str(arguments["keyword"]).strip()
            if not kw:
                raise PlannerValidationError(
                    "search_keyword 'keyword' must not be empty."
                )
            arguments["keyword"] = kw

        elif action == "list_headings":
            if "doc_id" not in arguments:
                raise PlannerValidationError(
                    "list_headings requires 'doc_id' in arguments."
                )

        elif action == "list_documents":
            # No arguments required
            arguments = {}

        elif action == "FINAL":
            # No arguments required
            arguments = {}

        question_type = str(data.get("question_type", "GENERAL"))
        strategy = str(data.get("strategy", ""))

        return PlannerDecision(
            action=action,
            arguments=arguments,
            reason=reason,
            question_type=question_type,
            strategy=strategy,
        )
