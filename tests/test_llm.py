"""Unit and Integration Tests for Groq LLM Service & Endpoint

Verifies GroqLLMService behavior, request schemas, error handling, session validation,
and two-phase monotonic turn invariants under strictly mocked HTTP boundaries (0 live API calls).
"""

import pytest
import httpx
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.config import Settings
from backend.app.models.schemas import ChatMessage, LLMRequest
from backend.app.services.llm import (
    GroqLLMService,
    GroqLLMServiceError,
    VOICE_SYSTEM_PROMPT,
)
from backend.app.core.session import default_session_store


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_session_store():
    default_session_store.clear()
    yield
    default_session_store.clear()


MOCK_GROQ_CHAT_RESPONSE = {
    "id": "chatcmpl-test-123",
    "object": "chat.completion",
    "created": 1725700000,
    "model": "qwen/qwen3.6-27b",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "Hello! How can I assist your flight booking today?",
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {
        "prompt_tokens": 32,
        "completion_tokens": 12,
        "total_tokens": 44,
    },
}


# ---------------------------------------------------------------------------
# 1. Configuration & Request Schema Tests
# ---------------------------------------------------------------------------

def test_llm_request_schema_validation():
    """Verify ChatMessage and LLMRequest schema validations."""
    msg = ChatMessage(role="user", content="Hello world")
    assert msg.role == "user"
    assert msg.content == "Hello world"

    req = LLMRequest(
        messages=[msg],
        temperature=0.5,
        max_tokens=100,
    )
    assert len(req.messages) == 1
    assert req.temperature == 0.5
    assert req.max_tokens == 100


def test_config_llm_settings():
    """Verify Groq LLM configuration fields in Settings."""
    s = Settings(
        rime_api_key="test-rime",
        groq_api_key="test-groq",
        gemini_api_key="test-gemini",
        groq_model="qwen/qwen3.6-27b",
    )
    assert s.groq_model == "qwen/qwen3.6-27b"
    assert s.groq_llm_url == "https://api.groq.com/openai/v1/chat/completions"
    assert "test-groq" not in repr(s)


