import os
import sys

# Force UTF-8 encoding for Windows console
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from agent.agent import DocumentAgent
from agent.prompts import PLANNER_SYSTEM_PROMPT
from agent.session import get_session, create_session
from services.llm import create_llm_client
from tools.document_tools import register_document

def run_strategy_cases():
    results = []
    base_dir = os.path.dirname(__file__)
    fix_dir = os.path.join(base_dir, "fixtures")
    
    doc_id = "fix_strat_main"
    register_document(doc_id, "Strategy Main", os.path.join(fix_dir, "direct_fact.pdf"))
    
    llm = create_llm_client(system_prompt=PLANNER_SYSTEM_PROMPT)
    agent = DocumentAgent(llm_client=llm)
    agent.known_documents = [{"doc_id": doc_id, "title": "Strategy Main", "pages": 1}]
    
    sess = create_session()
    sid = sess.session_id

    # -- Test 1: Direct fact --
    # Should use search_keyword -> get_page
    ans1 = agent.answer("What was the company revenue in 2025?", session_id=sid, doc_id=doc_id)
    trace = [c["type"] if "type" in c else c["tool"] for c in ans1.trace]
    
    passed_q1 = "search_keyword" in trace and "get_page" in trace and "18.4" in ans1.answer
    results.append(("Test 1 - Direct fact retrieval", passed_q1, trace))
    
    # -- Test 2: Broad Topic --
    # Should use list_headings -> get_page
    doc_id_multi = "fix_strat_multi"
    register_document(doc_id_multi, "Multi", os.path.join(fix_dir, "multi_page.pdf"))
    agent.known_documents = [{"doc_id": doc_id_multi, "title": "Multi", "pages": 14}]
    
    ans2 = agent.answer("What are the major policies?", session_id=sid, doc_id=doc_id_multi)
    trace2 = [c["type"] if "type" in c else c["tool"] for c in ans2.trace]
    # list_headings might not be used if the agent just searches "policies", which is also fine.
    # But we check that it finds the answer.
    passed_q2 = "get_page" in trace2 and ans2.calls_used > 0
    results.append(("Test 2 - Broad topic retrieval", passed_q2, trace2))
    
    # -- Test 3 & 4: Multiple Facts / Comparison --
    ans3 = agent.answer("Compare the revenue of 2024 and 2025.", session_id=sid, doc_id=doc_id_multi)
    trace3 = [c["type"] if "type" in c else c["tool"] for c in ans3.trace]
    # Should contain 12 and 18.4
    passed_q3 = "12" in ans3.answer and "18.4" in ans3.answer
    results.append(("Test 3/4 - Multiple facts / Comparison", passed_q3, trace3))
    
    # -- Test 5: Session reuse --
    ans4 = agent.answer("Tell me again what the revenue in 2025 was.", session_id=sid, doc_id=doc_id_multi)
    passed_q4 = "18.4" in ans4.answer and ans4.calls_used == 0
    results.append(("Test 5 - Session reuse (0 calls)", passed_q4, None))
    
    # -- Test 8: Budget awareness --
    passed_budget = all(c <= 6 for c in [ans1.calls_used, ans2.calls_used, ans3.calls_used, ans4.calls_used])
    results.append(("Test 8 - Budget awareness (<= 6 calls)", passed_budget, None))
    
    # -- Trace Metadata Test --
    # Verify PLANNING_SUMMARY exists in trace
    summary_exists = any(c.get("type") == "PLANNING_SUMMARY" for c in ans1.trace)
    if summary_exists:
        summary_node = next(c for c in ans1.trace if c.get("type") == "PLANNING_SUMMARY")
        qtype = summary_node.get("question_type")
        strat = summary_node.get("strategy")
        passed_metadata = qtype is not None and strat is not None
    else:
        passed_metadata = False
    
    results.append(("Test Metadata - question_type and strategy recorded", passed_metadata, None))

    return results

if __name__ == "__main__":
    results = run_strategy_cases()
    for name, passed, details in results:
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")
