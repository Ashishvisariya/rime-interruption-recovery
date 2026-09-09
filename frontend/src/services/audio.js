/**
 * Audio Playback Manager & Finite State Machine
 * 
 * Manages browser-native audio playback for Rime TTS audio payloads with:
 * - Deterministic playback state machine (IDLE, LOADING, READY, PLAYING, STOPPING, STOPPED, COMPLETED, DISCARDED, ERROR)
 * - Monotonic turn association and stale-turn rejection
 * - Immediate stop/flush mechanism for barge-in interruptions
 * - Structured lifecycle event emission
 * 
 * DataForge 2026 Rime Hackathon - Phase 6
 */

export const PlaybackState = {
  IDLE: 'IDLE',
  LOADING: 'LOADING',
  READY: 'READY',
  PLAYING: 'PLAYING',
  STOPPING: 'STOPPING',
  STOPPED: 'STOPPED',
  COMPLETED: 'COMPLETED',
  DISCARDED: 'DISCARDED',
  ERROR: 'ERROR',
};

export const AudioEventType = {
  AUDIO_LOAD_STARTED: 'AUDIO_LOAD_STARTED',
  AUDIO_READY: 'AUDIO_READY',
  AUDIO_PLAY_STARTED: 'AUDIO_PLAY_STARTED',
  AUDIO_PLAY_COMPLETED: 'AUDIO_PLAY_COMPLETED',
  AUDIO_STOP_REQUESTED: 'AUDIO_STOP_REQUESTED',
  AUDIO_STOPPED: 'AUDIO_STOPPED',
  AUDIO_DISCARDED: 'AUDIO_DISCARDED',
  AUDIO_PLAYBACK_ERROR: 'AUDIO_PLAYBACK_ERROR',
};

export class AudioPlaybackManager {
  /**
   * @param {Object} [options]
   * @param {HTMLAudioElement|Object} [options.audioElement] - Optional custom HTMLAudioElement or mock
   */
  constructor(options = {}) {
    this.activeSessionId = null;
    this.activeTurnId = 0;
    this.state = PlaybackState.IDLE;
    this.currentAudio = null;
    this.queue = [];
    this._eventListeners = new Set();
    this._stateListeners = new Set();

    // Browser audio instance
    if (options.audioElement) {
      this.audio = options.audioElement;
      this._bindAudioEvents();
    } else if (typeof Audio !== 'undefined') {
      this.audio = new Audio();
      this._bindAudioEvents();
    } else {
      this.audio = null;
    }
  }

  _bindAudioEvents() {
    if (!this.audio || !this.audio.addEventListener) return;

    this.audio.addEventListener('play', () => {
      // Race protection: Re-verify that currentAudio exists and matches active turn
      if (!this.currentAudio || this.currentAudio.turnId < this.activeTurnId) {
        try {
          this.audio.pause();
          this.audio.currentTime = 0;
          this.audio.removeAttribute('src');
        } catch (e) {}
        return;
      }

      if (this.state === PlaybackState.READY || this.state === PlaybackState.LOADING) {
        this._transitionTo(PlaybackState.PLAYING);
        if (this.currentAudio?.onStart) {
          try {
            this.currentAudio.onStart(this.currentAudio);
          } catch (e) {}
        }
        this._emitEvent(AudioEventType.AUDIO_PLAY_STARTED, {
          sessionId: this.currentAudio?.sessionId,
          turnId: this.currentAudio?.turnId,
          details: { duration: this.audio.duration },
        });
      }
    });

    this.audio.addEventListener('ended', () => {
      if (!this.currentAudio || this.currentAudio.turnId < this.activeTurnId) {
        this.currentAudio = null;
        this._transitionTo(PlaybackState.IDLE);
        return;
      }

      if (this.state === PlaybackState.PLAYING) {
        this._transitionTo(PlaybackState.COMPLETED);
        this._emitEvent(AudioEventType.AUDIO_PLAY_COMPLETED, {
          sessionId: this.currentAudio?.sessionId,
          turnId: this.currentAudio?.turnId,
        });

        // Reset to IDLE and process queue
        this.currentAudio = null;
        this._transitionTo(PlaybackState.IDLE);
        this._processNextInQueue();
      }
    });

    this.audio.addEventListener('error', (e) => {
      if (this.state !== PlaybackState.IDLE && this.state !== PlaybackState.STOPPED) {
        const errorDetail = this.audio?.error ? `MediaError code ${this.audio.error.code}` : 'Audio playback error';
        this._transitionTo(PlaybackState.ERROR);
        this._emitEvent(AudioEventType.AUDIO_PLAYBACK_ERROR, {
          sessionId: this.currentAudio?.sessionId,
          turnId: this.currentAudio?.turnId,
          details: { error: errorDetail },
        });
        this.currentAudio = null;
        this._transitionTo(PlaybackState.IDLE);
      }
    });
  }

