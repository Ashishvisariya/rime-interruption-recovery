/**
 * Phase 11 VAD & Interruption Detection Unit Tests (Node.js Test Runner)
 * 
 * Validates deterministic Voice Activity Detection, energy calculations,
 * click/keystroke debouncing, assistant-state awareness (PLAYING, THINKING, SYNTHESIZING vs IDLE),
 * interruption event generation, and lifecycle management.
 * 
 * Strictly 0 external API calls.
 */

import test from 'node:test';
import assert from 'node:assert/strict';
import { VoiceActivityDetector, VADState, VADEventType, DEFAULT_VAD_CONFIG } from '../src/services/vad.js';

// Helper: Generate synthetic audio buffer with specific amplitude
function generateSineWave(amplitude = 0.1, numSamples = 256) {
  const buffer = new Float32Array(numSamples);
  for (let i = 0; i < numSamples; i++) {
    buffer[i] = amplitude * Math.sin((2 * Math.PI * i * 440) / 16000);
  }
  return buffer;
}

test('1. VAD starts in INACTIVE state', () => {
  const vad = new VoiceActivityDetector();
  assert.equal(vad.state, VADState.INACTIVE);
  assert.equal(vad.isSpeaking, false);
  assert.equal(vad.currentEnergy, 0.0);
});

test('2. RMS calculation computes accurate signal energy', () => {
  const vad = new VoiceActivityDetector();
  
  // Silence (all zeros)
  const silence = new Float32Array(100);
  assert.equal(vad.calculateRMS(silence), 0.0);

  // Constant DC amplitude 0.5 -> RMS = 0.5
  const dc = new Float32Array(100).fill(0.5);
  assert.ok(Math.abs(vad.calculateRMS(dc) - 0.5) < 1e-6);

  // Sine wave amplitude 0.2 -> RMS = 0.2 / sqrt(2) ~ 0.1414
  const sine = generateSineWave(0.2, 512);
  const rms = vad.calculateRMS(sine);
  assert.ok(rms > 0.13 && rms < 0.15);
});

test('3. Continuous silence does not trigger speech or interruption', () => {
  const events = [];
  const vad = new VoiceActivityDetector({
    getAssistantState: () => 'PLAYING',
    getSessionContext: () => ({ sessionId: 'test_silence', activeTurnId: 1 }),
  });
  vad.onEvent((evt) => events.push(evt));
  vad.state = VADState.LISTENING_SILENCE;

  const silence = new Float32Array(256);
  let time = 1000;

  for (let i = 0; i < 20; i++) {
    time += 25;
    const res = vad.processFrame(silence, time);
    assert.equal(res.isSpeaking, false);
    assert.equal(res.interruptionTriggered, false);
  }

  assert.equal(vad.isSpeaking, false);
  const interruptionEvents = events.filter((e) => e.eventType === VADEventType.INTERRUPTION_DETECTED);
  assert.equal(interruptionEvents.length, 0);
});

test('4. Short noise / transient click (< 150ms) does NOT trigger interruption or speech onset', () => {
  const events = [];
  const vad = new VoiceActivityDetector({
    config: { minSpeechDurationMs: 150 },
    getAssistantState: () => 'PLAYING',
    getSessionContext: () => ({ sessionId: 'test_click', activeTurnId: 1 }),
  });
  vad.onEvent((evt) => events.push(evt));
  vad.state = VADState.LISTENING_SILENCE;

  const loudAudio = generateSineWave(0.3, 256); // above threshold
  let time = 1000;

  // Simulate 3 quick loud frames = 75ms (< 150ms minimum speech threshold)
  for (let i = 0; i < 3; i++) {
    time += 25;
    vad.processFrame(loudAudio, time);
  }

  // Followed immediately by silence
  const silence = new Float32Array(256);
  for (let i = 0; i < 5; i++) {
    time += 25;
    vad.processFrame(silence, time);
  }

  assert.equal(vad.isSpeaking, false);
  const interruptionEvents = events.filter((e) => e.eventType === VADEventType.INTERRUPTION_DETECTED);
  const speechEvents = events.filter((e) => e.eventType === VADEventType.SPEECH_STARTED);
  assert.equal(interruptionEvents.length, 0, 'Click must not trigger interruption');
  assert.equal(speechEvents.length, 0, 'Click must not trigger speech onset');
});

