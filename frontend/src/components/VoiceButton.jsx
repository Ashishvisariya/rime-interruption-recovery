import React from 'react';
import { PlaybackState } from '../services/audio.js';
import { IconMic, IconStop, IconZap, IconSend, IconRefresh } from './Icons.jsx';

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
  isDevMode = false,
  audioDevices = [],
  selectedDeviceId = '',
  onSelectDevice,
  onTestMic,
  isTestingMic = false,
  micLevel = 0,
}) {
  const isPlaying = state === PlaybackState.PLAYING || agentState === 'PLAYING';
  const isAssistantBusy = isPlaying || agentState === 'THINKING' || agentState === 'SYNTHESIZING' || agentState === 'TRANSCRIBING';

  return (
    <div className="controls-panel glass-card">
      {/* Microphone Device Selection & Live Audio Test */}
      <div className="mic-selection-bar">
        <div className="mic-select-left">
          <span className="mic-badge-icon">🎙️</span>
          <label htmlFor="mic-device-select" className="mic-label">Active Mic:</label>
          <select
            id="mic-device-select"
            className="mic-dropdown"
            value={selectedDeviceId}
            onChange={(e) => onSelectDevice && onSelectDevice(e.target.value)}
            disabled={isRecording || isTestingMic}
          >
            <option value="">Default System Microphone</option>
            {audioDevices.map((d, i) => (
              <option key={d.deviceId || i} value={d.deviceId}>
                {d.label || `Microphone ${i + 1}`}
              </option>
            ))}
          </select>
          <button
            type="button"
            className={`btn-tiny ${isTestingMic ? 'btn-danger' : 'btn-preset'}`}
            onClick={onTestMic}
            disabled={isRecording}
            title="Speak to test if your microphone is capturing audio"
          >
            {isTestingMic ? '⏹ Stop Test' : '🔍 Test Mic Level'}
          </button>
        </div>

        {(isRecording || isTestingMic) && (
          <div className="mic-meter-container">
            <span className="mic-meter-tag">{isTestingMic ? 'Live Mic Test:' : 'Mic Input:'}</span>
            <div className="mic-meter-track">
              <div
                className="mic-meter-fill"
                style={{
                  width: `${Math.min(100, Math.round((micLevel || 0) * 350))}%`,
                  backgroundColor: (micLevel || 0) > 0.015 ? '#10b981' : (micLevel || 0) > 0.003 ? '#f59e0b' : '#6b7280',
                }}
              />
            </div>
            <span className="mic-meter-status">
              {(micLevel || 0) > 0.015 ? '🟢 Voice Detected' : (micLevel || 0) > 0.003 ? '🟡 Low Sound' : '⚪ Silent (Check Mic)'}
            </span>
          </div>
        )}
      </div>
      <div className="button-group">
        <button
          id="btn-record-speech"
          className={`btn ${isRecording ? 'btn-danger pulse-recording' : 'btn-accent'}`}
          onClick={onToggleRecord}
          disabled={isLoading || isPlaying || isProcessing}
          title={isRecording ? 'Click to finish recording and invoke Voice Agent' : 'Click to speak to Voice Agent via microphone (Push-to-Talk)'}
        >
          <span className="btn-icon">
            {isRecording ? <IconStop size={16} color="#ef4444" /> : <IconMic size={16} color="#06b6d4" />}
          </span>
          <span>
            {isRecording
              ? 'Recording Voice... (Click to Finish)'
              : isProcessing
              ? `Processing (${agentState})...`
              : 'Talk to Voice Agent (PTT)'}
          </span>
        </button>

        <button
          id="btn-stop-audio"
          className={`btn btn-danger ${isPlaying ? 'pulse-stop' : ''}`}
          onClick={onStop}
          disabled={state === PlaybackState.IDLE && !isPlaying}
          title="Immediately halt active audio and flush buffers"
        >
          <span className="btn-icon"><IconStop size={16} /></span>
          <span>Stop Audio</span>
        </button>

        <button
          id="btn-toggle-vad"
          className={`btn ${isVADActive ? 'btn-success' : 'btn-secondary'}`}
          onClick={onToggleVAD}
          title={isVADActive ? 'Continuous VAD active (hands-free barge-in)' : 'Enable Continuous VAD for Hands-Free Barge-In'}
        >
          <span className="btn-icon"><IconMic size={16} color={isVADActive ? '#10b981' : '#94a3b8'} /></span>
          <span>{isVADActive ? 'VAD Active' : 'Enable Continuous VAD'}</span>
        </button>

        {isDevMode && (
          <>
            <button
              id="btn-barge-in"
              className={`btn btn-warning ${isAssistantBusy ? 'pulse-warning' : ''}`}
              onClick={onBargeIn}
              disabled={!isAssistantBusy}
              title="Trigger speech barge-in interruption while assistant is active"
            >
              <span className="btn-icon"><IconZap size={16} color="#f59e0b" /></span>
              <span>Barge-In / Interrupt</span>
            </button>

            <button
              id="btn-synthesize-play"
              className="btn btn-primary"
              onClick={onProcessText}
              disabled={isLoading || isPlaying || isRecording || isProcessing}
              title="Send prompt to LLM and synthesize Rime speech"
            >
              <span className="btn-icon"><IconSend size={16} /></span>
              <span>Send Prompt</span>
            </button>

            <button
              id="btn-advance-turn"
              className="btn btn-secondary"
              onClick={onAdvanceTurn}
              disabled={isLoading || isRecording || isProcessing}
              title="Advance turn sequence monotonically."
            >
              <span className="btn-icon"><IconRefresh size={16} /></span>
              <span>Advance Turn #{activeTurnId + 1}</span>
            </button>
          </>
        )}
      </div>
    </div>
  );
}

