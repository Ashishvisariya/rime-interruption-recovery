"""Comprehensive Test Suite for Phase 9 Conversation / Session Manager

Verifies in-memory session management, monotonic turn progression,
authoritative conversation history, strict stale-result rejection,
multi-session isolation, concurrency safety, and LLM context generation.

ZERO live external API calls are made (0 Groq, 0 Rime, 0 Gemini).
"""

import threading
import time
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.session import SessionStore, VoiceSession, default_session_store
from backend.app.models.schemas import TurnStatus
from backend.app.services.conversation import (
    ConversationManager,
    SessionClosedError,
    SessionNotFoundError,
    StaleTurnMutationError,
    default_conversation_manager,
)


@pytest.fixture
def client():
    default_session_store.clear()
    return TestClient(app)


@pytest.fixture
def fresh_manager():
    store = SessionStore()
    return ConversationManager(session_store=store)


# =====================================================================
# 1. Session Lifecycle & Isolation Tests
# =====================================================================

def test_session_creation_and_retrieval(fresh_manager):
    """Verify session instantiation, default properties, and retrieval."""
    session = fresh_manager.create_session("sess_alpha")
    assert session.session_id == "sess_alpha"
    assert session.active_turn_id == 0
    assert session.is_active is True
    assert session.status == "active"
    assert len(session.turns) == 0
    assert len(session.messages) == 0

    retrieved = fresh_manager.get_session("sess_alpha")
    assert retrieved is session

    info = fresh_manager.get_session_info("sess_alpha")
    assert info.session_id == "sess_alpha"
    assert info.active_turn_id == 0
    assert info.is_active is True
    assert info.turn_count == 0
    assert info.message_count == 0


def test_session_isolation(fresh_manager):
    """Verify state isolation between multiple distinct sessions."""
    sess1 = fresh_manager.create_session("sess_1")
    sess2 = fresh_manager.create_session("sess_2")

    t1_s1 = fresh_manager.create_turn("sess_1", "User prompt in session 1")
    t1_s2 = fresh_manager.create_turn("sess_2", "User prompt in session 2")
    t2_s2 = fresh_manager.create_turn("sess_2", "User follow-up in session 2")

    assert t1_s1 == 1
    assert t1_s2 == 1
    assert t2_s2 == 2

    assert sess1.active_turn_id == 1
    assert sess2.active_turn_id == 2

    # Session 1 has 1 message, Session 2 has 2 messages
    assert len(sess1.messages) == 1
    assert len(sess2.messages) == 2


def test_session_close_and_delete(fresh_manager):
    """Verify session closing and deletion lifecycle."""
    fresh_manager.create_session("sess_close_test")
    t1 = fresh_manager.create_turn("sess_close_test", "Hello")
    assert t1 == 1

    closed = fresh_manager.close_session("sess_close_test")
    assert closed is True

    sess = fresh_manager.get_session("sess_close_test")
    assert sess.is_active is False
    assert sess.status == "closed"

    # Creating turn on closed session raises SessionClosedError
    with pytest.raises(SessionClosedError):
        fresh_manager.create_turn("sess_close_test", "Should fail")

    # Deleting session removes it from registry
    deleted = fresh_manager.delete_session("sess_close_test")
    assert deleted is True
    assert fresh_manager.get_session("sess_close_test") is None


def test_invalid_session_handling(fresh_manager):
    """Verify error raises when querying or mutating non-existent sessions."""
    with pytest.raises(SessionNotFoundError):
        fresh_manager.create_turn("non_existent_sess", "Prompt")

    with pytest.raises(SessionNotFoundError):
        fresh_manager.get_active_turn("non_existent_sess")

    with pytest.raises(SessionNotFoundError):
        fresh_manager.get_llm_messages("non_existent_sess")

    assert fresh_manager.validate_turn("non_existent_sess", 1) is False


# =====================================================================
# 2. Monotonic Turn Progression & Ownership Invariant
# =====================================================================

