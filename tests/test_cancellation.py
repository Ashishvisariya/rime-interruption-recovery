"""Turn Cancellation State Tests

Tests explicit turn cancellation lifecycle states, cancellation reasons,
and state immutability in Phase 9.
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


def test_turn_cancellation_lifecycle(manager):
    """Verify explicit turn cancellation transitions state to CANCELLED."""
    sess = manager.create_session("sess_cancel_test")
    t1 = manager.create_turn("sess_cancel_test", "Request that will be cancelled")

    cancelled = manager.cancel_turn("sess_cancel_test", t1, reason="session_timeout")
    assert cancelled is True

    turn = sess.get_turn(t1)
    assert turn.status == TurnStatus.CANCELLED.value
    assert turn.metadata.get("cancellation_reason") == "session_timeout"

    # Cancelled turn is not active and cannot be completed
    assert manager.validate_turn("sess_cancel_test", t1) is False
    assert manager.complete_turn("sess_cancel_test", t1, "Late result") is False


def test_turn_failure_lifecycle(manager):
    """Verify turn failure transitions state to FAILED and records error."""
    sess = manager.create_session("sess_fail_test")
    t1 = manager.create_turn("sess_fail_test", "Request encountering tool error")

    failed = manager.fail_turn("sess_fail_test", t1, error="Network timeout during tool call")
    assert failed is True

    turn = sess.get_turn(t1)
    assert turn.status == TurnStatus.FAILED.value
    assert turn.error == "Network timeout during tool call"
    assert "failed_at_ms" in turn.metadata

    assert manager.validate_turn("sess_fail_test", t1) is False
