"""
react_agent.py — ReAct (Reason + Act) Agentic Loop.

This replaces the old linear pipeline with a proper agent that can:
  1. Reason about the problem at each step
  2. Choose from a set of tools to call
  3. Observe the result and update its understanding
  4. Decide whether to search again, respond, or escalate

The agent runs up to MAX_STEPS iterations. At each step, the LLM outputs
a structured JSON object with {"thought": ..., "action": ..., "input": ...}.
The orchestrator executes the action, appends the observation, and loops.

This is a true agentic pattern — not a fixed pipeline — because the LLM
controls the flow, can decide to search multiple times for different aspects
of a multi-intent ticket, and has explicit reasoning at every step.
"""

import json
import re
import time
from typing import Optional
from llm_client import LLMClient
from retriever import SupportRetriever


# ------------------------------------------------------------------ #
# Prompts
# ------------------------------------------------------------------ #

REACT_SYSTEM_PROMPT = """You are a precision support triage agent with access to three tools.
You MUST follow the ReAct (Reason + Act) format at every step.

## Multi-Lingual Protocol
1. Detect the language of the user's ticket.
2. If it is NOT English, you must still search the English corpus (it is the only ground truth).
3. Translate the final `response` back into the user's language.
4. Keep the `justification`, `product_area`, and `request_type` in English for the internal system.

## Available Tools

1. search_corpus(query, company)
   Searches the support documentation corpus. Call this to find relevant information.
   - query: a focused search string based on the user's issue
   - company: one of "HackerRank", "Claude", "Visa", or "None"

2. respond(response, product_area, request_type, justification, confidence_score, extracted_entities)
   Use when you find ANY information in the corpus that can help the user, even if it's not a 100% direct answer. Your job is to be as helpful as possible using the provided documentation.
   - response: a comprehensive, empathetic, and professional answer.
   - product_area: category (e.g., Billing, Technical, Visa)
   - confidence_score: how much you trust this answer (1-100).
   - request_type: classification (English)
   - justification: which document(s) you used and why (English)
   - extracted_entities: JSON object of key entities.

3. escalate(reason, product_area, request_type)
   Use ONLY as a last resort when:
   - The user is extremely angry or abusive.
   - The issue is a critical security breach (e.g., active hacking).
   - The corpus search returned ZERO relevant information after multiple attempts.
   - The issue is completely outside the scope of support (e.g., medical advice).
   
   DO NOT escalate just because you aren't 100% sure. Use your intelligence to provide the best possible guide from the documentation.

## Interaction Guidelines
1. GREETINGS: If the user message is a simple greeting (e.g., "Hi", "Hello", "How are you?"), you MAY respond directly without searching the corpus. Provide a warm, professional greeting and ask how you can assist. Set `confidence_score` to 100.
2. TECHNICAL ISSUES: For any technical issue, product question, or support request, you MUST search the corpus. You are NOT allowed to answer technical questions without grounding.
3. REFLEXION: In every `thought`, you must ask: "Is this a simple greeting or a technical issue requiring documentation?"

## Format (STRICT JSON ONLY)
{
  "thought": "your reasoning. Must include reflection: 'Is this a simple greeting or a technical issue requiring documentation?'",
  "action": "search_corpus" | "respond" | "escalate",
  "input": { ... }
}
"""

def _build_user_message(issue, subject, company, trajectory, sentiment_score=0.0, examples=""):
    """Constructs the growing conversation context for the ReAct loop."""
    sentiment_context = ""
    if sentiment_score < -0.3:
        sentiment_context = f"\n[System Note: User sentiment is negative ({sentiment_score:.2f}). Please adopt a highly empathetic and apologetic tone.]"
    
    lines = [
        f"## Support Ticket",
        f"Company: {company or 'Unknown'}",
        f"Subject: {subject or '(none)'}",
        f"Issue: {issue}{sentiment_context}",
        "",
    ]

    if examples:
        lines.append("## Relevant Examples (Few-Shot)")
        lines.append(examples)
        lines.append("")

    if trajectory:
        lines.append("## Agent Trajectory So Far")
        for step in trajectory:
            lines.append(f"Step {step['step']}:")
            lines.append(f"  Thought: {step['thought']}")
            lines.append(f"  Action: {step['action']}")
            lines.append(f"  Input: {json.dumps(step['input'])}")
            if "observation" in step:
                obs = step["observation"]
                if isinstance(obs, list):
                    doc_summary = "\n".join(
                        f"  - [{d['path']}] score={d.get('score', 0):.2f}:\n    {d['content'][:600]}"
                        for d in obs
                    ) or "  (no results found)"
                    lines.append(f"  Observation (search results):\n{doc_summary}")
                else:
                    lines.append(f"  Observation: {obs}")
        lines.append("")

    lines.append("## Your Next Step")
    lines.append("Output your next JSON step (thought + action + input):")
    return "\n".join(lines)


# ------------------------------------------------------------------ #
# ReAct Agent
# ------------------------------------------------------------------ #

