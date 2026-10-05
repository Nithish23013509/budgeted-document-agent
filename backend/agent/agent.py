"""
agent.py -- The controlled agent loop.

Architecture:

    User Question
          |
          v
    DocumentAgent.answer()
          |
          v
    +-----loop------+
    |                |
    | build context  |
    | ask planner    |
    | validate       |
    | if FINAL: stop |
    | execute tool   | <-- goes through Step 2 harness
    | store evidence |
    |                |
    +----------------+
          |
          v
    AgentResult(status="READY_FOR_VERIFICATION")

Key invariants:
    - The LLM NEVER directly executes Python functions.
    - All tool calls go through AgentRun.execute_tool() (harness).
    - Budget is enforced by the harness (max 6 calls).
    - Document text is treated as untrusted data.
    - The agent can return "Insufficient information" via FINAL.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from agent.harness import AgentRun, ToolBudgetExceeded
from agent.planner import Planner, PlannerDecision
from agent.prompts import build_planner_context
from agent.session import get_session, SessionMemory
from services.llm import LLMClient


# -- Evidence ----------------------------------------------------------

@dataclass
class EvidenceItem:
    """
    One piece of retrieved evidence with provenance.

    The verifier (Step 4) needs to know WHERE information came from.
    """
    doc_id: str
    page: int
    text: str
    retrieved_by: str  # always "get_page" for now


# -- Agent result ------------------------------------------------------

@dataclass
class AgentResult:
    """
    The output of one agent run, ready for the verification step.

    This does NOT contain a final answer yet.
    The verifier (Step 4) will generate the answer from the evidence.
    """
    question: str
    evidence: list[EvidenceItem] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)
    planner_decisions: list[PlannerDecision] = field(default_factory=list)
    previous_actions: list[dict] = field(default_factory=list)
    run: AgentRun | None = None
    status: str = "READY_FOR_VERIFICATION"

    def print_result(self) -> None:
        """Print a judge-friendly summary of the agent run."""
        print("=" * 60)
        print("  AGENT RESULT")
        print("=" * 60)
        print()
        print(f"  Question: {self.question}")
        print(f"  Status:   {self.status}")
        if self.run:
            print(f"  Tool calls: {self.run.calls_used} / 6")
        print(f"  Evidence pages: {len(self.evidence)}")
        print()

        # Show planner decisions
        for i, d in enumerate(self.planner_decisions, 1):
            prefix = "  >> " if d.action == "FINAL" else "  "
            print(f"{prefix}Decision {i}: {d.action}")
            if d.arguments:
                args_str = json.dumps(d.arguments, default=str)
                print(f"     Args: {args_str}")
            if d.reason:
                reason_short = d.reason[:120]
                if len(d.reason) > 120:
                    reason_short += "..."
                print(f"     Reason: {reason_short}")

        # Show evidence snippets
        if self.evidence:
            print()
            print("  Evidence collected:")
            for ev in self.evidence:
                snippet = ev.text[:100].replace("\n", " ")
                if len(ev.text) > 100:
                    snippet += "..."
                print(f"    Page {ev.page} ({ev.doc_id}): \"{snippet}\"")

        print()
        print("=" * 60)


# -- Document agent ----------------------------------------------------

class DocumentAgent:
    """
    The main agent loop.

    Given a user question, it iteratively:
        1. Builds context for the LLM planner.
        2. Asks the planner for the next action.
        3. Validates and executes the tool through the harness.
        4. Stores the result as evidence.
        5. Repeats until FINAL or budget exhaustion.

    Usage:
        llm = create_llm_client(system_prompt=PLANNER_SYSTEM_PROMPT)
        agent = DocumentAgent(llm_client=llm, known_documents=[...])
        result = agent.answer("What was the revenue?")
    """

    # Safety limit: max planner iterations (tool calls + FINAL + retries)
    MAX_PLANNER_ITERATIONS = 10

    def __init__(
        self,
        llm_client: LLMClient,
        known_documents: list[dict] | None = None,
    ) -> None:
        """
        Args:
            llm_client:       A configured LLMClient (with system prompt).
            known_documents:  Pre-known document metadata [{doc_id, title, pages}].
                              If provided, the agent won't waste a call on
                              list_documents().
        """
        self.planner = Planner(llm_client)
        self.known_documents: list[dict] = list(known_documents or [])

    def answer(self, question: str, session_id: str = None, doc_id: str = None) -> "models.verification.FinalAnswer":
        """
        Run the agent loop for a single user question.

        Args:
            question: The user's natural-language question.
            session_id: Optional session identifier for memory.
            doc_id: The primary document ID this question is about.

        Returns:
            FinalAnswer containing the verified text and sources.
        """
        import models.verification
        session = get_session(session_id)
        
        run = AgentRun(question=question)
        evidence: list[EvidenceItem] = []
        previous_actions: list[dict] = []
        planner_decisions: list[PlannerDecision] = []

        # Local copy of known docs -- may be updated by list_documents
        documents = list(self.known_documents)

        for _iteration in range(self.MAX_PLANNER_ITERATIONS):

            # -- Build context for this turn ---------------------------
            session_ev = [
                {"doc_id": ev.doc_id, "page": ev.page, "text": ev.text, "retrieved_by": ev.source}
                for ev in session.get_evidence(doc_id)
            ] if doc_id else []

            context = build_planner_context(
                question=question,
                documents=documents,
                evidence=[
                    {"doc_id": e.doc_id, "page": e.page,
                     "text": e.text, "retrieved_by": e.retrieved_by}
                    for e in evidence
                ],
                previous_actions=previous_actions,
                calls_used=run.calls_used,
                calls_remaining=run.calls_remaining,
                session_evidence=session_ev,
                conversation_history=[
                    {"role": msg.role, "content": msg.content}
                    for msg in session.conversation_history
                ]
            )

            # -- Ask the planner for the next action -------------------
            decision = self.planner.plan(context)
            planner_decisions.append(decision)

            # -- FINAL -> stop -----------------------------------------
            if decision.action == "FINAL":
                break

            # -- Budget check (defense in depth) -----------------------
            # The harness enforces this too, but we check here to
            # avoid a wasted LLM call on the next iteration.
            if run.calls_remaining <= 0:
                planner_decisions.append(PlannerDecision(
                    action="FINAL",
                    arguments={},
                    reason="Budget exhausted (forced FINAL by agent loop).",
                ))
                break

            # -- Execute through the Step 2 harness --------------------
            action_record: dict = {
                "tool": decision.action,
                "arguments": dict(decision.arguments),
                "reason": decision.reason,
            }

            # -- Duplicate & Loop Protection ---------------------------
            is_duplicate = False
            for pa in previous_actions:
                if pa["tool"] == decision.action and pa["arguments"] == decision.arguments:
                    is_duplicate = True
                    break

            if is_duplicate:
                action_record["result"] = None
                action_record["success"] = False
                action_record["error"] = "DUPLICATE_CALL: You already made this exact call. Try a different search term, retrieve a different page, or choose FINAL."
                previous_actions.append(action_record)
                continue

            try:
                result = run.execute_tool(
                    decision.action, **decision.arguments
                )
                action_record["result"] = result
                action_record["success"] = True

                # -- Store evidence from get_page ----------------------
                if decision.action == "get_page" and isinstance(result, dict):
                    page_text = result.get("text", "")
                    page_num = result.get("page", 0)
                    doc_id_result = result.get("doc_id", "")
                    evidence.append(EvidenceItem(
                        doc_id=doc_id_result,
                        page=page_num,
                        text=page_text,
                        retrieved_by="get_page",
                    ))
                    # Also add to session memory
                    if doc_id_result:
                        session.add_evidence(
                            doc_id=doc_id_result,
                            page=page_num,
                            text=page_text,
                            run_id=run.run_id
                        )

                # -- Update known documents from list_documents --------
                if decision.action == "list_documents" and isinstance(result, list):
                    documents = result

            except ToolBudgetExceeded:
                # Harness blocked the call -- stop the loop
                action_record["result"] = None
                action_record["success"] = False
                action_record["error"] = "BLOCKED by harness: tool budget exceeded"
                previous_actions.append(action_record)

                planner_decisions.append(PlannerDecision(
                    action="FINAL",
                    arguments={},
                    reason="Budget exceeded (harness blocked the call).",
                ))
                break

            except Exception as exc:
                # Tool execution failed (bad page number, etc.)
                # The harness already counted this call.
                action_record["result"] = None
                action_record["success"] = False
                action_record["error"] = str(exc)

            previous_actions.append(action_record)

        # -- Step 4: Verification ------------------------------------------
        run.log_planning_summary(planner_decisions)
        run.log_verification_started()
        
        # We need a separate LLM client for the verifier, potentially with 
        # a different system prompt, but we can just use the provided LLMClient 
        # since we will pass the verifier's system prompt to it. Wait, the 
        # LLMClient has the system_prompt baked in at init.
        # So we should create a new LLMClient for the verifier/generator.
        # To do this cleanly, we can import create_llm_client here.
        from services.llm import create_llm_client
        from agent.prompts import VERIFIER_SYSTEM_PROMPT
        from agent.verifier import Verifier
        from agent.answer_generator import AnswerGenerator
        
        verifier_llm = create_llm_client(system_prompt=VERIFIER_SYSTEM_PROMPT)
        verifier = Verifier(verifier_llm)
        
        evidence_dicts = [
            {"doc_id": e.doc_id, "page": e.page, "text": e.text, "retrieved_by": e.retrieved_by}
            for e in evidence
        ]
        session_ev_dicts = [
            {"doc_id": ev.doc_id, "page": ev.page, "text": ev.text, "retrieved_by": ev.source}
            for ev in session.get_evidence(doc_id)
        ] if doc_id else []
        
        verification_result = verifier.verify(question, evidence_dicts, session_ev_dicts)
        
        run.log_verification_result(verification_result.to_dict())
        
        # -- Step 4: Final Answer Generation -------------------------------
        # For the final answer generator, we don't need a strict JSON mode
        # system prompt. We can use a simple one.
        from agent.prompts import FINAL_ANSWER_PROMPT
        generator_llm = create_llm_client(system_prompt=FINAL_ANSWER_PROMPT)
        generator = AnswerGenerator(generator_llm)
        
        final_answer = generator.generate(question, verification_result)
        run.set_final_answer(final_answer.answer)
        
        # Add to session conversation history
        session.add_message("user", question)
        session.add_message("assistant", final_answer.answer)

        # Populate run metadata for the API
        final_answer.run_id = run.run_id
        final_answer.calls_used = run.calls_used
        final_answer.calls_remaining = run.calls_remaining
        final_answer.trace = run.trace

        return final_answer
