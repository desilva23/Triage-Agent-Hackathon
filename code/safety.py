"""
safety.py — Deterministic safety guardrails.

This module runs BEFORE any LLM call. It uses fast keyword matching to
immediately escalate high-risk tickets without burning any API tokens.
This is auditable, reproducible, and cannot hallucinate.
"""

import re

# High-severity keywords that ALWAYS trigger escalation regardless of context.
# Grouped by category for explainability.
ESCALATION_RULES = {
    "financial_fraud": [
        "fraud", "scam", "chargeback", "unauthorized charge",
        "unauthorized transaction", "stolen card", "card stolen",
        "card was stolen", "card has been stolen", "card compromised",
        "money stolen", "stolen money", "my card is lost",
        "lost my card", "card lost",
    ],
    "security_breach": [
        "hacked", "account hacked", "data breach", "security breach",
        "compromised account", "unauthorized access", "phishing",
        "identity theft", "credential stuffing",
    ],
    "legal_threat": [
        "lawsuit", "sue", "lawyer", "attorney", "legal action",
        "court", "litigation", "gdpr complaint", "regulatory complaint",
        "file a complaint",
    ],
    "harm_or_abuse": [
        "hate speech", "harassment", "abuse", "threat", "violence",
        "self-harm", "suicide",
    ],
    "critical_outage": [
        "site is down", "completely down", "total outage",
        "all pages are inaccessible", "service unavailable",
    ],
    "pii_or_sensitive": [
        "social security", "ssn", "passport number", "bank account number",
    ],
    "billing_dispute": [
        "billing dispute", "wrong charge", "overcharged", "refund request",
        "payment failed", "subscription cancelled without",
    ],
}


def check_safety(text: str) -> dict:
    """
    Runs deterministic safety checks against the issue text.

    Returns a dict:
        {
            "escalate": bool,
            "category": str | None,
            "matched_keyword": str | None,
            "reason": str
        }
    """
    if not text:
        return {"escalate": False, "category": None, "matched_keyword": None, "reason": "Empty text"}

    lowered = text.lower()

    for category, keywords in ESCALATION_RULES.items():
        for kw in keywords:
            # Use word-boundary matching to avoid partial matches (e.g. "court" in "courtesy")
            pattern = r'\b' + re.escape(kw) + r'\b'
            if re.search(pattern, lowered):
                reason = (
                    f"Deterministic safety rule triggered: category='{category}', "
                    f"keyword='{kw}'. This ticket requires human intervention."
                )
                return {
                    "escalate": True,
                    "category": category,
                    "matched_keyword": kw,
                    "reason": reason,
                }

    return {
        "escalate": False,
        "category": None,
        "matched_keyword": None,
        "reason": "No safety triggers found.",
    }
