"""Unit and Integration Tests for Phase 10 Voice Agent Orchestration

Tests the complete end-to-end voice agent pipeline:
Audio/Text -> STT -> Conversation Manager -> LLM -> Rime TTS -> Spoken Output

ALL external providers (Groq STT, Groq LLM, Rime TTS) are strictly mocked.
ZERO live external API calls are made in this test suite.
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.session import default_session_store
from backend.app.models.schemas import RimeTTSMetadata, TranscriptionResponse
from backend.app.services.stt import default_stt_service, STTError
from backend.app.services.llm import default_llm_service, GroqLLMServiceError
from backend.app.services.rime_tts import default_rime_service, RimeTTSError
from backend.app.services.conversation import default_conversation_manager
from backend.app.services.voice_agent import (
    VoiceAgentOrchestrator,
    VoiceAgentStaleTurnError,
    VoiceAgentOrchestrationError,
    default_voice_agent,
)


@pytest.fixture
def client():
    default_session_store.clear()
    return TestClient(app)


@pytest.fixture
def mock_pipeline():
    """Setup mocked STT, LLM, and Rime TTS services."""
    fake_audio = b"\xff\xfb\x90\x44" + b"\x00" * 256
    fake_stt_response = TranscriptionResponse(
        session_id="sess_agent_test",
        turn_id=1,
        text="What is the weather today?",
        provider="groq",
        model="whisper-large-v3",
        status="SUCCESS",
    )
    fake_llm_response = {
        "text": "The weather is sunny and pleasant today.",
        "provider": "groq",
        "model": "qwen/qwen3.6-27b",
        "prompt_tokens": 12,
        "completion_tokens": 10,
        "latency_ms": 110.0,
    }
    fake_tts_metadata = RimeTTSMetadata(
        session_id="sess_agent_test",
        turn_id=1,
        provider="rime",
        model_id="coda",
        speaker="celeste",
        audio_format="mp3",
        audio_bytes_length=len(fake_audio),
        status="SUCCESS",
    )

    return {
        "audio": fake_audio,
        "stt": fake_stt_response,
        "llm": fake_llm_response,
        "tts_metadata": fake_tts_metadata,
    }


# =====================================================================
# 1. Orchestrator Service Unit Tests
# =====================================================================

@pytest.mark.asyncio
async def test_process_turn_audio_success(mock_pipeline):
    """Verify end-to-end processing of audio input through STT, LLM, and TTS."""
    default_session_store.clear()
    session = default_conversation_manager.create_session("sess_agent_audio")

    with patch.object(default_stt_service, "transcribe", new=AsyncMock(return_value=mock_pipeline["stt"])), \
         patch.object(default_llm_service, "generate", new=AsyncMock(return_value=mock_pipeline["llm"])), \
         patch.object(default_rime_service, "synthesize", new=AsyncMock(return_value=(mock_pipeline["audio"], mock_pipeline["tts_metadata"]))):

        result = await default_voice_agent.process_turn(
            session_id="sess_agent_audio",
            audio_bytes=b"fake_mic_audio_payload",
        )

        assert result.session_id == "sess_agent_audio"
        assert result.turn_id == 1
        assert result.user_prompt == "What is the weather today?"
        assert result.assistant_text == "The weather is sunny and pleasant today."
        assert len(result.audio_bytes) > 0
        assert result.tts_metadata.speaker == "celeste"
        assert result.latency_ms > 0

        # Verify conversation history was committed
        history = session.get_conversation_history()
        assert len(history) == 2
        assert history[0].role == "user"
        assert history[0].content == "What is the weather today?"
        assert history[1].role == "assistant"
        assert history[1].content == "The weather is sunny and pleasant today."


@pytest.mark.asyncio
async def test_process_turn_text_success(mock_pipeline):
    """Verify end-to-end processing of text prompt through LLM and TTS."""
    default_session_store.clear()
    session = default_conversation_manager.create_session("sess_agent_text")

    with patch.object(default_llm_service, "generate", new=AsyncMock(return_value=mock_pipeline["llm"])), \
         patch.object(default_rime_service, "synthesize", new=AsyncMock(return_value=(mock_pipeline["audio"], mock_pipeline["tts_metadata"]))):

        result = await default_voice_agent.process_turn(
            session_id="sess_agent_text",
            text_prompt="Tell me about quantum computing",
        )

        assert result.session_id == "sess_agent_text"
        assert result.turn_id == 1
        assert result.user_prompt == "Tell me about quantum computing"
        assert result.assistant_text == "The weather is sunny and pleasant today."

        # Verify history
        history = session.get_conversation_history()
        assert len(history) == 2
        assert history[0].content == "Tell me about quantum computing"
        assert history[1].content == "The weather is sunny and pleasant today."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("prompt", "assistant_text"),
    [
        ("Search for a flight from New York to Tokyo.", "Sure. What date would you like to travel?"),
        ("What is the capital of France?", "The capital of France is Paris."),
        ("Tell me a quick joke.", "Why did the computer get cold? It left its Windows open."),
        ("How far is the Moon from Earth?", "The Moon is about 384,400 kilometers away on average."),
        ("Plan a weekend trip to Delhi.", "Sure. What dates would you like to travel?"),
    ],
)
async def test_five_voice_requests_send_only_natural_text_to_tts(prompt, assistant_text, mock_pipeline):
    """Verify representative user requests reach TTS without prompt or reasoning text."""
    default_session_store.clear()
    session = default_conversation_manager.create_session(f"sess_voice_{abs(hash(prompt))}")
    llm_result = {**mock_pipeline["llm"], "text": assistant_text}
    tts = AsyncMock(return_value=(mock_pipeline["audio"], mock_pipeline["tts_metadata"]))

    with patch.object(default_llm_service, "generate", new=AsyncMock(return_value=llm_result)), \
         patch.object(default_rime_service, "synthesize", new=tts):
        result = await default_voice_agent.process_turn(
            session_id=session.session_id,
            text_prompt=prompt,
        )

    assert result.assistant_text == assistant_text
    assert tts.await_args.kwargs["text"] == assistant_text


@pytest.mark.asyncio
async def test_multi_turn_context_retention(mock_pipeline):
    """Verify Turn 2 LLM generation includes Turn 1 conversation context."""
    default_session_store.clear()
    session = default_conversation_manager.create_session("sess_agent_multiturn")

    captured_llm_messages = []

    async def mock_capture_llm(messages, **kwargs):
        captured_llm_messages.append(list(messages))
        return mock_pipeline["llm"]

    with patch.object(default_llm_service, "generate", new=mock_capture_llm), \
         patch.object(default_rime_service, "synthesize", new=AsyncMock(return_value=(mock_pipeline["audio"], mock_pipeline["tts_metadata"]))):

        # Turn 1
        await default_voice_agent.process_turn(
            session_id="sess_agent_multiturn",
            text_prompt="My name is Alice.",
        )

        # Turn 2
        await default_voice_agent.process_turn(
            session_id="sess_agent_multiturn",
            text_prompt="What is my name?",
        )

        # Turn 2 LLM should have received Turn 1 user + assistant + Turn 2 user prompt
        assert len(captured_llm_messages) == 2
        turn2_messages = captured_llm_messages[1]
        assert len(turn2_messages) == 3
        assert turn2_messages[0]["role"] == "user"
        assert turn2_messages[0]["content"] == "My name is Alice."
        assert turn2_messages[1]["role"] == "assistant"
        assert turn2_messages[2]["role"] == "user"
        assert turn2_messages[2]["content"] == "What is my name?"


# =====================================================================
# 2. Failure & Error Handling Tests
# =====================================================================

@pytest.mark.asyncio
async def test_stt_failure_raises_orchestration_error(mock_pipeline):
    """Verify STT service failure raises VoiceAgentOrchestrationError and leaves session intact."""
    default_session_store.clear()
    session = default_conversation_manager.create_session("sess_stt_fail")

    with patch.object(default_stt_service, "transcribe", new=AsyncMock(side_effect=STTError("Upstream STT failed", status_code=502))):
        with pytest.raises(VoiceAgentOrchestrationError) as exc_info:
            await default_voice_agent.process_turn(
                session_id="sess_stt_fail",
                audio_bytes=b"raw_audio",
            )
        assert exc_info.value.status_code == 502
        assert "STT Failure" in str(exc_info.value)

    # Conversation history must NOT contain incomplete/failed assistant response
    assert len(session.get_conversation_history()) <= 1


@pytest.mark.asyncio
async def test_llm_failure_raises_orchestration_error(mock_pipeline):
    """Verify LLM service failure raises VoiceAgentOrchestrationError."""
    default_session_store.clear()

    with patch.object(default_llm_service, "generate", new=AsyncMock(side_effect=GroqLLMServiceError("LLM Rate Limit"))):
        with pytest.raises(VoiceAgentOrchestrationError) as exc_info:
            await default_voice_agent.process_turn(
                session_id="sess_llm_fail",
                text_prompt="Hello",
            )
        assert exc_info.value.status_code == 502
        assert "LLM Generation Failure" in str(exc_info.value)


@pytest.mark.asyncio
async def test_rime_failure_raises_orchestration_error(mock_pipeline):
    """Verify Rime TTS failure raises VoiceAgentOrchestrationError."""
    default_session_store.clear()

    with patch.object(default_llm_service, "generate", new=AsyncMock(return_value=mock_pipeline["llm"])), \
         patch.object(default_rime_service, "synthesize", new=AsyncMock(side_effect=RimeTTSError("Rime TTS Down", status_code=502))):

        with pytest.raises(VoiceAgentOrchestrationError) as exc_info:
            await default_voice_agent.process_turn(
                session_id="sess_rime_fail",
                text_prompt="Test TTS",
            )
        assert exc_info.value.status_code == 502
        assert "Rime TTS Failure" in str(exc_info.value)


# =====================================================================
# 3. Stale Turn Rejection Invariant Tests
# =====================================================================

@pytest.mark.asyncio
async def test_stale_turn_after_llm_rejected(mock_pipeline):
    """Verify that if barge-in advances the turn during LLM generation, the result is rejected."""
    default_session_store.clear()
    session = default_conversation_manager.create_session("sess_stale_mid_llm")
    turn1_id = session.create_next_turn("Turn 1 slow query")

    async def mock_slow_llm(*args, **kwargs):
        # User barges in, advancing the session to Turn 2 while LLM is generating Turn 1
        session.create_next_turn("Turn 2 barge-in")
        return mock_pipeline["llm"]

    with patch.object(default_llm_service, "generate", new=mock_slow_llm):
        with pytest.raises(VoiceAgentStaleTurnError) as exc_info:
            await default_voice_agent.process_turn(
                session_id="sess_stale_mid_llm",
                turn_id=turn1_id,
                text_prompt="Turn 1 slow query",
            )
        assert "superseded during LLM generation" in str(exc_info.value)

    # History must NOT contain Turn 1 assistant reply
    history = session.get_conversation_history()
    assistant_replies = [m.content for m in history if m.role == "assistant"]
    assert len(assistant_replies) == 0


@pytest.mark.asyncio
async def test_stale_turn_after_tts_rejected(mock_pipeline):
    """Verify that if turn is superseded during TTS synthesis, audio is discarded."""
    default_session_store.clear()
    session = default_conversation_manager.create_session("sess_stale_mid_tts")
    turn1_id = session.create_next_turn("Turn 1 synthesis")

    async def mock_slow_tts(*args, **kwargs):
        # User barges in during TTS synthesis
        session.create_next_turn("Turn 2 barge-in")
        return mock_pipeline["audio"], mock_pipeline["tts_metadata"]

    with patch.object(default_llm_service, "generate", new=AsyncMock(return_value=mock_pipeline["llm"])), \
         patch.object(default_rime_service, "synthesize", new=mock_slow_tts):

        with pytest.raises(VoiceAgentStaleTurnError) as exc_info:
            await default_voice_agent.process_turn(
                session_id="sess_stale_mid_tts",
                turn_id=turn1_id,
                text_prompt="Turn 1 synthesis",
            )
        assert "superseded during TTS synthesis" in str(exc_info.value)


# =====================================================================
# 4. REST API Endpoint Integration Tests
# =====================================================================

def test_api_process_audio_endpoint_success(client, mock_pipeline):
    """Verify POST /api/voice/agent/process-audio returns binary audio with metadata headers."""
    client.post("/api/voice/session", json={"session_id": "sess_api_audio"})

    with patch.object(default_stt_service, "transcribe", new=AsyncMock(return_value=mock_pipeline["stt"])), \
         patch.object(default_llm_service, "generate", new=AsyncMock(return_value=mock_pipeline["llm"])), \
         patch.object(default_rime_service, "synthesize", new=AsyncMock(return_value=(mock_pipeline["audio"], mock_pipeline["tts_metadata"]))):

        res = client.post(
            "/api/voice/agent/process-audio",
            data={"session_id": "sess_api_audio"},
            files={"file": ("speech.webm", b"fake_audio_bytes", "audio/webm")},
        )

        assert res.status_code == 200
        assert res.headers["x-session-id"] == "sess_api_audio"
        assert res.headers["x-turn-id"] == "1"
        assert res.headers["x-user-transcript"] == "What is the weather today?"
        assert res.headers["x-assistant-response"] == "The weather is sunny and pleasant today."
        assert res.headers["x-speaker"] == "celeste"
        assert res.headers["x-audio-format"] == "mp3"
        assert len(res.content) == len(mock_pipeline["audio"])


def test_api_process_text_endpoint_success(client, mock_pipeline):
    """Verify POST /api/voice/agent/process-text returns binary audio with metadata headers."""
    client.post("/api/voice/session", json={"session_id": "sess_api_text"})

    with patch.object(default_llm_service, "generate", new=AsyncMock(return_value=mock_pipeline["llm"])), \
         patch.object(default_rime_service, "synthesize", new=AsyncMock(return_value=(mock_pipeline["audio"], mock_pipeline["tts_metadata"]))):

        res = client.post(
            "/api/voice/agent/process-text",
            json={
                "session_id": "sess_api_text",
                "text": "What is the capital of Japan?",
            },
        )

        assert res.status_code == 200
        assert res.headers["x-session-id"] == "sess_api_text"
        assert res.headers["x-turn-id"] == "1"
        assert res.headers["x-user-transcript"] == "What is the capital of Japan?"
        assert res.headers["x-assistant-response"] == "The weather is sunny and pleasant today."
        assert res.headers["x-speaker"] == "celeste"
        assert len(res.content) > 0


def test_api_chat_endpoint_success(client, mock_pipeline):
    """Verify POST /api/voice/agent/chat returns structured VoiceAgentResponse JSON."""
    client.post("/api/voice/session", json={"session_id": "sess_api_chat"})

    with patch.object(default_llm_service, "generate", new=AsyncMock(return_value=mock_pipeline["llm"])), \
         patch.object(default_rime_service, "synthesize", new=AsyncMock(return_value=(mock_pipeline["audio"], mock_pipeline["tts_metadata"]))):

        res = client.post(
            "/api/voice/agent/chat",
            json={
                "session_id": "sess_api_chat",
                "text": "Tell me a joke",
            },
        )

        assert res.status_code == 200
        data = res.json()
        assert data["session_id"] == "sess_api_chat"
        assert data["turn_id"] == 1
        assert data["user_prompt"] == "Tell me a joke"
        assert data["assistant_text"] == "The weather is sunny and pleasant today."
        assert data["tts_speaker"] == "celeste"
        assert data["status"] == "SUCCESS"


def test_api_agent_empty_audio_rejected(client):
    """Verify POST /api/voice/agent/process-audio rejects empty audio files with 400 Bad Request."""
    res = client.post(
        "/api/voice/agent/process-audio",
        data={"session_id": "sess_empty"},
        files={"file": ("empty.webm", b"", "audio/webm")},
    )
    assert res.status_code == 400
    assert "cannot be empty" in res.json()["error"]


def test_api_agent_silence_hallucination_rejected(client):
    """Verify POST /api/voice/agent/process-audio rejects Whisper silence hallucinations like 'you'."""
    client.post("/api/voice/session", json={"session_id": "sess_silence_check"})

    hallucinated_stt = TranscriptionResponse(
        session_id="sess_silence_check",
        turn_id=1,
        text="you",
        provider="groq",
        model="whisper-large-v3",
        status="SUCCESS",
    )

    with patch.object(default_stt_service, "transcribe", new=AsyncMock(return_value=hallucinated_stt)):
        res = client.post(
            "/api/voice/agent/process-audio",
            data={"session_id": "sess_silence_check"},
            files={"file": ("silent.webm", b"fake_silent_audio", "audio/webm")},
        )

        assert res.status_code == 400
        assert "No speech detected" in res.json()["error"]

