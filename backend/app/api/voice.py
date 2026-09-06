"""Voice Session & Orchestration API Endpoints

Provides REST gateway for voice session lifecycle management.
Full-duplex real-time streaming WebSockets will be wired in Phase 5+.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from backend.app.core.session import default_session_store
from backend.app.models.schemas import VoiceSessionInfo

router = APIRouter(prefix="/voice", tags=["Voice Sessions"])


class CreateSessionRequest(BaseModel):
    """Optional session initialization payload."""
    session_id: Optional[str] = None


class CreateTurnRequest(BaseModel):
    """Payload to trigger turn progression."""
    prompt: Optional[str] = None


@router.post(
    "/session",
    response_model=VoiceSessionInfo,
    status_code=status.HTTP_201_CREATED,
    summary="Create Voice Session",
    description="Initializes a new isolated voice conversation session.",
)
def create_session(request: Optional[CreateSessionRequest] = None) -> VoiceSessionInfo:
    req_id = request.session_id if request else None
    session = default_session_store.get_or_create_session(session_id=req_id)
    return session.to_info()


@router.get(
    "/session/{session_id}",
    response_model=VoiceSessionInfo,
    summary="Get Voice Session Info",
    description="Retrieves active session state and current active turn ID.",
)
def get_session(session_id: str) -> VoiceSessionInfo:
    session = default_session_store.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )
    return session.to_info()


@router.post(
    "/session/{session_id}/turn",
    response_model=VoiceSessionInfo,
    summary="Create Next Turn",
    description="Advances the session to a new monotonic turn ID, rendering older turns obsolete.",
)
def create_turn(session_id: str, request: Optional[CreateTurnRequest] = None) -> VoiceSessionInfo:
    session = default_session_store.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )
    prompt = request.prompt if request else None
    session.create_next_turn(prompt=prompt)
    return session.to_info()
