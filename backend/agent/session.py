import uuid
from typing import Dict, List
from pydantic import BaseModel, Field

class SessionEvidence(BaseModel):
    doc_id: str
    page: int
    text: str
    source: str = "get_page"
    retrieved_in_run_id: str

class Message(BaseModel):
    role: str
    content: str

class SessionMemory(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_history: List[Message] = Field(default_factory=list)
    # Mapping of doc_id -> list of retrieved evidence
    evidence_by_doc: Dict[str, List[SessionEvidence]] = Field(default_factory=dict)

    def add_message(self, role: str, content: str):
        self.conversation_history.append(Message(role=role, content=content))

    def add_evidence(self, doc_id: str, page: int, text: str, run_id: str):
        if doc_id not in self.evidence_by_doc:
            self.evidence_by_doc[doc_id] = []
        
        # Avoid duplicate pages
        for ev in self.evidence_by_doc[doc_id]:
            if ev.page == page:
                return
                
        self.evidence_by_doc[doc_id].append(
            SessionEvidence(
                doc_id=doc_id,
                page=page,
                text=text,
                source="get_page",
                retrieved_in_run_id=run_id
            )
        )

    def get_evidence(self, doc_id: str) -> List[SessionEvidence]:
        return self.evidence_by_doc.get(doc_id, [])

# Simple in-memory global store
_STORE: Dict[str, SessionMemory] = {}

def create_session() -> SessionMemory:
    sess = SessionMemory()
    _STORE[sess.session_id] = sess
    return sess

def get_session(session_id: str) -> SessionMemory:
    if not session_id or session_id not in _STORE:
        # Auto-create if missing for robustness
        sess = SessionMemory(session_id=session_id or str(uuid.uuid4()))
        _STORE[sess.session_id] = sess
        return sess
    return _STORE[session_id]