  /**
   * Set active conversation session and current turn ID.
   * If switching to a new session, halts existing playback from the previous session.
   * @param {string} sessionId 
   * @param {number} activeTurnId 
   */
  setSession(sessionId, activeTurnId = 0) {
    if (this.activeSessionId && this.activeSessionId !== sessionId) {
      if (this.state === PlaybackState.PLAYING || this.state === PlaybackState.LOADING || this.state === PlaybackState.READY) {
        this.stopCurrentAudio('session_changed');
      }
    }
    this.activeSessionId = sessionId;
    this.setActiveTurn(activeTurnId);
  }

  /**
   * Prime browser media playback during a user gesture so delayed TTS audio
   * is not blocked by autoplay policy after the network request completes.
   */
  primePlayback() {
    if (!this.audio) return;

    const previousSrc = this.audio.src;
    const wasMuted = this.audio.muted;
    this.audio.muted = true;
    this.audio.src = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA=';

    const primePromise = this.audio.play();
    if (primePromise && typeof primePromise.then === 'function') {
      primePromise
        .then(() => {
          this.audio.pause();
          this.audio.currentTime = 0;
          this.audio.src = previousSrc;
          this.audio.muted = wasMuted;
        })
        .catch(() => {
          this.audio.src = previousSrc;
          this.audio.muted = wasMuted;
        });
    } else {
      this.audio.pause();
      this.audio.src = previousSrc;
      this.audio.muted = wasMuted;
    }
  }

  /**
   * Monotonically advance active turn ID.
   * Immediately invalidates and stops any audio associated with older turns.
   * @param {number} turnId 
   */
  setActiveTurn(turnId) {
    const previousTurnId = this.activeTurnId;
    this.activeTurnId = turnId;

    // Invariant: If a newer turn arrives, older playing or queued audio is obsolete.
    if (this.currentAudio && this.currentAudio.turnId < turnId) {
      const obsoleteAudio = this.currentAudio;
      this.stopCurrentAudio('turn_superseded');
      this._emitEvent(AudioEventType.AUDIO_DISCARDED, {
        sessionId: obsoleteAudio.sessionId,
        turnId: obsoleteAudio.turnId,
        details: { reason: `Superseded by turn ${turnId} (was turn ${obsoleteAudio.turnId})` },
      });
    }

    // Purge any obsolete items from the queue
    this.clearObsoleteQueuedAudio();
  }

  /**
   * Discard all queued items strictly older than the active turn ID.
   */
  clearObsoleteQueuedAudio() {
    const validQueue = [];
    for (const item of this.queue) {
      if (item.turnId < this.activeTurnId || (this.activeSessionId && item.sessionId !== this.activeSessionId)) {
        if (item._createdBlobUrl && typeof URL !== 'undefined' && URL.revokeObjectURL) {
          try {
            URL.revokeObjectURL(item._createdBlobUrl);
          } catch (e) {}
        }
        this._emitEvent(AudioEventType.AUDIO_DISCARDED, {
          sessionId: item.sessionId,
          turnId: item.turnId,
          details: { reason: 'Queued item superseded before playback' },
        });
      } else {
        validQueue.push(item);
      }
    }
    this.queue = validQueue;
  }

