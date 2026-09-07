"""Unit and Integration Tests for Phase 6 Backend

Tests CORS headers, Phase 6 root endpoint, and browser-compatible audio endpoint behavior.
ZERO live Rime API calls are made during the execution of this test module.
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.session import default_session_store
from backend.app.models.schemas import RimeTTSMetadata
from backend.app.services.rime_tts import default_rime_service


@pytest.fixture
def client():
    default_session_store.clear()
    return TestClient(app)


def test_root_endpoint_phase6(client):
    """Verify root endpoint reports online and valid phase."""
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["service"] == "Rime Voice AI Assistant"
    assert data["phase"] >= 6
    assert data["status"] == "online"


def test_cors_headers_on_tts_options_request(client):
    """Verify CORS preflight OPTIONS request returns appropriate allowed/exposed headers."""
    res = client.options(
        "/api/voice/tts",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert res.status_code == 200
    assert "access-control-allow-origin" in res.headers
    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_tts_response_exposes_metadata_headers(client):
    """Verify TTS endpoint exposes custom X-Session-ID, X-Turn-ID, X-Speaker headers for browser client."""
    client.post("/api/voice/session", json={"session_id": "sess_cors_test"})
    client.post("/api/voice/session/sess_cors_test/turn", json={"prompt": "Hello"})

    fake_audio = b"\xff\xfb\x90\x44" + b"\x00" * 512
    metadata = RimeTTSMetadata(
        session_id="sess_cors_test",
        turn_id=1,
        provider="rime",
        model_id="coda",
        speaker="celeste",
        audio_format="mp3",
        audio_bytes_length=len(fake_audio),
        status="SUCCESS",
    )

    with patch.object(
        default_rime_service,
        "synthesize",
        new=AsyncMock(return_value=(fake_audio, metadata)),
    ):
        res = client.post(
            "/api/voice/tts",
            headers={"Origin": "http://localhost:5173"},
            json={
                "session_id": "sess_cors_test",
                "turn_id": 1,
                "text": "Testing CORS metadata headers.",
            },
        )

        assert res.status_code == 200
        assert res.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert res.headers["x-session-id"] == "sess_cors_test"
        assert res.headers["x-turn-id"] == "1"
        assert res.headers["x-model-id"] == "coda"
        assert res.headers["x-speaker"] == "celeste"
        assert res.headers["x-audio-format"] == "mp3"
        assert res.headers["x-audio-bytes-length"] == str(len(fake_audio))
