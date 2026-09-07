"""Comprehensive Deterministic Unit & Integration Test Suite for Phase 14 Real-Time WebSocket Layer

Validates all 20 required full-duplex WebSocket invariants:
1. WebSocket connection succeeds (CONNECT_ACK).
2. Malformed JSON message is safely handled with ERROR event.
3. Session isolation (Session A and Session B do not cross-talk).
4. T1 starts correctly via TEXT_PROMPT.
5. Interruption advances T1 -> T2 and emits AUDIO_STOP + TURN_INTERRUPTED.
6. T1 background task cancellation is requested upon interruption.
7. T1 stale result is dropped and not sent to client.
8. T1 stale audio payload is rejected by pre-send validation gate.
9. T2 events are delivered authoritatively.
10. T2 audio is allowed and delivered.
11. Disconnect cancels all session-owned tasks.
12. Reconnecting uses active state without stale turn reuse.
13. Multiple sessions operate concurrently and independently.
14. Rapid consecutive interruptions (T1 -> T2 -> T3).
15. Race condition: T1 completion vs T2 creation.
16. Race condition: stale T1 event vs active T2.
17. Unknown event type handling.
18. Binary audio chunks accumulation during speech.
19. Speech start barge-in while assistant task is in flight.
20. Session cleanup and registry purging.

Strict Invariants:
"Cancellation is best-effort; stale-result rejection is the correctness guarantee."
0 real Groq calls | 0 real Rime calls | 0 Gemini calls | 0 external API calls.
"""

import asyncio
import base64
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.testclient import TestClient

from backend.app.main import app
from backend.app.core.session import SessionStore, default_session_store
from backend.app.core.cancellation import CancellationManager, default_cancellation_manager
from backend.app.services.conversation import ConversationManager, default_conversation_manager
from backend.app.api.websocket import VoiceWebSocketManager, default_ws_manager, WebSocketEventType
from backend.app.models.schemas import RimeTTSMetadata


@pytest.fixture(autouse=True)
def reset_globals():
    """Reset global stores between tests."""
    default_cancellation_manager.clear()
    default_session_store.clear()
    default_ws_manager._connections.clear()
    default_ws_manager._audio_buffers.clear()
    yield
    default_cancellation_manager.clear()
    default_session_store.clear()
    default_ws_manager._connections.clear()
    default_ws_manager._audio_buffers.clear()


# =====================================================================
# Test 1: WebSocket Connection Succeeds (CONNECT_ACK)
# =====================================================================
def test_websocket_connect_success():
    """Scenario 1: Client connects and immediately receives CONNECT_ACK with active_turn_id."""
    client = TestClient(app)
    with client.websocket_connect("/api/voice/ws/sess_test_1") as ws:
        ack = ws.receive_json()
        assert ack["event_type"] == WebSocketEventType.CONNECT_ACK
        assert ack["session_id"] == "sess_test_1"
        assert "active_turn_id" in ack["data"]
        assert ack["data"]["status"] == "connected"


# =====================================================================
# Test 2: Malformed JSON Message Handling
# =====================================================================
def test_websocket_malformed_json_handling():
    """Scenario 2: Malformed text payload returns ERROR event without dropping connection."""
    client = TestClient(app)
    with client.websocket_connect("/api/voice/ws/sess_test_2") as ws:
        _ = ws.receive_json()  # Consume CONNECT_ACK

        ws.send_text("this-is-not-valid-json")
        err_event = ws.receive_json()
        assert err_event["event_type"] == WebSocketEventType.ERROR
        assert "Invalid JSON" in err_event["data"]["error"]


