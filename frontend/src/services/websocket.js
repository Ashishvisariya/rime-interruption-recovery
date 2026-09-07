/**
 * Real-Time Voice WebSocket Client
 * 
 * Provides full-duplex bidirectional streaming communication between browser and FastAPI backend:
 * - Session connection & heartbeat
 * - Audio streaming (chunks / frames)
 * - VAD interruption & barge-in event transmission
 * - Server event routing (TURN_STARTED, TRANSCRIPT, THINKING, AUDIO_STARTED, AUDIO_DATA, AUDIO_STOP, TURN_COMPLETED, ERROR)
 * - Clean teardown & zero dangling connections
 * 
 * DataForge 2026 Rime Hackathon - Phase 14
 */

export const WebSocketState = {
  DISCONNECTED: 'DISCONNECTED',
  CONNECTING: 'CONNECTING',
  CONNECTED: 'CONNECTED',
  ERROR: 'ERROR',
};

export const ServerEventType = {
  CONNECT_ACK: 'CONNECT_ACK',
  SPEECH_STARTED: 'SPEECH_STARTED',
  TURN_STARTED: 'TURN_STARTED',
  TRANSCRIPT: 'TRANSCRIPT',
  THINKING: 'THINKING',
  AUDIO_STARTED: 'AUDIO_STARTED',
  AUDIO_DATA: 'AUDIO_DATA',
  AUDIO_CHUNK: 'AUDIO_CHUNK',
  AUDIO_STOP: 'AUDIO_STOP',
  TURN_INTERRUPTED: 'TURN_INTERRUPTED',
  TURN_CANCELLED: 'TURN_CANCELLED',
  TURN_COMPLETED: 'TURN_COMPLETED',
  ERROR: 'ERROR',
};

export class VoiceWebSocketClient {
  constructor(baseUrl = null) {
    this.baseUrl = baseUrl || (typeof window !== 'undefined' ? (window.location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + (window.location.hostname || '127.0.0.1') + ':8000' : 'ws://127.0.0.1:8000');
    this.ws = null;
    this.sessionId = null;
    this.state = WebSocketState.DISCONNECTED;
    this.stateListeners = new Set();
    this.eventListeners = new Set();
    this.errorListeners = new Set();
    this.reconnectTimer = null;
    this.isManualDisconnect = false;
  }

  onStateChange(callback) {
    this.stateListeners.add(callback);
    callback(this.state);
    return () => this.stateListeners.delete(callback);
  }

  onEvent(callback) {
    this.eventListeners.add(callback);
    return () => this.eventListeners.delete(callback);
  }

  onError(callback) {
    this.errorListeners.add(callback);
    return () => this.errorListeners.delete(callback);
  }

  _setState(newState) {
    if (this.state !== newState) {
      this.state = newState;
      this.stateListeners.forEach((cb) => {
        try {
          cb(newState);
        } catch (e) {
          console.error('Error in state listener:', e);
        }
      });
    }
  }

  _notifyEvent(evt) {
    this.eventListeners.forEach((cb) => {
      try {
        cb(evt);
      } catch (e) {
        console.error('Error in event listener:', e);
      }
    });
  }

  _notifyError(err) {
    this.errorListeners.forEach((cb) => {
      try {
        cb(err);
      } catch (e) {
        console.error('Error in error listener:', e);
      }
    });
  }

  connect(sessionId = null) {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.isManualDisconnect = false;
    this._setState(WebSocketState.CONNECTING);
    this.sessionId = sessionId;

    const url = sessionId 
      ? `${this.baseUrl}/api/voice/ws/${sessionId}` 
      : `${this.baseUrl}/api/voice/ws`;

    try {
      this.ws = new WebSocket(url);
      this.ws.binaryType = 'arraybuffer';

      this.ws.onopen = () => {
        this._setState(WebSocketState.CONNECTED);
      };

      this.ws.onmessage = (event) => {
        if (typeof event.data === 'string') {
          try {
            const parsed = JSON.parse(event.data);
            this._notifyEvent(parsed);
          } catch (e) {
            console.error('Failed to parse incoming WebSocket JSON:', e, event.data);
          }
        } else if (event.data instanceof ArrayBuffer) {
          // Binary audio data
          this._notifyEvent({
            event_type: ServerEventType.AUDIO_DATA,
            session_id: this.sessionId,
            binary_data: event.data,
            timestamp_ms: Date.now(),
          });
        }
      };

      this.ws.onerror = (err) => {
        console.warn('WebSocket error:', err);
        this._setState(WebSocketState.ERROR);
        this._notifyError(err);
      };

      this.ws.onclose = (event) => {
        this._setState(WebSocketState.DISCONNECTED);
        this.ws = null;
      };
    } catch (err) {
      this._setState(WebSocketState.ERROR);
      this._notifyError(err);
    }
  }

  disconnect() {
    this.isManualDisconnect = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      try {
        if (this.ws.readyState === WebSocket.OPEN) {
          this.ws.send(JSON.stringify({ event_type: 'DISCONNECT' }));
        }
        this.ws.close();
      } catch (e) {
        // Ignored during close
      }
      this.ws = null;
    }
    this._setState(WebSocketState.DISCONNECTED);
  }

  send(eventType, data = {}, turnId = null) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return false;
    }
    const payload = {
      event_type: eventType,
      session_id: this.sessionId,
      turn_id: turnId,
      timestamp_ms: Date.now(),
      data: data || {},
    };
    try {
      this.ws.send(JSON.stringify(payload));
      return true;
    } catch (e) {
      console.error('Failed to send WebSocket message:', e);
      return false;
    }
  }

  sendBinary(arrayBuffer) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return false;
    }
    try {
      this.ws.send(arrayBuffer);
      return true;
    } catch (e) {
      console.error('Failed to send binary WebSocket message:', e);
      return false;
    }
  }

  sendSpeechStarted(data = {}) {
    return this.send('SPEECH_STARTED', data);
  }

  sendSpeechEnded(data = {}) {
    return this.send('SPEECH_ENDED', data);
  }

  sendAudioChunk(base64Data, format = 'webm') {
    return this.send('AUDIO_CHUNK', { audio_bytes_b64: base64Data, format });
  }

  sendInterruption({ previousTurnId, newTurnId, reason = 'vad_barge_in', detectionSource = 'vad', assistantState = null }) {
    return this.send('INTERRUPTION_DETECTED', {
      previous_turn_id: previousTurnId,
      new_turn_id: newTurnId,
      reason,
      detection_source: detectionSource,
      assistant_state: assistantState,
    }, previousTurnId);
  }

  sendTextPrompt(text, metadata = {}) {
    return this.send('TEXT_PROMPT', { text, ...metadata });
  }
}

export const defaultWebSocketClient = new VoiceWebSocketClient();
