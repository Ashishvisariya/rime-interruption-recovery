"""Main FastAPI Application Entrypoint."""

from fastapi import FastAPI
from backend.app.config import get_settings

app = FastAPI(
    title="Rime Voice AI Assistant with Interruption & Recovery",
    description="DataForge 2026 Rime Hackathon - Phase 1 Foundation",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/")
def root():
    """Root endpoint for status information."""
    settings = get_settings()
    return {
        "service": "Rime Voice AI Assistant",
        "status": "online",
        "phase": 1,
        "rime_configured": settings.is_rime_configured,
    }
