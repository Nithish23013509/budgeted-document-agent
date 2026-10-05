import os
import sys
from agent.agent import DocumentAgent
from agent.session import get_session, create_session
from agent.harness import AgentRun
from services.llm import LLMClient

class MockLLM(LLMClient):
    def generate(self, prompt, require_json=True):
        if 'VERIFICATION RESULT' in prompt:
            return 'Mock answer'
        if 'USER QUESTION' in prompt and 'RETRIEVED EVIDENCE' in prompt:
            return '{"status": "ANSWERED", "answer": "Mock answer", "reason": "Mock", "supporting_pages": [1], "conflicts": [], "confidence": "high"}'
        
        # Planner
        return '{"action": "FINAL", "arguments": {}, "reason": "Mock"}'

a = DocumentAgent(MockLLM())
a.planner.llm = MockLLM()
ans = a.answer('hello')
print(ans.answer)
