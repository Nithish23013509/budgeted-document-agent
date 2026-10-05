"""
main.py -- FastAPI application for the Budgeted Document-Answering Agent.

Run:
    uvicorn main:app --reload --port 8000

Docs:
    http://localhost:8000/docs
"""

import sys

# Force UTF-8 encoding for Windows console
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.upload import router as upload_router
from api.chat import router as chat_router


# ── App ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Budgeted Document-Answering Agent",
    description=(
        "An AI agent that answers questions about uploaded PDF documents "
        "using a strict 6-tool-call budget. No RAG, no embeddings, "
        "no vector databases."
    ),
    version="1.0.0",
)


# ── CORS (for React dev server) ──────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routers ──────────────────────────────────────────────────────────

app.include_router(upload_router)
app.include_router(chat_router)


# ── Health ───────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}
