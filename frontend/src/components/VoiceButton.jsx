import React from 'react';
import { PlaybackState } from '../services/audio.js';

export default function VoiceButton({
  state,
  onAdvanceTurn,
  onSynthesizeAndPlay,
  onStop,
  onToggleRecord,
  isRecording,
  isTranscribing,
  isLoading,
  activeTurnId,
}) {
  const isPlaying = state === PlaybackState.PLAYING;

  return (
    <div className="controls-panel glass-card">
      <div className="button-group">
        <button
          id="btn-record-speech"
          className={`btn ${isRecording ? 'btn-danger pulse-recording' : 'btn-accent'}`}
          onClick={onToggleRecord}
          disabled={isLoading || isPlaying || isTranscribing}
          title={isRecording ? 'Click to stop recording and transcribe' : 'Click to record your voice via microphone'}
        >
          <span className="btn-icon">{isRecording ? '🔴' : isTranscribing ? '⏳' : '🎤'}</span>
          <span>
            {isRecording
              ? 'Recording... (Click to Finish)'
              : isTranscribing
              ? 'Transcribing Speech...'
              : 'Record Voice (Mic PTT)'}
          </span>
        </button>

        <button
          id="btn-advance-turn"
          className="btn btn-secondary"
          onClick={onAdvanceTurn}
          disabled={isLoading || isRecording || isTranscribing}
          title="Increment active turn sequence. Inactive/superseded older audio is instantly invalidated."
        >
          <span className="btn-icon">⚡</span>
          <span>Advance to Turn #{activeTurnId + 1}</span>
        </button>

        <button
          id="btn-synthesize-play"
          className="btn btn-primary"
          onClick={onSynthesizeAndPlay}
          disabled={isLoading || isPlaying || isRecording || isTranscribing}
          title="Synthesize and play genuine Rime audio for active turn"
        >
          <span className="btn-icon">▶</span>
          <span>{isLoading ? 'Synthesizing...' : 'Synthesize & Play Rime Audio'}</span>
        </button>

        <button
          id="btn-stop-audio"
          className={`btn btn-danger ${isPlaying ? 'pulse-stop' : ''}`}
          onClick={onStop}
          disabled={state === PlaybackState.IDLE && !isPlaying}
          title="Immediately halt active audio and flush buffers (Barge-in simulation)"
        >
          <span className="btn-icon">⏹</span>
          <span>Stop / Interrupt Speech</span>
        </button>
      </div>
    </div>
  );
}