# =====================================================================
# Test 3: Session Isolation
# =====================================================================
def test_websocket_session_isolation():
    """Scenario 3: Events sent to Session A are never received by Session B."""
    client = TestClient(app)
    with client.websocket_connect("/api/voice/ws/sess_A") as ws_a, \
         client.websocket_connect("/api/voice/ws/sess_B") as ws_b:
        _ = ws_a.receive_json()  # ACK A
        _ = ws_b.receive_json()  # ACK B

        # Send event on Session A
        ws_a.send_json({
            "event_type": "SPEECH_STARTED",
            "data": {"reason": "test"},
        })
        resp_a = ws_a.receive_json()
        assert resp_a["event_type"] == "SPEECH_STARTED"
        assert resp_a["session_id"] == "sess_A"

        # Verify Session B received nothing (by sending a prompt on B and getting immediate turn started)
        ws_b.send_json({
            "event_type": "TEXT_PROMPT",
            "data": {"text": "Hello Session B"},
        })
        resp_b = ws_b.receive_json()
        assert resp_b["event_type"] == "TURN_STARTED"
        assert resp_b["session_id"] == "sess_B"


# =====================================================================
# Test 4: T1 Starts Correctly via TEXT_PROMPT
# =====================================================================
def test_websocket_t1_starts_via_text_prompt():
    """Scenario 4: Client sends TEXT_PROMPT and receives TURN_STARTED with monotonic turn_id."""
    client = TestClient(app)
    with client.websocket_connect("/api/voice/ws/sess_t1_start") as ws:
        _ = ws.receive_json()  # ACK

        ws.send_json({
            "event_type": "TEXT_PROMPT",
            "data": {"text": "What is the weather?"},
        })

        turn_started = ws.receive_json()
        assert turn_started["event_type"] == "TURN_STARTED"
        assert turn_started["turn_id"] == 1
        assert turn_started["data"]["prompt"] == "What is the weather?"


# =====================================================================
# Test 5: Interruption Advances T1 -> T2 and Emits AUDIO_STOP
# =====================================================================
def test_websocket_interruption_advances_turn_and_emits_audio_stop():
    """Scenario 5: INTERRUPTION_DETECTED emits AUDIO_STOP and TURN_INTERRUPTED."""
    client = TestClient(app)
    with client.websocket_connect("/api/voice/ws/sess_interrupt") as ws:
        _ = ws.receive_json()  # ACK

        # Start Turn 1
        ws.send_json({
            "event_type": "TEXT_PROMPT",
            "data": {"text": "Tell me a story"},
        })
        _ = ws.receive_json()  # TURN_STARTED T1

        # User barge-in
        ws.send_json({
            "event_type": "INTERRUPTION_DETECTED",
            "data": {
                "previous_turn_id": 1,
                "reason": "user_barge_in",
                "detection_source": "vad",
            },
        })

        # Collect events emitted from interruption & task cancellation
        received_events = {}
        for _ in range(4):
            evt = ws.receive_json()
            received_events[evt["event_type"]] = evt
            if "AUDIO_STOP" in received_events and "TURN_INTERRUPTED" in received_events:
                break

        assert "AUDIO_STOP" in received_events
        stop_evt = received_events["AUDIO_STOP"]
        assert stop_evt["turn_id"] == 1
        assert stop_evt["data"]["interrupted_turn_id"] == 1
        assert stop_evt["data"]["new_turn_id"] == 2

        assert "TURN_INTERRUPTED" in received_events
        int_evt = received_events["TURN_INTERRUPTED"]
        assert int_evt["turn_id"] == 2
        assert int_evt["data"]["new_turn_id"] == 2