class ReActAgent:
    MAX_STEPS = 5

    def __init__(self, retriever: SupportRetriever, llm: LLMClient):
        self.retriever = retriever
        self.llm = llm

    def run(self, issue: str, subject: str, company: str, sentiment_score: float = 0.0, examples: str = "") -> dict:
        """Standard blocking run for CLI/Batch."""
        final_result = {}
        for event in self.run_stream(issue, subject, company, sentiment_score, examples):
            if event["type"] == "final":
                final_result = event["data"]
        return final_result

    def run_stream(self, issue: str, subject: str, company: str, sentiment_score: float = 0.0, examples: str = ""):
        """
        Generator that yields ReAct steps and the final result.
        """
        trajectory = []

        for step_num in range(1, self.MAX_STEPS + 1):
            user_msg = _build_user_message(issue, subject, company, trajectory, sentiment_score, examples)
            raw = self.llm.get_structured_output(REACT_SYSTEM_PROMPT, user_msg)

            if not raw:
                res = self._escalate("LLM returned no response.", "", "product_issue")
                yield {"type": "final", "data": self._finalize_run(res, trajectory, issue)}
                return

            step_data = self._parse_step(raw)
            if not step_data:
                res = self._escalate("Could not parse LLM reasoning.", "", "product_issue")
                yield {"type": "final", "data": self._finalize_run(res, trajectory, issue)}
                return

            action = step_data.get("action", "")
            thought = step_data.get("thought", "")
            inp = step_data.get("input", {})

            # Yield the step to the UI
            yield {
                "type": "step",
                "step": step_num,
                "thought": thought,
                "action": action,
                "input": inp
            }

            if action == "respond":
                confidence = inp.get("confidence_score", 100)
                result = {
                    "status": "replied",
                    "product_area": inp.get("product_area", ""),
                    "response": inp.get("response", ""),
                    "justification": inp.get("justification", ""),
                    "request_type": inp.get("request_type", "product_issue"),
                    "confidence_score": confidence,
                    "extracted_entities": inp.get("extracted_entities", {})
                }
                trajectory.append({"step": step_num, "thought": thought, "action": action, "input": inp, "observation": "Final Response Sent."})
                yield {"type": "final", "data": self._finalize_run(result, trajectory, issue)}
                return

            if action == "escalate":
                res = self._escalate(inp.get("reason", "Agent decided to escalate."), inp.get("product_area", ""), inp.get("request_type", "product_issue"))
                trajectory.append({"step": step_num, "thought": thought, "action": action, "input": inp, "observation": "Escalated."})
                yield {"type": "final", "data": self._finalize_run(res, trajectory, issue)}
                return

            if action == "search_corpus":
                query = inp.get("query", issue)
                corp_company = inp.get("company", company) or company
                docs = self.retriever.search(query, company=corp_company, top_k=2)
                
                observation = docs
                trajectory.append({
                    "step": step_num,
                    "thought": thought,
                    "action": action,
                    "input": inp,
                    "observation": observation,
                })
                
                # Yield the observation
                yield {
                    "type": "observation",
                    "step": step_num,
                    "observation": f"Found {len(docs)} relevant documents."
                }
                continue

            res = self._escalate(f"Unknown action: {action}", "", "product_issue")
            yield {"type": "final", "data": self._finalize_run(res, trajectory, issue)}
            return

        res = self._escalate("Max steps reached.", "", "product_issue")
        yield {"type": "final", "data": self._finalize_run(res, trajectory, issue)}

    def _finalize_run(self, result: dict, trajectory: list, issue: str) -> dict:
        """Saves reasoning trace to disk and returns result."""
        self._save_trace(issue, trajectory, result)
        return result

    def _save_trace(self, issue: str, trajectory: list, result: dict):
        """Saves a Markdown reasoning trace for observability."""
        import os, hashlib
        os.makedirs("traces", exist_ok=True)
        # Use short hash of issue for filename
        issue_hash = hashlib.md5(issue.encode()).hexdigest()[:8]
        path = f"traces/trace_{issue_hash}.md"
        
        md = [
            f"# Reasoning Trace for Ticket: {issue_hash}",
            f"**Original Issue:** {issue[:200]}...",
            f"**Final Status:** {result['status']}",
            "\n## ReAct Trajectory\n"
        ]
        for step in trajectory:
            md.append(f"### Step {step['step']}")
            md.append(f"- **Thought:** {step['thought']}")
            md.append(f"- **Action:** `{step['action']}`")
            md.append(f"- **Input:** `{json.dumps(step['input'])}`")
            if isinstance(step['observation'], list):
                md.append("- **Observation:** (Search Results)")
                for d in step['observation']:
                    md.append(f"  - [{d['path']}] {d['content'][:200]}...")
            else:
                md.append(f"- **Observation:** {step['observation']}")
            md.append("")
        
        md.append("\n## Final Output")
        md.append(f"```json\n{json.dumps(result, indent=2)}\n```")
        
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(md))

    def _parse_step(self, raw: str) -> Optional[dict]:
        try: return json.loads(raw.strip())
        except: pass
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try: return json.loads(match.group(0))
            except: pass
        return None

    def _escalate(self, reason: str, product_area: str, request_type: str) -> dict:
        return {
            "status": "escalated",
            "product_area": product_area,
            "response": "Escalate to a human",
            "justification": reason,
            "request_type": request_type,
        }
