"""Phase 1 Tests: Health Check, Configuration & Safe Secret Handling."""

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.config import Settings, get_settings


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    """Verify that GET /health returns 200 OK with expected JSON payload."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_endpoint(client):
    """Verify that GET / returns service information without secrets."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Rime Voice AI Assistant"
    assert data["status"] == "online"
    assert data["phase"] == 1
    assert "rime_configured" in data


def test_config_safe_representation():
    """Verify that str() and repr() of Settings never leak actual API keys."""
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
    """Verify that validate_required_keys fails clearly when keys are missing."""
    settings = Settings(rime_api_key="", groq_api_key="", gemini_api_key="")
    
    with pytest.raises(ValueError) as exc_info:
        settings.validate_required_keys()
    
    err_msg = str(exc_info.value)
    assert "Missing required configuration key(s)" in err_msg
    assert "RIME_API_KEY" in err_msg
    assert "GROQ_API_KEY" in err_msg
    assert "GEMINI_API_KEY" in err_msg


def test_config_valid_keys_passes():
    """Verify that validate_required_keys succeeds when all required keys are set."""
    settings = Settings(
        rime_api_key="valid_key",
        groq_api_key="valid_key",
        gemini_api_key="valid_key",
    )
    # Should not raise
    settings.validate_required_keys()
    assert settings.is_fully_configured is True
    assert settings.is_rime_configured is True
