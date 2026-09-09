/**
 * Voice Activity Detection (VAD) & Real-Time Interruption Detector Service
 * 
 * Provides browser-native audio energy analysis, sustained speech onset detection,
 * debounce against acoustic transients (clicks, keystrokes), and assistant-aware
 * barge-in / interruption triggering.
 * 
 * DataForge 2026 Rime Hackathon - Phase 11
 */

export const VADState = {
  INACTIVE: 'INACTIVE',
  LISTENING_SILENCE: 'LISTENING_SILENCE',
  SPEECH_DETECTED: 'SPEECH_DETECTED',
  INTERRUPTED: 'INTERRUPTED',
  ERROR: 'ERROR',
};

export const VADEventType = {
  VAD_STARTED: 'VAD_STARTED',
  VAD_STOPPED: 'VAD_STOPPED',
  SPEECH_STARTED: 'SPEECH_STARTED',
  SPEECH_ENDED: 'SPEECH_ENDED',
  INTERRUPTION_DETECTED: 'INTERRUPTION_DETECTED',
  ENERGY_UPDATED: 'ENERGY_UPDATED',
};

export const DEFAULT_VAD_CONFIG = {
  // RMS energy threshold for speech onset (0.0 to 1.0)
  // 0.022 ignores room floor, fan hum, and distant background noise
  energyThreshold: 0.022,

  // Higher RMS energy threshold while assistant is playing audio
  // to prevent speaker bleed/echo from triggering the microphone
  playbackEnergyThreshold: 0.032,

  // Minimum duration of continuous speech above threshold before triggering speech onset (ms)
  // 350ms ignores short clicks, keyboard clatter, throat clearing, and noise bursts
  minSpeechDurationMs: 350,

  // Snappy continuous speech duration for barge-in while AI is speaking (ms)
  bargeInSpeechDurationMs: 180,

  // Duration of continuous silence below threshold before declaring speech ended (ms)
  // 800ms provides natural pause tolerance without premature auto-submitting
  silenceDurationMs: 800,

  // Minimum interval between successive interruption events to prevent event spam (ms)
  debounceMs: 400,

  // Analysis frame interval for polling/processing in milliseconds
  analysisIntervalMs: 25,
};

export class VoiceActivityDetector {
  /**
   * @param {Object} [options]
   * @param {Object} [options.config] - Custom VAD configuration overrides
   * @param {Function} [options.getAssistantState] - Callback returning current assistant state ('PLAYING', 'THINKING', 'SYNTHESIZING', 'IDLE')
   * @param {Function} [options.getSessionContext] - Callback returning { sessionId, activeTurnId }
   * @param {Function} [options.isAudioPlaying] - Callback returning boolean whether audio is actively playing or queued
   * @param {Function} [options.onBargeIn] - Immediate synchronous callback when barge-in is triggered
   * @param {Function} [options.onSpeechOnset] - Callback fired at first speech onset frame
   * @param {Function} [options.onSpeechCancel] - Callback fired if speech onset was not sustained
   */
  constructor(options = {}) {
    this.config = { ...DEFAULT_VAD_CONFIG, ...(options.config || {}) };
    this.getAssistantState = options.getAssistantState || (() => 'IDLE');
    this.getSessionContext = options.getSessionContext || (() => ({ sessionId: 'default', activeTurnId: 0 }));
    this.isAudioPlaying = options.isAudioPlaying || (() => false);
    this.onBargeIn = options.onBargeIn || null;
    this.onSpeechOnset = options.onSpeechOnset || null;
    this.onSpeechCancel = options.onSpeechCancel || null;

    this.state = VADState.INACTIVE;
    this.isSpeaking = false;
    this.speechStartTime = null;
    this.silenceStartTime = null;
    this.lastInterruptionTime = null;
    this.currentEnergy = 0.0;

    this.audioContext = null;
    this.mediaStream = null;
    this.analyser = null;
    this.sourceNode = null;
    this._intervalId = null;

    this._eventListeners = new Set();
    this._stateListeners = new Set();
  }

  /**
   * Compute Root Mean Square (RMS) energy from audio sample buffer.
   * @param {Float32Array|Array<number>} samples 
   * @returns {number} RMS energy value (0.0 to 1.0)
   */
  calculateRMS(samples) {
    if (!samples || samples.length === 0) return 0.0;
    let sumSquares = 0.0;
    for (let i = 0; i < samples.length; i++) {
      const val = samples[i];
      sumSquares += val * val;
    }
    return Math.sqrt(sumSquares / samples.length);
  }

