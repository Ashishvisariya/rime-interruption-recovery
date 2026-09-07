"""Interruption & Turn Recovery State Tests

Tests state transitions during user barge-in, sequential rapid interruptions,
and graceful recovery of conversation progression in Phase 9.
ZERO live external API calls are made.
"""

import pytest
from backend.app.core.session import SessionStore, VoiceSession
from backend.app.models.schemas import TurnStatus
from backend.app.services.conversation import ConversationManager


@pytest.fixture
def manager():
    store = SessionStore()
    return ConversationManager(session_store=store)


def test_rapid_sequential_interruptions(manager):
    """Verify handling of rapid consecutive user barge-in turns (T1 -> T2 -> T3 -> T4)."""
    sess = manager.create_session("sess_rapid_int")

    t1 = manager.create_turn("sess_rapid_int", "Book flight to Tokyo")
    assert t1 == 1
    assert manager.validate_turn("sess_rapid_int", 1) is True

    # Immediate barge-in 1
    t2 = manager.create_turn("sess_rapid_int", "Wait, make it Paris")
    assert t2 == 2
    assert manager.validate_turn("sess_rapid_int", 1) is False
    assert manager.validate_turn("sess_rapid_int", 2) is True

    # Immediate barge-in 2
    t3 = manager.create_turn("sess_rapid_int", "Actually, make it London")
    assert t3 == 3
    assert manager.validate_turn("sess_rapid_int", 2) is False
    assert manager.validate_turn("sess_rapid_int", 3) is True

    # Immediate barge-in 3
    t4 = manager.create_turn("sess_rapid_int", "Confirm London for 2 passengers")
    assert t4 == 4
    assert manager.validate_turn("sess_rapid_int", 3) is False
    assert manager.validate_turn("sess_rapid_int", 4) is True

    # Turn 4 settles and completes
    manager.complete_turn("sess_rapid_int", 4, "Confirmed London for 2 passengers.")

    # Check turn statuses
    session = manager.get_session("sess_rapid_int")
    assert session.get_turn(1).status == TurnStatus.SUPERSEDED.value
    assert session.get_turn(2).status == TurnStatus.SUPERSEDED.value
    assert session.get_turn(3).status == TurnStatus.SUPERSEDED.value
    assert session.get_turn(4).status == TurnStatus.COMPLETED.value

    # Check conversation history
    history = manager.get_conversation_history("sess_rapid_int")
    assert len(history) == 5
    assert [m.role for m in history] == ["user", "user", "user", "user", "assistant"]
    assert history[4].content == "Confirmed London for 2 passengers."


def test_explicit_interruption_event_recording(manager):
    """Verify explicit interruption records timestamps and reasons."""
    manager.create_session("sess_explicit_int")
    t1 = manager.create_turn("sess_explicit_int", "Tell me a long story")

    manager.interrupt_turn(
        session_id="sess_explicit_int",
        turn_id=t1,
        reason="user_button_press",
    )

    session = manager.get_session("sess_explicit_int")
    turn = session.get_turn(t1)
    assert turn.status == TurnStatus.INTERRUPTED.value
    assert turn.interrupted_at_ms is not None
    assert turn.metadata.get("interruption_reason") == "user_button_press"
    assert manager.validate_turn("sess_explicit_int", t1) is False
