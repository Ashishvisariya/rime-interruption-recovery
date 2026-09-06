"""Session & Turn State Management Core

Provides thread-safe session state tracking, monotonic turn ID generation,
and the fundamental correctness invariant:
"A result may affect user-visible state only if its turn_id equals the current active_turn_id."
"""

import time
import uuid
import threading
from typing import Dict, Optional
from backend.app.models.schemas import VoiceSessionInfo, VoiceTurn, TurnContext


class VoiceSession:
    """Encapsulates active conversation state and monotonic turn lifecycle for a single session."""

    def __init__(self, session_id: Optional[str] = None):
        self.session_id: str = session_id or f"sess_{uuid.uuid4().hex[:12]}"
        self.active_turn_id: int = 0
        self.is_active: bool = True
        self.turns: Dict[int, VoiceTurn] = {}
        self._lock = threading.Lock()

    def create_next_turn(self, prompt: Optional[str] = None) -> int:
        """Create a new conversational turn, atomically advancing the active turn sequence.
        
        Any in-progress turn prior to this is rendered superseded/obsolete.
        
        Returns:
            The new monotonically incremented turn_id.
        """
        with self._lock:
            # Advance turn sequence monotonically
            self.active_turn_id += 1
            new_turn_id = self.active_turn_id

            # Mark all previous turns as superseded
            for tid, turn in self.turns.items():
                if tid < new_turn_id and turn.status == "active":
                    turn.status = "superseded"

            # Register the new turn
            now_ms = int(time.time() * 1000)
            self.turns[new_turn_id] = VoiceTurn(
                turn_id=new_turn_id,
                prompt=prompt,
                status="active",
                created_at_ms=now_ms,
            )
            return new_turn_id

    def is_turn_active(self, turn_id: int) -> bool:
        """Check whether the given turn_id is the currently active turn."""
        with self._lock:
            return self.is_active and (turn_id == self.active_turn_id) and (turn_id > 0)

    def validate_turn(self, turn_id: int) -> bool:
        """Validate whether a worker's result is permitted to affect user-visible output.
        
        Enforces the Phase 3 Architectural Invariant:
        A result may only affect user-visible state if its turn_id equals the current active_turn_id.
        """
        return self.is_turn_active(turn_id)

    def invalidate_older_turns(self, up_to_turn_id: int) -> None:
        """Explicitly mark all turns strictly prior to `up_to_turn_id` as obsolete."""
        with self._lock:
            for tid, turn in self.turns.items():
                if tid < up_to_turn_id and turn.status == "active":
                    turn.status = "superseded"

    def get_turn_context(self, turn_id: int) -> TurnContext:
        """Generate an immutable turn context descriptor."""
        return TurnContext(session_id=self.session_id, turn_id=turn_id)

    def to_info(self) -> VoiceSessionInfo:
        """Serialize current session summary to API response model."""
        with self._lock:
            return VoiceSessionInfo(
                session_id=self.session_id,
                active_turn_id=self.active_turn_id,
                is_active=self.is_active,
                turn_count=len(self.turns),
            )


class SessionStore:
    """Thread-safe in-memory registry of active voice sessions."""

    def __init__(self):
        self._sessions: Dict[str, VoiceSession] = {}
        self._lock = threading.Lock()

    def get_or_create_session(self, session_id: Optional[str] = None) -> VoiceSession:
        """Retrieve existing session or instantiate a new one."""
        with self._lock:
            if session_id and session_id in self._sessions:
                return self._sessions[session_id]
            session = VoiceSession(session_id=session_id)
            self._sessions[session.session_id] = session
            return session

    def get_session(self, session_id: str) -> Optional[VoiceSession]:
        """Retrieve a session by its ID, returning None if not found."""
        with self._lock:
            return self._sessions.get(session_id)

    def clear(self) -> None:
        """Clear all sessions (primarily for clean test fixture resets)."""
        with self._lock:
            self._sessions.clear()


# Default global session store instance
default_session_store = SessionStore()
