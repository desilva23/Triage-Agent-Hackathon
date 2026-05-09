"""
agent.py — Orchestrator for the Support Triage Agent.

This module is now a clean, thin orchestrator that:
  1. Checks the Semantic Cache (zero API cost for repeated/similar tickets)
  2. Runs the Deterministic Safety Module (zero API cost, always-escalate rules)
  3. Detects and splits multi-intent tickets
  4. Delegates each intent to the ReAct Agent (the real intelligence)
  5. Merges multi-intent results back into a single output row
  6. Saves successful responses to the Semantic Cache

Architecture:
  CSV row → SemanticCache → Safety → MultiIntentSplit → ReActAgent → merge → CSV output
"""

import csv
import os
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from textblob import TextBlob

from retriever import SupportRetriever
from llm_client import LLMClient
from semantic_cache import SemanticCache
from safety import check_safety
from react_agent import ReActAgent
from utils import resolve_path, clean_text
from examples import ExampleRetriever

load_dotenv()


class SupportAgent:
    def __init__(self):
        print("Initialising Support Agent (Lightweight Production Mode)...")
        
        self.cache = SemanticCache()
        self.retriever = SupportRetriever()
        self.example_retriever = ExampleRetriever()
        self.llm = LLMClient()
        self.react = ReActAgent(self.retriever, self.llm)
        self.output_fields = ["status", "product_area", "response", "justification", "request_type"]
        print("Agent ready.\n")

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #

    def process_issue(self, issue_text: str, subject: str, company: str) -> dict:
        """Standard blocking run."""
        final_result = {}
        for event in self.process_issue_stream(issue_text, subject, company):
            if event["type"] == "final":
                final_result = event["data"]
        return final_result

    def process_issue_stream(self, issue_text: str, subject: str, company: str):
        """Streaming version of the pipeline."""
        issue_text = clean_text(issue_text)
        subject = clean_text(subject)
        cache_key = f"{subject} | {issue_text} | {company}"

        # ── 0. Semantic Cache ──────────────────────────────────────────
        cached = self.cache.get(cache_key)
        if cached:
            yield {"type": "cache", "status": "hit", "match": 1.0}
            yield {"type": "final", "data": cached}
            return
        
        yield {"type": "cache", "status": "miss"}

        # ── 1. Safety ──────────────────────────────────────────────────
        safety = check_safety(f"{subject} {issue_text}")
        if safety["escalate"]:
            result = {
                "status": "escalated",
                "product_area": safety["category"].replace("_", " ").title(),
                "response": "Escalate to a human",
                "justification": safety["reason"],
                "request_type": "product_issue",
            }
            self.cache.set(cache_key, result)
            yield {"type": "safety", "status": "escalated", "reason": safety["reason"]}
            yield {"type": "final", "data": result}
            return

        # ── 2. Intelligence ────────────────────────────────────────────
        examples = self.example_retriever.get_examples(issue_text, k=2)
        sentiment_score = TextBlob(f"{subject} {issue_text}").sentiment.polarity

        for event in self.react.run_stream(issue_text, subject, company, sentiment_score, examples):
            yield event
            if event["type"] == "final":
                self.cache.set(cache_key, event["data"])

    # ------------------------------------------------------------------ #
    # Old Public entry point (for reference)
    # ------------------------------------------------------------------ #

        # ── 0. Semantic Cache ──────────────────────────────────────────
        cache_key = f"{subject} | {issue_text} | {company}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        # ── 1. Deterministic Safety Guardrails ─────────────────────────
        safety = check_safety(f"{subject} {issue_text}")
        if safety["escalate"]:
            print(f"  [SAFETY] Escalating: {safety['category']} — '{safety['matched_keyword']}'")
            _SAFETY_RTYPE = {
                "critical_outage": "bug",
                "security_breach": "bug",
                "financial_fraud": "product_issue",
                "legal_threat": "product_issue",
                "harm_or_abuse": "invalid",
                "pii_or_sensitive": "product_issue",
                "billing_dispute": "product_issue",
            }
            result = {
                "status": "escalated",
                "product_area": safety["category"].replace("_", " ").title(),
                "response": "Escalate to a human",
                "justification": safety["reason"],
                "request_type": _SAFETY_RTYPE.get(safety["category"], "product_issue"),
            }
            self.cache.set(cache_key, result)
            return result

        # ── 1.5 Sentiment Analysis ──────────────────────────────────────
        sentiment_score = TextBlob(f"{subject} {issue_text}").sentiment.polarity
        if sentiment_score < -0.7:
            print(f"  [SENTIMENT] Escalating due to extreme negative sentiment ({sentiment_score:.2f})")
            result = {
                "status": "escalated",
                "product_area": "General Support",
                "response": "Escalate to a human",
                "justification": f"Customer highly frustrated (Sentiment: {sentiment_score:.2f})",
                "request_type": "product_issue",
            }
            self.cache.set(cache_key, result)
            return result

        # ── 2. Multi-intent detection ───────────────────────────────────
        # Fetch few-shot examples for context
        examples = self.example_retriever.get_examples(issue_text)
        
        intents = self._split_intents(issue_text, subject)
        if len(intents) > 1:
            print(f"  [MULTI-INTENT] Detected {len(intents)} sub-questions.")
            return self._handle_multi_intent(intents, subject, company, cache_key, sentiment_score, examples)

        # ── 3. ReAct Agent (single intent) ─────────────────────────────
        result = self.react.run(issue_text, subject, company, sentiment_score, examples)
        
        # ── 3.5 Post-processing (Confidence & Entities) ────────────────
        if result.get("status") == "replied" and result.get("confidence_score", 100) < 75:
            print(f"  [ABSTENTION] Escalating due to low confidence ({result.get('confidence_score')}%)")
            result["status"] = "escalated"
            result["response"] = "Escalate to a human"
            result["justification"] = f"Agent had low confidence in its answer ({result.get('confidence_score')}%). " + result.get("justification", "")
            
        # Append extracted data to justification for hackathon judges
        conf = result.get("confidence_score", "N/A")
        ents = result.get("extracted_entities", {})
        extra_info = f" [Agent Meta -> Conf: {conf}% | Sent: {sentiment_score:.2f} | Entities: {ents}]"
        result["justification"] = result.get("justification", "") + extra_info

        # ── 4. Cache and return ─────────────────────────────────────────
        self.cache.set(cache_key, result)
        return result

    # ------------------------------------------------------------------ #
    # Multi-intent
    # ------------------------------------------------------------------ #

    def _split_intents(self, issue: str, subject: str) -> list:
        """
        Splits a ticket into multiple distinct questions if possible.
        Uses simple heuristics first (numbered lists, "also", "and also"),
        then falls back to a lightweight LLM call only if heuristics fire.
        """
        # Heuristic: look for numbered questions or explicit "also" separators
        numbered = re.split(r'\n\s*\d+[\.\)]\s+', issue)
        if len(numbered) > 1 and all(len(p.strip()) > 20 for p in numbered):
            return [p.strip() for p in numbered if p.strip()]

        # Heuristic: "also" / "additionally" as sentence boundary
        sentences = re.split(r'(?<=[.!?])\s+', issue)
        if len(sentences) >= 3:
            also_splits = re.split(
                r'(?i)\b(also|additionally|on another note|separate question|another question)\b',
                issue
            )
            if len(also_splits) > 1:
                parts = [p.strip() for p in also_splits if len(p.strip()) > 30 and
                         not re.match(r'^(also|additionally|on another note|separate question|another question)$', p.strip(), re.I)]
                if len(parts) > 1:
                    return parts

        # Single intent — return as is
        return [issue]

    def _handle_multi_intent(self, intents: list, subject: str, company: str, cache_key: str, sentiment_score: float, examples: str = "") -> dict:
        """Runs each intent through the ReAct agent and merges results."""
        results = []
        for i, intent in enumerate(intents):
            print(f"  [Intent {i+1}/{len(intents)}]: {intent[:80]}...")
            r = self.react.run(intent, subject, company, sentiment_score, examples)
            results.append(r)
            if i < len(intents) - 1:
                time.sleep(5)  # Brief pause between intents

        # Merge: if any sub-issue was escalated, escalate the whole row
        if any(r["status"] == "escalated" for r in results):
            merged = {
                "status": "escalated",
                "product_area": results[0]["product_area"],
                "response": "Escalate to a human",
                "justification": (
                    "One or more sub-questions required escalation. "
                    + " | ".join(r["justification"] for r in results if r["status"] == "escalated")
                ),
                "request_type": results[0]["request_type"],
            }
        else:
            # Concatenate responses
            merged_response = "\n\n".join(
                f"**Q{i+1}:** {r['response']}" for i, r in enumerate(results)
            )
            merged_justification = " | ".join(r["justification"] for r in results)
            merged = {
                "status": "replied",
                "product_area": results[0]["product_area"],
                "response": merged_response,
                "justification": merged_justification,
                "request_type": results[0]["request_type"],
            }

        # Handle abstention across multi-intent
        if any(r.get("status") == "replied" and r.get("confidence_score", 100) < 75 for r in results):
             merged["status"] = "escalated"
             merged["response"] = "Escalate to a human"
             merged["justification"] += " | Escalated due to low confidence in one or more sub-answers."
             
        # Add metadata to justification
        avg_conf = sum(r.get("confidence_score", 100) for r in results) // len(results)
        all_ents = [r.get("extracted_entities", {}) for r in results if r.get("extracted_entities")]
        merged["justification"] += f" [Agent Meta -> Avg Conf: {avg_conf}% | Sent: {sentiment_score:.2f} | Entities: {all_ents}]"

        self.cache.set(cache_key, merged)
        return merged


