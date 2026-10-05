import os
import sys

# Force UTF-8 encoding for Windows console
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from agent.harness import AgentRun, ToolBudgetExceeded
from tools.document_tools import register_document

def run_budget_cases():
    results = []
    
    base_dir = os.path.dirname(__file__)
    fix_dir = os.path.join(base_dir, "fixtures")
    doc_id = "fix_budget"
    
    # 1. Budget limits (Part 11)
    register_document(doc_id, "Budget Doc", os.path.join(fix_dir, "direct_fact.pdf"))
    run = AgentRun(question="Test")
    for i in range(6):
        run.execute_tool("search_keyword", doc_id=doc_id, keyword="test")
        
    passed_limit = (run.calls_used == 6)
    
    try:
        run.execute_tool("search_keyword", doc_id=doc_id, keyword="test")
        passed_rejection = False
    except ToolBudgetExceeded:
        passed_rejection = True
        
    results.append(("6-call limit enforcement", passed_limit and passed_rejection, None))
    
    # 2. Failed tool calls (Part 12)
    register_document(doc_id, "Budget Doc", os.path.join(fix_dir, "direct_fact.pdf"))
    run2 = AgentRun(question="Test2")
    try:
        res = run2.execute_tool("get_page", doc_id=doc_id, page_number=99999)
        passed_failed = False
    except Exception as exc:
        passed_failed = (run2.calls_used == 1)
        
    results.append(("Failed tool calls consume budget", passed_failed, None))
    
    return results

if __name__ == "__main__":
    run_budget_cases()
