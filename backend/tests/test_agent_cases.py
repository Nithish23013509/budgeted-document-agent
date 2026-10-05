import os
import sys

# Force UTF-8 encoding for Windows console
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from tools.document_tools import register_document
from agent.agent import DocumentAgent
from agent.prompts import PLANNER_SYSTEM_PROMPT
from services.llm import create_llm_client

def get_agent(doc_id: str, title: str, pages: int = 20) -> DocumentAgent:
    llm = create_llm_client(system_prompt=PLANNER_SYSTEM_PROMPT)
    agent = DocumentAgent(llm_client=llm)
    agent.known_documents = [{"doc_id": doc_id, "title": title, "pages": pages}]
    return agent

def run_test(agent: DocumentAgent, question: str, expected_status: str, expected_in_answer: list[str] = None):
    ans = agent.answer(question)
    
    status_match = ans.verification.status == expected_status if ans.verification else ans.answer == "Insufficient information."
    if not status_match and ans.verification and expected_status == "INSUFFICIENT_INFORMATION" and ans.verification.status == "CONFLICT_REQUIRES_REVIEW":
        status_match = True # Also valid for missing info

    text_match = True
    ans_text = ans.answer.replace('\u202f', ' ')
    if expected_in_answer:
        for ex in expected_in_answer:
            if ex.lower() not in ans_text.lower():
                text_match = False
                break
                
    passed = status_match and text_match
    return passed, ans

def run_agent_cases():
    base_dir = os.path.dirname(__file__)
    fix_dir = os.path.join(base_dir, "fixtures")
    
    results = []
    import time
    
    # 1. Direct Fact

    doc_id = "fix_direct_fact"
    register_document(doc_id, "Direct Fact", os.path.join(fix_dir, "direct_fact.pdf"))
    a = get_agent(doc_id, "Direct Fact", 1)
    passed, ans = run_test(a, "What was the company's revenue in 2025?", "ANSWERED", ["18.4"])
    results.append(("Direct Fact", passed, ans))
    time.sleep(3)

    # 2. Multi-page
    doc_id = "fix_multi_page"
    register_document(doc_id, "Multi Page", os.path.join(fix_dir, "multi_page.pdf"))
    a = get_agent(doc_id, "Multi Page", 14)
    passed, ans = run_test(a, "How did revenue change from 2024 to 2025?", "ANSWERED", ["10", "12"])
    results.append(("Multi-page Info", passed, ans))
    time.sleep(3)

    # 3. Contradiction / Temporal Update
    doc_id = "fix_temporal"
    register_document(doc_id, "Temporal", os.path.join(fix_dir, "temporal_update.pdf"))
    a = get_agent(doc_id, "Temporal", 30)
    passed, ans = run_test(a, "What is the current project deadline?", "ANSWERED", ["June 25"])
    results.append(("Superseding Information", passed, ans))
    time.sleep(3)

    # 4. Unresolved Conflict
    doc_id = "fix_conflict"
    register_document(doc_id, "Conflict", os.path.join(fix_dir, "contradiction.pdf"))
    a = get_agent(doc_id, "Conflict", 30)
    passed, ans = run_test(a, "What is the project budget?", "INSUFFICIENT_INFORMATION")
    results.append(("Unresolved Conflict", passed, ans))
    time.sleep(3)
    
    # 5. Missing Info
    doc_id = "fix_missing"
    register_document(doc_id, "Missing", os.path.join(fix_dir, "insufficient.pdf"))
    a = get_agent(doc_id, "Missing", 1)
    passed, ans = run_test(a, "What is the CEO's home address?", "INSUFFICIENT_INFORMATION")
    results.append(("Insufficient Information", passed, ans))
    time.sleep(3)

    # 6. Synonym Variation
    doc_id = "fix_synonym"
    register_document(doc_id, "Synonym", os.path.join(fix_dir, "synonym.pdf"))
    a = get_agent(doc_id, "Synonym", 1)
    passed, ans = run_test(a, "What was the company's annual turnover?", "ANSWERED", ["12 million"])
    results.append(("Synonym Variation", passed, ans))
    time.sleep(3)

    
    # 7. Compound Question
    doc_id = "fix_compound"
    register_document(doc_id, "Compound", os.path.join(fix_dir, "compound.pdf"))
    a = get_agent(doc_id, "Compound", 1)
    passed, ans = run_test(a, "Who approved the project and what budget did they approve?", "INSUFFICIENT_INFORMATION")
    results.append(("Compound Sufficiency", passed, ans))

    # 8. Multi Document
    doc_id_a = "fix_multi_a"
    doc_id_b = "fix_multi_b"
    register_document(doc_id_a, "Doc A", os.path.join(fix_dir, "multi_document", "document_a.pdf"))
    register_document(doc_id_b, "Doc B", os.path.join(fix_dir, "multi_document", "document_b.pdf"))
    llm = create_llm_client(system_prompt=PLANNER_SYSTEM_PROMPT)
    agent = DocumentAgent(llm_client=llm)
    agent.known_documents = [
        {"doc_id": doc_id_a, "title": "Doc A", "pages": 1},
        {"doc_id": doc_id_b, "title": "Doc B", "pages": 1}
    ]
    ans = agent.answer("Which document contains the revised project deadline?")
    ans_text = ans.answer.replace('\u202f', ' ')
    passed = "doc b" in ans_text.lower() or "document_b" in ans_text.lower() or doc_id_b in ans.verification.supporting_pages
    results.append(("Multi-Document Search", passed, ans))

    return results

if __name__ == "__main__":
    run_agent_cases()
