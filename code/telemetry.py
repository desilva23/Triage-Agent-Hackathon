"""
telemetry.py — Tracking for Token Usage, Latency, and ROI.

This module provides a centralized singleton to track:
1. LLM Token Usage (Prompt, Completion, Total)
2. Cache ROI (Tokens saved by the Semantic Cache)
3. Latency per request
"""

import json
import os
import threading
from utils import resolve_path

class Telemetry:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(Telemetry, cls).__new__(cls)
                cls._instance._reset()
        return cls._instance

    def _reset(self):
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens_used = 0
        self.total_tokens_saved = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.total_requests = 0
        # Average costs per 1M tokens (Llama 3 8B) - rough estimate
        self.COST_PER_1M_PROMPT = 0.05
        self.COST_PER_1M_COMPLETION = 0.10

    def log_usage(self, prompt_tokens, completion_tokens):
        with self._lock:
            self.total_prompt_tokens += prompt_tokens
            self.total_completion_tokens += completion_tokens
            self.total_tokens_used += (prompt_tokens + completion_tokens)
            self.total_requests += 1

    def log_cache_hit(self, estimated_prompt_tokens):
        with self._lock:
            self.cache_hits += 1
            self.total_tokens_saved += estimated_prompt_tokens
            self.total_requests += 1

    def log_cache_miss(self):
        with self._lock:
            self.cache_misses += 1

    def get_summary(self):
        with self._lock:
            actual_cost = (
                (self.total_prompt_tokens / 1_000_000) * self.COST_PER_1M_PROMPT +
                (self.total_completion_tokens / 1_000_000) * self.COST_PER_1M_COMPLETION
            )
            saved_cost = (self.total_tokens_saved / 1_000_000) * self.COST_PER_1M_PROMPT
            
            return {
                "requests": self.total_requests,
                "cache_hits": self.cache_hits,
                "tokens_used": self.total_tokens_used,
                "tokens_saved": self.total_tokens_saved,
                "actual_cost_usd": round(actual_cost, 4),
                "saved_cost_usd": round(saved_cost, 4),
                "savings_percentage": round((self.cache_hits / self.total_requests * 100), 2) if self.total_requests > 0 else 0
            }

    def print_report(self):
        s = self.get_summary()
        print("\n" + "="*40)
        print("  ROI & TOKEN ANALYTICS REPORT")
        print("="*40)
        print(f"Total Requests:   {s['requests']}")
        print(f"Cache Hits:       {s['cache_hits']} ({s['savings_percentage']}%)")
        print(f"Tokens Used:      {s['tokens_used']:,}")
        print(f"Tokens Saved:     {s['tokens_saved']:,}")
        print("-" * 40)
        print(f"Actual API Cost:  ${s['actual_cost_usd']:.4f}")
        print(f"Estimated Savings: ${s['saved_cost_usd']:.4f}")
        print("="*40 + "\n")

telemetry = Telemetry()
