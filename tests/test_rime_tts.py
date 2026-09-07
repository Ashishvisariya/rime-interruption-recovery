"""Unit Tests for Rime TTS Integration

Tests RimeTTSService, request parameter validation, turn association,
stale turn rejection invariants, and API endpoints using mocked HTTP boundaries.
ZERO live Rime API calls are made during the execution of this test module.
"""

import pytest
import httpx
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.config import Settings
from backend.app.core.session import default_session_store
from backend.app.models.schemas import RimeTTSMetadata
from backend.app.services.rime_tts import RimeTTSService, RimeTTSError, default_rime_service


@pytest.fixture
def client():
    default_session_store.clear()
    return TestClient(app)


@pytest.fixture
def sample_audio_bytes():
    # Fake binary audio header/bytes (MP3 frame sync header simulation)
    return b"\xff\xfb\x90\x44" + b"\x00" * 1024


# --- 1. RimeTTSService Unit Tests (Mocked Transport) ---

@pytest.mark.asyncio
async def test_rime_service_successful_synthesis(sample_audio_bytes):
    """Verify RimeTTSService constructs payload correctly and parses binary audio."""
    mock_response = httpx.Response(
        status_code=200,
        content=sample_audio_bytes,
        headers={"Content-Type": "audio/mpeg"},
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)

    settings = Settings(
        rime_api_key="mock_test_key_12345",
        rime_api_url="https://users.rime.ai/v1/rime-tts",
        rime_default_model="coda",
        rime_default_speaker="celeste",
        rime_default_format="mp3",
    )

    service = RimeTTSService(settings=settings, client=mock_client)
    audio, metadata = await service.synthesize(
        text="Hello Rime!",
        session_id="sess_mock_1",
        turn_id=1,
    )

    assert audio == sample_audio_bytes
    assert isinstance(metadata, RimeTTSMetadata)
    assert metadata.session_id == "sess_mock_1"
    assert metadata.turn_id == 1
    assert metadata.provider == "rime"
    assert metadata.model_id == "coda"
    assert metadata.speaker == "celeste"
    assert metadata.audio_format == "mp3"
    assert metadata.audio_bytes_length == len(sample_audio_bytes)
    assert metadata.status == "SUCCESS"

    # Verify HTTP request arguments
    mock_client.post.assert_called_once()
    called_args, called_kwargs = mock_client.post.call_args
    assert called_args[0] == "https://users.rime.ai/v1/rime-tts"
    assert called_kwargs["headers"]["Authorization"] == "Bearer mock_test_key_12345"
    assert called_kwargs["headers"]["Accept"] == "audio/mpeg"
    assert called_kwargs["json"] == {
        "speaker": "celeste",
        "text": "Hello Rime!",
        "modelId": "coda",
        "audioFormat": "mp3",
    }


@pytest.mark.asyncio
async def test_rime_service_custom_overrides(sample_audio_bytes):
    """Verify RimeTTSService supports model, speaker, format, and lang overrides."""
    mock_response = httpx.Response(
        status_code=200,
        content=sample_audio_bytes,
        headers={"Content-Type": "audio/wav"},
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)

    settings = Settings(rime_api_key="mock_key")
    service = RimeTTSService(settings=settings, client=mock_client)

    audio, metadata = await service.synthesize(
        text="Custom options test",
        session_id="sess_custom",
        turn_id=3,
        model_id="mistv3",
        speaker="astra",
        audio_format="wav",
        lang="en",
    )

    assert metadata.model_id == "mistv3"
    assert metadata.speaker == "astra"
    assert metadata.audio_format == "wav"

    called_kwargs = mock_client.post.call_args[1]
    assert called_kwargs["headers"]["Accept"] == "audio/wav"
    assert called_kwargs["json"] == {
        "speaker": "astra",
        "text": "Custom options test",
        "modelId": "mistv3",
        "audioFormat": "wav",
        "lang": "en",
    }


@pytest.mark.asyncio
async def test_rime_service_empty_text_raises():
    """Verify empty text raises ValueError without making network request."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    settings = Settings(rime_api_key="mock_key")
    service = RimeTTSService(settings=settings, client=mock_client)

    with pytest.raises(ValueError, match="cannot be empty"):
        await service.synthesize(text="", session_id="s1", turn_id=1)

    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_rime_service_unconfigured_api_key_raises():
    """Verify unconfigured RIME_API_KEY raises ValueError without network request."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    settings = Settings(rime_api_key="")
    service = RimeTTSService(settings=settings, client=mock_client)

    with pytest.raises(ValueError, match="RIME_API_KEY is not configured"):
        await service.synthesize(text="Hello", session_id="s1", turn_id=1)

    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_rime_service_http_error_handling():
    """Verify non-200 HTTP responses raise sanitized RimeTTSError."""
    mock_response = httpx.Response(
        status_code=401,
        json={"detail": "Invalid authorization token"},
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)

    settings = Settings(rime_api_key="test_secret_key_123")
    service = RimeTTSService(settings=settings, client=mock_client)

    with pytest.raises(RimeTTSError) as exc_info:
        await service.synthesize(text="Hello", session_id="s1", turn_id=1)

    err_msg = str(exc_info.value)
    assert "HTTP 401" in err_msg
    assert "Invalid authorization token" in err_msg
    # Ensure raw secret key is never leaked in error
    assert "test_secret_key_123" not in err_msg