  /**
   * Process a discrete frame of audio samples or pre-calculated RMS energy.
   * Deterministic core method used by both live Web Audio loop and unit test suites.
   * 
   * @param {Float32Array|Array<number>|number} input - Audio samples or direct RMS energy value
   * @param {number} [currentTimeMs] - Optional explicit timestamp for deterministic testing
   * @returns {Object} Frame processing result
   */
  processFrame(input, currentTimeMs = Date.now()) {
    if (this.state === VADState.INACTIVE) {
      return { energy: 0.0, isSpeaking: false, interruptionTriggered: false };
    }

    const energy = typeof input === 'number' ? input : this.calculateRMS(input);
    this.currentEnergy = energy;

    this._emitEvent(VADEventType.ENERGY_UPDATED, {
      energy,
      timestamp: currentTimeMs,
    });

    const isAudioPlaying = typeof this.isAudioPlaying === 'function' ? this.isAudioPlaying() : false;
    const assistantState = this.getAssistantState();
    const sessionCtx = this.getSessionContext();
    const isAssistantActive = isAudioPlaying || ['PLAYING', 'THINKING', 'SYNTHESIZING'].includes(assistantState);

    // Audio-aware threshold: if AI is speaking, use playback threshold to prevent self-trigger from speaker echo
    const effectiveThreshold = isAudioPlaying
      ? (this.config.playbackEnergyThreshold || 0.032)
      : this.config.energyThreshold;

    const isAboveThreshold = energy >= effectiveThreshold;
    let interruptionTriggered = false;

    if (isAboveThreshold) {
      // Audio energy is above threshold
      this.silenceStartTime = null;

      if (!this.isSpeaking) {
        if (this.speechStartTime === null) {
          this.speechStartTime = currentTimeMs;
          if (typeof this.onSpeechOnset === 'function') {
            try { this.onSpeechOnset(); } catch (e) {}
          }
        } else {
          const speechDuration = currentTimeMs - this.speechStartTime;
          const requiredDuration = isAssistantActive
            ? Math.min(180, this.config.minSpeechDurationMs)
            : this.config.minSpeechDurationMs;

          if (speechDuration >= requiredDuration) {
            // Sustained speech confirmed!
            this.isSpeaking = true;
            this._transitionTo(VADState.SPEECH_DETECTED);
            console.log('[VAD] speech_detected', { rms: energy.toFixed(4), timestamp: currentTimeMs, speechDuration, isAssistantActive });

            const isDebounced = this.lastInterruptionTime &&
              (currentTimeMs - this.lastInterruptionTime < this.config.debounceMs);

            if (isAssistantActive && !isDebounced) {
              // Trigger barge-in interruption immediately!
              this.lastInterruptionTime = currentTimeMs;
              interruptionTriggered = true;
              this._transitionTo(VADState.INTERRUPTED);

              // BARGE-IN AT VAD/AUDIO LEVEL FIRST: Stop playback synchronously before anything else
              if (typeof this.onBargeIn === 'function') {
                try {
                  this.onBargeIn({
                    sessionId: sessionCtx.sessionId,
                    previousTurnId: sessionCtx.activeTurnId,
                    newTurnId: (sessionCtx.activeTurnId || 0) + 1,
                  });
                } catch (e) {
                  console.error('[VAD] onBargeIn callback error:', e);
                }
              }

              this._emitEvent(VADEventType.INTERRUPTION_DETECTED, {
                sessionId: sessionCtx.sessionId,
                previousTurnId: sessionCtx.activeTurnId,
                newTurnId: (sessionCtx.activeTurnId || 0) + 1,
                timestamp: currentTimeMs,
                detectionSource: 'vad_speech_start',
                assistantState: isAudioPlaying ? 'PLAYING' : assistantState,
                energy: energy,
                speechDurationMs: speechDuration,
              });
            } else if (!isAssistantActive) {
              // Normal speech start
              this._emitEvent(VADEventType.SPEECH_STARTED, {
                sessionId: sessionCtx.sessionId,
                turnId: sessionCtx.activeTurnId,
                timestamp: currentTimeMs,
                detectionSource: 'vad_speech_start',
                assistantState: assistantState,
                energy: energy,
              });
            }
          }
        }
      }
    } else {
      // Audio energy is below threshold
      if (!this.isSpeaking && this.speechStartTime !== null) {
        if (typeof this.onSpeechCancel === 'function') {
          try { this.onSpeechCancel(); } catch (e) {}
        }
      }
      this.speechStartTime = null;

      if (this.isSpeaking) {
        if (this.silenceStartTime === null) {
          this.silenceStartTime = currentTimeMs;
        } else {
          const silenceDuration = currentTimeMs - this.silenceStartTime;
          if (silenceDuration >= this.config.silenceDurationMs) {
            // Speech ended
            this.isSpeaking = false;
            this.silenceStartTime = null;
            this._transitionTo(VADState.LISTENING_SILENCE);

            const sessionCtx = this.getSessionContext();
            this._emitEvent(VADEventType.SPEECH_ENDED, {
              sessionId: sessionCtx.sessionId,
              turnId: sessionCtx.activeTurnId,
              timestamp: currentTimeMs,
              silenceDurationMs: silenceDuration,
            });
          }
        }
      }
    }

    return {
      energy,
      isSpeaking: this.isSpeaking,
      interruptionTriggered,
      state: this.state,
    };
  }

