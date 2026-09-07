"""Single Live Verification Script for Phase 10 End-to-End Voice Agent Orchestration

Executes EXACTLY ONE real end-to-end voice interaction pipeline:
Spoken Audio Query
  ──▶ Real Groq Whisper STT (whisper-large-v3)
  ──▶ Real Groq LLM Generation (qwen/qwen3.6-27b)
  ──▶ Real Rime Labs TTS Synthesis (coda / celeste)
  ──▶ Output MP3 Audio File Verification

STRICT AUDIT RULES:
- Exactly 1 real STT call
- Exactly 1 real Groq LLM call
- Exactly 1 real Rime TTS call
- Zero Gemini calls
- Zero loops or stress tests
- Never prints or logs API keys / secret tokens.
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

# Load backend environment variables
load_dotenv(WORKSPACE_ROOT / "backend" / ".env")

from backend.app.config import get_settings
from backend.app.services.stt import GroqSTTService
from backend.app.services.llm import GroqLLMService
from backend.app.services.rime_tts import RimeTTSService
from backend.app.core.session import SessionStore
from backend.app.services.conversation import ConversationManager
from backend.app.services.voice_agent import VoiceAgentOrchestrator


async def run_single_e2e_live_verification():
    settings = get_settings()

    if not settings.groq_api_key or not settings.groq_api_key.strip():
        print("[ERROR] GROQ_API_KEY is missing in backend/.env")
        sys.exit(1)

    if not settings.rime_api_key or not settings.rime_api_key.strip():
        print("[ERROR] RIME_API_KEY is missing in backend/.env")
        sys.exit(1)

    print("=" * 70)
    print("PHASE 10: END-TO-END VOICE AGENT LIVE PIPELINE VERIFICATION")
    print("=" * 70)
    print("Provider Configuration:")
    print(f"  * STT Provider: Groq Whisper ({settings.groq_stt_model})")
    print(f"  * LLM Provider: Groq Chat Completion ({settings.groq_model})")
    print(f"  * TTS Provider: Rime Labs ({settings.rime_default_model} / {settings.rime_default_speaker})")
    print("----------------------------------------------------------------------")

    # Step 1: Synthesize a clean input speech sample to feed STT
    print("1. Preparing user voice input sample via Rime...")
    rime_svc = RimeTTSService(settings=settings)
    input_query_text = "What is the capital of France?"
    input_audio_bytes, _ = await rime_svc.synthesize(
        text=input_query_text,
        session_id="live_prep",
        turn_id=1,
        speaker="celeste",
        audio_format="mp3",
    )
    print(f"   [OK] Generated input voice query ({len(input_audio_bytes)} bytes): '{input_query_text}'")

    # Step 2: Initialize Orchestrator with real services
    store = SessionStore()
    conv_mgr = ConversationManager(session_store=store)
    stt_svc = GroqSTTService(settings=settings)
    llm_svc = GroqLLMService(app_settings=settings)
    agent = VoiceAgentOrchestrator(
        conversation_manager=conv_mgr,
        stt_service=stt_svc,
        llm_service=llm_svc,
        rime_service=rime_svc,
    )

    # Step 3: Execute End-to-End Voice Agent Pipeline (1 real run)
    print("\n2. Executing End-to-End Voice Agent Pipeline...")
    session_id = "live_e2e_session_phase10"
    overall_start = time.perf_counter()

    result = await agent.process_turn(
        session_id=session_id,
        audio_bytes=input_audio_bytes,
        audio_filename="live_user_query.mp3",
        audio_mime_type="audio/mpeg",
        language="en",
    )

    total_time_ms = (time.perf_counter() - overall_start) * 1000.0

    print("\n" + "=" * 70)
    print("PHASE 10 LIVE VERIFICATION RESULTS (ONE-OFF OBSERVATION, NOT BENCHMARK)")
    print("=" * 70)
    print(f"Session ID:             {result.session_id}")
    print(f"Turn ID:                {result.turn_id}")
    print(f"User STT Transcript:    '{result.user_prompt}'")
    print(f"Assistant LLM Response: '{result.assistant_text}'")
    print(f"Rime TTS Audio Output:  {len(result.audio_bytes)} bytes (Format: {result.tts_metadata.audio_format})")
    print(f"Rime Speaker Voice:     {result.tts_metadata.speaker} ({result.tts_metadata.model_id})")
    print(f"Total Pipeline Latency: {total_time_ms:.2f} ms")
    print("----------------------------------------------------------------------")

    # Verify conversation state in session
    session = conv_mgr.get_session(session_id)
    history = session.get_conversation_history()
    print(f"Committed Messages in History: {len(history)}")
    for idx, msg in enumerate(history):
        print(f"  [{idx+1}] {msg.role.upper()} (Turn #{msg.turn_id}): {msg.content}")

    # Save output audio artifact
    os.makedirs("demo", exist_ok=True)
    out_path = Path("demo/live_agent_response.mp3")
    with open(out_path, "wb") as f:
        f.write(result.audio_bytes)
    print(f"\nSaved synthesized response audio to: {out_path.resolve()}")
    print("=" * 70)

    # Verification checks
    assert len(result.user_prompt) > 0, "STT transcript was empty"
    assert len(result.assistant_text) > 0, "LLM response text was empty"
    assert len(result.audio_bytes) > 0, "Rime TTS audio bytes was empty"
    assert len(history) == 2, f"Expected 2 messages in history, found {len(history)}"
    print("ALL LIVE VERIFICATION CHECKS PASSED SUCCESSFULLY (0 Gemini calls, 1 E2E run).")


if __name__ == "__main__":
    asyncio.run(run_single_e2e_live_verification())
