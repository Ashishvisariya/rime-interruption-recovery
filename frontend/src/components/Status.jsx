import React from 'react';
import { PlaybackState } from '../services/audio.js';

export default function Status({ sessionId, activeTurnId, state, agentState, metadata, backendStatus }) {
  const getBadgeClass = () => {
    if (agentState === 'INTERRUPTING') return 'badge-interrupting';
    if (agentState === 'LISTENING') return 'badge-recording';
    if (agentState === 'TRANSCRIBING' || agentState === 'THINKING' || agentState === 'SYNTHESIZING') return 'badge-loading';
    if (state === PlaybackState.PLAYING) return 'badge-playing';
    if (state === PlaybackState.STOPPED) return 'badge-stopped';
    if (state === PlaybackState.ERROR || agentState === 'ERROR') return 'badge-error';
    return 'badge-idle';
  };

  return (
    <div className="status-panel glass-card">
      <div className="status-grid">
        <div className="status-item">
          <span className="status-caption">Session Identity</span>
          <span className="status-value mono">{sessionId || 'Not Initialized'}</span>
        </div>

        <div className="status-item">
          <span className="status-caption">Active Monotonic Turn</span>
          <span className="status-value highlight">#{activeTurnId}</span>
        </div>

        <div className="status-item">
          <span className="status-caption">Agent Pipeline State</span>
          <span className={`status-badge ${getBadgeClass()}`}>
            {agentState || state}
          </span>
        </div>

        <div className="status-item">
          <span className="status-caption">LLM & TTS Stack</span>
          <span className="status-value">
            Groq (<span className="mono">qwen3.6-27b</span>) &bull; Rime (<span className="mono">{metadata?.speaker || 'celeste'}</span>)
          </span>
        </div>

        <div className="status-item">
          <span className="status-caption">Backend Gateway</span>
          <span className="status-value online">
            {backendStatus ? `Online (Phase ${backendStatus.phase})` : 'Connecting...'}
          </span>
        </div>
      </div>
    </div>
  );
}