# =====================================================================
# Test 6: T1 Background Task Cancellation is Requested
# =====================================================================
@pytest.mark.asyncio
async def test_websocket_t1_task_cancellation():
    """Scenario 6: In-flight T1 task is cancelled when barge-in occurs."""
    task_cancelled = False

    async def mock_hanging_task():
        nonlocal task_cancelled
        try:
            await asyncio.sleep(5.0)
        except asyncio.CancelledError:
            task_cancelled = True
            raise

    task = asyncio.create_task(mock_hanging_task())
    default_cancellation_manager.register_task(
        session_id="sess_task_cancel",
        turn_id=1,
        task=task,
        task_type="ws_turn_pipeline",
    )
    await asyncio.sleep(0.01)

    session = default_session_store.get_or_create_session("sess_task_cancel")
    session.active_turn_id = 1

    # Interruption arrives
    mock_ws = MagicMock()
    mock_ws.send_text = AsyncMock()

    await default_ws_manager.handle_message(
        websocket=mock_ws,
        session_id="sess_task_cancel",
        raw_message=json.dumps({
            "event_type": "INTERRUPTION_DETECTED",
            "data": {"reason": "barge_in"},
        }),
    )

    with pytest.raises(asyncio.CancelledError):
        await task

    assert task_cancelled is True


# =====================================================================
# Test 7: T1 Stale Result is Dropped and Not Sent
# =====================================================================
@pytest.mark.asyncio
async def test_websocket_stale_result_dropped():
    """Scenario 7: Pre-send validation gate drops events if turn_id is stale."""
    session = default_session_store.get_or_create_session("sess_stale_drop")
    t1 = session.create_next_turn("T1")
    t2 = session.create_next_turn("T2")  # T2 is active, T1 is stale

    mock_ws = MagicMock()
    mock_ws.send_text = AsyncMock()

    # Attempt to send T1 event with validate_turn=True
    sent = await default_ws_manager.send_event(
        websocket=mock_ws,
        session_id="sess_stale_drop",
        turn_id=t1,
        event_type=WebSocketEventType.TURN_COMPLETED,
        data={"assistant_response": "Stale message"},
        validate_turn=True,
    )

    assert sent is False
    assert mock_ws.send_text.call_count == 0


# =====================================================================
# Test 8: T1 Stale Audio Payload is Rejected
# =====================================================================
@pytest.mark.asyncio
async def test_websocket_stale_audio_payload_rejected():
    """Scenario 8: Stale audio chunk payload is dropped if turn changed before transmission."""
    session = default_session_store.get_or_create_session("sess_stale_audio")
    t1 = session.create_next_turn("T1")
    t2 = session.create_next_turn("T2")

    mock_ws = MagicMock()
    mock_ws.send_text = AsyncMock()

    sent = await default_ws_manager.send_event(
        websocket=mock_ws,
        session_id="sess_stale_audio",
        turn_id=t1,
        event_type=WebSocketEventType.AUDIO_DATA,
        data={"audio_b64": base64.b64encode(b"stale_audio").decode("utf-8")},
        validate_turn=True,
    )

    assert sent is False
    assert mock_ws.send_text.call_count == 0


# =====================================================================
# Test 9: T2 Events are Delivered Authoritatively
# =====================================================================
@pytest.mark.asyncio
async def test_websocket_t2_events_delivered():
    """Scenario 9: Valid active turn events pass the pre-send validation gate."""
    session = default_session_store.get_or_create_session("sess_t2_deliver")
    t1 = session.create_next_turn("T1")
    t2 = session.create_next_turn("T2")

    mock_ws = MagicMock()
    mock_ws.send_text = AsyncMock()

    sent = await default_ws_manager.send_event(
        websocket=mock_ws,
        session_id="sess_t2_deliver",
        turn_id=t2,
        event_type=WebSocketEventType.TURN_COMPLETED,
        data={"assistant_response": "Authoritative T2 response"},
        validate_turn=True,
    )

    assert sent is True
    assert mock_ws.send_text.call_count == 1


