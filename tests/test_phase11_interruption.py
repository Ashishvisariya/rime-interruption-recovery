"""Phase 11 Interruption & Barge-In Detection Tests

Tests atomic turn invalidation, monotonic turn sequence advancement,
thread-safe state transitions, and REST interruption endpoints.
Strictly ZERO live external API calls (0 Groq, 0 Rime, 0 Gemini).
"""

import threading
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.session import SessionStore, VoiceSession
from backend.app.models.schemas import TurnStatus
from backend.app.services.conversation import ConversationManager


@pytest.fixture
def fresh_manager():
    store = SessionStore()
    return ConversationManager(session_store=store)


@pytest.fixture
def client():
    return TestClient(app)


def test_interruption_creates_next_monotonic_turn(fresh_manager):
    """Verify interruption advances monotonic turn and marks previous turn as interrupted."""
    sess = fresh_manager.create_session("sess_int_mono")
    t1 = fresh_manager.create_turn("sess_int_mono", "What is quantum computing?")
    assert t1 == 1
    assert fresh_manager.validate_turn("sess_int_mono", 1) is True

    result = fresh_manager.interrupt_and_advance_turn(
        session_id="sess_int_mono",
        reason="barge_in",
        detection_source="vad",
        assistant_state="PLAYING",
    )

    assert result["session_id"] == "sess_int_mono"
    assert result["previous_turn_id"] == 1
    assert result["new_turn_id"] == 2
    assert result["status"] == "interrupted"
    assert result["reason"] == "barge_in"
    assert result["detection_source"] == "vad"
    assert result["assistant_state"] == "PLAYING"

    # Previous turn must now be invalid and stale
    assert fresh_manager.validate_turn("sess_int_mono", 1) is False
    # New turn must now be authoritative and active
    assert fresh_manager.validate_turn("sess_int_mono", 2) is True

    turn1 = sess.get_turn(1)
    assert turn1.status == TurnStatus.INTERRUPTED.value
    assert turn1.interrupted_at_ms is not None
    assert turn1.metadata["interruption_reason"] == "barge_in"
    assert turn1.metadata["detection_source"] == "vad"
    assert turn1.metadata["assistant_state_at_interruption"] == "PLAYING"

    turn2 = sess.get_turn(2)
    assert turn2.status == TurnStatus.ACTIVE.value
    assert turn2.metadata["triggered_by"] == "interruption"
    assert turn2.metadata["previous_turn_id"] == 1


def test_superseded_turn_cannot_commit_history_post_interruption(fresh_manager):
    """Verify that an asynchronous worker on interrupted turn 1 cannot append messages."""
    fresh_manager.create_session("sess_int_stale")
    t1 = fresh_manager.create_turn("sess_int_stale", "Tell me about Mars")

    # Interruption occurs while worker is processing
    fresh_manager.interrupt_and_advance_turn(
        session_id="sess_int_stale",
        reason="barge_in",
        detection_source="vad",
    )

    # Late worker from turn 1 attempts to commit response
    stale_write_success = fresh_manager.record_assistant_response(
        session_id="sess_int_stale",
        turn_id=t1,
        response_text="Mars is the fourth planet from the Sun.",
        strict=False,
    )
    assert stale_write_success is False

    # Turn 2 commits authoritative response
    fresh_manager.record_user_prompt("sess_int_stale", 2, "Nevermind, tell me about Venus")
    active_write_success = fresh_manager.record_assistant_response(
        session_id="sess_int_stale",
        turn_id=2,
        response_text="Venus is the second planet from the Sun.",
    )
    assert active_write_success is True

    history = fresh_manager.get_conversation_history("sess_int_stale")
    assert len(history) == 3
    assert history[0].content == "Tell me about Mars"
    assert history[1].content == "Nevermind, tell me about Venus"
    assert history[2].content == "Venus is the second planet from the Sun."


