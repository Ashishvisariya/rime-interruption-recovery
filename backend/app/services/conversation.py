"""Conversation Manager Service Layer

Provides high-level session and conversation lifecycle orchestration.
Coordinates turn transitions, context building for LLM consumers,
and guarantees stale-result rejection across asynchronous workers.
Zero external API calls are executed in this service.
"""

from typing import Any, Dict, List, Optional
from backend.app.core.session import SessionStore, VoiceSession, default_session_store
from backend.app.models.schemas import ChatMessage, VoiceSessionInfo, VoiceTurn


class SessionNotFoundError(Exception):
    """Raised when an operation references a non-existent session."""
    pass


class SessionClosedError(Exception):
    """Raised when attempting to mutate a closed or inactive session."""
    pass


class StaleTurnMutationError(Exception):
    """Raised when an asynchronous worker attempts to mutate state for a superseded/stale turn."""
    pass


class ConversationManager:
    """Orchestrates conversation sessions, monotonic turns, and authoritative message histories."""

    def __init__(self, session_store: Optional[SessionStore] = None):
        self._store: SessionStore = session_store or default_session_store

    def create_session(self, session_id: Optional[str] = None) -> VoiceSession:
        """Create a new isolated session."""
        return self._store.create_session(session_id=session_id)

    def get_session(self, session_id: str) -> Optional[VoiceSession]:
        """Retrieve a session by ID."""
        return self._store.get_session(session_id)

    def get_or_create_session(self, session_id: Optional[str] = None) -> VoiceSession:
        """Retrieve an existing session or instantiate a new one."""
        return self._store.get_or_create_session(session_id=session_id)

    def create_turn(self, session_id: str, prompt: Optional[str] = None) -> int:
        """Create a new monotonic active turn for the given session.
        
        Automatically renders any previous active turn superseded/stale.
        """
        session = self._store.get_session(session_id)
        if not session:
            raise SessionNotFoundError(f"Session '{session_id}' not found.")
        if not session.is_active:
            raise SessionClosedError(f"Session '{session_id}' is closed.")
        return session.create_next_turn(prompt=prompt)

    def get_active_turn(self, session_id: str) -> Optional[VoiceTurn]:
        """Retrieve the currently active turn for a session."""
        session = self._store.get_session(session_id)
        if not session:
            raise SessionNotFoundError(f"Session '{session_id}' not found.")
        return session.get_active_turn()

    def validate_turn(self, session_id: str, turn_id: int) -> bool:
        """Check whether turn_id is currently the active authoritative turn."""
        session = self._store.get_session(session_id)
        if not session:
            return False
        return session.validate_turn(turn_id)

    def record_user_prompt(self, session_id: str, turn_id: int, prompt: str, strict: bool = False) -> bool:
        """Record a user prompt to the session for a specific turn.
        
        Guarantees rejection if the turn is stale.
        """
        session = self._store.get_session(session_id)
        if not session:
            raise SessionNotFoundError(f"Session '{session_id}' not found.")
        if not session.is_active:
            raise SessionClosedError(f"Session '{session_id}' is closed.")

        success = session.append_user_message(turn_id=turn_id, content=prompt)
        if not success and strict:
            raise StaleTurnMutationError(
                f"Turn {turn_id} is not active on session '{session_id}' (active: {session.active_turn_id}). Prompt rejected."
            )
        return success

    def record_assistant_response(self, session_id: str, turn_id: int, response_text: str, strict: bool = False) -> bool:
        """Record an assistant response to the authoritative conversation history.
        
        Guarantees rejection if the turn was superseded or interrupted.
        """
        session = self._store.get_session(session_id)
        if not session:
            raise SessionNotFoundError(f"Session '{session_id}' not found.")
        if not session.is_active:
            raise SessionClosedError(f"Session '{session_id}' is closed.")

        success = session.append_assistant_message(turn_id=turn_id, content=response_text)
        if not success and strict:
            raise StaleTurnMutationError(
                f"Turn {turn_id} is stale on session '{session_id}' (active: {session.active_turn_id}). Response write rejected."
            )
        return success

    def complete_turn(
        self,
        session_id: str,
        turn_id: int,
        assistant_response: Optional[str] = None,
        strict: bool = False,
    ) -> bool:
        """Complete the specified turn and commit final assistant response to history.
        
        Rejects stale writes if turn is no longer active.
        """
        session = self._store.get_session(session_id)
        if not session:
            raise SessionNotFoundError(f"Session '{session_id}' not found.")
        if not session.is_active:
            raise SessionClosedError(f"Session '{session_id}' is closed.")

        success = session.mark_turn_completed(turn_id=turn_id, assistant_response=assistant_response)
        if not success and strict:
            raise StaleTurnMutationError(
                f"Turn {turn_id} is stale on session '{session_id}' (active: {session.active_turn_id}). Turn completion rejected."
            )
        return success

    def interrupt_turn(
        self,
        session_id: str,
        turn_id: Optional[int] = None,
        reason: Optional[str] = "interrupted",
    ) -> bool:
        """Interrupt a specific turn or the current active turn."""
        session = self._store.get_session(session_id)
        if not session:
            raise SessionNotFoundError(f"Session '{session_id}' not found.")

        target_turn_id = turn_id if turn_id is not None else session.active_turn_id
        if target_turn_id <= 0:
            return False
        return session.mark_turn_interrupted(turn_id=target_turn_id, reason=reason)

    def interrupt_and_advance_turn(
        self,
        session_id: str,
        reason: Optional[str] = "barge_in",
        detection_source: Optional[str] = "vad",
        new_prompt: Optional[str] = None,
        assistant_state: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Atomically mark the active turn as interrupted and advance to the next monotonic turn."""
        session = self._store.get_session(session_id)
        if not session:
            raise SessionNotFoundError(f"Session '{session_id}' not found.")
        if not session.is_active:
            raise SessionClosedError(f"Session '{session_id}' is closed.")

        return session.interrupt_and_advance(
            reason=reason,
            detection_source=detection_source,
            new_prompt=new_prompt,
            assistant_state=assistant_state,
        )

    def cancel_turn(self, session_id: str, turn_id: int, reason: Optional[str] = None) -> bool:
        """Cancel a turn."""
        session = self._store.get_session(session_id)
        if not session:
            raise SessionNotFoundError(f"Session '{session_id}' not found.")
        return session.mark_turn_cancelled(turn_id=turn_id, reason=reason)

    def fail_turn(self, session_id: str, turn_id: int, error: str) -> bool:
        """Mark a turn as failed."""
        session = self._store.get_session(session_id)
        if not session:
            raise SessionNotFoundError(f"Session '{session_id}' not found.")
        return session.mark_turn_failed(turn_id=turn_id, error=error)

    def get_llm_messages(
        self,
        session_id: str,
        system_prompt: Optional[str] = None,
        max_messages: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """Retrieve conversation history formatted for LLM inference (role, content)."""
        session = self._store.get_session(session_id)
        if not session:
            raise SessionNotFoundError(f"Session '{session_id}' not found.")
        return session.get_context_for_llm(system_prompt=system_prompt, max_messages=max_messages)

    def get_conversation_history(self, session_id: str) -> List[ChatMessage]:
        """Retrieve full committed chat message history."""
        session = self._store.get_session(session_id)
        if not session:
            raise SessionNotFoundError(f"Session '{session_id}' not found.")
        return session.get_conversation_history()

    def get_session_info(self, session_id: str) -> VoiceSessionInfo:
        """Retrieve session info summary."""
        session = self._store.get_session(session_id)
        if not session:
            raise SessionNotFoundError(f"Session '{session_id}' not found.")
        return session.to_info()

    def close_session(self, session_id: str) -> bool:
        """Close session."""
        return self._store.close_session(session_id)

    def delete_session(self, session_id: str) -> bool:
        """Delete session."""
        return self._store.delete_session(session_id)

    def reset_session(self, session_id: str) -> bool:
        """Reset session state."""
        session = self._store.get_session(session_id)
        if not session:
            raise SessionNotFoundError(f"Session '{session_id}' not found.")
        session.reset()
        return True

    def clear_all(self) -> None:
        """Clear all sessions."""
        self._store.clear()


# Default global conversation manager singleton
default_conversation_manager = ConversationManager(default_session_store)