# =====================================================================
# Test 10: T2 Audio is Allowed and Delivered
# =====================================================================
@pytest.mark.asyncio
async def test_websocket_t2_audio_delivered():
    """Scenario 10: Valid active turn audio data is sent to the client."""
    session = default_session_store.get_or_create_session("sess_t2_audio")
    t2 = session.create_next_turn("T2")

    mock_ws = MagicMock()
    mock_ws.send_text = AsyncMock()

    sent = await default_ws_manager.send_event(
        websocket=mock_ws,
        session_id="sess_t2_audio",
        turn_id=t2,
        event_type=WebSocketEventType.AUDIO_DATA,
        data={"audio_b64": base64.b64encode(b"valid_t2_audio").decode("utf-8"), "format": "mp3"},
        validate_turn=True,
    )

    assert sent is True
    assert mock_ws.send_text.call_count == 1


# =====================================================================
# Test 11: Disconnect Cancels Session-Owned Tasks
# =====================================================================
@pytest.mark.asyncio
async def test_websocket_disconnect_cancels_tasks():
    """Scenario 11: Client disconnect purges and cancels in-flight tasks for session."""
    task_cancelled = False

    async def hanging_work():
        nonlocal task_cancelled
        try:
            await asyncio.sleep(5.0)
        except asyncio.CancelledError:
            task_cancelled = True
            raise

    task = asyncio.create_task(hanging_work())
    default_cancellation_manager.register_task(
        session_id="sess_disconnect_test",
        turn_id=1,
        task=task,
    )
    await asyncio.sleep(0.01)

    mock_ws = MagicMock()
    default_ws_manager._connections["sess_disconnect_test"] = {mock_ws}

    # Disconnect
    default_ws_manager.disconnect(mock_ws, "sess_disconnect_test")

    with pytest.raises(asyncio.CancelledError):
        await task

    assert task_cancelled is True
    assert "sess_disconnect_test" not in default_ws_manager._connections


# =====================================================================
# Test 12: Reconnect Isolation
# =====================================================================
def test_websocket_reconnect_isolation():
    """Scenario 12: Reconnecting to the same session returns the current active_turn_id accurately."""
    client = TestClient(app)
    with client.websocket_connect("/api/voice/ws/sess_reconnect") as ws1:
        ack1 = ws1.receive_json()
        assert ack1["session_id"] == "sess_reconnect"

        # Advance turn
        ws1.send_json({
            "event_type": "TEXT_PROMPT",
            "data": {"text": "First prompt"},
        })
        _ = ws1.receive_json()  # TURN_STARTED T1

    # Reconnect on fresh connection
    with client.websocket_connect("/api/voice/ws/sess_reconnect") as ws2:
        ack2 = ws2.receive_json()
        assert ack2["session_id"] == "sess_reconnect"
        assert ack2["data"]["active_turn_id"] == 1


# =====================================================================
# Test 13: Multiple Sessions Operate Concurrently & Independently
# =====================================================================
def test_websocket_concurrent_multi_session():
    """Scenario 13: Two distinct sessions can initiate turns concurrently without collision."""
    client = TestClient(app)
    with client.websocket_connect("/api/voice/ws/sess_conc_1") as ws1, \
         client.websocket_connect("/api/voice/ws/sess_conc_2") as ws2:
        _ = ws1.receive_json()
        _ = ws2.receive_json()

        ws1.send_json({"event_type": "TEXT_PROMPT", "data": {"text": "Prompt 1"}})
        ws2.send_json({"event_type": "TEXT_PROMPT", "data": {"text": "Prompt 2"}})

        resp1 = ws1.receive_json()
        resp2 = ws2.receive_json()

        assert resp1["event_type"] == "TURN_STARTED"
        assert resp1["session_id"] == "sess_conc_1"

        assert resp2["event_type"] == "TURN_STARTED"
        assert resp2["session_id"] == "sess_conc_2"


