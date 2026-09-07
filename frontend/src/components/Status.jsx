import React from 'react';
import { PlaybackState } from '../services/audio.js';

export default function Status({ sessionId, activeTurnId, state, metadata, backendStatus }) {
  const getBadgeClass = (s) => {
    switch (s) {
      case PlaybackState.PLAYING:
        return 'badge-playing';
      case PlaybackState.LOADING:
        return 'badge-loading';
      case PlaybackState.STOPPED:
        return 'badge-stopped';
      case PlaybackState.COMPLETED:
        return 'badge-completed';
      case PlaybackState.ERROR:
        return 'badge-error';
      default:
        return 'badge-idle';
    }
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
          <span className="status-caption">Playback State</span>
          <span className={`status-badge ${getBadgeClass(state)}`}>
            {state}
          </span>
        </div>

        <div className="status-item">
          <span className="status-caption">Primary TTS Engine</span>
          <span className="status-value">
            Rime Labs (<span className="mono">{metadata?.modelId || 'coda'}</span> / <span className="mono">{metadata?.speaker || 'celeste'}</span>)
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
