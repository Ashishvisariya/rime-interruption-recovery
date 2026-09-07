"""Typed Pydantic Data Models & Schemas

Defines structured models for session management, turn tracking,
event logging, and API request/response payloads in accordance with the Phase 3 architecture.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Deterministic health check response model."""
    status: str = Field(default="ok", description="Service health status")


class RootStatusResponse(BaseModel):
    """Root service status response model."""
    service: str = "Rime Voice AI Assistant"
    status: str = "online"
    phase: int = 5
    rime_configured: bool = False


class RimeTTSRequest(BaseModel):
    """Payload for TTS generation request."""
    session_id: str = Field(..., description="Target session ID")
    turn_id: int = Field(..., ge=1, description="Associated turn ID")
    text: str = Field(..., min_length=1, description="Text string to synthesize into speech")
    model_id: Optional[str] = Field(default=None, description="Optional Rime model ID override (e.g. 'coda')")
    speaker: Optional[str] = Field(default=None, description="Optional speaker voice override (e.g. 'celeste')")
    audio_format: Optional[str] = Field(default=None, description="Audio format (e.g. 'mp3', 'wav')")
    lang: Optional[str] = Field(default=None, description="Language code (e.g. 'en')")


class RimeTTSMetadata(BaseModel):
    """Structured metadata describing synthesized speech."""
    session_id: str = Field(..., description="Associated session ID")
    turn_id: int = Field(..., description="Associated turn ID")
    provider: str = Field(default="rime", description="TTS Provider name")
    model_id: str = Field(..., description="Rime model ID used")
    speaker: str = Field(..., description="Rime speaker voice used")
    audio_format: str = Field(..., description="Audio format (mp3, wav)")
    audio_bytes_length: int = Field(..., ge=0, description="Length of synthesized audio binary in bytes")
    status: str = Field(default="SUCCESS", description="Synthesis outcome status")


class TurnContext(BaseModel):
    """Immutable context tagging every asynchronous task with session and turn identity."""
    session_id: str = Field(..., description="Unique identifier for the active conversation session")
    turn_id: int = Field(..., ge=1, description="Monotonically increasing turn sequence identifier")


class VoiceTurn(BaseModel):
    """Represents a single conversational turn within a session."""
    turn_id: int = Field(..., ge=1, description="Monotonic turn ID")
    prompt: Optional[str] = Field(default=None, description="Transcribed user prompt for this turn")
    status: str = Field(default="active", description="Turn status: active, completed, cancelled, or superseded")
    created_at_ms: int = Field(..., description="Turn start timestamp in epoch milliseconds")


class VoiceSessionInfo(BaseModel):
    """Session summary model exposed via API."""
    session_id: str = Field(..., description="Unique session identifier")
    active_turn_id: int = Field(..., ge=0, description="Currently active turn ID (0 if uninitiated)")
    is_active: bool = Field(default=True, description="Whether the session is active and accepting turns")
    turn_count: int = Field(default=0, description="Total turns initiated in this session")


class EventPayload(BaseModel):
    """Structured observability and event logging schema."""
    timestamp_ms: int = Field(..., description="Timestamp in milliseconds")
    session_id: str = Field(..., description="Associated session ID")
    turn_id: int = Field(..., description="Associated turn ID")
    event_type: str = Field(..., description="Event type matching architectural schema")
    component: str = Field(..., description="Component emitting the event")
    status: str = Field(default="SUCCESS", description="Execution status: SUCCESS, FAILED, or DISCARDED")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional context or timing metadata")
