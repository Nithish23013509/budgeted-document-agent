const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

export async function uploadPdf(file) {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Upload failed");
  }

  return res.json();
}

export async function createSession() {
  const res = await fetch(`${API_BASE}/session`, {
    method: "POST",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Could not create session");
  }
  return res.json();
}

export async function askQuestion(docId, question, sessionId) {
  const res = await fetch(`${API_BASE}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_id: docId, question, session_id: sessionId }),
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Agent encountered an error");
  }

  return res.json();
}

export async function getTrace(runId) {
  const res = await fetch(`${API_BASE}/trace/${runId}`);

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Could not fetch trace");
  }

  return res.json();
}