def test_monotonic_turn_ids_no_reuse(fresh_manager):
    """Verify turns are strictly monotonic, positive integers with no decrement or reuse."""
    sess = fresh_manager.create_session("sess_mono")

    turn_ids = []
    for i in range(5):
        tid = fresh_manager.create_turn("sess_mono", f"Prompt {i+1}")
        turn_ids.append(tid)

    assert turn_ids == [1, 2, 3, 4, 5]
    assert sess.active_turn_id == 5

    # Invariant: Only turn 5 is valid and active
    for tid in range(1, 5):
        assert sess.is_turn_active(tid) is False
        assert sess.validate_turn(tid) is False

    assert sess.is_turn_active(5) is True
    assert sess.validate_turn(5) is True


def test_turn_validation_invariant(fresh_manager):
    """Verify validate_turn(turn_id) is True ONLY when turn_id == active_turn_id."""
    fresh_manager.create_session("sess_val")
    assert fresh_manager.validate_turn("sess_val", 0) is False
    assert fresh_manager.validate_turn("sess_val", 1) is False

    t1 = fresh_manager.create_turn("sess_val", "Prompt 1")
    assert fresh_manager.validate_turn("sess_val", t1) is True
    assert fresh_manager.validate_turn("sess_val", 999) is False

    t2 = fresh_manager.create_turn("sess_val", "Prompt 2")
    assert fresh_manager.validate_turn("sess_val", t1) is False
    assert fresh_manager.validate_turn("sess_val", t2) is True


# =====================================================================
# 3. Turn Lifecycle: Completion, Interruption, and Invalidation
# =====================================================================

def test_turn_completion_commits_assistant_history(fresh_manager):
    """Verify completing an active turn updates turn status and appends assistant message."""
    fresh_manager.create_session("sess_complete")
    t1 = fresh_manager.create_turn("sess_complete", "What is the capital of France?")

    # Complete Turn 1 with response
    success = fresh_manager.complete_turn(
        session_id="sess_complete",
        turn_id=t1,
        assistant_response="The capital of France is Paris.",
    )
    assert success is True

    turn = fresh_manager.get_session("sess_complete").get_turn(t1)
    assert turn.status == TurnStatus.COMPLETED.value
    assert turn.completed_at_ms is not None
    assert turn.assistant_response == "The capital of France is Paris."

    history = fresh_manager.get_conversation_history("sess_complete")
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[0].content == "What is the capital of France?"
    assert history[1].role == "assistant"
    assert history[1].content == "The capital of France is Paris."


def test_turn_interruption_marks_turn_superseded(fresh_manager):
    """Verify interrupting an active turn transitions its state and prevents completion."""
    fresh_manager.create_session("sess_interrupt")
    t1 = fresh_manager.create_turn("sess_interrupt", "Long query...")

    # User interrupts Turn 1
    interrupted = fresh_manager.interrupt_turn("sess_interrupt", t1, reason="user_barge_in")
    assert interrupted is True

    turn1 = fresh_manager.get_session("sess_interrupt").get_turn(t1)
    assert turn1.status == TurnStatus.INTERRUPTED.value
    assert turn1.interrupted_at_ms is not None
    assert turn1.metadata.get("interruption_reason") == "user_barge_in"

    # Turn 1 is now inactive and cannot be completed
    assert fresh_manager.validate_turn("sess_interrupt", t1) is False
    comp_success = fresh_manager.complete_turn("sess_interrupt", t1, "Late answer")
    assert comp_success is False


def test_turn_creation_after_interruption(fresh_manager):
    """Verify creating Turn 2 after Turn 1 interruption maintains state integrity."""
    fresh_manager.create_session("sess_recover")
    t1 = fresh_manager.create_turn("sess_recover", "Book a flight to Tokyo")
    fresh_manager.interrupt_turn("sess_recover", t1, reason="client_barge_in")

    t2 = fresh_manager.create_turn("sess_recover", "Actually, make it London")
    assert t2 == 2
    assert fresh_manager.validate_turn("sess_recover", t2) is True
    assert fresh_manager.validate_turn("sess_recover", t1) is False

    # Turn 2 completes normally
    fresh_manager.complete_turn("sess_recover", t2, "Booked a flight to London.")
    history = fresh_manager.get_conversation_history("sess_recover")

    # Authoritative history contains Turn 1 user prompt, Turn 2 user prompt, and Turn 2 assistant reply
    # but NOT any late assistant reply from Turn 1!
    roles = [msg.role for msg in history]
    contents = [msg.content for msg in history]
    assert roles == ["user", "user", "assistant"]
    assert contents == [
        "Book a flight to Tokyo",
        "Actually, make it London",
        "Booked a flight to London.",
    ]


