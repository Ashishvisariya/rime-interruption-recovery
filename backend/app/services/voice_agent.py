"""Voice Agent Pipeline Orchestrator

Coordinates the full end-to-end voice interaction pipeline:
Microphone Audio / User Prompt
  ──▶ Groq Whisper STT
  ──▶ Conversation & Session Manager
  ──▶ Groq LLM Generation
  ──▶ Monotonic Turn Invariant Gating
  ──▶ Rime Labs TTS Synthesis
  ──▶ Browser Audio Playback & History Commitment

Preserves strict turn ownership and stale-result protection at every asynchronous transition.
"""

import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from backend.app.services.stt import GroqSTTService, default_stt_service, STTError
from backend.app.services.llm import GroqLLMService, default_llm_service, GroqLLMServiceError
from backend.app.services.rime_tts import RimeTTSService, default_rime_service, RimeTTSError
from backend.app.services.conversation import (
    ConversationManager,
    SessionNotFoundError,
    SessionClosedError,
    StaleTurnMutationError,
    default_conversation_manager,
)
from backend.app.models.schemas import RimeTTSMetadata, VoiceAgentResponse


class VoiceAgentStaleTurnError(Exception):
    """Raised when turn becomes superseded or stale during pipeline progression."""
    def __init__(self, message: str, session_id: str, turn_id: int):
        super().__init__(message)
        self.session_id = session_id
        self.turn_id = turn_id


class VoiceAgentOrchestrationError(Exception):
    """Raised when an unrecoverable error occurs in the pipeline."""
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class VoiceAgentExecutionResult:
    """Internal structured output of a completed voice agent orchestration turn."""
    session_id: str
    turn_id: int
    user_prompt: str
    assistant_text: str
    audio_bytes: bytes
    tts_metadata: RimeTTSMetadata
    llm_metadata: Dict[str, Any]
    latency_ms: float

    def to_response(self) -> VoiceAgentResponse:
        """Convert execution result to API response model."""
        return VoiceAgentResponse(
            session_id=self.session_id,
            turn_id=self.turn_id,
            user_prompt=self.user_prompt,
            assistant_text=self.assistant_text,
            llm_provider=self.llm_metadata.get("provider", "groq"),
            llm_model=self.llm_metadata.get("model", "qwen/qwen3.6-27b"),
            tts_provider=self.tts_metadata.provider,
            tts_model=self.tts_metadata.model_id,
            tts_speaker=self.tts_metadata.speaker,
            audio_format=self.tts_metadata.audio_format,
            audio_bytes_length=len(self.audio_bytes),
            latency_ms=self.latency_ms,
            status="SUCCESS",
        )