# =====================================================================
# Test 14: Rapid Consecutive Interruptions (T1 -> T2 -> T3)
# =====================================================================
def test_websocket_rapid_interruptions_chain():
    """Scenario 14: Rapid back-to-back interruptions cleanly advance turns."""
    client = TestClient(app)
    with client.websocket_connect("/api/voice/ws/sess_rapid_chain") as ws:
        _ = ws.receive_json()  # ACK

        # Start T1
        ws.send_json({"event_type": "TEXT_PROMPT", "data": {"text": "T1"}})
        _ = ws.receive_json()  # TURN_STARTED T1

        # Interruption 1 (T1 -> T2)
        ws.send_json({"event_type": "INTERRUPTION_DETECTED", "data": {"previous_turn_id": 1, "reason": "vad_1"}})
        
        events1 = {}
        for _ in range(4):
            e = ws.receive_json()
            events1[e["event_type"]] = e
            if "AUDIO_STOP" in events1 and "TURN_INTERRUPTED" in events1:
                break

        assert "AUDIO_STOP" in events1
        assert events1["AUDIO_STOP"]["turn_id"] == 1
        assert "TURN_INTERRUPTED" in events1
        assert events1["TURN_INTERRUPTED"]["turn_id"] == 2

        # Interruption 2 (T2 -> T3)
        ws.send_json({"event_type": "INTERRUPTION_DETECTED", "data": {"previous_turn_id": 2, "reason": "vad_2"}})
        events2 = {}
        for _ in range(4):
            e = ws.receive_json()
            events2[e["event_type"]] = e
            if "AUDIO_STOP" in events2 and "TURN_INTERRUPTED" in events2:
                break

        assert "AUDIO_STOP" in events2
        assert events2["AUDIO_STOP"]["turn_id"] == 2
        assert "TURN_INTERRUPTED" in events2
        assert events2["TURN_INTERRUPTED"]["turn_id"] == 3


# =====================================================================
# Test 15: Race Condition: T1 Completion vs T2 Creation
# =====================================================================
@pytest.mark.asyncio
async def test_websocket_race_completion_vs_turn_creation():
    """Scenario 15: If T1 completion arrives after T2 creation, T1 result is safely discarded."""
    session = default_session_store.get_or_create_session("sess_race_15")
    t1 = session.create_next_turn("Prompt 1")
    t2 = session.create_next_turn("Prompt 2")

    mock_ws = MagicMock()
    mock_ws.send_text = AsyncMock()

    # Attempt to transmit completed T1 response
    sent = await default_ws_manager.send_event(
        websocket=mock_ws,
        session_id="sess_race_15",
        turn_id=t1,
        event_type=WebSocketEventType.TURN_COMPLETED,
        data={"assistant_response": "Late T1 answer"},
        validate_turn=True,
    )

    assert sent is False
    assert mock_ws.send_text.call_count == 0


# =====================================================================
# Test 16: Race Condition: Stale T1 Event vs Active T2
# =====================================================================
@pytest.mark.asyncio
async def test_websocket_race_stale_event_vs_active_turn():
    """Scenario 16: Sending intermediate T1 events (THINKING, TRANSCRIPT) is dropped when T2 is active."""
    session = default_session_store.get_or_create_session("sess_race_16")
    t1 = session.create_next_turn("T1")
    t2 = session.create_next_turn("T2")

    mock_ws = MagicMock()
    mock_ws.send_text = AsyncMock()

    # Send T1 THINKING
    sent_thinking = await default_ws_manager.send_event(
        websocket=mock_ws,
        session_id="sess_race_16",
        turn_id=t1,
        event_type=WebSocketEventType.THINKING,
        data={"status": "thinking"},
        validate_turn=True,
    )
    assert sent_thinking is False

    # Send T2 THINKING
    sent_t2 = await default_ws_manager.send_event(
        websocket=mock_ws,
        session_id="sess_race_16",
        turn_id=t2,
        event_type=WebSocketEventType.THINKING,
        data={"status": "thinking"},
        validate_turn=True,
    )
    assert sent_t2 is True
    assert mock_ws.send_text.call_count == 1


