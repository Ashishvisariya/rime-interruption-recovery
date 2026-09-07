/**
 * Phase 12 Playback Interruption & Audio Cancellation Unit Tests (Node.js Test Runner)
 * 
 * Validates deterministic Rime audio playback cancellation, queue flushing,
 * stale audio rejection, race condition protection, and resource cleanup.
 * 
 * Strictly 0 external API calls.
 */

import test from 'node:test';
import assert from 'node:assert/strict';
import { AudioPlaybackManager, PlaybackState, AudioEventType } from '../src/services/audio.js';

// Deterministic Mock Audio Element for Headless Testing
class MockAudioElement {
  constructor() {
    this.src = '';
    this.currentTime = 0;
    this.duration = 2.5;
    this.paused = true;
    this._listeners = {};
    this.error = null;
    this.playCallCount = 0;
    this.pauseCallCount = 0;
    this.loadCallCount = 0;
    this.removedAttributes = [];
  }

  addEventListener(event, callback) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(callback);
  }

  removeEventListener(event, callback) {
    if (!this._listeners[event]) return;
    this._listeners[event] = this._listeners[event].filter((cb) => cb !== callback);
  }

  emit(event, data) {
    if (this._listeners[event]) {
      for (const cb of this._listeners[event]) {
        cb(data);
      }
    }
  }

  async play() {
    this.paused = false;
    this.playCallCount++;
    this.emit('play');
    return Promise.resolve();
  }

  pause() {
    this.paused = true;
    this.pauseCallCount++;
    this.emit('pause');
  }

  load() {
    this.loadCallCount++;
  }

  removeAttribute(attr) {
    this.removedAttributes.push(attr);
    if (attr === 'src') this.src = '';
  }
}

test('1. Active audio stops immediately on interruption', async () => {
  const mockAudio = new MockAudioElement();
  const manager = new AudioPlaybackManager({ audioElement: mockAudio });
  manager.setSession('sess_int_1', 1);

  await manager.playAudio({
    sessionId: 'sess_int_1',
    turnId: 1,
    audioSource: 'http://example.com/turn1.mp3',
  });

  assert.equal(manager.state, PlaybackState.PLAYING);
  assert.equal(mockAudio.paused, false);

  // User barge-in interruption occurs
  const events = [];
  manager.onEvent((e) => events.push(e));
  manager.stopCurrentAudio('interruption_barge_in');

  assert.equal(mockAudio.paused, true);
  assert.equal(mockAudio.currentTime, 0);
  assert.equal(manager.state, PlaybackState.IDLE);
  assert.equal(manager.currentAudio, null);

  const stopReq = events.find((e) => e.event_type === AudioEventType.AUDIO_STOP_REQUESTED);
  const stopped = events.find((e) => e.event_type === AudioEventType.AUDIO_STOPPED);
  assert.ok(stopReq, 'Must emit AUDIO_STOP_REQUESTED');
  assert.ok(stopped, 'Must emit AUDIO_STOPPED');
  assert.equal(stopped.details.wasPlaying, true);
});

test('2. Playback queue is completely cleared on interruption', () => {
  const mockAudio = new MockAudioElement();
  const manager = new AudioPlaybackManager({ audioElement: mockAudio });
  manager.setSession('sess_queue', 1);

  manager.enqueueAudio({ sessionId: 'sess_queue', turnId: 1, audioSource: 'chunk1.mp3' });
  manager.enqueueAudio({ sessionId: 'sess_queue', turnId: 1, audioSource: 'chunk2.mp3' });

  assert.ok(manager.queue.length > 0);

  manager.stopCurrentAudio('interruption_barge_in');
  assert.equal(manager.queue.length, 0, 'Queue must be empty after interruption stop');
});

test('3. Stale turn audio is discarded and prevented from playing', async () => {
  const mockAudio = new MockAudioElement();
  const manager = new AudioPlaybackManager({ audioElement: mockAudio });
  manager.setSession('sess_stale', 2); // Active turn is 2

  const events = [];
  manager.onEvent((e) => events.push(e));

  // Late arrival of Turn 1 audio
  const played = await manager.playAudio({
    sessionId: 'sess_stale',
    turnId: 1,
    audioSource: 'turn1_late.mp3',
  });

  assert.equal(played, false);
  assert.equal(manager.state, PlaybackState.IDLE);
  assert.equal(mockAudio.playCallCount, 0, 'Must never invoke play on stale audio');

  const discarded = events.find((e) => e.event_type === AudioEventType.AUDIO_DISCARDED);
  assert.ok(discarded, 'Must emit AUDIO_DISCARDED for stale turn');
  assert.equal(discarded.turn_id, 1);
});

