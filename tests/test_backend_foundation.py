"""Backend Foundation Test Suite

Comprehensive tests for FastAPI app initialization, deterministic health probes,
safe configuration parsing, session state lifecycle, and monotonic turn invalidation.
"""

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.config import Settings, get_settings
from backend.app.core.session import VoiceSession, SessionStore, default_session_store


@pytest.fixture
def client():
    # Reset default session store before each test
    default_session_store.clear()
    return TestClient(app)


# --- 1. Health & Root Endpoints ---

def test_health_endpoint(client):
    """Verify that GET /health returns 200 OK with deterministic JSON payload."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_endpoint(client):
    """Verify that GET / returns service information without secret exposure."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Rime Voice AI Assistant"
    assert data["status"] == "online"
    assert data["phase"] == 4
    assert isinstance(data["rime_configured"], bool)


# --- 2. Configuration & Secret Safety ---

def test_config_safe_representation():
    """Verify that repr() and str() of Settings never leak actual API keys."""
    settings = Settings(
        rime_api_key="secret_rime_key_123",
        groq_api_key="secret_groq_key_456",
        gemini_api_key="secret_gemini_key_789",
    )
    rep = repr(settings)
    s = str(settings)

    assert "secret_rime_key_123" not in rep
    assert "secret_groq_key_456" not in rep
    assert "secret_gemini_key_789" not in rep
    assert "***" in rep

    assert "secret_rime_key_123" not in s
    assert "secret_groq_key_456" not in s
    assert "secret_gemini_key_789" not in s


def test_config_missing_keys_raises_error():
    """Verify that validate_required_keys fails clearly with missing variable names."""
    settings = Settings(rime_api_key="", groq_api_key="", gemini_api_key="")
    
    with pytest.raises(ValueError) as exc_info:
        settings.validate_required_keys()
    
    err_msg = str(exc_info.value)
    assert "Missing required configuration key(s)" in err_msg
    assert "RIME_API_KEY" in err_msg
    assert "GROQ_API_KEY" in err_msg
    assert "GEMINI_API_KEY" in err_msg


def test_config_valid_keys_passes():
    """Verify that validate_required_keys succeeds when keys are present."""
    settings = Settings(
        rime_api_key="valid_key",
        groq_api_key="valid_key",
        gemini_api_key="valid_key",
    )
    settings.validate_required_keys()
    assert settings.is_fully_configured is True
    assert settings.is_rime_configured is True


# --- 3. Core Session & Turn Invalidation Invariant ---

def test_session_monotonic_turn_creation():
    """Verify that turns increment monotonically starting from 1."""
    session = VoiceSession()
    assert session.active_turn_id == 0

    t1 = session.create_next_turn("First query")
    assert t1 == 1
    assert session.active_turn_id == 1
    assert session.is_turn_active(1) is True

    t2 = session.create_next_turn("Interrupted query")
    assert t2 == 2
    assert session.active_turn_id == 2
    assert session.is_turn_active(2) is True


def test_session_turn_isolation_and_invalidation():
    """Verify that creating Turn 2 immediately invalidates Turn 1."""
    session = VoiceSession()
    t1 = session.create_next_turn("Turn 1 prompt")
    assert session.is_turn_active(t1) is True

    t2 = session.create_next_turn("Turn 2 prompt")
    
    # Invariant: Turn 1 is no longer active
    assert session.is_turn_active(t1) is False
    assert session.validate_turn(t1) is False

    # Invariant: Turn 2 is active
    assert session.is_turn_active(t2) is True
    assert session.validate_turn(t2) is True


def test_stale_turn_result_rejection_invariant():
    """Verify that stale turn results are strictly rejected by the session state."""
    session = VoiceSession()
    t1 = session.create_next_turn("Query A")
    t2 = session.create_next_turn("Query B")
    t3 = session.create_next_turn("Query C")

    assert session.validate_turn(t1) is False
    assert session.validate_turn(t2) is False
    assert session.validate_turn(t3) is True
    assert session.validate_turn(999) is False


def test_session_store_lifecycle():
    """Verify thread-safe SessionStore operations."""
    store = SessionStore()
    sess_a = store.get_or_create_session("sess_custom_1")
    assert sess_a.session_id == "sess_custom_1"

    # Retrieving existing session returns identical instance
    sess_a_retrieved = store.get_session("sess_custom_1")
    assert sess_a_retrieved is sess_a

    # Non-existent session returns None
    assert store.get_session("non_existent") is None


# --- 4. API Gateway Endpoints ---

def test_api_create_and_get_session(client):
    """Verify POST /api/voice/session and GET /api/voice/session/{id}."""
    res_create = client.post("/api/voice/session", json={"session_id": "test_sess_100"})
    assert res_create.status_code == 201
    data = res_create.json()
    assert data["session_id"] == "test_sess_100"
    assert data["active_turn_id"] == 0
    assert data["is_active"] is True

    res_get = client.get("/api/voice/session/test_sess_100")
    assert res_get.status_code == 200
    assert res_get.json()["session_id"] == "test_sess_100"


def test_api_turn_advancement(client):
    """Verify POST /api/voice/session/{id}/turn advances active turn sequence."""
    client.post("/api/voice/session", json={"session_id": "sess_turn_test"})
    
    res_t1 = client.post("/api/voice/session/sess_turn_test/turn", json={"prompt": "Hello"})
    assert res_t1.status_code == 200
    assert res_t1.json()["active_turn_id"] == 1

    res_t2 = client.post("/api/voice/session/sess_turn_test/turn", json={"prompt": "New instruction"})
    assert res_t2.status_code == 200
    assert res_t2.json()["active_turn_id"] == 2


def test_api_session_not_found(client):
    """Verify 404 error handling for non-existent session."""
    res = client.get("/api/voice/session/missing_session_xyz")
    assert res.status_code == 404
    assert "error" in res.json()