  /**
   * Start live microphone capture and real-time VAD analysis.
   * @returns {Promise<void>}
   */
  async start() {
    if (this.state !== VADState.INACTIVE) {
      return;
    }

    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      // Headless/test fallback mode
      this._transitionTo(VADState.LISTENING_SILENCE);
      this._emitEvent(VADEventType.VAD_STARTED, { timestamp: Date.now(), mode: 'simulated' });
      return;
    }

    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: { ideal: true },
          noiseSuppression: { ideal: true },
          autoGainControl: { ideal: true },
        },
      });

      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      this.audioContext = new AudioCtx();
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = 512;
      this.analyser.smoothingTimeConstant = 0.2;

      this.sourceNode = this.audioContext.createMediaStreamSource(this.mediaStream);
      this.sourceNode.connect(this.analyser);

      const bufferLength = this.analyser.fftSize;
      const dataArray = new Float32Array(bufferLength);

      this._transitionTo(VADState.LISTENING_SILENCE);
      this._emitEvent(VADEventType.VAD_STARTED, { timestamp: Date.now(), mode: 'live' });

      // Run periodic analysis loop
      this._intervalId = setInterval(() => {
        if (this.state === VADState.INACTIVE || !this.analyser) return;
        this.analyser.getFloatTimeDomainData(dataArray);
        this.processFrame(dataArray, Date.now());
      }, this.config.analysisIntervalMs);

    } catch (err) {
      this.stop();
      this._transitionTo(VADState.ERROR);
      throw new Error(`Failed to initialize VAD: ${err.message}`);
    }
  }

  /**
   * Get the active media stream if VAD is running.
   * @returns {MediaStream|null}
   */
  getMediaStream() {
    return this.mediaStream;
  }

  /**
   * Stop VAD listening and clean up all audio streams and nodes.
   */
  stop() {
    if (this._intervalId) {
      clearInterval(this._intervalId);
      this._intervalId = null;
    }

    if (this.sourceNode) {
      try {
        this.sourceNode.disconnect();
      } catch (e) {
        // ignore
      }
      this.sourceNode = null;
    }

    if (this.audioContext) {
      try {
        this.audioContext.close();
      } catch (e) {
        // ignore
      }
      this.audioContext = null;
    }

    if (this.mediaStream) {
      try {
        this.mediaStream.getTracks().forEach((track) => track.stop());
      } catch (e) {
        // ignore
      }
      this.mediaStream = null;
    }

    this.analyser = null;
    this.isSpeaking = false;
    this.speechStartTime = null;
    this.silenceStartTime = null;
    this.currentEnergy = 0.0;

    const prevState = this.state;
    this._transitionTo(VADState.INACTIVE);
    if (prevState !== VADState.INACTIVE) {
      this._emitEvent(VADEventType.VAD_STOPPED, { timestamp: Date.now() });
    }
  }

  /**
   * Reset internal detection state (e.g. after turn transition).
   */
  resetState() {
    this.isSpeaking = false;
    this.speechStartTime = null;
    this.silenceStartTime = null;
    if (this.state !== VADState.INACTIVE && this.state !== VADState.ERROR) {
      this._transitionTo(VADState.LISTENING_SILENCE);
    }
  }

  _transitionTo(nextState) {
    if (this.state === nextState) return;
    const prevState = this.state;
    this.state = nextState;
    for (const listener of this._stateListeners) {
      try {
        listener(this.state, prevState);
      } catch (e) {
        console.error('VAD state listener error:', e);
      }
    }
  }

  _emitEvent(eventType, payload) {
    const event = {
      eventType,
      ...payload,
    };
    for (const listener of this._eventListeners) {
      try {
        listener(event);
      } catch (e) {
        console.error('VAD event listener error:', e);
      }
    }
  }

  onEvent(callback) {
    this._eventListeners.add(callback);
    return () => this._eventListeners.delete(callback);
  }

  onStateChange(callback) {
    this._stateListeners.add(callback);
    return () => this._stateListeners.delete(callback);
  }
}

export const defaultVAD = new VoiceActivityDetector();
