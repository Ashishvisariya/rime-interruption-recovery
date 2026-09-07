"""Unit Tests for Speech-to-Text (STT) Integration

Tests GroqSTTService, parameter serialization, multipart uploads, error sanitization,
and the /api/voice/transcribe endpoint using mocked HTTP boundaries.
ZERO live Groq API calls are made during the execution of this test module.
"""

import pytest
import httpx
from io import BytesIO
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.config import Settings
from backend.app.core.session import default_session_store
from backend.app.models.schemas import TranscriptionResponse
from backend.app.services.stt import GroqSTTService, STTError, default_stt_service


@pytest.fixture
def client():
    default_session_store.clear()
    return TestClient(app)


@pytest.fixture
def sample_audio_payload():
    # Fake PCM / WAV header + dummy audio bytes
    return b"RIFF" + b"\x00" * 36 + b"data" + b"\x00" * 512


# --- 1. GroqSTTService Unit Tests (Mocked Transport) ---

@pytest.mark.asyncio
async def test_stt_service_successful_transcription(sample_audio_payload):
    """Verify GroqSTTService sends multipart request and parses transcript."""
    mock_response = httpx.Response(
        status_code=200,
        json={"text": "Hello, this is a speech recognition test."},
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)

    settings = Settings(
        groq_api_key="mock_groq_key_998877",
        groq_stt_url="https://api.groq.com/openai/v1/audio/transcriptions",
        groq_stt_model="whisper-large-v3",
    )

    service = GroqSTTService(settings=settings, client=mock_client)
    res = await service.transcribe(
        audio_bytes=sample_audio_payload,
        filename="speech.wav",
        mime_type="audio/wav",
        language="en",
        session_id="sess_stt_1",
        turn_id=1,
    )

    assert isinstance(res, TranscriptionResponse)
    assert res.text == "Hello, this is a speech recognition test."
    assert res.provider == "groq"
    assert res.model == "whisper-large-v3"
    assert res.session_id == "sess_stt_1"
    assert res.turn_id == 1
    assert res.status == "SUCCESS"

    # Verify HTTP request parameters
    mock_client.post.assert_called_once()
    called_args, called_kwargs = mock_client.post.call_args
    assert called_args[0] == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert called_kwargs["headers"]["Authorization"] == "Bearer mock_groq_key_998877"
    assert called_kwargs["data"]["model"] == "whisper-large-v3"
    assert called_kwargs["data"]["language"] == "en"


@pytest.mark.asyncio
async def test_stt_service_empty_audio_raises():
    """Verify empty audio bytes raise ValueError before network request."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    settings = Settings(groq_api_key="mock_key")
    service = GroqSTTService(settings=settings, client=mock_client)

    with pytest.raises(ValueError, match="cannot be empty"):
        await service.transcribe(audio_bytes=b"")

    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_stt_service_unconfigured_api_key_raises(sample_audio_payload):
    """Verify missing GROQ_API_KEY raises ValueError before network request."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    settings = Settings(groq_api_key="")
    service = GroqSTTService(settings=settings, client=mock_client)

    with pytest.raises(ValueError, match="GROQ_API_KEY is not configured"):
        await service.transcribe(audio_bytes=sample_audio_payload)

    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_stt_service_http_error_sanitization(sample_audio_payload):
    """Verify upstream non-200 HTTP responses raise sanitized STTError without leaking API keys."""
    mock_response = httpx.Response(
        status_code=401,
        json={"error": {"message": "Invalid API Key provided"}},
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)

    settings = Settings(groq_api_key="secret_groq_key_val_12345")
    service = GroqSTTService(settings=settings, client=mock_client)

    with pytest.raises(STTError) as exc_info:
        await service.transcribe(audio_bytes=sample_audio_payload)

    err_msg = str(exc_info.value)
    assert "HTTP 401" in err_msg
    assert "Invalid API Key" in err_msg
    assert "secret_groq_key_val_12345" not in err_msg


@pytest.mark.asyncio
async def test_stt_service_timeout_handling(sample_audio_payload):
    """Verify network timeout raises STTError."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(side_effect=httpx.ReadTimeout("Request timed out"))

    settings = Settings(groq_api_key="mock_key")
    service = GroqSTTService(settings=settings, client=mock_client)

    with pytest.raises(STTError, match="timed out"):
        await service.transcribe(audio_bytes=sample_audio_payload)


# --- 2. API Endpoint /api/voice/transcribe Unit Tests ---

def test_api_transcribe_missing_session(client, sample_audio_payload):
    """Verify 404 when session_id is provided but not found."""
    files = {"file": ("test.wav", sample_audio_payload, "audio/wav")}
    data = {"session_id": "nonexistent_sess_123"}
    res = client.post("/api/voice/transcribe", files=files, data=data)
    assert res.status_code == 404
    assert "not found" in res.json()["error"].lower()


def test_api_transcribe_empty_file_rejected(client):
    """Verify 400 Bad Request when uploaded audio file is empty."""
    files = {"file": ("empty.wav", b"", "audio/wav")}
    res = client.post("/api/voice/transcribe", files=files)
    assert res.status_code == 400
    assert "empty" in res.json()["error"].lower()


def test_api_transcribe_success_with_mocked_service(client, sample_audio_payload):
    """Verify 200 OK and TranscriptionResponse from /api/voice/transcribe."""
    # Setup session
    client.post("/api/voice/session", json={"session_id": "sess_transcribe_ok"})

    mock_result = TranscriptionResponse(
        session_id="sess_transcribe_ok",
        turn_id=1,
        text="Recognized user command.",
        provider="groq",
        model="whisper-large-v3",
        status="SUCCESS",
    )

    with patch.object(
        default_stt_service,
        "transcribe",
        new=AsyncMock(return_value=mock_result),
    ):
        files = {"file": ("mic_recording.webm", sample_audio_payload, "audio/webm")}
        data = {
            "session_id": "sess_transcribe_ok",
            "turn_id": "1",
            "language": "en",
        }
        res = client.post("/api/voice/transcribe", files=files, data=data)

        assert res.status_code == 200
        data = res.json()
        assert data["text"] == "Recognized user command."
        assert data["provider"] == "groq"
        assert data["model"] == "whisper-large-v3"
        assert data["session_id"] == "sess_transcribe_ok"
        assert data["turn_id"] == 1
        assert data["status"] == "SUCCESS"
