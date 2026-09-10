import { test } from 'node:test';
import assert from 'node:assert/strict';
import { getLatestMessagePreview, getSessionPreview } from '../src/services/session_utils.js';

test('1. getLatestMessagePreview returns empty string for empty turns array', () => {
  assert.equal(getLatestMessagePreview([]), '');
  assert.equal(getLatestMessagePreview(null), '');
  assert.equal(getLatestMessagePreview(undefined), '');
});

test('2. getLatestMessagePreview returns assistant response if available in latest turn', () => {
  const turns = [
    { userPrompt: 'Tell me a joke.', assistantResponse: 'Why did the chicken cross the road?' },
  ];
  assert.equal(getLatestMessagePreview(turns), 'Why did the chicken cross the road?');
});

test('3. getLatestMessagePreview falls back to userPrompt if assistantResponse is empty', () => {
  const turns = [
    { userPrompt: 'What is the weather?', assistantResponse: '' },
  ];
  assert.equal(getLatestMessagePreview(turns), 'What is the weather?');
});

test('4. getLatestMessagePreview falls back to preceding turn if latest turn is completely blank', () => {
  const turns = [
    { userPrompt: 'Explain quantum computing.', assistantResponse: 'Quantum computing leverages qubits and superposition.' },
    { userPrompt: '', assistantResponse: '' },
  ];
  assert.equal(getLatestMessagePreview(turns), 'Quantum computing leverages qubits and superposition.');
});

test('5. getLatestMessagePreview handles multi-turn conversation and extracts strictly the latest', () => {
  const turns = [
    { userPrompt: 'Turn 1', assistantResponse: 'Response 1' },
    { userPrompt: 'Turn 2', assistantResponse: 'Response 2' },
    { userPrompt: 'Turn 3', assistantResponse: 'Response 3' },
  ];
  assert.equal(getLatestMessagePreview(turns), 'Response 3');
});

test('6. getSessionPreview uses session.preview if already populated', () => {
  const sess = { id: 'sess-123', title: 'Test Chat', preview: 'Existing preview text' };
  assert.equal(getSessionPreview(sess), 'Existing preview text');
});

test('7. getSessionPreview falls back to chatsMap when session.preview is missing', () => {
  const sess = { id: 'sess-abc', title: 'Test Chat' };
  const chatsMap = {
    'sess-abc': [
      { userPrompt: 'Hello', assistantResponse: 'Hi! How can I assist you today?' }
    ]
  };
  assert.equal(getSessionPreview(sess, chatsMap), 'Hi! How can I assist you today?');
});
