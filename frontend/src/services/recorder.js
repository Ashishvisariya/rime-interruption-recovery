/**
 * Browser Microphone Recorder Service
 * 
 * Captures user speech audio using native MediaRecorder & getUserMedia APIs.
 * Supports push-to-talk recording with deterministic state transitions.
 * 
 * DataForge 2026 Rime Hackathon - Phase 7
 */

export const RecorderState = {
  IDLE: 'IDLE',
  RECORDING: 'RECORDING',
  PROCESSING: 'PROCESSING',
  TRANSCRIBED: 'TRANSCRIBED',
  ERROR: 'ERROR',
};

export class MicrophoneRecorder {
  constructor() {
    this.state = RecorderState.IDLE;
    this.mediaRecorder = null;
    this.mediaStream = null;
    this.audioChunks = [];
    this.startTime = null;
    this._stateListeners = new Set();
  }

  /**
   * Check if microphone capture is supported in the current environment.
   */
  isSupported() {
    return (
      typeof navigator !== 'undefined' &&
      !!navigator.mediaDevices &&
      !!navigator.mediaDevices.getUserMedia &&
      typeof MediaRecorder !== 'undefined'
    );
  }

  /**
   * Request microphone permission and begin recording audio.
   * @returns {Promise<void>}
   */
  async startRecording() {
    if (!this.isSupported()) {
      this._transitionTo(RecorderState.ERROR);
      throw new Error('Microphone recording is not supported in this browser environment.');
    }

    if (this.state === RecorderState.RECORDING) {
      return;
    }

    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });

      // Detect supported mime type
      let mimeType = 'audio/webm;codecs=opus';
      if (!MediaRecorder.isTypeSupported(mimeType)) {
        mimeType = MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : MediaRecorder.isTypeSupported('audio/mp4')
          ? 'audio/mp4'
          : 'audio/ogg';
      }

      this.audioChunks = [];
      this.mediaRecorder = new MediaRecorder(this.mediaStream, { mimeType });

      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          this.audioChunks.push(event.data);
        }
      };

      this.startTime = Date.now();
      this.mediaRecorder.start(100); // collect in 100ms slices
      this._transitionTo(RecorderState.RECORDING);

    } catch (err) {
      this._transitionTo(RecorderState.ERROR);
      this._cleanupStream();
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        throw new Error('Microphone permission was denied. Please allow microphone access in your browser.');
      }
      throw new Error(`Failed to access microphone: ${err.message}`);
    }
  }

  /**
   * Stop recording and return the recorded audio Blob.
   * @returns {Promise<{ blob: Blob, mimeType: string, durationMs: number }>}
   */
  async stopRecording() {
    if (this.state !== RecorderState.RECORDING || !this.mediaRecorder) {
      return null;
    }

    this._transitionTo(RecorderState.PROCESSING);

    return new Promise((resolve, reject) => {
      this.mediaRecorder.onstop = () => {
        try {
          const mimeType = this.mediaRecorder?.mimeType || 'audio/webm';
          const blob = new Blob(this.audioChunks, { type: mimeType });
          const durationMs = this.startTime ? Date.now() - this.startTime : 0;

          this._cleanupStream();
          this._transitionTo(RecorderState.IDLE);

          resolve({ blob, mimeType, durationMs });
        } catch (err) {
          this._cleanupStream();
          this._transitionTo(RecorderState.ERROR);
          reject(err);
        }
      };

      this.mediaRecorder.onerror = (err) => {
        this._cleanupStream();
        this._transitionTo(RecorderState.ERROR);
        reject(err);
      };

      try {
        this.mediaRecorder.stop();
      } catch (err) {
        this._cleanupStream();
        this._transitionTo(RecorderState.ERROR);
        reject(err);
      }
    });
  }

  /**
   * Cancel recording immediately and discard audio data.
   */
  cancelRecording() {
    if (this.mediaRecorder && this.state === RecorderState.RECORDING) {
      try {
        this.mediaRecorder.stop();
      } catch (e) {
        // ignore on cancel
      }
    }
    this._cleanupStream();
    this.audioChunks = [];
    this._transitionTo(RecorderState.IDLE);
  }

  _cleanupStream() {
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => track.stop());
      this.mediaStream = null;
    }
    this.mediaRecorder = null;
  }

  _transitionTo(nextState) {
    if (this.state === nextState) return;
    const prevState = this.state;
    this.state = nextState;
    for (const listener of this._stateListeners) {
      try {
        listener(this.state, prevState);
      } catch (e) {
        console.error('Recorder state listener error:', e);
      }
    }
  }

  onStateChange(callback) {
    this._stateListeners.add(callback);
    return () => this._stateListeners.delete(callback);
  }
}

export const defaultRecorder = new MicrophoneRecorder();