test('5. Audio below threshold does not trigger interruption even if sustained', () => {
  const events = [];
  const vad = new VoiceActivityDetector({
    config: { energyThreshold: 0.05, minSpeechDurationMs: 150 },
    getAssistantState: () => 'PLAYING',
  });
  vad.onEvent((evt) => events.push(evt));
  vad.state = VADState.LISTENING_SILENCE;

  const quietAudio = generateSineWave(0.01, 256); // RMS ~ 0.007 < 0.05
  let time = 1000;

  for (let i = 0; i < 15; i++) {
    time += 25;
    vad.processFrame(quietAudio, time);
  }

  assert.equal(vad.isSpeaking, false);
  assert.equal(events.filter((e) => e.eventType === VADEventType.INTERRUPTION_DETECTED).length, 0);
});

test('6. Sustained speech while assistant is PLAYING triggers INTERRUPTION_DETECTED', () => {
  const events = [];
  const vad = new VoiceActivityDetector({
    config: { minSpeechDurationMs: 150 },
    getAssistantState: () => 'PLAYING',
    getSessionContext: () => ({ sessionId: 'sess_playing_int', activeTurnId: 3 }),
  });
  vad.onEvent((evt) => events.push(evt));
  vad.state = VADState.LISTENING_SILENCE;

  const voiceAudio = generateSineWave(0.2, 256); // RMS ~ 0.14 > 0.02
  let time = 1000;

  // Process frames spanning 200ms (> 150ms)
  for (let i = 0; i < 8; i++) {
    time += 25;
    vad.processFrame(voiceAudio, time);
  }

  assert.equal(vad.isSpeaking, true);
  assert.equal(vad.state, VADState.INTERRUPTED);

  const intEvents = events.filter((e) => e.eventType === VADEventType.INTERRUPTION_DETECTED);
  assert.equal(intEvents.length, 1);
  const intEvt = intEvents[0];
  assert.equal(intEvt.sessionId, 'sess_playing_int');
  assert.equal(intEvt.previousTurnId, 3);
  assert.equal(intEvt.newTurnId, 4);
  assert.equal(intEvt.assistantState, 'PLAYING');
  assert.equal(intEvt.detectionSource, 'vad_speech_start');
});

test('7. Sustained speech while assistant is THINKING triggers INTERRUPTION_DETECTED', () => {
  const events = [];
  const vad = new VoiceActivityDetector({
    config: { minSpeechDurationMs: 150 },
    getAssistantState: () => 'THINKING',
    getSessionContext: () => ({ sessionId: 'sess_thinking_int', activeTurnId: 5 }),
  });
  vad.onEvent((evt) => events.push(evt));
  vad.state = VADState.LISTENING_SILENCE;

  const voiceAudio = generateSineWave(0.2, 256);
  let time = 2000;

  for (let i = 0; i < 8; i++) {
    time += 25;
    vad.processFrame(voiceAudio, time);
  }

  assert.equal(vad.isSpeaking, true);
  const intEvents = events.filter((e) => e.eventType === VADEventType.INTERRUPTION_DETECTED);
  assert.equal(intEvents.length, 1);
  assert.equal(intEvents[0].assistantState, 'THINKING');
  assert.equal(intEvents[0].previousTurnId, 5);
  assert.equal(intEvents[0].newTurnId, 6);
});

test('8. Sustained speech while assistant is SYNTHESIZING triggers INTERRUPTION_DETECTED', () => {
  const events = [];
  const vad = new VoiceActivityDetector({
    config: { minSpeechDurationMs: 150 },
    getAssistantState: () => 'SYNTHESIZING',
    getSessionContext: () => ({ sessionId: 'sess_synth_int', activeTurnId: 7 }),
  });
  vad.onEvent((evt) => events.push(evt));
  vad.state = VADState.LISTENING_SILENCE;

  const voiceAudio = generateSineWave(0.2, 256);
  let time = 3000;

  for (let i = 0; i < 8; i++) {
    time += 25;
    vad.processFrame(voiceAudio, time);
  }

  assert.equal(vad.isSpeaking, true);
  const intEvents = events.filter((e) => e.eventType === VADEventType.INTERRUPTION_DETECTED);
  assert.equal(intEvents.length, 1);
  assert.equal(intEvents[0].assistantState, 'SYNTHESIZING');
  assert.equal(intEvents[0].previousTurnId, 7);
  assert.equal(intEvents[0].newTurnId, 8);
});

