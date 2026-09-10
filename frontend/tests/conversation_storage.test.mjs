import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  formatRelativeTime,
  generateTitleFromPrompt,
  extractLatestPreview,
  turnsToMessages,
  createNewConversationRecord,
  persistConversationTurns,
  getStoredConversation,
  loadAllConversations,
  saveAllConversations,
  CONVERSATIONS_STORAGE_KEY,
} from '../src/services/conversation_storage.js';

// Setup mock localStorage in Node environment
const mockStorage = new Map();
globalThis.window = {
  localStorage: {
    getItem: (key) => mockStorage.get(key) || null,
    setItem: (key, val) => mockStorage.set(key, String(val)),
    removeItem: (key) => mockStorage.delete(key),
    clear: () => mockStorage.clear(),
  },
};
globalThis.localStorage = globalThis.window.localStorage;

test('1. formatRelativeTime handles recent and older timestamps correctly', () => {
  const now = Date.now();
  assert.equal(formatRelativeTime(now - 10000), 'Just now');
  assert.equal(formatRelativeTime(now - 5 * 60 * 1000), '5 min ago');
  assert.equal(formatRelativeTime(now - 65 * 60 * 1000), '1 hour ago');
  assert.equal(formatRelativeTime(now - 3 * 3600 * 1000), '3 hours ago');
  assert.equal(formatRelativeTime(now - 25 * 3600 * 1000), 'Yesterday');
  assert.equal(formatRelativeTime(now - 3 * 24 * 3600 * 1000), '3 days ago');
});

test('2. generateTitleFromPrompt cleans and truncates prompts', () => {
  assert.equal(generateTitleFromPrompt('Tell me a joke'), 'Tell me a joke');
  assert.equal(generateTitleFromPrompt('tell me a joke?'), 'Tell me a joke');
  assert.equal(generateTitleFromPrompt('What is the weather today in Tokyo and how is it?'), 'What is the weather today in T...');
  assert.equal(generateTitleFromPrompt(''), 'New Chat');
});

test('3. extractLatestPreview extracts latest assistant response or user prompt', () => {
  const turns = [
    { userPrompt: 'Tell me a joke', assistantResponse: 'Why did the chicken cross the road?' },
    { userPrompt: 'What about cows?', assistantResponse: 'Moo-ve over!' },
  ];
  assert.equal(extractLatestPreview(turns), 'Moo-ve over!');

  // Fallback to user prompt if assistant response is empty
  const pendingTurns = [
    { userPrompt: 'Tell me a joke', assistantResponse: 'Funny joke' },
    { userPrompt: 'Pending question', assistantResponse: '' },
  ];
  assert.equal(extractLatestPreview(pendingTurns), 'Pending question');
});

test('4. turnsToMessages maps turns to role/content message list', () => {
  const turns = [
    { userPrompt: 'Hello', assistantResponse: 'Hi there!' },
  ];
  const msgs = turnsToMessages(turns);
  assert.equal(msgs.length, 2);
  assert.equal(msgs[0].role, 'user');
  assert.equal(msgs[0].content, 'Hello');
  assert.equal(msgs[1].role, 'assistant');
  assert.equal(msgs[1].content, 'Hi there!');
});

test('5. Multi-conversation isolation: distinct sessions never overwrite each other', () => {
  mockStorage.clear();

  // User Chat 1
  const conv1 = createNewConversationRecord('sess-1', 'Tell me a joke');
  persistConversationTurns('sess-1', [
    { turnId: 1, userPrompt: 'Tell me a joke', assistantResponse: 'Why did the chicken cross the road?' }
  ]);

  // User clicks "New Chat" -> User Chat 2
  const conv2 = createNewConversationRecord('sess-2', 'New Chat');
  persistConversationTurns('sess-2', [
    { turnId: 1, userPrompt: "What's the weather today?", assistantResponse: "Today's weather is sunny." }
  ]);

  // Verify both conversations exist independently in storage
  const all = loadAllConversations();
  assert.equal(all.length, 2);

  const restored1 = getStoredConversation('sess-1');
  const restored2 = getStoredConversation('sess-2');

  assert.equal(restored1.id, 'sess-1');
  assert.equal(restored1.title, 'Tell me a joke');
  assert.equal(restored1.turns.length, 1);
  assert.equal(restored1.turns[0].userPrompt, 'Tell me a joke');
  assert.equal(restored1.turns[0].assistantResponse, 'Why did the chicken cross the road?');

  assert.equal(restored2.id, 'sess-2');
  assert.equal(restored2.title, "What's the weather today");
  assert.equal(restored2.turns.length, 1);
  assert.equal(restored2.turns[0].userPrompt, "What's the weather today?");
  assert.equal(restored2.turns[0].assistantResponse, "Today's weather is sunny.");

  // Appending to Chat 1 preserves Chat 2 untouched
  persistConversationTurns('sess-1', [
    { turnId: 1, userPrompt: 'Tell me a joke', assistantResponse: 'Why did the chicken cross the road?' },
    { turnId: 2, userPrompt: 'Another one', assistantResponse: 'Knock knock!' }
  ]);

  const updated1 = getStoredConversation('sess-1');
  const check2 = getStoredConversation('sess-2');

  assert.equal(updated1.turns.length, 2);
  assert.equal(check2.turns.length, 1);
  assert.equal(check2.turns[0].userPrompt, "What's the weather today?");
});