# =====================================================================
# Test 17: Unknown Event Type Handling
# =====================================================================
def test_websocket_unknown_event_type():
    """Scenario 17: Sending unknown event_type returns ERROR event gracefully."""
    client = TestClient(app)
    with client.websocket_connect("/api/voice/ws/sess_unknown_evt") as ws:
        _ = ws.receive_json()  # ACK

        ws.send_json({
            "event_type": "NON_EXISTENT_EVENT",
            "data": {},
        })

        err_evt = ws.receive_json()
        assert err_evt["event_type"] == "ERROR"
        assert "Unknown event_type" in err_evt["data"]["error"]


# =====================================================================
# Test 18: Binary Audio Chunk Accumulation
# =====================================================================
@pytest.mark.asyncio
async def test_websocket_binary_audio_chunk_accumulation():
    """Scenario 18: Binary frames sent to WebSocket accumulate in session audio buffer."""
    mock_ws = MagicMock()
    session = default_session_store.get_or_create_session("sess_audio_accum")
    default_ws_manager._audio_buffers["sess_audio_accum"] = bytearray()

    chunk1 = b"\x01\x02\x03\x04"
    chunk2 = b"\x05\x06\x07\x08"

    await default_ws_manager.handle_message(mock_ws, "sess_audio_accum", chunk1)
    await default_ws_manager.handle_message(mock_ws, "sess_audio_accum", chunk2)

    assert bytes(default_ws_manager._audio_buffers["sess_audio_accum"]) == chunk1 + chunk2


# =====================================================================
# Test 19: Speech Started Barge-in While In-Flight Task Runs
# =====================================================================
@pytest.mark.asyncio
async def test_websocket_speech_started_barge_in():
    """Scenario 19: SPEECH_STARTED while an active turn task is running triggers interruption."""
    session = default_session_store.get_or_create_session("sess_speech_start_barge")
    t1 = session.create_next_turn("Active T1")

    async def in_flight():
        try:
            await asyncio.sleep(5.0)
        except asyncio.CancelledError:
            raise

    task = asyncio.create_task(in_flight())
    default_cancellation_manager.register_task(
        session_id="sess_speech_start_barge",
        turn_id=t1,
        task=task,
    )
    await asyncio.sleep(0.01)

    mock_ws = MagicMock()
    mock_ws.send_text = AsyncMock()

    await default_ws_manager.handle_message(
        websocket=mock_ws,
        session_id="sess_speech_start_barge",
        raw_message=json.dumps({"event_type": "SPEECH_STARTED", "data": {}}),
    )

    with pytest.raises(asyncio.CancelledError):
        await task

    assert session.active_turn_id == 2


# =====================================================================
# Test 20: Session Cleanup and Registry Purging
# =====================================================================
@pytest.mark.asyncio
async def test_websocket_session_cleanup():
    """Scenario 20: Full disconnect cleans buffers, connections, and cancellation tasks."""
    mock_ws = MagicMock()
    mock_ws.close = AsyncMock()
    session = default_session_store.get_or_create_session("sess_purge_20")
    t1 = session.create_next_turn("p1")

    async def bg_work():
        try:
            await asyncio.sleep(5.0)
        except asyncio.CancelledError:
            raise

    task = asyncio.create_task(bg_work())
    default_cancellation_manager.register_task("sess_purge_20", t1, task)
    default_ws_manager._connections["sess_purge_20"] = {mock_ws}
    default_ws_manager._audio_buffers["sess_purge_20"] = bytearray(b"some_audio")
    await asyncio.sleep(0.01)

    # Send DISCONNECT
    await default_ws_manager.handle_message(
        websocket=mock_ws,
        session_id="sess_purge_20",
        raw_message=json.dumps({"event_type": "DISCONNECT"}),
    )

    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.01)

    assert "sess_purge_20" not in default_ws_manager._connections
    assert "sess_purge_20" not in default_ws_manager._audio_buffers
    assert len(default_cancellation_manager.get_active_tasks("sess_purge_20")) == 0