@pytest.mark.asyncio
async def test_rime_service_empty_audio_response_raises():
    """Verify empty audio body from upstream raises RimeTTSError."""
    mock_response = httpx.Response(status_code=200, content=b"")
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)

    settings = Settings(rime_api_key="mock_key")
    service = RimeTTSService(settings=settings, client=mock_client)

    with pytest.raises(RimeTTSError, match="empty audio"):
        await service.synthesize(text="Hello", session_id="s1", turn_id=1)


@pytest.mark.asyncio
async def test_rime_service_timeout_handling():
    """Verify network timeout raises RimeTTSError cleanly."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(side_effect=httpx.ReadTimeout("Read timed out"))

    settings = Settings(rime_api_key="mock_key")
    service = RimeTTSService(settings=settings, client=mock_client)

    with pytest.raises(RimeTTSError, match="timed out"):
        await service.synthesize(text="Hello", session_id="s1", turn_id=1)


# --- 2. API Endpoint /api/voice/tts Unit Tests ---

def test_api_tts_missing_session(client):
    """Verify 404 when session does not exist."""
    res = client.post(
        "/api/voice/tts",
        json={"session_id": "nonexistent_sess", "turn_id": 1, "text": "Test"},
    )
    assert res.status_code == 404
    assert "not found" in res.json()["error"].lower()


def test_api_tts_invalid_or_superseded_turn(client):
    """Verify 409 Conflict when turn_id is superseded or not active."""
    # Create session and advance to Turn 2
    sess_res = client.post("/api/voice/session", json={"session_id": "sess_stale_tts"})
    assert sess_res.status_code == 201

    client.post("/api/voice/session/sess_stale_tts/turn", json={"prompt": "Turn 1"})
    client.post("/api/voice/session/sess_stale_tts/turn", json={"prompt": "Turn 2"})

    # Attempt TTS for superseded Turn 1
    res = client.post(
        "/api/voice/tts",
        json={"session_id": "sess_stale_tts", "turn_id": 1, "text": "Old turn prompt"},
    )
    assert res.status_code == 409
    assert "not active" in res.json()["error"].lower()


def test_api_tts_success_with_mocked_service(client, sample_audio_bytes):
    """Verify 200 OK with binary audio and response headers upon successful synthesis."""
    # Setup session and active Turn 1
    client.post("/api/voice/session", json={"session_id": "sess_tts_ok"})
    client.post("/api/voice/session/sess_tts_ok/turn", json={"prompt": "Hello"})

    metadata = RimeTTSMetadata(
        session_id="sess_tts_ok",
        turn_id=1,
        provider="rime",
        model_id="coda",
        speaker="celeste",
        audio_format="mp3",
        audio_bytes_length=len(sample_audio_bytes),
        status="SUCCESS",
    )

    with patch.object(
        default_rime_service,
        "synthesize",
        new=AsyncMock(return_value=(sample_audio_bytes, metadata)),
    ):
        res = client.post(
            "/api/voice/tts",
            json={
                "session_id": "sess_tts_ok",
                "turn_id": 1,
                "text": "Rime TTS integration test.",
            },
        )

        assert res.status_code == 200
        assert res.content == sample_audio_bytes
        assert res.headers["content-type"] == "audio/mpeg"
        assert res.headers["x-session-id"] == "sess_tts_ok"
        assert res.headers["x-turn-id"] == "1"
        assert res.headers["x-provider"] == "rime"
        assert res.headers["x-model-id"] == "coda"
        assert res.headers["x-speaker"] == "celeste"
        assert res.headers["x-audio-format"] == "mp3"


def test_api_tts_mid_generation_turn_invalidation(client, sample_audio_bytes):
    """Verify mid-generation barge-in discards audio and returns 409 Conflict."""
    # Setup session and Turn 1
    client.post("/api/voice/session", json={"session_id": "sess_race_tts"})
    client.post("/api/voice/session/sess_race_tts/turn", json={"prompt": "Turn 1"})

    metadata = RimeTTSMetadata(
        session_id="sess_race_tts",
        turn_id=1,
        provider="rime",
        model_id="coda",
        speaker="celeste",
        audio_format="mp3",
        audio_bytes_length=len(sample_audio_bytes),
        status="SUCCESS",
    )

    # Simulate barge-in happening during the async synthesize call
    async def simulate_barge_in(*args, **kwargs):
        session = default_session_store.get_session("sess_race_tts")
        session.create_next_turn("Turn 2 (Barge-In!)")  # active_turn_id becomes 2
        return (sample_audio_bytes, metadata)

    with patch.object(default_rime_service, "synthesize", new=AsyncMock(side_effect=simulate_barge_in)):
        res = client.post(
            "/api/voice/tts",
            json={
                "session_id": "sess_race_tts",
                "turn_id": 1,
                "text": "Turn 1 text to speak",
            },
        )

        assert res.status_code == 409
        assert "superseded during audio synthesis" in res.json()["error"]
