"""Query Groq GET /models endpoint to verify active production chat models."""
import os
import sys
import httpx
from dotenv import load_dotenv

load_dotenv("backend/.env")

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    print("ERROR: GROQ_API_KEY not found in environment or backend/.env")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

print("Querying GET https://api.groq.com/openai/v1/models ...")
try:
    with httpx.Client(timeout=10.0) as client:
        resp = client.get("https://api.groq.com/openai/v1/models", headers=headers)
        if resp.status_code != 200:
            print(f"FAILED: HTTP {resp.status_code} - {resp.text}")
            sys.exit(1)
        data = resp.json()
        models = data.get("data", [])
        print(f"Retrieved {len(models)} models from Groq API:")
        chat_models = []
        for m in sorted(models, key=lambda x: x.get("id", "")):
            model_id = m.get("id", "")
            active = m.get("active", True)
            owned_by = m.get("owned_by", "")
            print(f" - {model_id} (active: {active}, owned_by: {owned_by})")
            if "whisper" not in model_id and "guard" not in model_id and active:
                chat_models.append(model_id)
        
        print("\nCandidate production chat models:")
        for cm in chat_models:
            print(f" * {cm}")
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
