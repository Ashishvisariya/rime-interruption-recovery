"""Voice Session & Orchestration API Endpoints

Provides REST gateway for voice session lifecycle management,
turn state transitions, context retrieval, STT, LLM, and TTS dispatch.
Full-duplex real-time streaming WebSockets will be wired in Phase 5+.
"""

from typing import Optional
from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from backend.app.core.session import default_session_store
from backend.app.models.schemas import (
    ConversationContextResponse,
    LLMRequest,
    LLMResponse,
    RimeTTSRequest,
    TranscriptionResponse,
    VoiceSessionInfo,
)
from backend.app.services.rime_tts import default_rime_service, RimeTTSError
from backend.app.services.stt import default_stt_service, STTError
from backend.app.services.llm import default_llm_service, GroqLLMServiceError

router = APIRouter(prefix="/voice", tags=["Voice Sessions"])


class CreateSessionRequest(BaseModel):
    """Optional session initialization payload."""
    session_id: Optional[str] = None


class CreateTurnRequest(BaseModel):
    """Payload to trigger turn progression."""
    prompt: Optional[str] = None


class InterruptTurnRequest(BaseModel):
    """Payload to signal turn interruption."""
    turn_id: Optional[int] = Field(default=None, description="Optional turn ID to interrupt (defaults to active)")
    reason: Optional[str] = Field(default="user_interruption", description="Reason for interruption")


class CompleteTurnRequest(BaseModel):
    """Payload to complete an active turn."""
    turn_id: int = Field(..., ge=1, description="Turn ID to complete")
    assistant_response: Optional[str] = Field(default=None, description="Final assistant response text to commit")


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


@router.delete(
    "/session/{session_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Voice Session",
    description="Closes and removes an active voice conversation session.",
)
def delete_session(session_id: str):
    deleted = default_session_store.delete_session(session_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )
    return {"message": f"Session '{session_id}' deleted successfully."}


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
    if not session.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Session '{session_id}' is closed.",
        )
    prompt = request.prompt if request else None
    session.create_next_turn(prompt=prompt)
    return session.to_info()


@router.get(
    "/session/{session_id}/context",
    response_model=ConversationContextResponse,
    summary="Get Conversation Context",
    description="Retrieves authoritative conversational history formatted for LLM context.",
)
def get_conversation_context(session_id: str) -> ConversationContextResponse:
    session = default_session_store.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )
    return ConversationContextResponse(
        session_id=session.session_id,
        active_turn_id=session.active_turn_id,
        is_active=session.is_active,
        messages=session.get_conversation_history(),
    )


@router.post(
    "/session/{session_id}/interrupt",
    response_model=VoiceSessionInfo,
    summary="Interrupt Turn",
    description="Marks the active turn as interrupted and superseded.",
)
def interrupt_turn(session_id: str, request: Optional[InterruptTurnRequest] = None) -> VoiceSessionInfo:
    session = default_session_store.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )
    turn_id = request.turn_id if request and request.turn_id else session.active_turn_id
    reason = request.reason if request else "user_interruption"
    if turn_id > 0:
        session.mark_turn_interrupted(turn_id=turn_id, reason=reason)
    return session.to_info()


@router.post(
    "/session/{session_id}/complete",
    response_model=VoiceSessionInfo,
    summary="Complete Turn",
    description="Marks an active turn as completed, appending optional assistant response to history.",
)
def complete_turn(session_id: str, request: CompleteTurnRequest) -> VoiceSessionInfo:
    session = default_session_store.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )
    success = session.mark_turn_completed(
        turn_id=request.turn_id,
        assistant_response=request.assistant_response,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Turn {request.turn_id} is stale on session '{session_id}' (active: {session.active_turn_id}). Cannot complete turn.",
        )
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


@router.post(
    "/transcribe",
    response_model=TranscriptionResponse,
    summary="Transcribe Speech to Text via Groq Whisper",
    description="Transcribes uploaded speech audio to text using genuine Groq Whisper STT API.",
)
async def transcribe_speech(
    file: UploadFile = File(..., description="Binary speech audio file"),
    session_id: Optional[str] = Form(default=None, description="Optional associated session ID"),
    turn_id: Optional[int] = Form(default=None, description="Optional associated turn ID"),
    language: Optional[str] = Form(default="en", description="Spoken language ISO code"),
    model: Optional[str] = Form(default=None, description="Optional Whisper model override"),
) -> TranscriptionResponse:
    """STT Endpoint accepting audio uploads and returning structured transcriptions."""
    # 1. Validate session if session_id is provided
    if session_id:
        session = default_session_store.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found.",
            )

    # 2. Read audio payload
    audio_bytes = await file.read()
    if not audio_bytes or len(audio_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded audio file cannot be empty.",
        )

    # 3. Call STT Service
    try:
        result = await default_stt_service.transcribe(
            audio_bytes=audio_bytes,
            filename=file.filename or "audio.webm",
            mime_type=file.content_type or "audio/webm",
            language=language,
            model=model,
            session_id=session_id,
            turn_id=turn_id,
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except STTError as e:
        status_code = status.HTTP_502_BAD_GATEWAY if (e.status_code is None or e.status_code >= 500) else e.status_code
        raise HTTPException(
            status_code=status_code,
            detail=str(e),
        )


@router.post(
    "/respond",
    response_model=LLMResponse,
    summary="Generate LLM Voice Response via Groq",
    description="Generates conversational response text using Groq LLM with two-phase turn validation.",
    responses={
        200: {"description": "LLM response text and generation metadata."},
        400: {"description": "Validation error or invalid message payload."},
        404: {"description": "Session not found."},
        409: {"description": "Turn superseded before or during LLM generation."},
        502: {"description": "Upstream Groq API communication error."},
    },
)
async def respond_with_llm(request: LLMRequest) -> LLMResponse:
    """LLM generation endpoint with monotonic turn validation and stale response rejection."""
    session = None
    if request.session_id:
        session = default_session_store.get_session(request.session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{request.session_id}' not found.",
            )

        # Pre-generation turn validation
        if request.turn_id is not None and not session.validate_turn(request.turn_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Turn {request.turn_id} is not active (current active turn: {session.active_turn_id}). LLM generation rejected.",
            )

    # Call LLM service
    try:
        result = await default_llm_service.generate(
            messages=request.messages,
            system_prompt=request.system_prompt,
            temperature=request.temperature or 0.7,
            max_tokens=request.max_tokens or 256,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except GroqLLMServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        )

    # Post-generation turn validation (rejects stale response if turn changed in-flight)
    if session and request.turn_id is not None:
        if not session.validate_turn(request.turn_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Turn {request.turn_id} was superseded during LLM response generation. Generated response discarded.",
            )
        # Commit assistant response to authoritative conversation history
        session.append_assistant_message(request.turn_id, result["text"])

    return LLMResponse(
        session_id=request.session_id,
        turn_id=request.turn_id,
        text=result["text"],
        provider=result["provider"],
        model=result["model"],
        prompt_tokens=result.get("prompt_tokens"),
        completion_tokens=result.get("completion_tokens"),
        latency_ms=result.get("latency_ms"),
        status="SUCCESS",
    )
