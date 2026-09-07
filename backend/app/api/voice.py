"""Voice Session & Orchestration API Endpoints

Provides REST gateway for voice session lifecycle management,
turn state transitions, context retrieval, STT, LLM, TTS dispatch,
and End-to-End Voice Agent Orchestration in Phase 10.
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
    VoiceAgentResponse,
    VoiceAgentTextRequest,
    VoiceSessionInfo,
)
from backend.app.services.rime_tts import default_rime_service, RimeTTSError
from backend.app.services.stt import default_stt_service, STTError
from backend.app.services.llm import default_llm_service, GroqLLMServiceError
from backend.app.services.conversation import SessionNotFoundError, SessionClosedError, StaleTurnMutationError
from backend.app.services.voice_agent import (
    default_voice_agent,
    VoiceAgentOrchestrationError,
    VoiceAgentStaleTurnError,
)

router = APIRouter(prefix="/voice", tags=["Voice Sessions & Agent Orchestration"])


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


# =====================================================================
# 1. Session Lifecycle Endpoints
# =====================================================================

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


# =====================================================================
# 2. Individual Component Endpoints (TTS, STT, LLM)
# =====================================================================

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


# =====================================================================
# 3. End-to-End Voice Agent Orchestration Endpoints (Phase 10)
# =====================================================================

@router.post(
    "/agent/process-audio",
    summary="Process User Audio via End-to-End Voice Agent Pipeline",
    description="Full voice interaction: STT -> Turn State -> LLM -> Rime TTS -> Spoken Audio Response.",
    responses={
        200: {
            "content": {"audio/mpeg": {}, "audio/wav": {}},
            "description": "Synthesized binary audio response from Rime Labs with turn metadata headers.",
        },
        400: {"description": "Invalid input or empty audio payload."},
        404: {"description": "Session not found."},
        409: {"description": "Turn superseded during processing. Result discarded."},
        502: {"description": "Upstream STT, LLM, or TTS provider error."},
    },
)
async def process_agent_audio(
    file: UploadFile = File(..., description="Binary audio recording from browser mic"),
    session_id: Optional[str] = Form(default=None, description="Optional target session ID"),
    turn_id: Optional[int] = Form(default=None, description="Optional turn ID (advances monotonic turn if omitted)"),
    language: Optional[str] = Form(default="en", description="Language code"),
    system_prompt: Optional[str] = Form(default=None, description="Optional system instruction override"),
    speaker: Optional[str] = Form(default=None, description="Optional Rime speaker override"),
    model_id: Optional[str] = Form(default=None, description="Optional Rime model ID override"),
    audio_format: Optional[str] = Form(default="mp3", description="Desired audio format"),
) -> Response:
    """Process user microphone speech audio through full voice agent pipeline."""
    audio_bytes = await file.read()
    if not audio_bytes or len(audio_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded audio recording cannot be empty.",
        )

    try:
        result = await default_voice_agent.process_turn(
            session_id=session_id,
            turn_id=turn_id,
            audio_bytes=audio_bytes,
            audio_filename=file.filename or "recording.webm",
            audio_mime_type=file.content_type or "audio/webm",
            language=language or "en",
            system_prompt=system_prompt,
            speaker=speaker,
            model_id=model_id,
            audio_format=audio_format or "mp3",
        )
    except VoiceAgentStaleTurnError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except SessionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except SessionClosedError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except VoiceAgentOrchestrationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    media_type = default_rime_service._resolve_accept_header(result.tts_metadata.audio_format)
    headers = {
        "X-Session-ID": result.session_id,
        "X-Turn-ID": str(result.turn_id),
        "X-User-Transcript": result.user_prompt,
        "X-Assistant-Response": result.assistant_text,
        "X-LLM-Provider": result.llm_metadata.get("provider", "groq"),
        "X-LLM-Model": result.llm_metadata.get("model", "qwen/qwen3.6-27b"),
        "X-Provider": result.tts_metadata.provider,
        "X-Model-ID": result.tts_metadata.model_id,
        "X-Speaker": result.tts_metadata.speaker,
        "X-Audio-Format": result.tts_metadata.audio_format,
        "X-Audio-Bytes-Length": str(len(result.audio_bytes)),
        "X-Pipeline-Latency-Ms": str(result.latency_ms),
    }

    return Response(content=result.audio_bytes, media_type=media_type, headers=headers)


@router.post(
    "/agent/process-text",
    summary="Process User Text via End-to-End Voice Agent Pipeline",
    description="Text-driven voice interaction: Turn State -> LLM -> Rime TTS -> Spoken Audio Response.",
    responses={
        200: {
            "content": {"audio/mpeg": {}, "audio/wav": {}},
            "description": "Synthesized binary audio response from Rime Labs with turn metadata headers.",
        },
        400: {"description": "Invalid input or empty prompt."},
        404: {"description": "Session not found."},
        409: {"description": "Turn superseded during processing. Result discarded."},
        502: {"description": "Upstream LLM or TTS provider error."},
    },
)
async def process_agent_text(request: VoiceAgentTextRequest) -> Response:
    """Process user text prompt through LLM and Rime TTS returning binary audio."""
    try:
        result = await default_voice_agent.process_turn(
            session_id=request.session_id,
            turn_id=request.turn_id,
            text_prompt=request.text,
            system_prompt=request.system_prompt,
            speaker=request.speaker,
            model_id=request.model_id,
            audio_format=request.audio_format or "mp3",
        )
    except VoiceAgentStaleTurnError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except SessionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except SessionClosedError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except VoiceAgentOrchestrationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    media_type = default_rime_service._resolve_accept_header(result.tts_metadata.audio_format)
    headers = {
        "X-Session-ID": result.session_id,
        "X-Turn-ID": str(result.turn_id),
        "X-User-Transcript": result.user_prompt,
        "X-Assistant-Response": result.assistant_text,
        "X-LLM-Provider": result.llm_metadata.get("provider", "groq"),
        "X-LLM-Model": result.llm_metadata.get("model", "qwen/qwen3.6-27b"),
        "X-Provider": result.tts_metadata.provider,
        "X-Model-ID": result.tts_metadata.model_id,
        "X-Speaker": result.tts_metadata.speaker,
        "X-Audio-Format": result.tts_metadata.audio_format,
        "X-Audio-Bytes-Length": str(len(result.audio_bytes)),
        "X-Pipeline-Latency-Ms": str(result.latency_ms),
    }

    return Response(content=result.audio_bytes, media_type=media_type, headers=headers)


@router.post(
    "/agent/chat",
    response_model=VoiceAgentResponse,
    summary="Execute Voice Agent Pipeline (JSON Metadata Only)",
    description="Executes voice agent pipeline and returns structured JSON metadata without binary audio stream.",
)
async def chat_voice_agent(request: VoiceAgentTextRequest) -> VoiceAgentResponse:
    """Execute voice agent turn returning structured JSON metadata."""
    try:
        result = await default_voice_agent.process_turn(
            session_id=request.session_id,
            turn_id=request.turn_id,
            text_prompt=request.text,
            system_prompt=request.system_prompt,
            speaker=request.speaker,
            model_id=request.model_id,
            audio_format=request.audio_format or "mp3",
        )
        return result.to_response()
    except VoiceAgentStaleTurnError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except SessionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except SessionClosedError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except VoiceAgentOrchestrationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