  /**
   * Clear all pending items in the playback queue.
   */
  clearQueue() {
    for (const item of this.queue) {
      if (item._createdBlobUrl && typeof URL !== 'undefined' && URL.revokeObjectURL) {
        try {
          URL.revokeObjectURL(item._createdBlobUrl);
        } catch (e) {}
      }
      this._emitEvent(AudioEventType.AUDIO_DISCARDED, {
        sessionId: item.sessionId,
        turnId: item.turnId,
        details: { reason: 'Queue cleared' },
      });
    }
    this.queue = [];
  }

  /**
   * Enqueue an audio item for playback.
   * If the turn is already stale, discards immediately.
   * @param {Object} item
   * @param {string} item.sessionId
   * @param {number} item.turnId
   * @param {Blob|string} item.audioSource - Audio Blob or Object URL
   * @param {Object} [item.metadata]
   */
  enqueueAudio(item) {
    // 1. Stale-turn protection
    if (item.turnId < this.activeTurnId || (this.activeSessionId && item.sessionId !== this.activeSessionId)) {
      this._emitEvent(AudioEventType.AUDIO_DISCARDED, {
        sessionId: item.sessionId,
        turnId: item.turnId,
        details: { reason: `Rejected stale audio (turn ${item.turnId} < active ${this.activeTurnId})` },
      });
      return false;
    }

    // 2. Add to queue and trigger if idle
    this.queue.push(item);
    if (this.state === PlaybackState.IDLE) {
      this._processNextInQueue();
    }
    return true;
  }

  /**
   * Enqueue or immediately play a streaming audio chunk for an active turn.
   * Discards stale chunks immediately if turnId < activeTurnId.
   * @param {number} turnId
   * @param {string|Blob} audioChunk - Base64 string, Blob, or Object URL
   * @param {Object} [metadata]
   * @param {Function} [onStart] - Optional callback fired when audio chunk physically starts playing
   * @returns {boolean}
   */
  queueAudioChunk(turnId, audioChunk, metadata = {}, onStart = null) {
    if (turnId < this.activeTurnId) {
      this._emitEvent(AudioEventType.AUDIO_DISCARDED, {
        sessionId: this.activeSessionId,
        turnId,
        details: { reason: `Rejected stale audio chunk (turn ${turnId} < active ${this.activeTurnId})` },
      });
      return false;
    }

    let audioSource = audioChunk;
    if (typeof audioChunk === 'string' && !audioChunk.startsWith('blob:') && !audioChunk.startsWith('http') && !audioChunk.startsWith('data:')) {
      try {
        const binary = atob(audioChunk);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        const format = metadata.format || 'mp3';
        const mime = format === 'mp3' ? 'audio/mpeg' : `audio/${format}`;
        audioSource = new Blob([bytes], { type: mime });
      } catch (e) {
        console.error('Failed to convert base64 audio chunk to blob:', e);
        return false;
      }
    }

    const item = {
      sessionId: this.activeSessionId,
      turnId,
      audioSource,
      metadata,
      onStart,
      chunkIndex: metadata.chunk_index !== undefined ? metadata.chunk_index : (metadata.chunkIndex || 0),
      isFinal: metadata.is_final !== undefined ? metadata.is_final : false,
    };

    if (this.state === PlaybackState.IDLE) {
      this.playAudio(item);
      return true;
    }

    if (this.currentAudio && this.currentAudio.turnId === turnId) {
      this.queue.push(item);
      return true;
    }

    if (this.currentAudio && this.currentAudio.turnId < turnId) {
      this.stopCurrentAudio('turn_superseded');
      this.playAudio(item);
      return true;
    }

    this.queue.push(item);
    return true;
  }