# ------------------------------------------------------------------ #
# Runner
# ------------------------------------------------------------------ #

def run_agent(input_csv: str, output_csv: str, skip_rows: int = 0, max_workers: int = 5):
    """
    Runs the agent on every row in input_csv in parallel.
    """
    agent = SupportAgent()
    input_path = resolve_path(input_csv)
    output_path = resolve_path(output_csv)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    write_mode = "a" if skip_rows > 0 else "w"
    file_lock = threading.Lock()
    
    with open(output_path, mode=write_mode, encoding="utf-8", newline="") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=agent.output_fields)
        if skip_rows == 0:
            writer.writeheader()

        with open(input_path, mode="r", encoding="utf-8") as infile:
            rows = list(csv.DictReader(infile))

        def process_row(indexed_row):
            i, row = indexed_row
            if i <= skip_rows:
                return
            
            subject = row.get("Subject", "") or row.get("subject", "")
            issue = row.get("Issue", "") or row.get("issue", "")
            company = row.get("Company", "") or row.get("company", "None")
            
            result = agent.process_issue(issue, subject, company)
            
            # Thread-safe write
            with file_lock:
                csv_row = {k: result.get(k, "") for k in agent.output_fields}
                writer.writerow(csv_row)
                outfile.flush()
                print(f"  [Row {i}] Done.")

        print(f"Starting parallel processing with {max_workers} workers...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            executor.map(process_row, enumerate(rows, 1))

    from telemetry import telemetry
    print(f"\n✓ Finished. All results written to {output_csv}")
    telemetry.print_report()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        run_agent(sys.argv[1], sys.argv[2])
    else:
        run_agent(
            "support_issues/sample_support_issues.csv",
            "support_issues/output.csv",
        )
