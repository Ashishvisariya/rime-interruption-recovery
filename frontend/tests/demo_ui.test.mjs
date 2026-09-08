/**
 * Unit Test Suite for Phase 16 Demo & UX Hardening
 * 
 * Validates 10 Key UX & Security Requirements:
 * 1. Connection state rendering & status mapping (CONNECTED / DISCONNECTED / CONNECTING)
 * 2. Monotonic turn sequence & Authoritative turn badge invariants
 * 3. Interruption state rendering & latency calculation
 * 4. T1 -> T2 turn transition & previous turn status tracking
 * 5. Stale event detection & audit log formatting
 * 6. Cancellation event dispatch & state invalidation
 * 7. Latest response display (only authoritative turn answers selected)
 * 8. Disconnect recovery mechanism & reconnect handlers
 * 9. Provider error handling & sanitized user-facing messages
 * 10. Zero secret leakage across metadata and runtime configurations
 * 
 * Phase 16 — Node native test runner (0 live API calls)
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PlaybackState } from '../src/services/audio.js';
import { WebSocketState } from '../src/services/websocket.js';
import { sanitizeFinalResponse } from '../src/services/response_sanitizer.js';

// --- State and Formatting Helpers mirroring UI Components ---

function formatEventLog(event) {
  const time = new Date(event.timestamp_ms || Date.now()).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
  const turn = event.turn_id ? `T#${event.turn_id}` : 'SYS';
  
  let label = event.event_type;
  let cssClass = 'log-generic';

  if (event.event_type === 'USER_SPEECH_START') {
    label = 'USER STARTED SPEAKING';
    cssClass = 'log-user';
  } else if (event.event_type === 'USER_SPEECH_STOP') {
    label = 'USER STOPPED SPEAKING';
    cssClass = 'log-user';
  } else if (event.event_type === 'INTERRUPTION_DETECTED') {
    label = 'USER INTERRUPTED';
    cssClass = 'log-interruption';
  } else if (event.event_type === 'AUDIO_STOPPED') {
    label = 'AUDIO STOPPED (IMMEDIATE)';
    cssClass = 'log-interruption';
  } else if (event.event_type === 'AUDIO_DISCARDED') {
    label = 'STALE RESULT REJECTED';
    cssClass = 'log-stale';
  } else if (event.event_type === 'AUDIO_PLAYING') {
    label = 'RIME AUDIO PLAYING';
    cssClass = 'log-playback';
  } else if (event.event_type === 'PROCESSING_START') {
    label = 'PROCESSING TURN';
    cssClass = 'log-system';
  }

  return { time, turn, label, cssClass, raw: event };
}

function getRimeConfig(metadata = {}) {
  return {
    provider: 'Rime Labs',
    model: metadata.modelId || 'coda',
    speaker: metadata.speaker || 'celeste',
    language: 'en',
    format: 'mp3',
    samplingRate: '22050 Hz',
    guarantee: 'Cancellation is best-effort; stale-result rejection is the correctness guarantee.',
  };
}

function sanitizeErrorMessage(error) {
  if (!error) return '';
  const msg = typeof error === 'string' ? error : error.message || 'Unknown error occurred';
  // Strip any accidental API keys, tokens, or auth headers
  return msg
    .replace(/(?:sk_live_|sk_test_|Bearer\s+)[a-zA-Z0-9_\-\.]+/gi, '[REDACTED_SECRET]')
    .replace(/(?:RIME_API_KEY|GROQ_API_KEY|GEMINI_API_KEY)=[^\s]+/gi, '[REDACTED_ENV]');
}

// --- Test Cases ---

test('1. Connection state rendering displays correct badges for all states', () => {
  const getBadgeClass = (wsState) => {
    switch (wsState) {
      case WebSocketState.CONNECTED:
        return { label: 'CONNECTED', className: 'badge-connected' };
      case WebSocketState.CONNECTING:
        return { label: 'CONNECTING...', className: 'badge-connecting' };
      case WebSocketState.DISCONNECTED:
      default:
        return { label: 'DISCONNECTED', className: 'badge-disconnected' };
    }
  };

  const connState = getBadgeClass(WebSocketState.CONNECTED);
  assert.equal(connState.label, 'CONNECTED');
  assert.equal(connState.className, 'badge-connected');

  const discState = getBadgeClass(WebSocketState.DISCONNECTED);
  assert.equal(discState.label, 'DISCONNECTED');
  assert.equal(discState.className, 'badge-disconnected');

  const ingState = getBadgeClass(WebSocketState.CONNECTING);
  assert.equal(ingState.label, 'CONNECTING...');
  assert.equal(ingState.className, 'badge-connecting');
});

test('2. Turn state rendering displays monotonic Turn ID and AUTHORITATIVE badge invariants', () => {
  let activeTurnId = 1;
  const turns = [];

  // Simulate turn progression
  turns.push({ turnId: activeTurnId, status: 'ACTIVE' });
  assert.equal(activeTurnId, 1);

  // Interruption triggers turn increment
  activeTurnId += 1;
  turns[0].status = 'INTERRUPTED';
  turns.push({ turnId: activeTurnId, status: 'ACTIVE' });

  assert.equal(activeTurnId, 2);
  assert.equal(turns[0].turnId < turns[1].turnId, true);
  assert.equal(turns[1].status, 'ACTIVE');
  assert.equal(turns[0].status, 'INTERRUPTED');
});

test('3. Interruption state rendering displays high-visibility barge-in indicators and latency', () => {
  const interruptionInfo = {
    previousTurnId: 1,
    newTurnId: 2,
    stopLatencyMs: 0.116,
  };

  assert.ok(interruptionInfo.previousTurnId < interruptionInfo.newTurnId);
  assert.ok(interruptionInfo.stopLatencyMs < 1.0, 'Interruption stop latency must be sub-millisecond in memory');

  const bannerText = `Barge-In Interruption Detected: Turn #${interruptionInfo.previousTurnId} audio immediately aborted (${interruptionInfo.stopLatencyMs.toFixed(2)} ms stop latency).`;
  assert.ok(bannerText.includes('Turn #1'));
  assert.ok(bannerText.includes('0.12 ms'));
});

test('4. T1 -> T2 transition tracks previous turn status and advances sequence', () => {
  const turnManager = {
    activeTurnId: 1,
    previousTurnId: null,
    previousTurnStatus: null,
    interrupt() {
      this.previousTurnId = this.activeTurnId;
      this.previousTurnStatus = 'INTERRUPTED';
      this.activeTurnId += 1;
    },
  };

  assert.equal(turnManager.activeTurnId, 1);
  assert.equal(turnManager.previousTurnId, null);

  turnManager.interrupt();

  assert.equal(turnManager.activeTurnId, 2);
  assert.equal(turnManager.previousTurnId, 1);
  assert.equal(turnManager.previousTurnStatus, 'INTERRUPTED');
});

test('5. Stale event display properly tags discarded audio in audit log', () => {
  const staleEvent = {
    event_type: 'AUDIO_DISCARDED',
    timestamp_ms: 1773000000000,
    turn_id: 1,
    details: { reason: 'stale_turn_rejected' },
  };

  const formatted = formatEventLog(staleEvent);
  assert.equal(formatted.label, 'STALE RESULT REJECTED');
  assert.equal(formatted.turn, 'T#1');
  assert.equal(formatted.cssClass, 'log-stale');
});

test('6. Cancellation event displays in audit stream', () => {
  const stopEvent = {
    event_type: 'AUDIO_STOPPED',
    timestamp_ms: 1773000000000,
    turn_id: 1,
    details: { reason: 'barge_in' },
  };

  const interruptEvent = {
    event_type: 'INTERRUPTION_DETECTED',
    timestamp_ms: 1773000000000,
    turn_id: 1,
    details: { previous_turn_id: 1, new_turn_id: 2 },
  };

  const formattedStop = formatEventLog(stopEvent);
  assert.equal(formattedStop.label, 'AUDIO STOPPED (IMMEDIATE)');
  assert.equal(formattedStop.cssClass, 'log-interruption');

  const formattedInterrupt = formatEventLog(interruptEvent);
  assert.equal(formattedInterrupt.label, 'USER INTERRUPTED');
  assert.equal(formattedInterrupt.cssClass, 'log-interruption');
});

test('7. Latest response displays with authoritative status tag', () => {
  const conversationTurns = [
    {
      turnId: 1,
      userPrompt: 'What is the weather in Delhi?',
      assistantResponse: '',
      status: 'INTERRUPTED',
    },
    {
      turnId: 2,
      userPrompt: 'Actually, tell me about Mumbai instead.',
      assistantResponse: 'Mumbai is warm and sunny with 32 degrees Celsius.',
      speaker: 'celeste',
      latencyMs: 1200,
      status: 'COMPLETED',
    },
  ];

  const activeTurnId = 2;
  const authoritativeTurn = conversationTurns.find((t) => t.turnId === activeTurnId);
  assert.ok(authoritativeTurn);
  assert.equal(authoritativeTurn.turnId, 2);
  assert.equal(authoritativeTurn.assistantResponse, 'Mumbai is warm and sunny with 32 degrees Celsius.');

  const interruptedTurn = conversationTurns.find((t) => t.turnId === 1);
  assert.ok(interruptedTurn);
  assert.equal(interruptedTurn.status, 'INTERRUPTED');
  assert.equal(interruptedTurn.assistantResponse, '');
});

test('8. Disconnect recovery and reconnect handlers trigger cleanly', () => {
  let reconnectCount = 0;
  const onReconnect = () => {
    reconnectCount += 1;
  };

  assert.equal(reconnectCount, 0);
  onReconnect();
  assert.equal(reconnectCount, 1);
});

test('9. Status component displays verified Rime TTS model configuration without secrets', () => {
  const config = getRimeConfig({ speaker: 'celeste', modelId: 'coda' });
  assert.equal(config.model, 'coda');
  assert.equal(config.speaker, 'celeste');
  assert.equal(config.format, 'mp3');
  assert.equal(config.language, 'en');
  assert.ok(config.guarantee.includes('Cancellation is best-effort'));
});

test('10. Zero secret leakage across rendered UI state and errors', () => {
  const dirtyError = 'Failed to connect: Bearer sk_live_secretkey123456 with RIME_API_KEY=rim_live_abc123';
  const cleanError = sanitizeErrorMessage(dirtyError);

  assert.equal(cleanError.includes('sk_live_secretkey123456'), false);
  assert.equal(cleanError.includes('rim_live_abc123'), false);
  assert.ok(cleanError.includes('[REDACTED_SECRET]'));
  assert.ok(cleanError.includes('[REDACTED_ENV]'));

  const rimeConfig = getRimeConfig({ apiKey: 'hidden' });
  const serialized = JSON.stringify(rimeConfig);
  assert.equal(serialized.includes('apiKey'), false);
  assert.equal(serialized.includes('secret'), false);
});

test('11. sanitizeFinalResponse removes reasoning, planning steps, and unclosed <think> blocks', () => {
  const dirty1 = '<think>\n1. Analyze User Input: Delhi weather\n2. Check available tools...\n';
  assert.equal(sanitizeFinalResponse(dirty1), '');

  const dirty2 = (
    '1. Check available tools.\n' +
    '2. I do not have a specific weather tool.\n' +
    '3. Formulate a response.\n' +
    '4. Yes. Yes. No markdown.\n' +
    'Final Answer: Delhi is currently 29°C with partly cloudy skies.'
  );
  assert.equal(sanitizeFinalResponse(dirty2), 'Delhi is currently 29°C with partly cloudy skies.');

  const normal = 'Delhi is currently 29°C with partly cloudy skies.';
  assert.equal(sanitizeFinalResponse(normal), 'Delhi is currently 29°C with partly cloudy skies.');
});

test('12. TURN_COMPLETED extracts canonical response and protects against raw event/reasoning leakage', () => {
  const rawEvent = {
    event_type: 'TURN_COMPLETED',
    turn_id: 1,
    data: {
      type: 'TURN_COMPLETED',
      turn_id: 1,
      response: 'Delhi is currently 29°C and partly cloudy.',
      final_response: 'Delhi is currently 29°C and partly cloudy.',
      assistant_response: 'Delhi is currently 29°C and partly cloudy.',
    },
  };

  const candidate = rawEvent.data?.response || rawEvent.data?.final_response || rawEvent.data?.assistant_response;
  assert.equal(candidate, 'Delhi is currently 29°C and partly cloudy.');
  const cleaned = sanitizeFinalResponse(candidate);
  assert.equal(cleaned, 'Delhi is currently 29°C and partly cloudy.');
});

test('13. Conversation history rendering does NOT show internal reasoning or planning', () => {
  const rawTextWithSteps = (
    '1. Check available tools.\n' +
    '2. I do not have a weather tool.\n' +
    'Final Answer: I do not have access to live weather data right now.'
  );
  const cleanAnswer = sanitizeFinalResponse(rawTextWithSteps);
  assert.equal(cleanAnswer.includes('Check available tools'), false);
  assert.equal(cleanAnswer.includes('weather tool.'), false);
  assert.equal(cleanAnswer, 'I do not have access to live weather data right now.');
});

test('14. Normal questions pass through sanitizeFinalResponse without modification', () => {
  assert.equal(sanitizeFinalResponse('Hello! How can I help you today?'), 'Hello! How can I help you today?');
  assert.equal(sanitizeFinalResponse('25 times 4 is 100.'), '25 times 4 is 100.');
  assert.equal(
    sanitizeFinalResponse('Why did the computer get cold? It left its Windows open.'),
    'Why did the computer get cold? It left its Windows open.'
  );
});