# ---------------------------------------------------------------------------
# 2. GroqLLMService Unit Tests (Mocked HTTP Boundary)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_groq_llm_successful_generation():
    """Verify successful generation and parsing of Groq chat completion response."""
    test_settings = Settings(
        rime_api_key="test-rime",
        groq_api_key="gsk_test_key",
        gemini_api_key="test-gemini",
        groq_model="qwen/qwen3.6-27b",
    )
    service = GroqLLMService(app_settings=test_settings)

    mock_resp = httpx.Response(
        status_code=200,
        json=MOCK_GROQ_CHAT_RESPONSE,
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        result = await service.generate(
            messages=[ChatMessage(role="user", content="Book a flight to Tokyo.")],
        )

        assert result["text"] == "Hello! How can I assist your flight booking today?"
        assert result["provider"] == "groq"
        assert result["model"] == "qwen/qwen3.6-27b"
        assert result["prompt_tokens"] == 32
        assert result["completion_tokens"] == 12
        assert result["status"] == "SUCCESS"
        assert result["latency_ms"] >= 0

        # Check call arguments
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["json"]["model"] == "qwen/qwen3.6-27b"
        assert call_kwargs["json"]["messages"][0]["role"] == "system"
        assert call_kwargs["json"]["messages"][0]["content"] == VOICE_SYSTEM_PROMPT
        assert call_kwargs["json"]["messages"][1]["role"] == "user"
        assert call_kwargs["json"]["messages"][1]["content"] == "Book a flight to Tokyo."


@pytest.mark.asyncio
async def test_groq_llm_custom_system_prompt():
    """Verify custom system prompt override in GroqLLMService."""
    test_settings = Settings(
        rime_api_key="test-rime",
        groq_api_key="gsk_test_key",
        gemini_api_key="test-gemini",
    )
    service = GroqLLMService(app_settings=test_settings)

    mock_resp = httpx.Response(
        status_code=200,
        json=MOCK_GROQ_CHAT_RESPONSE,
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        await service.generate(
            messages=[ChatMessage(role="user", content="Hello")],
            system_prompt="Custom pilot voice instruction.",
        )

        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["json"]["messages"][0]["content"] == "Custom pilot voice instruction."


@pytest.mark.asyncio
async def test_groq_llm_empty_messages_raises():
    """Verify validation error when messages list is empty."""
    service = GroqLLMService(
        app_settings=Settings(
            rime_api_key="r", groq_api_key="g", gemini_api_key="gm"
        )
    )
    with pytest.raises(GroqLLMServiceError, match="empty"):
        await service.generate(messages=[])


@pytest.mark.asyncio
async def test_groq_llm_unconfigured_api_key_raises():
    """Verify error raised when GROQ_API_KEY is empty."""
    test_settings = Settings(
        rime_api_key="test-rime",
        groq_api_key="",
        gemini_api_key="test-gemini",
    )
    service = GroqLLMService(app_settings=test_settings)
    with pytest.raises(GroqLLMServiceError, match="Groq API key is not configured"):
        await service.generate(messages=[ChatMessage(role="user", content="Hello")])


@pytest.mark.asyncio
async def test_groq_llm_auth_error_sanitization():
    """Verify HTTP 401 upstream error is sanitized cleanly without secret leakage."""
    test_settings = Settings(
        rime_api_key="test-rime",
        groq_api_key="invalid_key",
        gemini_api_key="test-gemini",
    )
    service = GroqLLMService(app_settings=test_settings)

    mock_resp = httpx.Response(
        status_code=401,
        json={"error": {"message": "Invalid API Key"}},
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(GroqLLMServiceError, match="authentication failed"):
            await service.generate(messages=[ChatMessage(role="user", content="Hi")])


@pytest.mark.asyncio
async def test_groq_llm_rate_limit_error():
    """Verify HTTP 429 upstream error is mapped properly."""
    test_settings = Settings(
        rime_api_key="test-rime",
        groq_api_key="gsk_key",
        gemini_api_key="test-gemini",
    )
    service = GroqLLMService(app_settings=test_settings)

    mock_resp = httpx.Response(
        status_code=429,
        json={"error": {"message": "Rate limit reached"}},
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(GroqLLMServiceError, match="rate limit or quota exceeded"):
            await service.generate(messages=[ChatMessage(role="user", content="Hi")])


@pytest.mark.asyncio
async def test_groq_llm_timeout_handling():
    """Verify timeout exception mapping."""
    test_settings = Settings(
        rime_api_key="test-rime",
        groq_api_key="gsk_key",
        gemini_api_key="test-gemini",
    )
    service = GroqLLMService(app_settings=test_settings, timeout_seconds=1.0)

    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Timed out")):
        with pytest.raises(GroqLLMServiceError, match="timed out"):
            await service.generate(messages=[ChatMessage(role="user", content="Hi")])


@pytest.mark.asyncio
async def test_groq_llm_empty_choices_handling():
    """Verify handling when Groq returns empty choices."""
    test_settings = Settings(
        rime_api_key="test-rime",
        groq_api_key="gsk_key",
        gemini_api_key="test-gemini",
    )
    service = GroqLLMService(app_settings=test_settings)

    mock_resp = httpx.Response(
        status_code=200,
        json={"choices": []},
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(GroqLLMServiceError, match="empty choices"):
            await service.generate(messages=[ChatMessage(role="user", content="Hi")])


# ---------------------------------------------------------------------------
# 3. API Endpoint Tests (POST /api/voice/respond)
# ---------------------------------------------------------------------------

def test_api_respond_missing_session(client):
    """Verify HTTP 404 when session_id is provided but does not exist."""
    payload = {
        "session_id": "non-existent-session-id",
        "turn_id": 1,
        "messages": [{"role": "user", "content": "Hello"}],
    }
    res = client.post("/api/voice/respond", json=payload)
    assert res.status_code == 404
    assert "not found" in res.json()["error"]


def test_api_respond_superseded_turn_pre_call(client):
    """Verify HTTP 409 when turn_id is not active before calling LLM."""
    session = default_session_store.get_or_create_session("sess-test-pre")
    session.create_next_turn("Turn 1 prompt")  # Turn 1
    session.create_next_turn("Turn 2 prompt")  # Turn 2, Turn 1 is now superseded

    payload = {
        "session_id": "sess-test-pre",
        "turn_id": 1,  # Superseded turn
        "messages": [{"role": "user", "content": "Turn 1 request"}],
    }
    res = client.post("/api/voice/respond", json=payload)
    assert res.status_code == 409
    assert "not active" in res.json()["error"]


def test_api_respond_stale_turn_post_completion(client):
    """Verify HTTP 409 and discard when turn is superseded while LLM call is running."""
    session = default_session_store.get_or_create_session("sess-test-post")
    turn1_id = session.create_next_turn("Find flights to Tokyo")  # Turn 1

    # Mock LLM service to simulate side-effect of barge-in advancing turn during generation
    async def simulate_barge_in(*args, **kwargs):
        # User interrupts with Turn 2 while Turn 1 LLM generation is in flight
        session.create_next_turn("Actually make it London")
        return {
            "text": "Here are flights to Tokyo.",
            "provider": "groq",
            "model": "qwen/qwen3.6-27b",
            "prompt_tokens": 20,
            "completion_tokens": 10,
            "latency_ms": 150.0,
            "status": "SUCCESS",
        }

    with patch("backend.app.api.voice.default_llm_service.generate", side_effect=simulate_barge_in):
        payload = {
            "session_id": "sess-test-post",
            "turn_id": turn1_id,
            "messages": [{"role": "user", "content": "Find flights to Tokyo"}],
        }
        res = client.post("/api/voice/respond", json=payload)

        # Invariant check: Turn 1 response MUST be rejected and discarded
        assert res.status_code == 409
        assert "superseded during LLM response generation" in res.json()["error"]
        assert session.active_turn_id == 2


def test_api_respond_success_with_mocked_service(client):
    """Verify HTTP 200 successful response when turn remains active."""
    session = default_session_store.get_or_create_session("sess-test-success")
    turn_id = session.create_next_turn("What is the weather?")

    mock_llm_result = {
        "text": "The weather is sunny and 72 degrees.",
        "provider": "groq",
        "model": "qwen/qwen3.6-27b",
        "prompt_tokens": 15,
        "completion_tokens": 9,
        "latency_ms": 120.5,
        "status": "SUCCESS",
    }

    with patch("backend.app.api.voice.default_llm_service.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_llm_result

        payload = {
            "session_id": "sess-test-success",
            "turn_id": turn_id,
            "messages": [{"role": "user", "content": "What is the weather?"}],
        }
        res = client.post("/api/voice/respond", json=payload)

        assert res.status_code == 200
        data = res.json()
        assert data["session_id"] == "sess-test-success"
        assert data["turn_id"] == turn_id
        assert data["text"] == "The weather is sunny and 72 degrees."
        assert data["provider"] == "groq"
        assert data["model"] == "qwen/qwen3.6-27b"
        assert data["status"] == "SUCCESS"
        assert data["latency_ms"] == 120.5