test('4. Active turn audio plays cleanly after interruption', async () => {
  const mockAudio = new MockAudioElement();
  const manager = new AudioPlaybackManager({ audioElement: mockAudio });
  manager.setSession('sess_advance', 1);

  await manager.playAudio({
    sessionId: 'sess_advance',
    turnId: 1,
    audioSource: 'turn1.mp3',
  });
  assert.equal(manager.state, PlaybackState.PLAYING);

  // Turn 1 interrupted -> Turn 2 becomes active
  manager.setActiveTurn(2);
  assert.equal(manager.state, PlaybackState.IDLE);

  // Turn 2 audio plays
  const played = await manager.playAudio({
    sessionId: 'sess_advance',
    turnId: 2,
    audioSource: 'turn2.mp3',
  });

  assert.equal(played, true);
  assert.equal(manager.state, PlaybackState.PLAYING);
  assert.equal(manager.currentAudio.turnId, 2);
});

test('5. Late playback play event cannot restart superseded audio (Race condition guard)', async () => {
  const mockAudio = new MockAudioElement();
  const manager = new AudioPlaybackManager({ audioElement: mockAudio });
  manager.setSession('sess_race', 1);

  await manager.playAudio({
    sessionId: 'sess_race',
    turnId: 1,
    audioSource: 'turn1.mp3',
  });

  // Turn 1 is superseded by Turn 2
  manager.setActiveTurn(2);
  assert.equal(manager.state, PlaybackState.IDLE);

  // Late spurious play event from obsolete Turn 1
  mockAudio.emit('play');

  assert.equal(manager.state, PlaybackState.IDLE, 'State must remain IDLE');
  assert.equal(manager.currentAudio, null);
});

test('6. Repeated PLAY -> INTERRUPT -> PLAY -> INTERRUPT cycles execute cleanly', async () => {
  const mockAudio = new MockAudioElement();
  const manager = new AudioPlaybackManager({ audioElement: mockAudio });
  manager.setSession('sess_cycles', 1);

  for (let turn = 1; turn <= 5; turn++) {
    manager.setActiveTurn(turn);
    const played = await manager.playAudio({
      sessionId: 'sess_cycles',
      turnId: turn,
      audioSource: `turn_${turn}.mp3`,
    });
    assert.equal(played, true);
    assert.equal(manager.state, PlaybackState.PLAYING);

    // Immediate interruption
    manager.stopCurrentAudio('rapid_barge_in');
    assert.equal(manager.state, PlaybackState.IDLE);
    assert.equal(mockAudio.paused, true);
  }

  assert.equal(manager.state, PlaybackState.IDLE);
});

test('7. Audio resource cleanup removes src and calls load() on stop', () => {
  const mockAudio = new MockAudioElement();
  const manager = new AudioPlaybackManager({ audioElement: mockAudio });
  manager.setSession('sess_clean', 1);

  manager.currentAudio = { sessionId: 'sess_clean', turnId: 1 };
  manager.state = PlaybackState.PLAYING;
  mockAudio.src = 'some_audio.mp3';

  manager.stopCurrentAudio('cleanup_test');

  assert.ok(mockAudio.removedAttributes.includes('src'), 'Must remove src attribute');
  assert.ok(mockAudio.loadCallCount > 0, 'Must invoke load() to release audio decoder');
  assert.equal(manager.currentAudio, null);
});

test('8. Blob Object URL cleanup is invoked upon discarding queued audio', () => {
  let revokedUrls = [];
  const origRevoke = globalThis.URL?.revokeObjectURL;
  if (!globalThis.URL) {
    globalThis.URL = {};
  }
  globalThis.URL.revokeObjectURL = (url) => revokedUrls.push(url);

  try {
    const mockAudio = new MockAudioElement();
    const manager = new AudioPlaybackManager({ audioElement: mockAudio });
    manager.setSession('sess_blob_clean', 1);

    manager.enqueueAudio({
      sessionId: 'sess_blob_clean',
      turnId: 1,
      audioSource: 'blob1.mp3',
      _createdBlobUrl: 'blob:http://localhost/uuid-1',
    });

    // Advance turn to 2 -> purges Turn 1 queue
    manager.setActiveTurn(2);

    assert.ok(revokedUrls.includes('blob:http://localhost/uuid-1'), 'Must revoke Blob URL on discard');
  } finally {
    if (origRevoke) {
      globalThis.URL.revokeObjectURL = origRevoke;
    }
  }
});

test('9. Interruption does not affect independent sessions', async () => {
  const mockAudio = new MockAudioElement();
  const manager = new AudioPlaybackManager({ audioElement: mockAudio });

  manager.setSession('session_A', 1);
  await manager.playAudio({
    sessionId: 'session_A',
    turnId: 1,
    audioSource: 'session_a.mp3',
  });
  assert.equal(manager.state, PlaybackState.PLAYING);

  // Switch to session B
  manager.setSession('session_B', 1);
  assert.equal(manager.state, PlaybackState.IDLE);

  const playedB = await manager.playAudio({
    sessionId: 'session_B',
    turnId: 1,
    audioSource: 'session_b.mp3',
  });
  assert.equal(playedB, true);
  assert.equal(manager.activeSessionId, 'session_B');
});