  /**
   * Immediately play or schedule an audio item.
   * @param {Object} item
   * @returns {Promise<boolean>}
   */
  async playAudio(item) {
    // 1. Stale-turn check
    if (item.turnId < this.activeTurnId || (this.activeSessionId && item.sessionId !== this.activeSessionId)) {
      this._emitEvent(AudioEventType.AUDIO_DISCARDED, {
        sessionId: item.sessionId,
        turnId: item.turnId,
        details: { reason: `Audio turn ${item.turnId} is stale (active turn is ${this.activeTurnId})` },
      });
      return false;
    }

    // Stop existing audio if playing
    if (this.state === PlaybackState.PLAYING || this.state === PlaybackState.LOADING) {
      this.stopCurrentAudio('superseded_by_new_playback');
    }

    this.currentAudio = item;
    this._transitionTo(PlaybackState.LOADING);
    this._emitEvent(AudioEventType.AUDIO_LOAD_STARTED, {
      sessionId: item.sessionId,
      turnId: item.turnId,
      details: item.metadata || {},
    });

    try {
      let srcUrl = '';
      if (typeof item.audioSource === 'string') {
        srcUrl = item.audioSource;
      } else if (item.audioSource instanceof Blob) {
        srcUrl = URL.createObjectURL(item.audioSource);
        item._createdBlobUrl = srcUrl;
      }

      // Pre-play turn validation (re-check in case turn advanced during prep)
      if (item.turnId < this.activeTurnId) {
        this._transitionTo(PlaybackState.DISCARDED);
        this._emitEvent(AudioEventType.AUDIO_DISCARDED, {
          sessionId: item.sessionId,
          turnId: item.turnId,
          details: { reason: 'Turn advanced while preparing audio source' },
        });
        this.currentAudio = null;
        this._transitionTo(PlaybackState.IDLE);
        return false;
      }

      if (this.audio) {
        this.audio.src = srcUrl;
        this._transitionTo(PlaybackState.READY);
        this._emitEvent(AudioEventType.AUDIO_READY, {
          sessionId: item.sessionId,
          turnId: item.turnId,
        });

        // Trigger native play
        const playPromise = this.audio.play();
        if (playPromise !== undefined) {
          await playPromise;
        }

        // Post-play promise turn and state re-validation
        if (item.turnId < this.activeTurnId || this.state === PlaybackState.STOPPED || this.state === PlaybackState.STOPPING || this.state === PlaybackState.IDLE || this.currentAudio !== item) {
          try {
            this.audio.pause();
            this.audio.currentTime = 0;
            this.audio.removeAttribute('src');
          } catch (e) {}
          return false;
        }

        if (this.state === PlaybackState.READY) {
          this._transitionTo(PlaybackState.PLAYING);
          this._emitEvent(AudioEventType.AUDIO_PLAY_STARTED, {
            sessionId: item.sessionId,
            turnId: item.turnId,
            details: { duration: this.audio.duration },
          });
        }
      } else {
        // Mock / headless environment fallback
        this._transitionTo(PlaybackState.READY);
        this._emitEvent(AudioEventType.AUDIO_READY, {
          sessionId: item.sessionId,
          turnId: item.turnId,
        });
        this._transitionTo(PlaybackState.PLAYING);
        if (item.onStart) {
          try { item.onStart(item); } catch (e) {}
        }
        this._emitEvent(AudioEventType.AUDIO_PLAY_STARTED, {
          sessionId: item.sessionId,
          turnId: item.turnId,
        });
      }
      return true;

    } catch (err) {
      if (this.state !== PlaybackState.STOPPED && this.state !== PlaybackState.STOPPING) {
        this._transitionTo(PlaybackState.ERROR);
        this._emitEvent(AudioEventType.AUDIO_PLAYBACK_ERROR, {
          sessionId: item.sessionId,
          turnId: item.turnId,
          details: { error: err?.message || String(err) },
        });
        this.currentAudio = null;
        this._transitionTo(PlaybackState.IDLE);
      }
      return false;
    }
  }

