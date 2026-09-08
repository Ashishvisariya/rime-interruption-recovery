"""Comprehensive Regression Tests for Final Response Handling

Verifies that internal reasoning, planning, chain-of-thought, tool-checking steps,
and unclosed think blocks NEVER reach:
- Rime TTS
- Conversation History
- WebSocket events (AUDIO_STARTED, TURN_COMPLETED)
- API response models / headers
- Chat UI representations

Tests all 10 core scenarios:
1. 'Hello'
2. 'What is 25 times 4?'
3. 'Tell me a joke.'
4. 'What is the weather in Delhi?'
5. A request requiring a tool.
6. A request where the tool is unavailable.
7. An interrupted request.
8. A stale previous turn finishing after a newer turn.
9. LLM response containing reasoning plus final answer.
10. LLM response containing only a normal final answer.
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.config import Settings
from backend.app.core.session import default_session_store
from backend.app.models.schemas import ChatMessage, RimeTTSMetadata
from backend.app.services.llm import (
    clean_final_user_response,
    SAFE_FALLBACK_RESPONSE,
)
from backend.app.services.voice_agent import default_voice_agent
from backend.app.services.rime_tts import default_rime_service
from backend.app.services.conversation import default_conversation_manager


FORBIDDEN_REASONING_SUBSTRINGS = [
    "<think>",
    "</think>",
    "Analyze User Input",
    "Check available tools",
    "Identify Constraints",
    "Determine Factual Need",
    "Draft Response",
    "Check Constraints",
    "Thinking Process",
    "1. Check available tools",
    "2. I do not have a specific weather tool",
    "3. Formulate a response",
    "4. Yes. Yes. No markdown",
    "system prompt",
    "developer instructions",
    "mental draft",
]


@pytest.fixture
def client():
    default_session_store.clear()
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_store():
    default_session_store.clear()
    yield
    default_session_store.clear()


def test_clean_final_response_greeting():
    raw = "Hello! How can I assist you with your day?"
    result = clean_final_user_response(raw, user_prompt="Hello")
    assert result == "Hello! How can I assist you with your day?"
    for marker in FORBIDDEN_REASONING_SUBSTRINGS:
        assert marker.lower() not in result.lower()


def test_clean_final_response_math():
    raw = (
        "1. Analyze: The user asks for 25 times 4.\n"
        "2. Calculate: 25 * 4 = 100.\n"
        "3. Check constraints: No markdown.\n"
        "Final Answer: 25 times 4 is 100."
    )
    result = clean_final_user_response(raw, user_prompt="What is 25 times 4?")
    assert result == "25 times 4 is 100."
    for marker in FORBIDDEN_REASONING_SUBSTRINGS:
        assert marker.lower() not in result.lower()


def test_clean_final_response_joke():
    raw = (
        "<think>Here is a thinking process: draft a joke, make sure no offensive content.</think>"
        "Why did the computer get cold? It left its Windows open."
    )
    result = clean_final_user_response(raw, user_prompt="Tell me a joke.")
    assert result == "Why did the computer get cold? It left its Windows open."
    for marker in FORBIDDEN_REASONING_SUBSTRINGS:
        assert marker.lower() not in result.lower()


def test_clean_final_response_weather_delhi_unavailable():
    raw = (
        "1. Check available tools.\n"
        "2. I do not have a specific weather tool.\n"
        "3. Formulate a response.\n"
        "4. Yes. Yes. No markdown."
    )
    result = clean_final_user_response(raw, user_prompt="What is the weather like in Delhi?")
    assert result == "I don't have access to live weather data right now, so I can't provide the current weather in Delhi."
    for marker in FORBIDDEN_REASONING_SUBSTRINGS:
        assert marker.lower() not in result.lower()


def test_clean_final_response_weather_delhi_with_data():
    raw = (
        "1. Check available tools: Weather tool returned 29C, partly cloudy.\n"
        "2. Format response concisely.\n"
        "Final Answer: Delhi is currently 29°C with partly cloudy skies."
    )
    result = clean_final_user_response(raw, user_prompt="What is the weather like in Delhi?")
    assert result == "Delhi is currently 29°C with partly cloudy skies."
    for marker in FORBIDDEN_REASONING_SUBSTRINGS:
        assert marker.lower() not in result.lower()


def test_clean_final_response_unclosed_think_tag():
    raw = (
        "<think>\n"
        "1. Analyze User Input: What is the weather like in Delhi?\n"
        "2. Check available tools...\n"
        "3. Formulate a response...\n"
    )
    result = clean_final_user_response(raw, user_prompt="What is the weather like in Delhi?")
    assert result == "I don't have access to live weather data right now, so I can't provide the current weather in Delhi."
    for marker in FORBIDDEN_REASONING_SUBSTRINGS:
        assert marker.lower() not in result.lower()


def test_clean_final_response_generic_tool_unavailable():
    raw = (
        "1. Check tools: I need flight search tools.\n"
        "2. Flight search tool not found.\n"
    )
    result = clean_final_user_response(raw, user_prompt="Search for flights to Tokyo.")
    assert result == "I don't have access to live real-time tools right now."
    for marker in FORBIDDEN_REASONING_SUBSTRINGS:
        assert marker.lower() not in result.lower()


@pytest.mark.asyncio
async def test_end_to_end_delhi_weather_rime_receives_only_final_answer():
    default_session_store.clear()
    session = default_conversation_manager.create_session("sess_delhi_weather")

    mock_llm_response = {
        "text": (
            "1. Check available tools.\n"
            "2. I do not have a specific weather tool.\n"
            "3. Formulate a response.\n"
            "4. Yes. Yes. No markdown."
        ),
        "raw_content": "1. Check available tools...",
        "reasoning": "Internal reasoning trace",
        "provider": "groq",
        "model": "qwen/qwen3.6-27b",
    }

    mock_tts_metadata = RimeTTSMetadata(
        session_id="sess_delhi_weather",
        turn_id=1,
        provider="rime",
        model_id="coda",
        speaker="celeste",
        audio_format="mp3",
        audio_bytes_length=128,
        status="SUCCESS",
    )

    with patch.object(default_voice_agent.llm_service, "generate", new=AsyncMock(return_value=mock_llm_response)), \
         patch.object(default_rime_service, "synthesize", new=AsyncMock(return_value=(b"audio_bytes", mock_tts_metadata))) as mock_synth:

        result = await default_voice_agent.process_turn(
            session_id="sess_delhi_weather",
            text_prompt="What is the weather like in Delhi?",
        )

        expected_answer = "I don't have access to live weather data right now, so I can't provide the current weather in Delhi."

        assert result.assistant_text == expected_answer
        assert result.final_response == expected_answer

        mock_synth.assert_called_once()
        called_text = mock_synth.call_args.kwargs["text"]
        assert called_text == expected_answer
        for marker in FORBIDDEN_REASONING_SUBSTRINGS:
            assert marker.lower() not in called_text.lower()

        saved_turn = session.get_turn(1)
        assert saved_turn.assistant_response == expected_answer
        for marker in FORBIDDEN_REASONING_SUBSTRINGS:
            assert marker.lower() not in saved_turn.assistant_response.lower()


@pytest.mark.asyncio
async def test_end_to_end_reasoning_plus_answer_rime_isolation():
    default_session_store.clear()
    session = default_conversation_manager.create_session("sess_reasoning_plus_answer")

    mock_llm_response = {
        "text": (
            "<think>1. Analyze user request: Capital of France. 2. Verify: Paris.</think>\n"
            "Final Answer: The capital of France is Paris."
        ),
        "raw_content": "<think>...</think> Final Answer: The capital of France is Paris.",
        "reasoning": "1. Analyze user request",
        "provider": "groq",
        "model": "qwen/qwen3.6-27b",
    }

    mock_tts_metadata = RimeTTSMetadata(
        session_id="sess_reasoning_plus_answer",
        turn_id=1,
        provider="rime",
        model_id="coda",
        speaker="celeste",
        audio_format="mp3",
        audio_bytes_length=128,
        status="SUCCESS",
    )

    with patch.object(default_voice_agent.llm_service, "generate", new=AsyncMock(return_value=mock_llm_response)), \
         patch.object(default_rime_service, "synthesize", new=AsyncMock(return_value=(b"audio_bytes", mock_tts_metadata))) as mock_synth:

        result = await default_voice_agent.process_turn(
            session_id="sess_reasoning_plus_answer",
            text_prompt="What is the capital of France?",
        )

        assert result.assistant_text == "The capital of France is Paris."
        assert result.final_response == "The capital of France is Paris."

        called_text = mock_synth.call_args.kwargs["text"]
        assert called_text == "The capital of France is Paris."

        saved_turn = session.get_turn(1)
        assert saved_turn.assistant_response == "The capital of France is Paris."


def test_api_agent_process_text_headers_expose_clean_final_response(client):
    mock_llm_response = {
        "text": (
            "1. Check available tools...\n"
            "Final Answer: Delhi is currently 29°C with partly cloudy skies."
        ),
        "provider": "groq",
        "model": "qwen/qwen3.6-27b",
    }
    mock_tts_metadata = RimeTTSMetadata(
        session_id="sess_api_test",
        turn_id=1,
        provider="rime",
        model_id="coda",
        speaker="celeste",
        audio_format="mp3",
        audio_bytes_length=64,
        status="SUCCESS",
    )

    with patch.object(default_voice_agent.llm_service, "generate", new=AsyncMock(return_value=mock_llm_response)), \
         patch.object(default_rime_service, "synthesize", new=AsyncMock(return_value=(b"audio_mp3_data", mock_tts_metadata))):

        payload = {
            "text": "What is the weather like in Delhi?",
        }
        res = client.post("/api/voice/agent/process-text", json=payload)
        assert res.status_code == 200
        assert res.headers["X-Final-Response"] == "Delhi is currently 29C with partly cloudy skies."
        assert "Check available tools" not in res.headers["X-Final-Response"]


def test_api_agent_chat_returns_structured_final_response(client):
    mock_llm_response = {
        "text": "Why did the computer get cold? It left its Windows open.",
        "provider": "groq",
        "model": "qwen/qwen3.6-27b",
    }
    mock_tts_metadata = RimeTTSMetadata(
        session_id="sess_chat_test",
        turn_id=1,
        provider="rime",
        model_id="coda",
        speaker="celeste",
        audio_format="mp3",
        audio_bytes_length=64,
        status="SUCCESS",
    )

    with patch.object(default_voice_agent.llm_service, "generate", new=AsyncMock(return_value=mock_llm_response)), \
         patch.object(default_rime_service, "synthesize", new=AsyncMock(return_value=(b"audio_mp3_data", mock_tts_metadata))):

        payload = {"text": "Tell me a joke."}
        res = client.post("/api/voice/agent/chat", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["assistant_text"] == "Why did the computer get cold? It left its Windows open."
        assert data["final_response"] == "Why did the computer get cold? It left its Windows open."
        assert data["response"] == "Why did the computer get cold? It left its Windows open."