class VoiceAgentOrchestrator:
    """Orchestrates end-to-end voice interactions across STT, Conversation State, LLM, and Rime TTS."""

    def __init__(
        self,
        conversation_manager: Optional[ConversationManager] = None,
        stt_service: Optional[GroqSTTService] = None,
        llm_service: Optional[GroqLLMService] = None,
        rime_service: Optional[RimeTTSService] = None,
    ):
        self.conversation_manager: ConversationManager = (
            conversation_manager or default_conversation_manager
        )
        self.stt_service: GroqSTTService = stt_service or default_stt_service
        self.llm_service: GroqLLMService = llm_service or default_llm_service
        self.rime_service: RimeTTSService = rime_service or default_rime_service

    async def process_turn(
        self,
        session_id: Optional[str] = None,
        turn_id: Optional[int] = None,
        audio_bytes: Optional[bytes] = None,
        text_prompt: Optional[str] = None,
        audio_filename: str = "audio.webm",
        audio_mime_type: str = "audio/webm",
        language: str = "en",
        system_prompt: Optional[str] = None,
        speaker: Optional[str] = None,
        model_id: Optional[str] = None,
        audio_format: Optional[str] = "mp3",
    ) -> VoiceAgentExecutionResult:
        """Execute one complete voice agent conversational turn end-to-end.
        
        Steps:
        1. Resolve or create session; establish active monotonic turn.
        2. Transcribe speech audio via Groq Whisper (if audio provided).
        3. Check turn validity.
        4. Obtain conversational context from ConversationManager.
        5. Generate response via Groq LLM.
        6. Check turn validity (two-phase LLM gating).
        7. Synthesize expressive voice via Rime TTS.
        8. Check turn validity (two-phase TTS gating).
        9. Commit authoritative assistant response to conversation history.
        10. Return synthesized audio bytes and metadata.
        """
        start_time = time.perf_counter()

        # Step 1: Session & Turn Resolution
        session = self.conversation_manager.get_or_create_session(session_id)
        current_session_id = session.session_id

        if not session.is_active:
            raise SessionClosedError(f"Session '{current_session_id}' is closed.")

        if turn_id is None:
            # Advance monotonic turn
            current_turn_id = session.create_next_turn(prompt=text_prompt)
        else:
            current_turn_id = turn_id
            if not session.validate_turn(current_turn_id):
                raise VoiceAgentStaleTurnError(
                    f"Turn {current_turn_id} is not active on session '{current_session_id}' (active: {session.active_turn_id}).",
                    session_id=current_session_id,
                    turn_id=current_turn_id,
                )
            if text_prompt:
                session.append_user_message(current_turn_id, text_prompt)

        # Step 2: Speech-to-Text Transcription (if audio supplied)
        user_prompt_text = text_prompt or ""
        if audio_bytes and len(audio_bytes) > 0:
            # Pre-STT Turn Validation
            if not session.validate_turn(current_turn_id):
                raise VoiceAgentStaleTurnError(
                    f"Turn {current_turn_id} superseded before STT transcription.",
                    session_id=current_session_id,
                    turn_id=current_turn_id,
                )

            try:
                stt_result = await self.stt_service.transcribe(
                    audio_bytes=audio_bytes,
                    filename=audio_filename,
                    mime_type=audio_mime_type,
                    language=language,
                    session_id=current_session_id,
                    turn_id=current_turn_id,
                )
                user_prompt_text = stt_result.text.strip()
            except STTError as e:
                raise VoiceAgentOrchestrationError(f"STT Failure: {str(e)}", status_code=502)
            except ValueError as e:
                raise VoiceAgentOrchestrationError(f"Invalid STT Input: {str(e)}", status_code=400)

            # Post-STT Turn Validation & Commit User Prompt
            if not session.validate_turn(current_turn_id):
                raise VoiceAgentStaleTurnError(
                    f"Turn {current_turn_id} superseded during STT transcription.",
                    session_id=current_session_id,
                    turn_id=current_turn_id,
                )

            # Update turn prompt & history if not already registered
            turn = session.get_turn(current_turn_id)
            if turn and not turn.prompt:
                turn.prompt = user_prompt_text
            # If user message wasn't appended during turn creation, append now
            if not any(m.turn_id == current_turn_id and m.role == "user" for m in session.messages):
                session.append_user_message(current_turn_id, user_prompt_text)

        if not user_prompt_text.strip():
            raise VoiceAgentOrchestrationError("User prompt is empty (speech was unparseable or text was blank).", status_code=400)

        # Step 3: Pre-LLM Turn Validation
        if not session.validate_turn(current_turn_id):
            raise VoiceAgentStaleTurnError(
                f"Turn {current_turn_id} superseded before LLM response generation.",
                session_id=current_session_id,
                turn_id=current_turn_id,
            )

        # Step 4: Extract LLM Conversation Context
        llm_messages = session.get_context_for_llm(system_prompt=system_prompt)

        # Step 5: Groq LLM Response Generation
        try:
            llm_result = await self.llm_service.generate(
                messages=llm_messages,
                system_prompt=system_prompt,
            )
            assistant_response_text = llm_result["text"].strip()
        except GroqLLMServiceError as e:
            raise VoiceAgentOrchestrationError(f"LLM Generation Failure: {str(e)}", status_code=502)
        except ValueError as e:
            raise VoiceAgentOrchestrationError(f"Invalid LLM Request: {str(e)}", status_code=400)

        # Step 6: Post-LLM / Pre-TTS Turn Validation
        if not session.validate_turn(current_turn_id):
            raise VoiceAgentStaleTurnError(
                f"Turn {current_turn_id} superseded during LLM generation. Generated response discarded.",
                session_id=current_session_id,
                turn_id=current_turn_id,
            )

        # Step 7: Rime TTS Voice Synthesis
        try:
            audio_bytes_out, tts_metadata = await self.rime_service.synthesize(
                text=assistant_response_text,
                session_id=current_session_id,
                turn_id=current_turn_id,
                speaker=speaker,
                model_id=model_id,
                audio_format=audio_format,
            )
        except RimeTTSError as e:
            status_code = 502 if (e.status_code is None or e.status_code >= 500) else e.status_code
            raise VoiceAgentOrchestrationError(f"Rime TTS Failure: {str(e)}", status_code=status_code)
        except ValueError as e:
            raise VoiceAgentOrchestrationError(f"Invalid TTS Input: {str(e)}", status_code=400)

        # Step 8: Post-TTS Turn Validation (Barge-in / Stale Result Protection)
        if not session.validate_turn(current_turn_id):
            raise VoiceAgentStaleTurnError(
                f"Turn {current_turn_id} superseded during TTS synthesis. Generated audio discarded.",
                session_id=current_session_id,
                turn_id=current_turn_id,
            )

        # Step 9: Authoritative History Commitment
        # Only the active turn commits its assistant response
        session.mark_turn_completed(
            turn_id=current_turn_id,
            assistant_response=assistant_response_text,
        )

        total_latency_ms = (time.perf_counter() - start_time) * 1000.0

        return VoiceAgentExecutionResult(
            session_id=current_session_id,
            turn_id=current_turn_id,
            user_prompt=user_prompt_text,
            assistant_text=assistant_response_text,
            audio_bytes=audio_bytes_out,
            tts_metadata=tts_metadata,
            llm_metadata=llm_result,
            latency_ms=round(total_latency_ms, 2),
        )


# Default global orchestrator singleton
default_voice_agent = VoiceAgentOrchestrator(
    conversation_manager=default_conversation_manager,
    stt_service=default_stt_service,
    llm_service=default_llm_service,
    rime_service=default_rime_service,
)