  /**
   * Immediately stops active audio playback, flushes buffers, and clears queue.
   * Safe and idempotent.
   * @param {string} [reason='manual_stop']
   */
  stopCurrentAudio(reason = 'manual_stop') {
    const hadActiveAudio = this.state === PlaybackState.PLAYING || this.state === PlaybackState.LOADING || this.state === PlaybackState.READY;
    const stoppingItem = this.currentAudio;

    this._emitEvent(AudioEventType.AUDIO_STOP_REQUESTED, {
      sessionId: stoppingItem?.sessionId || this.activeSessionId,
      turnId: stoppingItem?.turnId || this.activeTurnId,
      details: { reason },
    });

    if (this.audio) {
      try {
        this.audio.pause();
        this.audio.currentTime = 0;
        if (this.currentAudio?._createdBlobUrl) {
          URL.revokeObjectURL(this.currentAudio._createdBlobUrl);
        }
        this.audio.removeAttribute('src');
        if (this.audio.load) {
          this.audio.load();
        }
      } catch (e) {
        // Ignore audio cleanup errors on pause
      }
    }

    this._transitionTo(PlaybackState.STOPPING);
    this._transitionTo(PlaybackState.STOPPED);

    this._emitEvent(AudioEventType.AUDIO_STOPPED, {
      sessionId: stoppingItem?.sessionId || this.activeSessionId,
      turnId: stoppingItem?.turnId || this.activeTurnId,
      details: { reason, wasPlaying: hadActiveAudio },
    });

    // Clear active audio and reset to IDLE
    this.currentAudio = null;
    this.clearQueue();
    this._transitionTo(PlaybackState.IDLE);
  }

  /**
   * Process next queued item if available and valid.
   */
  _processNextInQueue() {
    this.clearObsoleteQueuedAudio();
    if (this.queue.length > 0) {
      const next = this.queue.shift();
      this.playAudio(next);
    }
  }

  /**
   * Internal state transition helper.
   * @param {string} nextState 
   */
  _transitionTo(nextState) {
    if (this.state === nextState) return;
    const prevState = this.state;
    this.state = nextState;
    for (const listener of this._stateListeners) {
      try {
        listener(this.state, prevState, this.currentAudio);
      } catch (e) {
        console.error('State listener error:', e);
      }
    }
  }

  /**
   * Internal structured event dispatcher.
   * @param {string} eventType 
   * @param {Object} payload 
   */
  _emitEvent(eventType, payload = {}) {
    const event = {
      event_type: eventType,
      timestamp_ms: Date.now(),
      session_id: payload.sessionId || this.activeSessionId || 'none',
      turn_id: payload.turnId !== undefined ? payload.turnId : this.activeTurnId,
      state: this.state,
      details: payload.details || {},
    };

    for (const listener of this._eventListeners) {
      try {
        listener(event);
      } catch (e) {
        console.error('Event listener error:', e);
      }
    }
  }

  /**
   * Subscribe to all playback lifecycle events.
   * @param {Function} callback 
   * @returns {Function} Unsubscribe function
   */
  onEvent(callback) {
    this._eventListeners.add(callback);
    return () => this._eventListeners.delete(callback);
  }

  /**
   * Subscribe to state machine transitions.
   * @param {Function} callback 
   * @returns {Function} Unsubscribe function
   */
  onStateChange(callback) {
    this._stateListeners.add(callback);
    return () => this._stateListeners.delete(callback);
  }

  /**
   * Retrieve current playback snapshot.
   */
  getPlaybackState() {
    return {
      state: this.state,
      activeSessionId: this.activeSessionId,
      activeTurnId: this.activeTurnId,
      currentAudio: this.currentAudio ? {
        sessionId: this.currentAudio.sessionId,
        turnId: this.currentAudio.turnId,
        metadata: this.currentAudio.metadata || {},
      } : null,
      queueLength: this.queue.length,
    };
  }

  /**
   * Returns true if audio is actively playing or queued to play.
   * Directly queries the underlying HTMLAudioElement and internal queue for zero-latency detection.
   * @returns {boolean}
   */
  isPlaying() {
    const isPlayingState = this.state === PlaybackState.PLAYING || this.state === PlaybackState.LOADING || this.state === PlaybackState.READY;
    const hasActiveAudio = Boolean(this.audio && !this.audio.paused && !this.audio.ended && this.audio.currentTime > 0);
    const hasQueue = this.queue.length > 0;
    return isPlayingState || hasActiveAudio || hasQueue;
  }
}

// Global default playback manager instance
export const defaultPlaybackManager = new AudioPlaybackManager();
