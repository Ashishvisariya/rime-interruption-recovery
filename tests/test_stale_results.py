"""Stale Result Protection Invariant Tests

Verifies the foundational architectural principle:
"Cancellation is best-effort; stale-result rejection is the correctness guarantee."

Guarantees that late-returning asynchronous results for superseded or interrupted turns
are strictly rejected and cannot mutate user-visible state or conversation history.
ZERO live external API calls are made.
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.session import default_session_store
from backend.app.models.schemas import RimeTTSMetadata
from backend.app.services.llm import default_llm_service
from backend.app.services.rime_tts import default_rime_service


@pytest.fixture
def client():
    default_session_store.clear()
    return TestClient(app)


def test_stale_llm_response_rejection_at_api_gate(client):
    """Verify that if Turn 1 LLM finishes after Turn 2 is created, the response is discarded (409 Conflict)."""
    client.post("/api/voice/session", json={"session_id": "sess_stale_llm"})
    client.post("/api/voice/session/sess_stale_llm/turn", json={"prompt": "Turn 1 request"})

    # Mock LLM generation
    mock_llm_result = {
        "text": "Stale LLM reply for Turn 1",
        "provider": "groq",
        "model": "qwen/qwen3.6-27b",
        "prompt_tokens": 10,
        "completion_tokens": 15,
        "latency_ms": 120.0,
    }

    async def mock_slow_llm(*args, **kwargs):
        # In-flight barge-in occurs: session advances to Turn 2 while LLM is running
        session = default_session_store.get_session("sess_stale_llm")
        session.create_next_turn("Turn 2 barge-in request")
        return mock_llm_result

    with patch.object(default_llm_service, "generate", new=mock_slow_llm):
        res = client.post(
            "/api/voice/respond",
            json={
                "session_id": "sess_stale_llm",
                "turn_id": 1,
                "messages": [{"role": "user", "content": "Turn 1 request"}],
            },
        )

        assert res.status_code == 409
        assert "superseded during LLM response generation" in res.json()["error"]

    # Verify session history contains Turn 1 prompt, Turn 2 prompt, but NO Turn 1 assistant reply
    session = default_session_store.get_session("sess_stale_llm")
    history = session.get_conversation_history()
    contents = [m.content for m in history]
    assert "Turn 1 request" in contents
    assert "Turn 2 barge-in request" in contents
    assert "Stale LLM reply for Turn 1" not in contents


def test_stale_tts_synthesis_rejection_at_api_gate(client):
    """Verify that if Turn 1 TTS finishes after Turn 2 is created, audio output is discarded (409 Conflict)."""
    client.post("/api/voice/session", json={"session_id": "sess_stale_tts"})
    client.post("/api/voice/session/sess_stale_tts/turn", json={"prompt": "Turn 1 TTS"})

    fake_audio = b"\xff\xfb\x90\x44" + b"\x00" * 256
    metadata = RimeTTSMetadata(
        session_id="sess_stale_tts",
        turn_id=1,
        provider="rime",
        model_id="coda",
        speaker="celeste",
        audio_format="mp3",
        audio_bytes_length=len(fake_audio),
        status="SUCCESS",
    )

    async def mock_slow_tts(*args, **kwargs):
        # User interrupts while TTS synthesis is in progress
        session = default_session_store.get_session("sess_stale_tts")
        session.create_next_turn("Turn 2 barge-in")
        return fake_audio, metadata

    with patch.object(default_rime_service, "synthesize", new=mock_slow_tts):
        res = client.post(
            "/api/voice/tts",
            json={
                "session_id": "sess_stale_tts",
                "turn_id": 1,
                "text": "Old text being synthesized",
            },
        )

        assert res.status_code == 409
        assert "superseded during audio synthesis" in res.json()["error"]


def test_stale_direct_turn_completion_rejection(client):
    """Verify complete_turn rejects stale attempts and keeps active turn intact."""
    session = default_session_store.get_or_create_session("sess_direct_stale")
    t1 = session.create_next_turn("Turn 1")
    t2 = session.create_next_turn("Turn 2")

    # Direct mutation attempt for Turn 1
    rejected = session.mark_turn_completed(t1, "Turn 1 assistant answer")
    assert rejected is False

    # Active Turn 2 can complete
    accepted = session.mark_turn_completed(t2, "Turn 2 assistant answer")
    assert accepted is True

    history = session.get_conversation_history()
    contents = [m.content for m in history]
    assert "Turn 1 assistant answer" not in contents
    assert "Turn 2 assistant answer" in contents