test('9. Sustained speech while assistant is IDLE triggers SPEECH_STARTED (Normal Utterance)', () => {
  const events = [];
  const vad = new VoiceActivityDetector({
    config: { minSpeechDurationMs: 150 },
    getAssistantState: () => 'IDLE',
    getSessionContext: () => ({ sessionId: 'sess_idle_user', activeTurnId: 1 }),
  });
  vad.onEvent((evt) => events.push(evt));
  vad.state = VADState.LISTENING_SILENCE;

  const voiceAudio = generateSineWave(0.2, 256);
  let time = 4000;

  for (let i = 0; i < 8; i++) {
    time += 25;
    vad.processFrame(voiceAudio, time);
  }

  assert.equal(vad.isSpeaking, true);
  assert.equal(vad.state, VADState.SPEECH_DETECTED);

  const intEvents = events.filter((e) => e.eventType === VADEventType.INTERRUPTION_DETECTED);
  const speechEvents = events.filter((e) => e.eventType === VADEventType.SPEECH_STARTED);
  assert.equal(intEvents.length, 0, 'No interruption when assistant is IDLE');
  assert.equal(speechEvents.length, 1, 'Emits normal speech started event');
  assert.equal(speechEvents[0].turnId, 1);
});

test('10. Rapid repeated speech events are debounced and prevent event spam', () => {
  const events = [];
  const vad = new VoiceActivityDetector({
    config: { minSpeechDurationMs: 50, debounceMs: 400 },
    getAssistantState: () => 'PLAYING',
    getSessionContext: () => ({ sessionId: 'sess_debounce', activeTurnId: 1 }),
  });
  vad.onEvent((evt) => events.push(evt));
  vad.state = VADState.LISTENING_SILENCE;

  const voiceAudio = generateSineWave(0.2, 256);
  let time = 5000;

  // Trigger 1st interruption at time 5075
  for (let i = 0; i < 4; i++) {
    time += 25;
    vad.processFrame(voiceAudio, time);
  }
  assert.equal(events.filter((e) => e.eventType === VADEventType.INTERRUPTION_DETECTED).length, 1);

  // Rapid continuation at time 5150 (within 400ms debounce window)
  vad.isSpeaking = false;
  vad.speechStartTime = null;
  for (let i = 0; i < 4; i++) {
    time += 25;
    vad.processFrame(voiceAudio, time);
  }

  // Must still be 1 interruption because of debounce
  assert.equal(events.filter((e) => e.eventType === VADEventType.INTERRUPTION_DETECTED).length, 1);
});

test('11. Silence duration triggers SPEECH_ENDED correctly', () => {
  const events = [];
  const vad = new VoiceActivityDetector({
    config: { minSpeechDurationMs: 50, silenceDurationMs: 200 },
    getAssistantState: () => 'IDLE',
  });
  vad.onEvent((evt) => events.push(evt));
  vad.state = VADState.LISTENING_SILENCE;

  const voiceAudio = generateSineWave(0.2, 256);
  let time = 6000;

  // Speak for 75ms
  for (let i = 0; i < 3; i++) {
    time += 25;
    vad.processFrame(voiceAudio, time);
  }
  assert.equal(vad.isSpeaking, true);

  // Silence for 225ms (> 200ms silenceDurationMs)
  const silence = new Float32Array(256);
  for (let i = 0; i < 9; i++) {
    time += 25;
    vad.processFrame(silence, time);
  }

  assert.equal(vad.isSpeaking, false);
  const endEvents = events.filter((e) => e.eventType === VADEventType.SPEECH_ENDED);
  assert.equal(endEvents.length, 1);
});

test('12. Lifecycle start, stop, and cleanup transitions work properly', async () => {
  const vad = new VoiceActivityDetector();
  await vad.start();
  assert.equal(vad.state, VADState.LISTENING_SILENCE);

  vad.stop();
  assert.equal(vad.state, VADState.INACTIVE);
  assert.equal(vad.isSpeaking, false);
  assert.equal(vad.analyser, null);
});
