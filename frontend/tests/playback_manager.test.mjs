import test from 'node:test';
import assert from 'node:assert/strict';
import { AudioPlaybackManager, PlaybackState, AudioEventType } from '../src/services/audio.js';

// Mock Audio element for deterministic headless testing
class MockAudioElement {
  constructor() {
    this.src = '';
    this.currentTime = 0;
    this.duration = 2.5;
    this.paused = true;
    this._listeners = {};
    this.error = null;
  }

  addEventListener(event, callback) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(callback);
  }

  removeEventListener(event, callback) {
    if (!this._listeners[event]) return;
    this._listeners[event] = this._listeners[event].filter(cb => cb !== callback);
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
    this.emit('play');
    return Promise.resolve();
  }

  pause() {
    this.paused = true;
    this.emit('pause');
  }

  load() {
    // no-op for mock
  }

  removeAttribute(attr) {
    if (attr === 'src') this.src = '';
  }
}

test('1. Audio starts in IDLE state', () => {
  const mockAudio = new MockAudioElement();
  const manager = new AudioPlaybackManager({ audioElement: mockAudio });
  assert.equal(manager.state, PlaybackState.IDLE);
  assert.equal(manager.currentAudio, null);
  assert.equal(manager.queue.length, 0);
});

test('2. Audio transitions to PLAYING', async () => {
  const mockAudio = new MockAudioElement();
  const manager = new AudioPlaybackManager({ audioElement: mockAudio });
  manager.setSession('sess_1', 1);

  const states = [];
  manager.onStateChange((s) => states.push(s));

  await manager.playAudio({
    sessionId: 'sess_1',
    turnId: 1,
    audioSource: 'data:audio/mp3;base64,mockdata',
  });

  assert.equal(manager.state, PlaybackState.PLAYING);
  assert.ok(states.includes(PlaybackState.LOADING));
  assert.ok(states.includes(PlaybackState.READY));
  assert.ok(states.includes(PlaybackState.PLAYING));
});

test('3. Completion transitions correctly to COMPLETED then IDLE', async () => {
  const mockAudio = new MockAudioElement();
  const manager = new AudioPlaybackManager({ audioElement: mockAudio });
  manager.setSession('sess_1', 1);

  const events = [];
  manager.onEvent((e) => events.push(e.event_type));

  await manager.playAudio({
    sessionId: 'sess_1',
    turnId: 1,
    audioSource: 'data:audio/mp3;base64,mockdata',
  });

  assert.equal(manager.state, PlaybackState.PLAYING);

  // Simulate audio reaching end of playback
  mockAudio.emit('ended');

  assert.equal(manager.state, PlaybackState.IDLE);
  assert.ok(events.includes(AudioEventType.AUDIO_PLAY_COMPLETED));
});

test('4. stopCurrentAudio stops active audio immediately', async () => {
  const mockAudio = new MockAudioElement();
  const manager = new AudioPlaybackManager({ audioElement: mockAudio });
  manager.setSession('sess_1', 1);

  const events = [];
  manager.onEvent((e) => events.push(e.event_type));

  await manager.playAudio({
    sessionId: 'sess_1',
    turnId: 1,
    audioSource: 'data:audio/mp3;base64,mockdata',
  });

  assert.equal(manager.state, PlaybackState.PLAYING);

  manager.stopCurrentAudio('barge_in');

  assert.equal(manager.state, PlaybackState.IDLE);
  assert.equal(manager.currentAudio, null);
  assert.equal(mockAudio.paused, true);
  assert.ok(events.includes(AudioEventType.AUDIO_STOP_REQUESTED));
  assert.ok(events.includes(AudioEventType.AUDIO_STOPPED));
});

test('5. stopCurrentAudio clears obsolete queued audio', async () => {
  const mockAudio = new MockAudioElement();
  const manager = new AudioPlaybackManager({ audioElement: mockAudio });
  manager.setSession('sess_1', 1);

  await manager.playAudio({
    sessionId: 'sess_1',
    turnId: 1,
    audioSource: 'data:audio/mp3;base64,mockdata1',
  });

  manager.enqueueAudio({
    sessionId: 'sess_1',
    turnId: 1,
    audioSource: 'data:audio/mp3;base64,mockdata2',
  });
  assert.equal(manager.queue.length, 1);

  manager.stopCurrentAudio('barge_in');

  assert.equal(manager.queue.length, 0);
  assert.equal(manager.currentAudio, null);
});

