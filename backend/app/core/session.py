"""Session & Turn State Management Core

Provides thread-safe in-memory session state tracking, monotonic turn ID progression,
conversation history encapsulation, and the fundamental correctness invariant:
"validate_turn(turn_id) == True ONLY when turn_id == active_turn_id and turn is ACTIVE."
Stale-result rejection is strictly enforced for all conversational state mutations.
"""

import time
import uuid
import threading
from typing import Any, Dict, List, Optional
from backend.app.models.schemas import (
    ChatMessage,
    TurnContext,
    TurnStatus,
    VoiceSessionInfo,
    VoiceTurn,
)


class VoiceSession:
    """Encapsulates active conversation state, history, and monotonic turn lifecycle for a single session."""

    def __init__(self, session_id: Optional[str] = None):
        now_ms = int(time.time() * 1000)
        self.session_id: str = session_id or f"sess_{uuid.uuid4().hex[:12]}"
        self.active_turn_id: int = 0
        self.is_active: bool = True
        self.status: str = "active"
        self.turns: Dict[int, VoiceTurn] = {}
        self.messages: List[ChatMessage] = []
        self.created_at_ms: int = now_ms
        self.updated_at_ms: int = now_ms
        self._lock = threading.RLock()

    def create_next_turn(self, prompt: Optional[str] = None) -> int:
        """Create a new conversational turn, atomically advancing the active turn sequence.
        
        Enforces:
        - Strictly monotonic turn IDs (never reused, never decremented).
        - Any previously active turn is superseded/interrupted.
        - If a prompt is provided, appends it as the authoritative user message.
        
        Returns:
            The newly created active turn_id.
        """
        with self._lock:
            if not self.is_active:
                raise RuntimeError(f"Cannot create turn on inactive session '{self.session_id}'.")

            now_ms = int(time.time() * 1000)
            self.updated_at_ms = now_ms

            # Advance turn sequence monotonically
            self.active_turn_id += 1
            new_turn_id = self.active_turn_id

            # Mark all previous turns as superseded/interrupted if still active
            for tid, turn in self.turns.items():
                if tid < new_turn_id and turn.status in (TurnStatus.ACTIVE.value, TurnStatus.CREATED.value):
                    turn.status = TurnStatus.SUPERSEDED.value
                    if turn.interrupted_at_ms is None:
                        turn.interrupted_at_ms = now_ms

            # Register the new turn
            new_turn = VoiceTurn(
                turn_id=new_turn_id,
                prompt=prompt,
                status=TurnStatus.ACTIVE.value,
                created_at_ms=now_ms,
            )
            self.turns[new_turn_id] = new_turn

            # Commit user prompt to conversation history if provided
            if prompt and prompt.strip():
                user_msg = ChatMessage(
                    role="user",
                    content=prompt.strip(),
                    turn_id=new_turn_id,
                    timestamp_ms=now_ms,
                    status="active",
                )
                self.messages.append(user_msg)

            return new_turn_id

    def is_turn_active(self, turn_id: int) -> bool:
        """Check whether the given turn_id is the currently authoritative active turn."""
        with self._lock:
            if not self.is_active or turn_id <= 0:
                return False
            if turn_id != self.active_turn_id:
                return False
            turn = self.turns.get(turn_id)
            if not turn or turn.status != TurnStatus.ACTIVE.value:
                return False
            return True

    def validate_turn(self, turn_id: int) -> bool:
        """Validate whether an asynchronous worker's result is permitted to affect user-visible output or state.
        
        Enforces Phase 9 Core Invariant:
        validate_turn(turn_id) == True ONLY when turn_id == active_turn_id and turn is ACTIVE.
        """
        return self.is_turn_active(turn_id)

    def get_turn(self, turn_id: int) -> Optional[VoiceTurn]:
        """Retrieve a turn model by its ID."""
        with self._lock:
            return self.turns.get(turn_id)

    def get_active_turn(self) -> Optional[VoiceTurn]:
        """Retrieve the currently active VoiceTurn or None if uninitiated/inactive."""
        with self._lock:
            if self.active_turn_id > 0 and self.is_turn_active(self.active_turn_id):
                return self.turns.get(self.active_turn_id)
            return None

    def mark_turn_completed(self, turn_id: int, assistant_response: Optional[str] = None) -> bool:
        """Mark the active turn as completed, optionally appending authoritative assistant response.
        
        STALE-RESULT PROTECTION:
        If turn_id is not currently active, mutation is REJECTED and returns False.
        """
        with self._lock:
            if not self.validate_turn(turn_id):
                return False

            now_ms = int(time.time() * 1000)
            self.updated_at_ms = now_ms

            turn = self.turns[turn_id]
            turn.status = TurnStatus.COMPLETED.value
            turn.completed_at_ms = now_ms

            if assistant_response and assistant_response.strip():
                turn.assistant_response = assistant_response.strip()
                assistant_msg = ChatMessage(
                    role="assistant",
                    content=assistant_response.strip(),
                    turn_id=turn_id,
                    timestamp_ms=now_ms,
                    status="active",
                )
                self.messages.append(assistant_msg)

            return True

    def mark_turn_interrupted(self, turn_id: int, reason: Optional[str] = None) -> bool:
        """Mark a turn as interrupted and no longer active."""
        with self._lock:
            turn = self.turns.get(turn_id)
            if not turn:
                return False

            now_ms = int(time.time() * 1000)
            self.updated_at_ms = now_ms

            turn.status = TurnStatus.INTERRUPTED.value
            turn.interrupted_at_ms = now_ms
            if reason:
                turn.metadata["interruption_reason"] = reason

            return True

    def interrupt_and_advance(
        self,
        reason: Optional[str] = "barge_in",
        detection_source: Optional[str] = "vad",
        new_prompt: Optional[str] = None,
        assistant_state: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Atomically mark active turn as interrupted and advance to the next monotonic active turn.
        
        Guarantees:
        - Thread-safe atomic turn progression.
        - Previous turn is marked INTERRUPTED with timestamp and reason.
        - Newly created turn is immediately authoritative (ACTIVE).
        - Older turns are rendered stale for validation.
        """
        with self._lock:
            if not self.is_active:
                raise RuntimeError(f"Cannot interrupt inactive session '{self.session_id}'.")

            now_ms = int(time.time() * 1000)
            self.updated_at_ms = now_ms
            prev_turn_id = self.active_turn_id

            # Mark previous active turn as INTERRUPTED
            if prev_turn_id > 0 and prev_turn_id in self.turns:
                prev_turn = self.turns[prev_turn_id]
                if prev_turn.status in (TurnStatus.ACTIVE.value, TurnStatus.CREATED.value):
                    prev_turn.status = TurnStatus.INTERRUPTED.value
                    if prev_turn.interrupted_at_ms is None:
                        prev_turn.interrupted_at_ms = now_ms
                    prev_turn.metadata["interruption_reason"] = reason or "barge_in"
                    prev_turn.metadata["detection_source"] = detection_source or "vad"
                    if assistant_state:
                        prev_turn.metadata["assistant_state_at_interruption"] = assistant_state

            # Advance turn sequence monotonically
            self.active_turn_id += 1
            new_turn_id = self.active_turn_id

            new_turn = VoiceTurn(
                turn_id=new_turn_id,
                prompt=new_prompt,
                status=TurnStatus.ACTIVE.value,
                created_at_ms=now_ms,
                metadata={
                    "triggered_by": "interruption",
                    "previous_turn_id": prev_turn_id,
                    "detection_source": detection_source or "vad",
                },
            )
            self.turns[new_turn_id] = new_turn

            if new_prompt and new_prompt.strip():
                user_msg = ChatMessage(
                    role="user",
                    content=new_prompt.strip(),
                    turn_id=new_turn_id,
                    timestamp_ms=now_ms,
                    status="active",
                )
                self.messages.append(user_msg)

            return {
                "session_id": self.session_id,
                "previous_turn_id": prev_turn_id,
                "new_turn_id": new_turn_id,
                "status": "interrupted",
                "timestamp_ms": now_ms,
                "reason": reason or "barge_in",
                "detection_source": detection_source or "vad",
                "assistant_state": assistant_state,
            }

    def mark_turn_cancelled(self, turn_id: int, reason: Optional[str] = None) -> bool:
        """Mark a turn as cancelled."""
        with self._lock:
            turn = self.turns.get(turn_id)
            if not turn:
                return False

            now_ms = int(time.time() * 1000)
            self.updated_at_ms = now_ms

            turn.status = TurnStatus.CANCELLED.value
            if reason:
                turn.metadata["cancellation_reason"] = reason

            return True

    def mark_turn_failed(self, turn_id: int, error: str) -> bool:
        """Mark a turn as failed with error details."""
        with self._lock:
            turn = self.turns.get(turn_id)
            if not turn:
                return False

            now_ms = int(time.time() * 1000)
            self.updated_at_ms = now_ms

            turn.status = TurnStatus.FAILED.value
            turn.error = error
            turn.metadata["failed_at_ms"] = now_ms

            return True

    def append_user_message(self, turn_id: int, content: str) -> bool:
        """Append user message to authoritative history with strict turn validation."""
        with self._lock:
            if not self.validate_turn(turn_id):
                return False

            now_ms = int(time.time() * 1000)
            self.updated_at_ms = now_ms

            turn = self.turns.get(turn_id)
            if turn and not turn.prompt:
                turn.prompt = content.strip()

            msg = ChatMessage(
                role="user",
                content=content.strip(),
                turn_id=turn_id,
                timestamp_ms=now_ms,
                status="active",
            )
            self.messages.append(msg)
            return True

    def append_assistant_message(self, turn_id: int, content: str) -> bool:
        """Append assistant response to authoritative history with strict turn validation.
        
        Rejects stale writes from superseded/interrupted turns.
        """
        with self._lock:
            if not self.validate_turn(turn_id):
                return False

            now_ms = int(time.time() * 1000)
            self.updated_at_ms = now_ms

            turn = self.turns.get(turn_id)
            if turn:
                turn.assistant_response = content.strip()

            msg = ChatMessage(
                role="assistant",
                content=content.strip(),
                turn_id=turn_id,
                timestamp_ms=now_ms,
                status="active",
            )
            self.messages.append(msg)
            return True

    def get_conversation_history(self) -> List[ChatMessage]:
        """Retrieve a copy of committed conversational message history."""
        with self._lock:
            return [msg.model_copy() for msg in self.messages]

    def get_context_for_llm(
        self,
        system_prompt: Optional[str] = None,
        max_messages: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """Construct a clean message list formatted for LLM invocation.
        
        Independent from external LLM providers (0 network calls).
        """
        with self._lock:
            payload: List[Dict[str, str]] = []
            if system_prompt and system_prompt.strip():
                payload.append({"role": "system", "content": system_prompt.strip()})

            history = self.messages
            if max_messages and max_messages > 0:
                history = history[-max_messages:]

            for msg in history:
                if msg.status == "active":
                    payload.append({"role": msg.role, "content": msg.content})

            return payload

    def invalidate_older_turns(self, up_to_turn_id: int) -> None:
        """Explicitly mark all turns strictly prior to `up_to_turn_id` as superseded."""
        with self._lock:
            now_ms = int(time.time() * 1000)
            for tid, turn in self.turns.items():
                if tid < up_to_turn_id and turn.status in (TurnStatus.ACTIVE.value, TurnStatus.CREATED.value):
                    turn.status = TurnStatus.SUPERSEDED.value
                    if turn.interrupted_at_ms is None:
                        turn.interrupted_at_ms = now_ms

    def get_turn_context(self, turn_id: int) -> TurnContext:
        """Generate an immutable turn context descriptor."""
        return TurnContext(session_id=self.session_id, turn_id=turn_id)

    def close(self) -> None:
        """Safely close session, invalidating active turn."""
        with self._lock:
            self.is_active = False
            self.status = "closed"
            if self.active_turn_id in self.turns:
                active_turn = self.turns[self.active_turn_id]
                if active_turn.status == TurnStatus.ACTIVE.value:
                    active_turn.status = TurnStatus.CANCELLED.value

    def reset(self) -> None:
        """Reset session conversational state while preserving session ID."""
        with self._lock:
            now_ms = int(time.time() * 1000)
            self.active_turn_id = 0
            self.turns.clear()
            self.messages.clear()
            self.is_active = True
            self.status = "active"
            self.updated_at_ms = now_ms

    def to_info(self) -> VoiceSessionInfo:
        """Serialize current session summary to API response model."""
        with self._lock:
            return VoiceSessionInfo(
                session_id=self.session_id,
                active_turn_id=self.active_turn_id,
                is_active=self.is_active,
                turn_count=len(self.turns),
                message_count=len(self.messages),
                status=self.status,
                created_at_ms=self.created_at_ms,
                updated_at_ms=self.updated_at_ms,
            )


class SessionStore:
    """Thread-safe in-memory registry of active voice sessions with complete session isolation."""

    def __init__(self):
        self._sessions: Dict[str, VoiceSession] = {}
        self._lock = threading.RLock()

    def get_or_create_session(self, session_id: Optional[str] = None) -> VoiceSession:
        """Retrieve existing session or instantiate a new one."""
        with self._lock:
            if session_id and session_id in self._sessions:
                return self._sessions[session_id]
            session = VoiceSession(session_id=session_id)
            self._sessions[session.session_id] = session
            return session

    def create_session(self, session_id: Optional[str] = None) -> VoiceSession:
        """Create a new isolated session."""
        with self._lock:
            session = VoiceSession(session_id=session_id)
            self._sessions[session.session_id] = session
            return session

    def get_session(self, session_id: str) -> Optional[VoiceSession]:
        """Retrieve a session by its ID, returning None if not found."""
        with self._lock:
            return self._sessions.get(session_id)

    def list_sessions(self) -> List[str]:
        """List all registered session IDs."""
        with self._lock:
            return list(self._sessions.keys())

    def delete_session(self, session_id: str) -> bool:
        """Delete a session from store."""
        with self._lock:
            if session_id in self._sessions:
                session = self._sessions.pop(session_id)
                session.close()
                return True
            return False

    def close_session(self, session_id: str) -> bool:
        """Close an active session without deleting it."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.close()
                return True
            return False

    def clear(self) -> None:
        """Clear all sessions (primarily for clean test fixture resets)."""
        with self._lock:
            for s in self._sessions.values():
                s.close()
            self._sessions.clear()


# Default global session store instance
default_session_store = SessionStore()
