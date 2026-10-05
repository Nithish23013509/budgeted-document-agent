import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from tools.document_tools import (
    get_page,
    list_documents,
    list_headings,
    search_keyword,
)


# ── Exceptions ───────────────────────────────────────────────────────

class ToolBudgetExceeded(Exception):
    """Raised when the agent attempts a 7th document-tool call."""
    pass


class UnknownToolError(Exception):
    """Raised when the agent requests a tool not in TOOL_REGISTRY."""
    pass


# ── Tool Registry ────────────────────────────────────────────────────
# ONLY these four functions may be called by the agent.
# No os.system, subprocess, open, eval, exec, or arbitrary code.

TOOL_REGISTRY: dict[str, Callable] = {
    "list_documents": list_documents,
    "list_headings":  list_headings,
    "search_keyword": search_keyword,
    "get_page":       get_page,
}


# ── Trace log path ──────────────────────────────────────────────────

LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
TRACES_FILE = os.path.join(LOGS_DIR, "traces.jsonl")


def _ensure_logs_dir() -> None:
    """Create logs/ directory if it doesn't exist."""
    os.makedirs(LOGS_DIR, exist_ok=True)


def _append_trace(entry: dict) -> None:
    """Append a single JSON line to traces.jsonl."""
    _ensure_logs_dir()
    with open(TRACES_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


# ── Budget Controller ───────────────────────────────────────────────

class ToolCallBudget:
    """
    Tracks and enforces the per-question tool-call budget.

    MAX_CALLS = 6 document-tool calls per question.
    The final answer generation is separate and does NOT count.
    """

    MAX_CALLS: int = 6

    def __init__(self) -> None:
        self.calls_used: int = 0

    @property
    def calls_remaining(self) -> int:
        return max(0, self.MAX_CALLS - self.calls_used)

    def can_call(self) -> bool:
        """True if at least one document-tool call remains."""
        return self.calls_used < self.MAX_CALLS

    def consume(self) -> None:
        """
        Consume one call from the budget.

        This is called AFTER the tool executes (or fails).
        A failed tool still consumes budget — this is intentional.
        """
        self.calls_used += 1


# ── Agent Run ────────────────────────────────────────────────────────

class AgentRun:
    """
    Represents one question-answering session with traced tool calls.

    Usage:
        run = AgentRun(question="What is the revenue?")
        result = run.execute_tool("search_keyword", doc_id="doc_001", keyword="revenue")
        result = run.execute_tool("get_page", doc_id="doc_001", page_number=12)
        run.set_final_answer("The revenue was $5M.")
        run.print_trace()
    """

    def __init__(self, question: str) -> None:
        self.run_id: str = str(uuid.uuid4())
        self.question: str = question
        self.budget: ToolCallBudget = ToolCallBudget()
        self.calls: list[dict] = []          # ordered trace of all calls
        self.final_answer: str | None = None

    # ── Convenience properties ───────────────────────────────────────

    @property
    def calls_used(self) -> int:
        return self.budget.calls_used

    @property
    def calls_remaining(self) -> int:
        return self.budget.calls_remaining

    @property
    def trace(self) -> list[dict]:
        """Return a copy of the call trace."""
        return list(self.calls)

    # ── Core execution method ────────────────────────────────────────

    def execute_tool(self, tool_name: str, **arguments: Any) -> Any:
        """
        Execute a document tool through the controlled harness.

        Flow:
            1. Validate tool_name against TOOL_REGISTRY.
            2. Check budget — if exhausted, raise ToolBudgetExceeded.
            3. Execute the tool function.
            4. Consume one budget unit (even on failure).
            5. Log the trace entry to memory and to traces.jsonl.
            6. Return the result (or re-raise the tool's exception).

        Args:
            tool_name:  Must be one of the 4 registered tool names.
            **arguments: Keyword arguments forwarded to the tool function.

        Returns:
            The tool's return value.

        Raises:
            UnknownToolError:    If tool_name is not in TOOL_REGISTRY.
            ToolBudgetExceeded:  If 6 calls have already been used.
            Exception:           Any exception the underlying tool raises
                                 (the call is still counted).
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        # ── 1. Registry check ────────────────────────────────────────
        if tool_name not in TOOL_REGISTRY:
            raise UnknownToolError(
                f"Unknown tool: '{tool_name}'. "
                f"Allowed tools: {list(TOOL_REGISTRY.keys())}"
            )

        # ── 2. Budget check (HARD enforcement) ──────────────────────
        #
        #   This is the critical security boundary.
        #   The 7th call is NEVER executed.
        #   The blocked attempt is NOT counted as a call.
        #
        if not self.budget.can_call():
            # Log the blocked attempt for judge visibility
            blocked_entry = {
                "run_id":      self.run_id,
                "call_number": self.budget.calls_used + 1,
                "tool":        tool_name,
                "arguments":   arguments,
                "result":      None,
                "success":     False,
                "error":       "BLOCKED: Tool budget exceeded (6/6 used)",
                "blocked":     True,
                "timestamp":   timestamp,
                "duration_ms": 0,
            }
            _append_trace(blocked_entry)

            raise ToolBudgetExceeded(
                f"Tool budget exceeded: {self.budget.calls_used}/{ToolCallBudget.MAX_CALLS} "
                f"calls used. The 7th call to '{tool_name}' was BLOCKED."
            )

        # ── 3. Execute the tool ──────────────────────────────────────
        tool_fn = TOOL_REGISTRY[tool_name]
        call_number = self.budget.calls_used + 1  # 1-based for the trace

        start = time.perf_counter()
        try:
            result = tool_fn(**arguments)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

            # ── 4. Consume budget (success) ──────────────────────────
            self.budget.consume()

            # ── 5. Build trace entry ─────────────────────────────────
            entry = {
                "run_id":      self.run_id,
                "call_number": call_number,
                "tool":        tool_name,
                "arguments":   arguments,
                "result":      result,
                "success":     True,
                "timestamp":   timestamp,
                "duration_ms": elapsed_ms,
            }
            self.calls.append(entry)
            _append_trace(entry)

            return result

        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

            # ── 4. Consume budget (failure -- still counts!) ─────────
            self.budget.consume()

            # ── 5. Build error trace entry ───────────────────────────
            entry = {
                "run_id":      self.run_id,
                "call_number": call_number,
                "tool":        tool_name,
                "arguments":   arguments,
                "result":      None,
                "success":     False,
                "error":       str(exc),
                "timestamp":   timestamp,
                "duration_ms": elapsed_ms,
            }
            self.calls.append(entry)
            _append_trace(entry)

            raise

    # ── Final answer & Metadata ──────────────────────────────────────
    
    def log_planning_summary(self, decisions: list) -> None:
        """Log the intelligence retrieval strategy trace entry."""
        if not decisions:
            return
            
        first_decision = decisions[0]
        # Calculate tool call sequence
        sequence = [d.action for d in decisions if d.action != "FINAL"]
        
        entry = {
            "run_id": self.run_id,
            "type": "PLANNING_SUMMARY",
            "question_type": getattr(first_decision, "question_type", "GENERAL"),
            "strategy": getattr(first_decision, "strategy", ""),
            "calls_used": self.calls_used,
            "tool_call_sequence": sequence,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.calls.append(entry)
        _append_trace(entry)

    def log_verification_started(self) -> None:
        entry = {
            "run_id": self.run_id,
            "type": "VERIFICATION_STARTED",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.calls.append(entry)
        _append_trace(entry)

    def log_verification_result(self, verification_result: dict) -> None:
        entry = {
            "run_id": self.run_id,
            "type": "VERIFICATION_RESULT",
            "result": verification_result,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.calls.append(entry)
        _append_trace(entry)

    def set_final_answer(self, answer: str) -> None:
        """
        Record the final answer. This does NOT consume a tool call.
        The problem statement says: 6 tool calls + 1 final answer (separate).
        """
        self.final_answer = answer
        entry = {
            "run_id": self.run_id,
            "type": "FINAL_ANSWER",
            "answer": answer,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.calls.append(entry)
        _append_trace(entry)

    # ── Pretty-print trace ───────────────────────────────────────────

    def print_trace(self) -> None:
        """Print a human-readable trace for judges / debugging."""
        print("=" * 60)
        print("  AGENT RUN")
        print("=" * 60)
        print()
        print(f"  Run ID:   {self.run_id}")
        print(f"  Question: {self.question}")
        print(f"  Tool calls: {self.calls_used} / {ToolCallBudget.MAX_CALLS}")
        print()

        for entry in self.calls:
            if "type" in entry:
                # This is a meta-event (verification, final answer)
                print("-" * 60)
                print(f"  EVENT: {entry['type']}")
                if "result" in entry:
                    print(f"    {json.dumps(entry['result'], indent=4, ensure_ascii=False)}")
                elif "answer" in entry:
                    print(f"    {entry['answer']}")
                print()
                continue
                
            print("-" * 60)
            status = "OK" if entry["success"] else "X FAILED"
            print(f"  CALL {entry['call_number']}  [{status}]")
            print(f"  Tool: {entry['tool']}")
            print(f"  Arguments:")
            print(f"    {json.dumps(entry['arguments'], indent=4, default=str)}")
            print()

            if entry["success"]:
                result_str = json.dumps(entry["result"], indent=4, ensure_ascii=False, default=str)
                # Truncate very long results for terminal readability
                if len(result_str) > 600:
                    result_str = result_str[:600] + "\n    ... (truncated)"
                print(f"  Result:")
                print(f"    {result_str}")
            else:
                print(f"  Error: {entry.get('error', 'Unknown error')}")
            print()

        if self.final_answer is not None:
            print("-" * 60)
            print(f"  FINAL ANSWER:")
            print(f"    {self.final_answer}")
            print()

        print("=" * 60)
