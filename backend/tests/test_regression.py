import os
import sys
import time

# Force UTF-8 encoding for Windows console
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from tests.test_agent_cases import run_agent_cases
from tests.test_budget import run_budget_cases
from tests.test_security import run_security_cases

def main():
    print("=========================================")
    print("RUNNING DOCUMENT AGENT REGRESSION SUITE")
    print("=========================================\n")
    
    all_results = []
    
    print("--- AGENT CASES ---")
    agent_results = run_agent_cases()
    all_results.extend(agent_results)
    for name, passed, _ in agent_results:
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")
        
    print("\n--- BUDGET ENFORCEMENT ---")
    budget_results = run_budget_cases()
    all_results.extend(budget_results)
    for name, passed, _ in budget_results:
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")

    print("\n--- SECURITY & ROBUSTNESS ---")
    security_results = run_security_cases()
    all_results.extend(security_results)
    for name, passed, _ in security_results:
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")

    # -- Evaluation Metrics (Part 21) --
    
    total_questions = 0
    correct_answers = 0
    insufficient_total = 0
    insufficient_correct = 0
    contradiction_total = 0
    contradiction_correct = 0
    prompt_inj_total = 0
    prompt_inj_correct = 0
    
    total_calls = 0
    max_calls = 0
    budget_violations = 0
    invalid_tool_executions = 0

    for name, passed, ans in all_results:
        if ans is not None:
            total_questions += 1
            if passed:
                correct_answers += 1
                
            calls = ans.calls_used
            total_calls += calls
            if calls > max_calls:
                max_calls = calls
            
            if calls > 6:
                budget_violations += 1
                
            if "Insufficient" in name:
                insufficient_total += 1
                if passed: insufficient_correct += 1
            elif "Conflict" in name or "Compound" in name:
                contradiction_total += 1
                if passed: contradiction_correct += 1
            elif "Injection" in name:
                prompt_inj_total += 1
                if passed: prompt_inj_correct += 1

    accuracy = (correct_answers / total_questions) * 100 if total_questions else 0
    ins_acc = (insufficient_correct / insufficient_total) * 100 if insufficient_total else 0
    con_acc = (contradiction_correct / contradiction_total) * 100 if contradiction_total else 0
    inj_acc = (prompt_inj_correct / prompt_inj_total) * 100 if prompt_inj_total else 0
    avg_calls = total_calls / total_questions if total_questions else 0

    print("\n=========================================")
    print("DOCUMENT AGENT EVALUATION")
    print("=========================================\n")
    print(f"Questions tested:              {total_questions}")
    print(f"Correct:                       {correct_answers}")
    print(f"Accuracy:                      {accuracy:.1f}%\n")
    
    if insufficient_total: print(f"Insufficient-info accuracy:    {ins_acc:.1f}%")
    if contradiction_total: print(f"Contradiction accuracy:        {con_acc:.1f}%")
    if prompt_inj_total: print(f"Prompt-injection resistance:   {inj_acc:.1f}%\n")
    
    print(f"Average tool calls:            {avg_calls:.1f}")
    print(f"Maximum tool calls:            {max_calls}\n")
    
    print(f"Budget violations:             {budget_violations}")
    print(f"Invalid tool executions:       {invalid_tool_executions}")
    print("=========================================\n")
    
    failures = [name for name, passed, _ in all_results if not passed]
    if failures:
        print("FAILING TESTS:")
        for f in failures:
            print(f" - {f}")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED.")

if __name__ == "__main__":
    main()
