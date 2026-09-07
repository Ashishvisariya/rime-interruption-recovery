"""Single Live Verification Script for Groq LLM Integration (Phase 8)

Executes EXACTLY ONE real Groq chat completion request using the verified model.
Zero loops, zero repeated calls, zero secret leakage.
"""

import os
import sys
import time
import httpx
from dotenv import load_dotenv

load_dotenv("backend/.env")

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    print("ERROR: GROQ_API_KEY not found in environment or backend/.env")
    sys.exit(1)

model_id = os.getenv("GROQ_MODEL", "qwen/qwen3.6-27b")
url = os.getenv("GROQ_LLM_URL", "https://api.groq.com/openai/v1/chat/completions")

headers = {
    "Authorization": f"Bearer {api_key.strip()}",
    "Content-Type": "application/json",
}

body = {
    "model": model_id,
    "messages": [
        {
            "role": "system",
            "content": "You are a voice assistant. Respond in one concise sentence without markdown.",
        },
        {
            "role": "user",
            "content": "Say hello in one short sentence.",
        },
    ],
    "temperature": 0.5,
    "max_tokens": 60,
}

print("=" * 60)
print("PHASE 8: EXECUTING EXACTLY ONE REAL GROQ LLM INFERENCE CALL")
print(f"Target Endpoint: {url}")
print(f"Model ID: {model_id}")
print("Prompt: 'Say hello in one short sentence.'")
print("=" * 60)

start_time = time.perf_counter()

try:
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(url, headers=headers, json=body)
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        if resp.status_code != 200:
            print(f"FAILED: HTTP {resp.status_code}")
            print(f"Response: {resp.text}")
            sys.exit(1)

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            print("FAILED: Empty choices returned")
            sys.exit(1)

        content = choices[0].get("message", {}).get("content", "").strip()
        usage = data.get("usage", {})

        print("\n--- REAL GROQ LLM VERIFICATION SUCCESS ---")
        print(f"HTTP Status: {resp.status_code} OK")
        print(f"Verified Model: {model_id}")
        print(f"Returned Text: \"{content}\"")
        print(f"Prompt Tokens: {usage.get('prompt_tokens')}")
        print(f"Completion Tokens: {usage.get('completion_tokens')}")
        print(f"Measured Roundtrip Latency: {latency_ms:.2f} ms")
        print("Credential Security: Masked & Protected")
        print("=" * 60)

except Exception as e:
    print(f"ERROR during live Groq LLM verification: {e}")
    sys.exit(1)