def test_rapid_consecutive_barge_in_chain(fresh_manager):
    """Verify chain of rapid consecutive barge-in events (T1 -> T2 -> T3 -> T4)."""
    fresh_manager.create_session("sess_rapid_barge")

    fresh_manager.create_turn("sess_rapid_barge", "Prompt 1")
    r1 = fresh_manager.interrupt_and_advance_turn("sess_rapid_barge", assistant_state="PLAYING")
    assert r1["previous_turn_id"] == 1
    assert r1["new_turn_id"] == 2

    r2 = fresh_manager.interrupt_and_advance_turn("sess_rapid_barge", assistant_state="THINKING")
    assert r2["previous_turn_id"] == 2
    assert r2["new_turn_id"] == 3

    r3 = fresh_manager.interrupt_and_advance_turn("sess_rapid_barge", assistant_state="SYNTHESIZING")
    assert r3["previous_turn_id"] == 3
    assert r3["new_turn_id"] == 4

    session = fresh_manager.get_session("sess_rapid_barge")
    assert session.active_turn_id == 4
    assert fresh_manager.validate_turn("sess_rapid_barge", 1) is False
    assert fresh_manager.validate_turn("sess_rapid_barge", 2) is False
    assert fresh_manager.validate_turn("sess_rapid_barge", 3) is False
    assert fresh_manager.validate_turn("sess_rapid_barge", 4) is True


def test_session_isolation_during_interruptions(fresh_manager):
    """Verify that interrupting session A has zero effect on session B."""
    fresh_manager.create_session("sess_A")
    fresh_manager.create_session("sess_B")

    fresh_manager.create_turn("sess_A", "Session A Query")
    fresh_manager.create_turn("sess_B", "Session B Query")

    fresh_manager.interrupt_and_advance_turn("sess_A", reason="user_barge_in")

    # Session A is now on turn 2
    assert fresh_manager.validate_turn("sess_A", 1) is False
    assert fresh_manager.validate_turn("sess_A", 2) is True

    # Session B is completely untouched on turn 1
    assert fresh_manager.validate_turn("sess_B", 1) is True
    assert fresh_manager.validate_turn("sess_B", 2) is False


def test_thread_safe_concurrent_interruptions(fresh_manager):
    """Verify thread-safety and monotonic integrity under concurrent interruption calls."""
    fresh_manager.create_session("sess_concurrent_int")
    fresh_manager.create_turn("sess_concurrent_int", "Initial prompt")

    interruption_results = []
    lock = threading.Lock()

    def interrupt_worker(idx):
        res = fresh_manager.interrupt_and_advance_turn(
            "sess_concurrent_int",
            reason=f"worker_{idx}",
            detection_source="vad",
        )
        with lock:
            interruption_results.append(res)

    threads = [threading.Thread(target=interrupt_worker, args=(i,)) for i in range(15)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Total 15 interruptions from initial turn 1 -> final turn must be 16
    assert len(interruption_results) == 15
    session = fresh_manager.get_session("sess_concurrent_int")
    assert session.active_turn_id == 16
    assert fresh_manager.validate_turn("sess_concurrent_int", 16) is True
    # All previous turns 1..15 are invalid
    for tid in range(1, 16):
        assert fresh_manager.validate_turn("sess_concurrent_int", tid) is False


def test_api_interrupt_endpoint_with_advance_turn(client):
    """Verify POST /api/voice/session/{id}/interrupt advances turn and returns structured payload."""
    client.post("/api/voice/session", json={"session_id": "sess_api_int_p11"})
    client.post("/api/voice/session/sess_api_int_p11/turn", json={"prompt": "Turn 1 Prompt"})

    res = client.post(
        "/api/voice/session/sess_api_int_p11/interrupt",
        json={
            "reason": "barge_in",
            "detection_source": "vad_speech_start",
            "advance_turn": True,
            "assistant_state": "PLAYING",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"] == "sess_api_int_p11"
    assert data["previous_turn_id"] == 1
    assert data["new_turn_id"] == 2
    assert data["status"] == "interrupted"
    assert data["reason"] == "barge_in"
    assert data["detection_source"] == "vad_speech_start"
    assert data["assistant_state"] == "PLAYING"
    assert isinstance(data["timestamp_ms"], int)

    # Verify session context reflects turn 2 active
    res_ctx = client.get("/api/voice/session/sess_api_int_p11/context")
    assert res_ctx.status_code == 200
    assert res_ctx.json()["active_turn_id"] == 2
