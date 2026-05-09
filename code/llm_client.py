import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

import time

class LLMClient:
    """
    Client for interacting with Groq Cloud LLM API.
    Features robust retry logic with exponential backoff to handle Rate Limits (429)
    and Service Unavailable (503/500) errors common in hackathon environments.
    """
    def __init__(self, model="llama-3.1-8b-instant"):
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not found in environment variables.")
        self.client = Groq(api_key=self.api_key)
        self.model = model

    def chat(self, messages: list, temperature: float = 0, max_tokens: int = 1024) -> str:
        """
        Sends a chat completion request with exponential backoff retry logic.
        """
        max_retries = 5
        base_delay = 10  # seconds

        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=1,
                    stream=False,
                )
                
                # Log usage to telemetry
                from telemetry import telemetry
                usage = getattr(response, 'usage', None)
                if usage:
                    telemetry.log_usage(usage.prompt_tokens, usage.completion_tokens)

                return response.choices[0].message.content
            
            except Exception as e:
                err_msg = str(e).lower()
                is_retryable = any(x in err_msg for x in ["rate_limit", "503", "500", "overloaded", "timeout"])
                
                if is_retryable and attempt < max_retries - 1:
                    # Exponential backoff: 10s, 20s, 40s, 80s...
                    delay = base_delay * (2 ** attempt)
                    print(f"  [API {attempt+1}/{max_retries}] Retryable error: {type(e).__name__}. Retrying in {delay}s...")
                    time.sleep(delay)
                    continue
                
                print(f"  [API ERROR] Non-retryable or max retries reached: {e}")
                return ""

    def get_structured_output(self, system_prompt: str, user_prompt: str) -> str:
        """
        Convenience wrapper for single-turn structured prompts.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        return self.chat(messages)
