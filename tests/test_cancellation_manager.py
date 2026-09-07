"""Comprehensive Unit & Integration Test Suite for Phase 13 Background Task Cancellation

Validates all 20 required cancellation and state isolation invariants:
1. Task registration
2. Task unregistration
3. Cancellation of active turn tasks
4. Cancellation of obsolete turns
5. Cancellation state transitions
6. Cancelled task cleanup
7. asyncio.CancelledError handling
8. Cancellation race with task completion
9. Stale result after failed cancellation (stale turn validation fallback)
10. Stale result after successful cancellation
11. Active T2 unaffected by T1 cancellation
12. Multiple-session isolation
13. No dangling tasks
14. No unhandled cancellation exceptions
15. LLM task cancellation behavior
16. TTS task cancellation behavior
17. Cancellation does not mutate conversation history
18. Cancelled task does not produce Rime output
19. Repeated interruption / cancellation cycles
20. Session cleanup and total registry purging

Strict Invariant:
"Cancellation is best-effort; stale-result rejection is the correctness guarantee."
0 real Groq calls | 0 real Rime calls | 0 Gemini calls | 0 external API calls.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.core.cancellation import (
    CancellationManager,
    TrackedTask,
    default_cancellation_manager,
)
from backend.app.core.session import SessionStore, VoiceSession
from backend.app.services.conversation import ConversationManager
from backend.app.services.voice_agent import (
    VoiceAgentOrchestrator,
    VoiceAgentStaleTurnError,
)
from backend.app.models.schemas import RimeTTSMetadata


@pytest.fixture
def clean_manager():
    """Provides an isolated CancellationManager instance."""
    mgr = CancellationManager()
    yield mgr
    mgr.clear()


@pytest.fixture
def clean_store():
    """Provides an isolated SessionStore instance."""
    store = SessionStore()
    yield store
    store.clear()


@pytest.fixture
def conversation_mgr(clean_store, clean_manager):
    """Provides an isolated ConversationManager backed by isolated store and cancellation manager."""
    return ConversationManager(session_store=clean_store, cancellation_manager=clean_manager)


# =====================================================================
# Test 1: Task Registration
# =====================================================================
@pytest.mark.asyncio
async def test_task_registration(clean_manager):
    """Scenario 1: Task registration correctly tracks task under (session_id, turn_id)."""
    async def dummy_coro():
        await asyncio.sleep(1.0)

    task = asyncio.create_task(dummy_coro())
    tracked = clean_manager.register_task(
        session_id="sess_1",
        turn_id=1,
        task=task,
        task_type="llm",
    )

    assert tracked.session_id == "sess_1"
    assert tracked.turn_id == 1
    assert tracked.task_type == "llm"
    assert not tracked.is_cancelled
    assert not tracked.is_done

    active_tasks = clean_manager.get_active_tasks("sess_1", 1)
    assert len(active_tasks) == 1
    assert active_tasks[0].task is task

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


# =====================================================================
# Test 2: Task Unregistration
# =====================================================================
@pytest.mark.asyncio
async def test_task_unregistration(clean_manager):
    """Scenario 2: Explicit task unregistration removes task from registry."""
    async def dummy_coro():
        await asyncio.sleep(1.0)

    task = asyncio.create_task(dummy_coro())
    tracked = clean_manager.register_task("sess_1", 1, task, task_type="agent_turn")

    assert len(clean_manager.get_active_tasks("sess_1", 1)) == 1

    # Unregister via task instance
    removed = clean_manager.unregister_task("sess_1", 1, task)
    assert removed is True
    assert len(clean_manager.get_active_tasks("sess_1", 1)) == 0

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


# =====================================================================
# Test 3: Cancellation of Active Turn Tasks
# =====================================================================
@pytest.mark.asyncio
async def test_cancellation_of_active_turn_tasks(clean_manager):
    """Scenario 3: cancel_turn_tasks aborts in-flight tasks for specified turn."""
    was_cancelled = False

    async def long_coro():
        nonlocal was_cancelled
        try:
            await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            was_cancelled = True
            raise

    task = asyncio.create_task(long_coro())
    clean_manager.register_task("sess_1", 1, task, task_type="llm")
    await asyncio.sleep(0.01)  # Allow coroutine to start executing try block

    count = clean_manager.cancel_turn_tasks("sess_1", 1, reason="user_barge_in")
    assert count == 1

    with pytest.raises(asyncio.CancelledError):
        await task

    assert was_cancelled is True


# =====================================================================
# Test 4: Cancellation of Obsolete Turns
# =====================================================================
@pytest.mark.asyncio
async def test_cancellation_of_obsolete_turn(clean_manager):
    """Scenario 4: cancel_obsolete_tasks cancels tasks with turn_id < active_turn_id."""
    t1_cancelled = False
    t2_running = True

    async def t1_coro():
        nonlocal t1_cancelled
        try:
            await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            t1_cancelled = True
            raise

    async def t2_coro():
        nonlocal t2_running
        await asyncio.sleep(0.05)
        t2_running = True
        return "t2_done"

    task1 = asyncio.create_task(t1_coro())
    task2 = asyncio.create_task(t2_coro())

    clean_manager.register_task("sess_1", 1, task1, task_type="llm")
    clean_manager.register_task("sess_1", 2, task2, task_type="llm")
    await asyncio.sleep(0.01)  # Allow tasks to begin execution

    # Advancing to active_turn_id=2 should cancel turn 1 only
    cancelled_count = clean_manager.cancel_obsolete_tasks("sess_1", active_turn_id=2)
    assert cancelled_count == 1

    with pytest.raises(asyncio.CancelledError):
        await task1

    res2 = await task2
    assert res2 == "t2_done"
    assert t1_cancelled is True
    assert not task2.cancelled()


# =====================================================================
# Test 5: Cancellation State Transitions
# =====================================================================
@pytest.mark.asyncio
async def test_cancellation_state_transitions(clean_manager):
    """Scenario 5: TrackedTask records cancellation timestamp and reason."""
    async def dummy_coro():
        await asyncio.sleep(2.0)

    task = asyncio.create_task(dummy_coro())
    tracked = clean_manager.register_task("sess_1", 1, task, task_type="llm")

    assert not tracked.is_cancelled
    assert tracked.cancelled_at_ms is None

    clean_manager.cancel_turn_tasks("sess_1", 1, reason="barge_in_detected")

    assert tracked.is_cancelled is True
    assert tracked.cancelled_at_ms is not None
    assert tracked.cancellation_reason == "barge_in_detected"

    with pytest.raises(asyncio.CancelledError):
        await task


# =====================================================================
# Test 6: Cancelled Task Cleanup (Done Callback)
# =====================================================================
@pytest.mark.asyncio
async def test_cancelled_task_cleanup(clean_manager):
    """Scenario 6: Automatic callback removes completed/cancelled tasks from registry."""
    async def short_coro():
        await asyncio.sleep(0.01)

    task = asyncio.create_task(short_coro())
    clean_manager.register_task("sess_1", 1, task, task_type="tts")

    await task
    # Allow event loop done callbacks to fire
    await asyncio.sleep(0.01)

    assert len(clean_manager.get_active_tasks("sess_1", 1)) == 0


# =====================================================================
# Test 7: asyncio.CancelledError Handling
# =====================================================================
@pytest.mark.asyncio
async def test_asyncio_cancelled_error_handling(conversation_mgr, clean_manager):
    """Scenario 7: CancelledError does not crash the orchestrator or leave corrupt session state."""
    session = conversation_mgr.create_session("sess_cancel_err")
    t1 = conversation_mgr.create_turn("sess_cancel_err", "test prompt")

    mock_stt = MagicMock()
    mock_llm = MagicMock()
    mock_rime = MagicMock()

    # Make LLM hang until cancelled
    async def hanging_llm(*args, **kwargs):
        await asyncio.sleep(5.0)
        return {"text": "should never return", "provider": "groq", "model": "test"}

    mock_llm.generate = AsyncMock(side_effect=hanging_llm)

    orchestrator = VoiceAgentOrchestrator(
        conversation_manager=conversation_mgr,
        stt_service=mock_stt,
        llm_service=mock_llm,
        rime_service=mock_rime,
        cancellation_manager=clean_manager,
    )

    agent_task = asyncio.create_task(
        orchestrator.process_turn(session_id="sess_cancel_err", turn_id=t1, text_prompt="hello")
    )

    await asyncio.sleep(0.02)  # Let process_turn start and register
    assert len(clean_manager.get_active_tasks("sess_cancel_err", t1)) == 1

    # Interrupt and advance turn to T2
    conversation_mgr.interrupt_and_advance_turn("sess_cancel_err", reason="barge_in")

    with pytest.raises(asyncio.CancelledError):
        await agent_task

    # Verify no assistant message was committed for T1
    history = conversation_mgr.get_conversation_history("sess_cancel_err")
    assert not any(m.role == "assistant" for m in history)


# =====================================================================
# Test 8: Cancellation Race with Task Completion
# =====================================================================
@pytest.mark.asyncio
async def test_cancellation_race_with_task_completion(clean_manager):
    """Scenario 8: If cancellation races with completion, cancel_turn_tasks is a safe no-op on done tasks."""
    async def fast_coro():
        return "completed_fast"

    task = asyncio.create_task(fast_coro())
    clean_manager.register_task("sess_1", 1, task, task_type="llm")

    await task
    # Race: cancellation arrives after task already completed
    cancelled_count = clean_manager.cancel_turn_tasks("sess_1", 1, reason="too_late")
    assert cancelled_count == 0
    assert task.result() == "completed_fast"


# =====================================================================
# Test 9: Stale Result After Failed Cancellation
# =====================================================================
@pytest.mark.asyncio
async def test_stale_result_after_failed_cancellation(conversation_mgr):
    """Scenario 9: Core invariant: even if cancellation fails or is ignored, stale turn validation rejects mutation."""
    session = conversation_mgr.create_session("sess_stale_fallback")
    t1 = conversation_mgr.create_turn("sess_stale_fallback", "T1 prompt")

    # T2 supersedes T1
    t2 = conversation_mgr.create_turn("sess_stale_fallback", "T2 prompt")

    # T1 worker attempts to record response
    recorded = conversation_mgr.record_assistant_response("sess_stale_fallback", turn_id=t1, response_text="stale T1 response")
    assert recorded is False

    # Authoritative history only contains user prompts, no stale assistant response
    history = conversation_mgr.get_conversation_history("sess_stale_fallback")
    assert len(history) == 2
    assert all(m.role == "user" for m in history)


# =====================================================================
# Test 10: Stale Result After Successful Cancellation
# =====================================================================
@pytest.mark.asyncio
async def test_stale_result_after_successful_cancellation(conversation_mgr, clean_manager):
    """Scenario 10: Successful cancellation guarantees no state mutation occurs."""
    session = conversation_mgr.create_session("sess_succ_cancel")
    t1 = conversation_mgr.create_turn("sess_succ_cancel", "prompt 1")

    async def mock_worker():
        await asyncio.sleep(2.0)
        conversation_mgr.record_assistant_response("sess_succ_cancel", t1, "late response")

    task = asyncio.create_task(mock_worker())
    clean_manager.register_task("sess_succ_cancel", t1, task)

    conversation_mgr.interrupt_and_advance_turn("sess_succ_cancel", reason="barge_in")

    with pytest.raises(asyncio.CancelledError):
        await task

    history = conversation_mgr.get_conversation_history("sess_succ_cancel")
    assert not any(m.role == "assistant" for m in history)


# =====================================================================
# Test 11: Active T2 Unaffected by T1 Cancellation
# =====================================================================
@pytest.mark.asyncio
async def test_active_t2_unaffected_by_t1_cancellation(conversation_mgr, clean_manager):
    """Scenario 11: Cancelling T1 background tasks leaves T2 active tasks completely unharmed."""
    session = conversation_mgr.create_session("sess_t2_safe")
    t1 = conversation_mgr.create_turn("sess_t2_safe", "prompt 1")

    async def t1_worker():
        await asyncio.sleep(2.0)

    async def t2_worker():
        await asyncio.sleep(0.05)
        conversation_mgr.record_assistant_response("sess_t2_safe", t2, "T2 authoritative answer")
        return "t2_success"

    task1 = asyncio.create_task(t1_worker())
    clean_manager.register_task("sess_t2_safe", t1, task1, task_type="llm")

    # Advance to T2
    t2 = conversation_mgr.create_turn("sess_t2_safe", "prompt 2")
    task2 = asyncio.create_task(t2_worker())
    clean_manager.register_task("sess_t2_safe", t2, task2, task_type="llm")

    # Cancel T1 obsolete tasks
    clean_manager.cancel_obsolete_tasks("sess_t2_safe", active_turn_id=t2)

    with pytest.raises(asyncio.CancelledError):
        await task1

    res2 = await task2
    assert res2 == "t2_success"
    assert not task2.cancelled()

    # Verify T2 committed its response
    history = conversation_mgr.get_conversation_history("sess_t2_safe")
    assistant_msgs = [m for m in history if m.role == "assistant"]
    assert len(assistant_msgs) == 1
    assert assistant_msgs[0].turn_id == t2
    assert assistant_msgs[0].content == "T2 authoritative answer"


# =====================================================================
# Test 12: Multiple-Session Isolation
# =====================================================================
@pytest.mark.asyncio
async def test_multiple_session_isolation(clean_manager):
    """Scenario 12: Cancelling Session A tasks has zero effect on Session B tasks."""
    sess_a_cancelled = False
    sess_b_done = False

    async def sess_a_coro():
        nonlocal sess_a_cancelled
        try:
            await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            sess_a_cancelled = True
            raise

    async def sess_b_coro():
        nonlocal sess_b_done
        await asyncio.sleep(0.05)
        sess_b_done = True
        return "sess_b_ok"

    task_a = asyncio.create_task(sess_a_coro())
    task_b = asyncio.create_task(sess_b_coro())

    clean_manager.register_task("sess_A", 1, task_a, task_type="llm")
    clean_manager.register_task("sess_B", 1, task_b, task_type="llm")
    await asyncio.sleep(0.01)  # Allow tasks to begin execution

    # Cancel all tasks for session A
    clean_manager.cancel_all_session_tasks("sess_A", reason="user_hangup")

    with pytest.raises(asyncio.CancelledError):
        await task_a

    res_b = await task_b
    assert res_b == "sess_b_ok"
    assert sess_a_cancelled is True
    assert sess_b_done is True
    assert not task_b.cancelled()


# =====================================================================
# Test 13: No Dangling Tasks
# =====================================================================
@pytest.mark.asyncio
async def test_no_dangling_tasks(clean_manager):
    """Scenario 13: All tasks are tracked and unregister upon completion or cancellation."""
    async def worker():
        await asyncio.sleep(0.02)

    tasks = [asyncio.create_task(worker()) for _ in range(5)]
    for i, t in enumerate(tasks):
        clean_manager.register_task("sess_dangle", 1, t, task_type=f"subtask_{i}")

    assert len(clean_manager.get_active_tasks("sess_dangle", 1)) == 5

    await asyncio.gather(*tasks)
    await asyncio.sleep(0.01)

    assert len(clean_manager.get_active_tasks("sess_dangle", 1)) == 0


# =====================================================================
# Test 14: No Unhandled Cancellation Exceptions
# =====================================================================
@pytest.mark.asyncio
async def test_no_unhandled_cancellation_exceptions(clean_manager):
    """Scenario 14: Cancellation on an already finished task does not raise unhandled errors."""
    async def finished_coro():
        return 42

    task = asyncio.create_task(finished_coro())
    clean_manager.register_task("sess_1", 1, task)

    await task
    # Double cancel
    count = clean_manager.cancel_turn_tasks("sess_1", 1)
    assert count == 0


# =====================================================================
# Test 15: LLM Task Cancellation Behavior
# =====================================================================
@pytest.mark.asyncio
async def test_llm_task_cancellation_behavior(conversation_mgr, clean_manager):
    """Scenario 15: In-flight Groq LLM generation is cancelled when interruption arrives."""
    session = conversation_mgr.create_session("sess_llm_cancel")
    t1 = conversation_mgr.create_turn("sess_llm_cancel", "Tell me a long story")

    llm_was_cancelled = False

    async def cancellable_llm(*args, **kwargs):
        nonlocal llm_was_cancelled
        try:
            await asyncio.sleep(5.0)
        except asyncio.CancelledError:
            llm_was_cancelled = True
            raise

    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(side_effect=cancellable_llm)
    mock_stt = MagicMock()
    mock_rime = MagicMock()

    orchestrator = VoiceAgentOrchestrator(
        conversation_manager=conversation_mgr,
        stt_service=mock_stt,
        llm_service=mock_llm,
        rime_service=mock_rime,
        cancellation_manager=clean_manager,
    )

    turn_task = asyncio.create_task(
        orchestrator.process_turn(session_id="sess_llm_cancel", turn_id=t1, text_prompt="Tell me a long story")
    )

    await asyncio.sleep(0.02)
    # User interrupts during LLM generation
    conversation_mgr.interrupt_and_advance_turn("sess_llm_cancel", reason="barge_in")

    with pytest.raises(asyncio.CancelledError):
        await turn_task

    assert llm_was_cancelled is True
    assert mock_rime.synthesize.call_count == 0


# =====================================================================
# Test 16: TTS Task Cancellation Behavior
# =====================================================================
@pytest.mark.asyncio
async def test_tts_task_cancellation_behavior(conversation_mgr, clean_manager):
    """Scenario 16: In-flight Rime TTS synthesis is cancelled when interruption arrives."""
    session = conversation_mgr.create_session("sess_tts_cancel")
    t1 = conversation_mgr.create_turn("sess_tts_cancel", "Speak to me")

    tts_was_cancelled = False

    async def instant_llm(*args, **kwargs):
        return {"text": "Here is the response.", "provider": "groq", "model": "qwen"}

    async def cancellable_tts(*args, **kwargs):
        nonlocal tts_was_cancelled
        try:
            await asyncio.sleep(5.0)
            return b"audio_bytes", RimeTTSMetadata(
                session_id="sess_tts_cancel",
                turn_id=t1,
                provider="rime",
                model_id="coda",
                speaker="celeste",
                audio_format="mp3",
                audio_bytes_length=11,
                status="SUCCESS",
            )
        except asyncio.CancelledError:
            tts_was_cancelled = True
            raise

    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(side_effect=instant_llm)
    mock_stt = MagicMock()
    mock_rime = MagicMock()
    mock_rime.synthesize = AsyncMock(side_effect=cancellable_tts)

    orchestrator = VoiceAgentOrchestrator(
        conversation_manager=conversation_mgr,
        stt_service=mock_stt,
        llm_service=mock_llm,
        rime_service=mock_rime,
        cancellation_manager=clean_manager,
    )

    turn_task = asyncio.create_task(
        orchestrator.process_turn(session_id="sess_tts_cancel", turn_id=t1, text_prompt="Speak to me")
    )

    await asyncio.sleep(0.02)
    # Barge-in occurs while Rime is synthesizing
    conversation_mgr.interrupt_and_advance_turn("sess_tts_cancel", reason="vad_speech_start")

    with pytest.raises(asyncio.CancelledError):
        await turn_task

    assert tts_was_cancelled is True


# =====================================================================
# Test 17: Cancellation Does Not Mutate Conversation History
# =====================================================================
@pytest.mark.asyncio
async def test_cancellation_does_not_mutate_conversation_history(conversation_mgr, clean_manager):
    """Scenario 17: Interrupted & cancelled turns leave no corrupt or partial assistant messages."""
    session = conversation_mgr.create_session("sess_history_clean")
    t1 = conversation_mgr.create_turn("sess_history_clean", "First question")

    async def hanging_llm(*args, **kwargs):
        await asyncio.sleep(5.0)
        return {"text": "should never return", "provider": "groq", "model": "test"}

    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(side_effect=hanging_llm)
    mock_stt = MagicMock()
    mock_rime = MagicMock()

    orchestrator = VoiceAgentOrchestrator(
        conversation_manager=conversation_mgr,
        stt_service=mock_stt,
        llm_service=mock_llm,
        rime_service=mock_rime,
        cancellation_manager=clean_manager,
    )

    turn_task = asyncio.create_task(
        orchestrator.process_turn(session_id="sess_history_clean", turn_id=t1, text_prompt="First question")
    )

    await asyncio.sleep(0.02)
    # Interrupt
    conversation_mgr.interrupt_and_advance_turn("sess_history_clean", reason="user_barge_in")

    with pytest.raises(asyncio.CancelledError):
        await turn_task

    messages = conversation_mgr.get_conversation_history("sess_history_clean")
    assert len(messages) == 1
    assert messages[0].role == "user"
    assert messages[0].turn_id == t1


# =====================================================================
# Test 18: Cancelled Task Does Not Produce Rime Output
# =====================================================================
@pytest.mark.asyncio
async def test_cancelled_task_does_not_produce_rime_output(conversation_mgr, clean_manager):
    """Scenario 18: Cancelled turn is prevented from dispatching or returning TTS audio."""
    session = conversation_mgr.create_session("sess_no_rime")
    t1 = conversation_mgr.create_turn("sess_no_rime", "Question")

    mock_stt = MagicMock()
    mock_llm = MagicMock()
    mock_rime = MagicMock()

    async def slow_llm(*args, **kwargs):
        await asyncio.sleep(5.0)
        return {"text": "Late answer", "provider": "groq", "model": "qwen"}

    mock_llm.generate = AsyncMock(side_effect=slow_llm)
    mock_rime.synthesize = AsyncMock()

    orchestrator = VoiceAgentOrchestrator(
        conversation_manager=conversation_mgr,
        stt_service=mock_stt,
        llm_service=mock_llm,
        rime_service=mock_rime,
        cancellation_manager=clean_manager,
    )

    turn_task = asyncio.create_task(
        orchestrator.process_turn(session_id="sess_no_rime", turn_id=t1, text_prompt="Question")
    )

    await asyncio.sleep(0.02)
    conversation_mgr.interrupt_and_advance_turn("sess_no_rime", reason="barge_in")

    with pytest.raises(asyncio.CancelledError):
        await turn_task

    assert mock_rime.synthesize.call_count == 0


# =====================================================================
# Test 19: Repeated Interruption / Cancellation Cycles
# =====================================================================
@pytest.mark.asyncio
async def test_repeated_interruption_cancellation_cycles(conversation_mgr, clean_manager):
    """Scenario 19: System cleanly handles rapid back-to-back interruption cycles."""
    session = conversation_mgr.create_session("sess_rapid_cycles")

    mock_stt = MagicMock()
    mock_llm = MagicMock()
    mock_rime = MagicMock()

    async def hanging_turn(*args, **kwargs):
        await asyncio.sleep(5.0)

    mock_llm.generate = AsyncMock(side_effect=hanging_turn)

    orchestrator = VoiceAgentOrchestrator(
        conversation_manager=conversation_mgr,
        stt_service=mock_stt,
        llm_service=mock_llm,
        rime_service=mock_rime,
        cancellation_manager=clean_manager,
    )

    for cycle in range(1, 6):
        t_id = conversation_mgr.create_turn("sess_rapid_cycles", f"Prompt {cycle}")
        task = asyncio.create_task(
            orchestrator.process_turn(session_id="sess_rapid_cycles", turn_id=t_id, text_prompt=f"Prompt {cycle}")
        )
        await asyncio.sleep(0.01)

        # Immediate barge-in
        conversation_mgr.interrupt_and_advance_turn("sess_rapid_cycles", reason="rapid_vad")

        with pytest.raises(asyncio.CancelledError):
            await task

    # Now run a normal 6th turn to completion
    t_final = conversation_mgr.create_turn("sess_rapid_cycles", "Final uninterrupted prompt")

    mock_llm.generate = AsyncMock(return_value={"text": "Final response", "provider": "groq", "model": "qwen"})
    mock_rime.synthesize = AsyncMock(return_value=(
        b"audio_final",
        RimeTTSMetadata(
            session_id="sess_rapid_cycles",
            turn_id=t_final,
            provider="rime",
            model_id="coda",
            speaker="celeste",
            audio_format="mp3",
            audio_bytes_length=11,
            status="SUCCESS",
        )
    ))

    result = await orchestrator.process_turn(
        session_id="sess_rapid_cycles",
        turn_id=t_final,
        text_prompt="Final uninterrupted prompt",
    )

    assert result.assistant_text == "Final response"
    assert result.turn_id == t_final

    # Active tasks should now be 0
    await asyncio.sleep(0.01)
    assert len(clean_manager.get_active_tasks("sess_rapid_cycles")) == 0


# =====================================================================
# Test 20: Session Cleanup and Total Registry Purging
# =====================================================================
@pytest.mark.asyncio
async def test_session_cleanup(conversation_mgr, clean_manager):
    """Scenario 20: Closing or deleting a session purges all tasks from registry."""
    session = conversation_mgr.create_session("sess_purge")
    t1 = conversation_mgr.create_turn("sess_purge", "p1")

    async def hanging_work():
        await asyncio.sleep(5.0)

    task = asyncio.create_task(hanging_work())
    clean_manager.register_task("sess_purge", t1, task)

    assert len(clean_manager.get_active_tasks("sess_purge")) == 1

    # Close session
    conversation_mgr.close_session("sess_purge")

    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(clean_manager.get_active_tasks("sess_purge")) == 0
