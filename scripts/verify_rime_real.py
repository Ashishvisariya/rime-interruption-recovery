"""One-Time Real Rime TTS Integration Verification Script

Strictly executes exactly ONE live synthesis request to https://users.rime.ai/v1/rime-tts
using the configured RIME_API_KEY. Prints only sanitized metadata.
Never prints or logs secret credentials.
"""

import asyncio
import time
from backend.app.config import get_settings
from backend.app.core.session import default_session_store
from backend.app.services.rime_tts import RimeTTSService, RimeTTSError


async def run_single_verification():
    settings = get_settings()
    if not settings.is_rime_configured:
        print("[ERROR] RIME_API_KEY is not configured in the environment.")
        return False

    print("==================================================")
    print("PHASE 5 — REAL RIME TTS INTEGRATION VERIFICATION")
    print("==================================================")
    print("Executing EXACTLY ONE live Rime TTS request...")
    print(f"Target Endpoint: {settings.rime_api_url}")
    print(f"Configured Model ID: {settings.rime_default_model}")
    print(f"Configured Speaker: {settings.rime_default_speaker}")
    print(f"Configured Audio Format: {settings.rime_default_format}")
    print("Test Sentence: 'Rime TTS integration test.'")
    print("--------------------------------------------------")

    # 1. Setup session & active turn
    session = default_session_store.get_or_create_session("sess_real_verification")
    turn_id = session.create_next_turn("Rime TTS integration test.")

    service = RimeTTSService(settings=settings)

    start_time = time.perf_counter()
    try:
        audio_bytes, metadata = await service.synthesize(
            text="Rime TTS integration test.",
            session_id=session.session_id,
            turn_id=turn_id,
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        print("[SUCCESS] Real Rime TTS request completed successfully!")
        print(f"  - Request Attempted: YES")
        print(f"  - HTTP Status: 200 OK")
        print(f"  - Provider: {metadata.provider}")
        print(f"  - Model ID: {metadata.model_id}")
        print(f"  - Speaker: {metadata.speaker}")
        print(f"  - Audio Format: {metadata.audio_format}")
        print(f"  - Audio Size (bytes): {metadata.audio_bytes_length}")
        print(f"  - Roundtrip Latency (ms): {elapsed_ms:.2f}")
        print(f"  - Session ID: {metadata.session_id}")
        print(f"  - Turn ID: {metadata.turn_id}")
        print(f"  - Turn Validated Post-Synthesis: {session.validate_turn(turn_id)}")
        print("==================================================")
        return True

    except RimeTTSError as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        print(f"[FAILED] Rime API Error after {elapsed_ms:.2f}ms:")
        print(f"  - Error: {e}")
        print(f"  - Status Code: {e.status_code}")
        print("==================================================")
        return False
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        print(f"[FAILED] Unexpected Error after {elapsed_ms:.2f}ms: {type(e).__name__}: {e}")
        print("==================================================")
        return False


if __name__ == "__main__":
    asyncio.run(run_single_verification())
