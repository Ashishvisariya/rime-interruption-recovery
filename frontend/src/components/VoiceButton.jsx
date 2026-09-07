import React from 'react';
import { PlaybackState } from '../services/audio.js';

export default function VoiceButton({
  state,
  agentState,
  onAdvanceTurn,
  onProcessText,
  onStop,
  onToggleRecord,
  onBargeIn,
  onToggleVAD,
  isRecording,
  isProcessing,
  isLoading,
  isVADActive,
  activeTurnId,
}) {
  const isPlaying = state === PlaybackState.PLAYING;
  const isAssistantBusy = isPlaying || agentState === 'THINKING' || agentState === 'SYNTHESIZING';

  return (
    <div className="controls-panel glass-card">
      <div className="button-group">
        <button
          id="btn-record-speech"
          className={`btn ${isRecording ? 'btn-danger pulse-recording' : 'btn-accent'}`}
          onClick={onToggleRecord}
          disabled={isLoading || isPlaying || isProcessing}
          title={isRecording ? 'Click to finish recording and invoke Voice Agent' : 'Click to speak to Voice Agent via microphone'}
        >
          <span className="btn-icon">{isRecording ? '🔴' : isProcessing ? '⏳' : '🎤'}</span>
          <span>
            {isRecording
              ? 'Recording... (Click to Finish & Send)'
              : isProcessing
              ? `Agent Processing (${agentState})...`
              : 'Talk to Voice Agent (PTT)'}
          </span>
        </button>

        <button
          id="btn-barge-in"
          className={`btn btn-warning ${isAssistantBusy ? 'pulse-warning' : ''}`}
          onClick={onBargeIn}
          disabled={!isAssistantBusy}
          title="Trigger speech barge-in interruption while assistant is active"
        >
          <span className="btn-icon">⚡</span>
          <span>Barge-In / Interruption</span>
        </button>

        <button
          id="btn-toggle-vad"
          className={`btn ${isVADActive ? 'btn-success' : 'btn-secondary'}`}
          onClick={onToggleVAD}
          title={isVADActive ? 'Continuous VAD active (listening for speech)' : 'Enable Continuous VAD for Hands-Free Barge-In'}
        >
          <span className="btn-icon">{isVADActive ? '🟢' : '⚪'}</span>
          <span>{isVADActive ? 'VAD Active (Listening)' : 'Enable Continuous VAD'}</span>
        </button>

        <button
          id="btn-synthesize-play"
          className="btn btn-primary"
          onClick={onProcessText}
          disabled={isLoading || isPlaying || isRecording || isProcessing}
          title="Send text prompt to LLM and synthesize Rime speech"
        >
          <span className="btn-icon">💬</span>
          <span>{isLoading ? 'Thinking & Synthesizing...' : 'Send Prompt to Voice Agent'}</span>
        </button>

        <button
          id="btn-advance-turn"
          className="btn btn-secondary"
          onClick={onAdvanceTurn}
          disabled={isLoading || isRecording || isProcessing}
          title="Increment active turn sequence. Inactive/superseded older audio is instantly invalidated."
        >
          <span className="btn-icon">⏩</span>
          <span>Advance to Turn #{activeTurnId + 1}</span>
        </button>

        <button
          id="btn-stop-audio"
          className={`btn btn-danger ${isPlaying ? 'pulse-stop' : ''}`}
          onClick={onStop}
          disabled={state === PlaybackState.IDLE && !isPlaying}
          title="Immediately halt active audio and flush buffers"
        >
          <span className="btn-icon">⏹</span>
          <span>Stop Audio</span>
        </button>
      </div>
    </div>
  );
}
