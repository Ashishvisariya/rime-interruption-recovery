"""Voice Session & Orchestration API Endpoints

Provides REST gateway for voice session lifecycle management.
Full-duplex real-time streaming WebSockets will be wired in Phase 5+.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
from backend.app.core.session import default_session_store
from backend.app.models.schemas import VoiceSessionInfo, RimeTTSRequest
from backend.app.services.rime_tts import default_rime_service, RimeTTSError

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


@router.post(
    "/tts",
    summary="Synthesize Speech via Rime TTS",
    description="Generates spoken output using real Rime Labs TTS API with strict turn validation.",
    responses={
        200: {
            "content": {"audio/mpeg": {}, "audio/wav": {}, "audio/pcm": {}},
            "description": "Genuine binary audio output from Rime TTS.",
        },
        400: {"description": "Validation error or unconfigured API credentials."},
        404: {"description": "Session not found."},
        409: {"description": "Turn superseded/stale before or during synthesis."},
        502: {"description": "Upstream Rime API communication error."},
    },
)
async def synthesize_speech(request: RimeTTSRequest) -> Response:
    """TTS Endpoint with two-phase turn validation (pre-dispatch and post-return)."""
    # 1. Validate session existence
    session = default_session_store.get_session(request.session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{request.session_id}' not found.",
        )

    # 2. Validate turn is currently active
    if not session.validate_turn(request.turn_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Turn {request.turn_id} is not active (current active turn: {session.active_turn_id}). Synthesis rejected.",
        )

    # 3. Call Rime TTS service
    try:
        audio_bytes, metadata = await default_rime_service.synthesize(
            text=request.text,
            session_id=request.session_id,
            turn_id=request.turn_id,
            model_id=request.model_id,
            speaker=request.speaker,
            audio_format=request.audio_format,
            lang=request.lang,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except RimeTTSError as e:
        status_code = status.HTTP_502_BAD_GATEWAY if (e.status_code is None or e.status_code >= 500) else e.status_code
        raise HTTPException(
            status_code=status_code,
            detail=str(e),
        )

    # 4. Post-synthesis turn validation (protecting against mid-generation barge-in)
    if not session.validate_turn(request.turn_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Turn {request.turn_id} was superseded during audio synthesis. Generated audio discarded.",
        )

    media_type = default_rime_service._resolve_accept_header(metadata.audio_format)
    headers = {
        "X-Session-ID": metadata.session_id,
        "X-Turn-ID": str(metadata.turn_id),
        "X-Provider": metadata.provider,
        "X-Model-ID": metadata.model_id,
        "X-Speaker": metadata.speaker,
        "X-Audio-Format": metadata.audio_format,
        "X-Audio-Bytes-Length": str(metadata.audio_bytes_length),
    }

    return Response(content=audio_bytes, media_type=media_type, headers=headers)