test('6. Stale turn audio is rejected and discarded', async () => {
  const mockAudio = new MockAudioElement();
  const manager = new AudioPlaybackManager({ audioElement: mockAudio });
  manager.setSession('sess_1', 2); // Active turn is 2

  const events = [];
  manager.onEvent((e) => events.push(e));

  // Attempt to enqueue/play Turn 1 (stale)
  const enqueued = manager.enqueueAudio({
    sessionId: 'sess_1',
    turnId: 1,
    audioSource: 'data:audio/mp3;base64,mockdata',
  });
  assert.equal(enqueued, false);

  const played = await manager.playAudio({
    sessionId: 'sess_1',
    turnId: 1,
    audioSource: 'data:audio/mp3;base64,mockdata',
  });
  assert.equal(played, false);
  assert.equal(manager.state, PlaybackState.IDLE);

  const discardEvent = events.find(e => e.event_type === AudioEventType.AUDIO_DISCARDED);
  assert.ok(discardEvent);
  assert.equal(discardEvent.turn_id, 1);
});

test('7. Newer turn audio can play cleanly', async () => {
  const mockAudio = new MockAudioElement();
  const manager = new AudioPlaybackManager({ audioElement: mockAudio });
  manager.setSession('sess_1', 1);

  await manager.playAudio({
    sessionId: 'sess_1',
    turnId: 1,
    audioSource: 'data:audio/mp3;base64,mockdata1',
  });
  assert.equal(manager.state, PlaybackState.PLAYING);
  assert.equal(manager.currentAudio.turnId, 1);

  // Advance turn to 2 (e.g. user interruption / new turn)
  manager.setActiveTurn(2);

  // Playing turn 1 is instantly stopped
  assert.equal(manager.state, PlaybackState.IDLE);

  // Play Turn 2
  await manager.playAudio({
    sessionId: 'sess_1',
    turnId: 2,
    audioSource: 'data:audio/mp3;base64,mockdata2',
  });
  assert.equal(manager.state, PlaybackState.PLAYING);
  assert.equal(manager.currentAudio.turnId, 2);
});

test('8. Playback errors transition safely to ERROR and recover to IDLE', async () => {
  const mockAudio = new MockAudioElement();
  mockAudio.play = async () => {
    throw new Error('Decoder error');
  };

  const manager = new AudioPlaybackManager({ audioElement: mockAudio });
  manager.setSession('sess_1', 1);

  const events = [];
  manager.onEvent((e) => events.push(e.event_type));

  const success = await manager.playAudio({
    sessionId: 'sess_1',
    turnId: 1,
    audioSource: 'corrupted_audio',
  });

  assert.equal(success, false);
  assert.equal(manager.state, PlaybackState.IDLE);
  assert.ok(events.includes(AudioEventType.AUDIO_PLAYBACK_ERROR));
});

test('9. Stopping twice is safe and idempotent', () => {
  const mockAudio = new MockAudioElement();
  const manager = new AudioPlaybackManager({ audioElement: mockAudio });
  manager.setSession('sess_1', 1);

  assert.doesNotThrow(() => {
    manager.stopCurrentAudio();
    manager.stopCurrentAudio();
  });
  assert.equal(manager.state, PlaybackState.IDLE);
});

test('10. Obsolete audio cannot resume automatically after stop', async () => {
  const mockAudio = new MockAudioElement();
  const manager = new AudioPlaybackManager({ audioElement: mockAudio });
  manager.setSession('sess_1', 1);

  await manager.playAudio({
    sessionId: 'sess_1',
    turnId: 1,
    audioSource: 'data:audio/mp3;base64,mockdata',
  });

  manager.stopCurrentAudio();
  assert.equal(manager.state, PlaybackState.IDLE);

  // Simulating stray ended or play events from previous instance
  mockAudio.emit('ended');
  assert.equal(manager.state, PlaybackState.IDLE);
  assert.equal(manager.currentAudio, null);
});
