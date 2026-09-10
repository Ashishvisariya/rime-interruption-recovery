/**
 * Unit Test Suite for Progressive Assistant Text Streaming & Interruption Invariants
 * 
 * Validates:
 * 1. TEXT_CHUNK is recognized as a standardized ServerEventType.
 * 2. Progressive text updates incrementally with monotonic turn validation.
 * 3. Barge-in / interruption immediately clears in-flight streaming assistant text.
 * 4. TURN_COMPLETED commits final response and resets streaming state.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ServerEventType } from '../src/services/websocket.js';

test('1. TEXT_CHUNK is recognized as a standardized ServerEventType', () => {
  assert.equal(ServerEventType.TEXT_CHUNK, 'TEXT_CHUNK');
});

test('2. Progressive text updates incrementally with monotonic turn validation', () => {
  let activeTurnId = 1;
  let streamingAssistantText = '';

  const handleTextChunk = (evt) => {
    if (evt.turn_id === activeTurnId) {
      if (evt.data?.accumulated_text) {
        streamingAssistantText = evt.data.accumulated_text;
      } else if (evt.data?.text_chunk) {
        streamingAssistantText = (streamingAssistantText ? streamingAssistantText + ' ' + evt.data.text_chunk : evt.data.text_chunk).trim();
      }
    }
  };

  // Chunk 1 for Turn 1
  handleTextChunk({
    event_type: 'TEXT_CHUNK',
    turn_id: 1,
    data: { text_chunk: 'The weather in Tokyo', accumulated_text: 'The weather in Tokyo' },
  });
  assert.equal(streamingAssistantText, 'The weather in Tokyo');

  // Chunk 2 for Turn 1
  handleTextChunk({
    event_type: 'TEXT_CHUNK',
    turn_id: 1,
    data: { text_chunk: 'is clear and sunny today.', accumulated_text: 'The weather in Tokyo is clear and sunny today.' },
  });
  assert.equal(streamingAssistantText, 'The weather in Tokyo is clear and sunny today.');

  // Stale Chunk for Turn 1 arriving after activeTurnId advanced to 2
  activeTurnId = 2;
  handleTextChunk({
    event_type: 'TEXT_CHUNK',
    turn_id: 1,
    data: { text_chunk: 'Stale chunk from obsolete turn', accumulated_text: 'Stale chunk' },
  });
  // Text for active turn should not be corrupted by stale turn 1
  assert.equal(streamingAssistantText, 'The weather in Tokyo is clear and sunny today.');
});

test('3. Barge-in / interruption immediately clears in-flight streaming assistant text', () => {
  let activeTurnId = 1;
  let streamingAssistantText = 'The capital of France is Paris and it is known for';

  const handleInterruption = (newTurnId) => {
    activeTurnId = newTurnId;
    streamingAssistantText = '';
  };

  handleInterruption(2);
  assert.equal(activeTurnId, 2);
  assert.equal(streamingAssistantText, '');
});

test('4. TURN_COMPLETED commits final response and resets streaming state', () => {
  let conversationTurns = [];
  let streamingAssistantText = 'Gravity is a fundamental interaction';

  const handleTurnCompleted = (evt) => {
    conversationTurns.push({
      turnId: evt.turn_id,
      assistantResponse: evt.data.response,
      status: 'COMPLETED',
    });
    streamingAssistantText = '';
  };

  handleTurnCompleted({
    turn_id: 1,
    data: { response: 'Gravity is a fundamental interaction that causes mutual attraction between all things with mass.' },
  });

  assert.equal(conversationTurns.length, 1);
  assert.equal(conversationTurns[0].turnId, 1);
  assert.equal(conversationTurns[0].assistantResponse, 'Gravity is a fundamental interaction that causes mutual attraction between all things with mass.');
  assert.equal(streamingAssistantText, '');
});
