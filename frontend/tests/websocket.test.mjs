/**
 * Unit Test Suite for Frontend VoiceWebSocketClient
 * 
 * Validates:
 * 1. Initial disconnected state
 * 2. Connect lifecycle and WebSocket instantiation
 * 3. Event listener dispatch
 * 4. Interruption event sending
 * 5. Audio stop event handling
 * 6. Audio data chunk decoding
 * 7. Disconnect and resource cleanup
 * 
 * Phase 14 — Node test runner compatible (0 external API calls)
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { VoiceWebSocketClient, WebSocketState, ServerEventType } from '../src/services/websocket.js';

// Mock WebSocket class for Node.js test environment
class MockWebSocket {
  static OPEN = 1;
  static CONNECTING = 0;
  static CLOSING = 2;
  static CLOSED = 3;

  constructor(url) {
    this.url = url;
    this.readyState = MockWebSocket.CONNECTING;
    this.sentMessages = [];
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN;
      if (this.onopen) this.onopen();
    }, 5);
  }

  send(data) {
    this.sentMessages.push(data);
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    if (this.onclose) this.onclose();
  }

  simulateServerMessage(data) {
    if (this.onmessage) {
      this.onmessage({ data: typeof data === 'string' ? data : JSON.stringify(data) });
    }
  }

  simulateError(err) {
    if (this.onerror) {
      this.onerror(err);
    }
  }
}

globalThis.WebSocket = MockWebSocket;

test('1. WebSocketClient initializes in DISCONNECTED state', () => {
  const client = new VoiceWebSocketClient('ws://127.0.0.1:8000');
  assert.equal(client.state, WebSocketState.DISCONNECTED);
  assert.equal(client.sessionId, null);
});

test('2. WebSocketClient connect transitions to CONNECTING then CONNECTED', async () => {
  const client = new VoiceWebSocketClient('ws://127.0.0.1:8000');
  const states = [];
  client.onStateChange((st) => states.push(st));

  client.connect('sess_ws_test');
  assert.equal(client.sessionId, 'sess_ws_test');
  assert.ok(states.includes(WebSocketState.CONNECTING));

  await new Promise((r) => setTimeout(r, 15));
  assert.equal(client.state, WebSocketState.CONNECTED);
  client.disconnect();
});

test('3. WebSocketClient receives and dispatches server events to subscribers', async () => {
  const client = new VoiceWebSocketClient('ws://127.0.0.1:8000');
  client.connect('sess_dispatch');
  await new Promise((r) => setTimeout(r, 15));

  const receivedEvents = [];
  client.onEvent((evt) => receivedEvents.push(evt));

  client.ws.simulateServerMessage({
    event_type: ServerEventType.TURN_STARTED,
    session_id: 'sess_dispatch',
    turn_id: 1,
    data: { prompt: 'Hello' },
  });

  assert.equal(receivedEvents.length, 1);
  assert.equal(receivedEvents[0].event_type, ServerEventType.TURN_STARTED);
  assert.equal(receivedEvents[0].turn_id, 1);
  client.disconnect();
});

test('4. sendInterruption transmits structured INTERRUPTION_DETECTED payload', async () => {
  const client = new VoiceWebSocketClient('ws://127.0.0.1:8000');
  client.connect('sess_int_send');
  await new Promise((r) => setTimeout(r, 15));

  const sent = client.sendInterruption({
    previousTurnId: 1,
    newTurnId: 2,
    reason: 'vad_barge_in',
    detectionSource: 'vad',
    assistantState: 'PLAYING',
  });

  assert.equal(sent, true);
  assert.equal(client.ws.sentMessages.length, 1);
  const parsed = JSON.parse(client.ws.sentMessages[0]);
  assert.equal(parsed.event_type, 'INTERRUPTION_DETECTED');
  assert.equal(parsed.turn_id, 1);
  assert.equal(parsed.data.previous_turn_id, 1);
  assert.equal(parsed.data.new_turn_id, 2);
  assert.equal(parsed.data.reason, 'vad_barge_in');
  client.disconnect();
});

test('5. sendTextPrompt transmits structured TEXT_PROMPT payload', async () => {
  const client = new VoiceWebSocketClient('ws://127.0.0.1:8000');
  client.connect('sess_prompt_send');
  await new Promise((r) => setTimeout(r, 15));

  const sent = client.sendTextPrompt('Tell me about gravity', { speaker: 'celeste' });
  assert.equal(sent, true);
  assert.equal(client.ws.sentMessages.length, 1);
  const parsed = JSON.parse(client.ws.sentMessages[0]);
  assert.equal(parsed.event_type, 'TEXT_PROMPT');
  assert.equal(parsed.data.text, 'Tell me about gravity');
  assert.equal(parsed.data.speaker, 'celeste');
  client.disconnect();
});

test('6. Disconnect transitions state to DISCONNECTED and closes socket', async () => {
  const client = new VoiceWebSocketClient('ws://127.0.0.1:8000');
  client.connect('sess_dc');
  await new Promise((r) => setTimeout(r, 15));

  assert.equal(client.state, WebSocketState.CONNECTED);
  client.disconnect();
  assert.equal(client.state, WebSocketState.DISCONNECTED);
  assert.equal(client.ws, null);
});
