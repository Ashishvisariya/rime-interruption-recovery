"""One-Time Real Groq STT Integration Verification Script

Strictly executes exactly ONE live transcription request to https://api.groq.com/openai/v1/audio/transcriptions
using the configured GROQ_API_KEY. Prints only sanitized metadata.
Never prints or logs secret credentials.
"""

import asyncio
import io
import math
import struct
import time
import wave
from backend.app.config import get_settings
from backend.app.core.session import default_session_store
from backend.app.services.stt import GroqSTTService, STTError
from backend.app.services.rime_tts import default_rime_service


def generate_test_wav_pcm() -> bytes:
    """Generate a valid 16kHz mono 16-bit PCM WAV audio container."""
    sample_rate = 16000
    duration_s = 1.0
    num_samples = int(sample_rate * duration_s)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)

        # Simple tone sequence to ensure valid non-empty audio payload
        frames = bytearray()
        for i in range(num_samples):
            val = int(10000 * math.sin(2 * math.pi * 440 * (i / sample_rate)))
            frames.extend(struct.pack("<h", val))
        wav_file.writeframes(frames)

    return buffer.getvalue()


async def run_single_groq_verification():
    settings = get_settings()
    if not settings.groq_api_key or not settings.groq_api_key.strip():
        print("[ERROR] GROQ_API_KEY is not configured in the environment.")
        return False

    print("==================================================")
    print("PHASE 7 — REAL GROQ STT INTEGRATION VERIFICATION")
    print("==================================================")
    print("Executing EXACTLY ONE live Groq Whisper STT request...")
    print(f"Target Endpoint: {settings.groq_stt_url}")
    print(f"Configured Model ID: {settings.groq_stt_model}")
    print("--------------------------------------------------")

    # Generate or obtain short test speech audio
    print("Preparing short spoken speech sample for transcription...")
    try:
        # Generate short speech via Rime ("Hello, this is a speech recognition test.")
        speech_bytes, _ = await default_rime_service.synthesize(
            text="Hello, this is a speech recognition test.",
            session_id="sess_stt_verification",
            turn_id=1,
            audio_format="mp3",
        )
        audio_filename = "test_speech.mp3"
        audio_mime = "audio/mpeg"
    except Exception as e:
        print(f"[NOTE] Falling back to PCM WAV: {e}")
        speech_bytes = generate_test_wav_pcm()
        audio_filename = "test_tone.wav"
        audio_mime = "audio/wav"

    print(f"Sample Audio Size: {len(speech_bytes)} bytes ({audio_filename})")

    session = default_session_store.get_or_create_session("sess_groq_verification")
    turn_id = session.create_next_turn("STT Verification Turn")

    service = GroqSTTService(settings=settings)

    start_time = time.perf_counter()
    try:
        result = await service.transcribe(
            audio_bytes=speech_bytes,
            filename=audio_filename,
            mime_type=audio_mime,
            language="en",
            session_id=session.session_id,
            turn_id=turn_id,
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        print("[SUCCESS] Real Groq STT request completed successfully!")
        print(f"  - Request Attempted: YES")
        print(f"  - Provider: {result.provider}")
        print(f"  - Model ID: {result.model}")
        print(f"  - HTTP / API Status: {result.status}")
        print(f"  - Returned Transcript: '{result.text}'")
        print(f"  - Audio Size (bytes): {len(speech_bytes)}")
        print(f"  - Roundtrip Latency (ms): {elapsed_ms:.2f}")
        print(f"  - Associated Session ID: {result.session_id}")
        print(f"  - Associated Turn ID: {result.turn_id}")
        print("==================================================")
        return True

    except STTError as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        print(f"[FAILED] Groq STT API Error after {elapsed_ms:.2f}ms:")
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
    asyncio.run(run_single_groq_verification())
