/**
 * Backend Voice API Client
 * 
 * Communicates exclusively with the server-side FastAPI backend.
 * Zero credentials or API keys are required or exposed in the client.
 */

const API_BASE_URL = import.meta.env?.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api';

export class VoiceApiClient {
  constructor(baseUrl = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  /**
   * Create or retrieve an isolated voice session.
   * @param {string} [sessionId]
   * @returns {Promise<{ session_id: string, active_turn_id: number, is_active: boolean, turn_count: number }>}
   */
  async createSession(sessionId = null) {
    const payload = sessionId ? { session_id: sessionId } : {};
    const res = await fetch(`${this.baseUrl}/voice/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(errData.error || `Failed to create session (${res.status})`);
    }
    return res.json();
  }

  /**
   * Advance the session to the next monotonic turn ID.
   * @param {string} sessionId 
   * @param {string} [prompt] 
   * @returns {Promise<{ session_id: string, active_turn_id: number, is_active: boolean, turn_count: number }>}
   */
  async createTurn(sessionId, prompt = null) {
    const payload = prompt ? { prompt } : {};
    const res = await fetch(`${this.baseUrl}/voice/session/${encodeURIComponent(sessionId)}/turn`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(errData.error || `Failed to create turn (${res.status})`);
    }
    return res.json();
  }

  /**
   * Request genuine Rime TTS synthesis from the backend for the given turn.
   * @param {Object} params
   * @param {string} params.sessionId
   * @param {number} params.turnId
   * @param {string} params.text
   * @param {string} [params.modelId]
   * @param {string} [params.speaker]
   * @param {string} [params.audioFormat]
   * @param {string} [params.lang]
   * @returns {Promise<{ blob: Blob, headers: Object }>}
   */
  async synthesizeSpeech({ sessionId, turnId, text, modelId, speaker, audioFormat, lang }) {
    const payload = {
      session_id: sessionId,
      turn_id: turnId,
      text,
      model_id: modelId,
      speaker: speaker,
      audio_format: audioFormat,
      lang: lang,
    };

    const res = await fetch(`${this.baseUrl}/voice/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({ error: res.statusText }));
      const error = new Error(errData.error || `TTS synthesis failed with status ${res.status}`);
      error.status = res.status;
      throw error;
    }

    const blob = await res.blob();
    const headers = {
      sessionId: res.headers.get('X-Session-ID'),
      turnId: parseInt(res.headers.get('X-Turn-ID') || String(turnId), 10),
      provider: res.headers.get('X-Provider'),
      modelId: res.headers.get('X-Model-ID'),
      speaker: res.headers.get('X-Speaker'),
      audioFormat: res.headers.get('X-Audio-Format'),
      audioBytesLength: parseInt(res.headers.get('X-Audio-Bytes-Length') || String(blob.size), 10),
    };

    return { blob, headers };
  }

  /**
   * Send speech audio to backend for Groq Whisper transcription.
   * @param {Object} params
   * @param {Blob} params.audioBlob
   * @param {string} [params.sessionId]
   * @param {number} [params.turnId]
   * @param {string} [params.language]
   * @param {string} [params.model]
   * @returns {Promise<{ session_id: string, turn_id: number, text: string, provider: string, model: string, status: string }>}
   */
  async transcribeAudio({ audioBlob, sessionId = null, turnId = null, language = 'en', model = null }) {
    const formData = new FormData();
    const filename = audioBlob.type.includes('mp4') ? 'recording.mp4' : audioBlob.type.includes('ogg') ? 'recording.ogg' : 'recording.webm';
    formData.append('file', audioBlob, filename);

    if (sessionId) formData.append('session_id', sessionId);
    if (turnId !== null && turnId !== undefined) formData.append('turn_id', String(turnId));
    if (language) formData.append('language', language);
    if (model) formData.append('model', model);

    const res = await fetch(`${this.baseUrl}/voice/transcribe`, {
      method: 'POST',
      body: formData,
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({ error: res.statusText }));
      const error = new Error(errData.error || `Audio transcription failed (${res.status})`);
      error.status = res.status;
      throw error;
    }

    return res.json();
  }
}

export const defaultApiClient = new VoiceApiClient();