# =====================================================================
# 4. Stale Result Protection & History Guarding
# =====================================================================

def test_stale_turn_cannot_mutate_conversation_history(fresh_manager):
    """Verify that late assistant writes from superseded turns are rejected."""
    fresh_manager.create_session("sess_stale_guard")
    t1 = fresh_manager.create_turn("sess_stale_guard", "Initial query")
    t2 = fresh_manager.create_turn("sess_stale_guard", "Corrected query")

    # Worker for Turn 1 arrives late and attempts to write assistant message
    rejected = fresh_manager.record_assistant_response(
        session_id="sess_stale_guard",
        turn_id=t1,
        response_text="Stale Turn 1 response that must not be saved",
        strict=False,
    )
    assert rejected is False

    # Strict mode raises StaleTurnMutationError
    with pytest.raises(StaleTurnMutationError):
        fresh_manager.record_assistant_response(
            session_id="sess_stale_guard",
            turn_id=t1,
            response_text="Stale Turn 1 response",
            strict=True,
        )

    # Verify history is not contaminated
    history = fresh_manager.get_conversation_history("sess_stale_guard")
    for msg in history:
        assert "Stale Turn 1 response" not in msg.content


def test_active_turn_can_mutate_history(fresh_manager):
    """Verify active turn successfully appends authoritative messages."""
    fresh_manager.create_session("sess_active_mut")
    t1 = fresh_manager.create_turn("sess_active_mut", "Query 1")
    success = fresh_manager.record_assistant_response("sess_active_mut", t1, "Valid response 1")
    assert success is True

    history = fresh_manager.get_conversation_history("sess_active_mut")
    assert len(history) == 2
    assert history[1].content == "Valid response 1"


# =====================================================================
# 5. LLM Context Generation Tests
# =====================================================================

def test_context_generation_formatting(fresh_manager):
    """Verify get_llm_messages builds proper role/content structure without external APIs."""
    fresh_manager.create_session("sess_ctx")
    t1 = fresh_manager.create_turn("sess_ctx", "Hello AI")
    fresh_manager.complete_turn("sess_ctx", t1, "Hello! How can I assist you?")
    t2 = fresh_manager.create_turn("sess_ctx", "What is the weather today?")

    context = fresh_manager.get_llm_messages(
        session_id="sess_ctx",
        system_prompt="You are a helpful voice assistant.",
    )

    expected = [
        {"role": "system", "content": "You are a helpful voice assistant."},
        {"role": "user", "content": "Hello AI"},
        {"role": "assistant", "content": "Hello! How can I assist you?"},
        {"role": "user", "content": "What is the weather today?"},
    ]
    assert context == expected


def test_context_generation_max_messages(fresh_manager):
    """Verify context truncation with max_messages constraint."""
    fresh_manager.create_session("sess_ctx_limit")
    for i in range(10):
        tid = fresh_manager.create_turn("sess_ctx_limit", f"User {i+1}")
        fresh_manager.complete_turn("sess_ctx_limit", tid, f"Bot {i+1}")

    # Total 20 messages. Limit to last 4
    context = fresh_manager.get_llm_messages(
        session_id="sess_ctx_limit",
        system_prompt="Sys Prompt",
        max_messages=4,
    )
    assert len(context) == 5  # 1 system + 4 history messages
    assert context[0]["role"] == "system"
    assert context[1]["content"] == "User 9"
    assert context[2]["content"] == "Bot 9"
    assert context[3]["content"] == "User 10"
    assert context[4]["content"] == "Bot 10"


# =====================================================================
# 6. Concurrency & Race Condition Safety Tests
# =====================================================================

