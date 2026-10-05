"""
chat.py -- Question-answering and trace endpoints.

POST /api/ask    -- Ask a question about an uploaded document.
GET  /api/trace/{run_id} -- Retrieve the full trace for a run.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tools.document_tools import DOCUMENTS
from agent.agent import DocumentAgent
from agent.prompts import PLANNER_SYSTEM_PROMPT
from agent.session import get_session, create_session
from services.llm import create_llm_client


router = APIRouter()

# In-memory store for run traces (keyed by run_id)
_run_store: dict[str, dict] = {}


class AskRequest(BaseModel):
    doc_id: str
    question: str
    session_id: str = None


@router.post("/api/session")
async def create_new_session():
    """Create a new session memory."""
    sess = create_session()
    return {"session_id": sess.session_id}


@router.post("/api/ask")
async def ask_question(req: AskRequest):
    """Ask the agent a question about an uploaded document."""

    # -- Validate inputs -----------------------------------------------
    if not req.doc_id or not req.doc_id.strip():
        raise HTTPException(status_code=400, detail="doc_id is required.")

    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty.")

    if req.doc_id not in DOCUMENTS:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{req.doc_id}' not found. Please upload a PDF first."
        )

    # -- Build document metadata for the agent -------------------------
    doc = DOCUMENTS[req.doc_id]
    known_documents = [{
        "doc_id": doc.doc_id,
        "title": doc.title,
        "pages": doc.page_count,
    }]

    # -- Create LLM + agent (fresh per question) -----------------------
    try:
        llm = create_llm_client(system_prompt=PLANNER_SYSTEM_PROMPT)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"LLM configuration error: {exc}"
        )

    agent = DocumentAgent(
        llm_client=llm,
        known_documents=known_documents,
    )

    # -- Run the agent -------------------------------------------------
    try:
        result = agent.answer(
            question=req.question.strip(), 
            session_id=req.session_id,
            doc_id=req.doc_id
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Agent error: {exc}"
        )

    # -- Build response ------------------------------------------------
    verification = result.verification
    status = verification.status if verification else "UNKNOWN"
    supporting_pages = verification.supporting_pages if verification else []

    # Sanitize trace for the frontend (remove internal paths, etc.)
    safe_trace = _sanitize_trace(result.trace)

    # Store the run for /api/trace/{run_id}
    run_data = {
        "run_id": result.run_id,
        "question": result.question,
        "answer": result.answer,
        "status": status,
        "supporting_pages": supporting_pages,
        "calls_used": result.calls_used,
        "calls_remaining": result.calls_remaining,
        "trace": safe_trace,
    }
    _run_store[result.run_id] = run_data

    return run_data


@router.get("/api/trace/{run_id}")
async def get_trace(run_id: str):
    """Retrieve the complete trace for a specific agent run."""
    if run_id not in _run_store:
        raise HTTPException(
            status_code=404,
            detail=f"Run '{run_id}' not found."
        )
    return _run_store[run_id]


def _sanitize_trace(trace: list[dict]) -> list[dict]:
    """
    Clean up the trace for frontend consumption.

    Removes internal fields and truncates very large text results
    to keep the API response manageable.
    """
    safe = []
    for entry in trace:
        clean = {}

        if "type" in entry:
            # Meta-events: VERIFICATION_STARTED, VERIFICATION_RESULT, FINAL_ANSWER, PLANNING_SUMMARY
            clean["type"] = entry["type"]
            if "result" in entry:
                clean["result"] = entry["result"]
            if "answer" in entry:
                clean["answer"] = entry["answer"]
            if entry["type"] == "PLANNING_SUMMARY":
                clean["question_type"] = entry.get("question_type")
                clean["strategy"] = entry.get("strategy")
                clean["calls_used"] = entry.get("calls_used")
                clean["tool_call_sequence"] = entry.get("tool_call_sequence")
        else:
            # Tool call entries
            clean["call_number"] = entry.get("call_number")
            clean["tool"] = entry.get("tool")
            clean["arguments"] = entry.get("arguments", {})
            clean["success"] = entry.get("success", False)
            clean["duration_ms"] = entry.get("duration_ms", 0)

            if entry.get("success"):
                result = entry.get("result")
                # Truncate page text in trace to keep response small
                if isinstance(result, dict) and "text" in result:
                    text = result["text"]
                    if len(text) > 500:
                        text = text[:500] + "..."
                    clean["result"] = {**result, "text": text}
                else:
                    clean["result"] = result
            else:
                clean["error"] = entry.get("error", "Unknown error")

        safe.append(clean)

    return safe