def test_concurrent_turn_and_stale_completion_race(fresh_manager):
    """Race Scenario: Worker A finishes Turn 1 while Worker B advances to Turn 2.
    
    Invariant:
    - Final active_turn_id is deterministically 2.
    - Turn 1 late completion is rejected.
    - Session history contains Turn 2 and NOT stale Turn 1 assistant output.
    """
    session = fresh_manager.create_session("sess_race")
    t1 = fresh_manager.create_turn("sess_race", "Slow tool query for Tokyo flights")

    results = {"worker_a_completed": None, "worker_b_turn": None}

    def worker_a_late_result():
        # Simulates late arrival of Turn 1 completion
        time.sleep(0.02)
        res = fresh_manager.complete_turn(
            "sess_race",
            t1,
            "Here are Tokyo flights: Flight A, Flight B",
        )
        results["worker_a_completed"] = res

    def worker_b_barge_in():
        # Simulates user barge-in advancing to Turn 2
        time.sleep(0.01)
        t2 = fresh_manager.create_turn("sess_race", "Change flight to London")
        results["worker_b_turn"] = t2

    th_a = threading.Thread(target=worker_a_late_result)
    th_b = threading.Thread(target=worker_b_barge_in)

    th_a.start()
    th_b.start()
    th_a.join()
    th_b.join()

    # Worker B created Turn 2
    assert results["worker_b_turn"] == 2
    assert session.active_turn_id == 2

    # Worker A was rejected because Turn 1 was superseded
    assert results["worker_a_completed"] is False

    # Turn 2 can complete cleanly
    fresh_manager.complete_turn("sess_race", 2, "Here are London flights: Flight X")

    history = fresh_manager.get_conversation_history("sess_race")
    contents = [m.content for m in history]

    # Stale Tokyo results never entered history
    assert "Here are Tokyo flights: Flight A, Flight B" not in contents
    assert "Here are London flights: Flight X" in contents


def test_concurrent_multi_thread_turn_creations(fresh_manager):
    """Verify thread-safety when multiple threads concurrently create turns."""
    sess = fresh_manager.create_session("sess_multi_thread")
    created_turns = []
    lock = threading.Lock()

    def create_turn_worker(idx):
        tid = fresh_manager.create_turn("sess_multi_thread", f"Concurrent Prompt {idx}")
        with lock:
            created_turns.append(tid)

    threads = [threading.Thread(target=create_turn_worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(created_turns) == 20
    # All turn IDs must be unique and span 1..20
    assert sorted(created_turns) == list(range(1, 21))
    assert sess.active_turn_id == 20
    assert sess.validate_turn(20) is True


# =====================================================================
# 7. FastAPI REST API Integration Tests
# =====================================================================

def test_api_session_context_endpoint(client):
    """Verify GET /api/voice/session/{id}/context returns clean conversation history."""
    client.post("/api/voice/session", json={"session_id": "sess_api_ctx"})
    client.post("/api/voice/session/sess_api_ctx/turn", json={"prompt": "Hello"})
    client.post(
        "/api/voice/session/sess_api_ctx/complete",
        json={"turn_id": 1, "assistant_response": "Hi there!"},
    )

    res = client.get("/api/voice/session/sess_api_ctx/context")
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"] == "sess_api_ctx"
    assert data["active_turn_id"] == 1
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["content"] == "Hello"
    assert data["messages"][1]["role"] == "assistant"
    assert data["messages"][1]["content"] == "Hi there!"


def test_api_interrupt_and_stale_completion(client):
    """Verify POST /api/voice/session/{id}/interrupt and rejection of subsequent completion."""
    client.post("/api/voice/session", json={"session_id": "sess_api_int"})
    client.post("/api/voice/session/sess_api_int/turn", json={"prompt": "Turn 1"})

    # Interrupt Turn 1
    res_int = client.post(
        "/api/voice/session/sess_api_int/interrupt",
        json={"turn_id": 1, "reason": "user_cancelled"},
    )
    assert res_int.status_code == 200

    # Attempt to complete interrupted Turn 1 -> 409 Conflict
    res_comp = client.post(
        "/api/voice/session/sess_api_int/complete",
        json={"turn_id": 1, "assistant_response": "Late response"},
    )
    assert res_comp.status_code == 409
    assert "Cannot complete turn" in res_comp.json()["error"]


def test_api_delete_session(client):
    """Verify DELETE /api/voice/session/{id} removes session."""
    client.post("/api/voice/session", json={"session_id": "sess_api_del"})
    res_del = client.delete("/api/voice/session/sess_api_del")
    assert res_del.status_code == 200

    res_get = client.get("/api/voice/session/sess_api_del")
    assert res_get.status_code == 404
