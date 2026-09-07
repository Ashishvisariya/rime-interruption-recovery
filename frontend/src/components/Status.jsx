import React from 'react';
import { PlaybackState } from '../services/audio.js';
import { WebSocketState } from '../services/websocket.js';

export default function Status({
  sessionId,
  activeTurnId,
  previousTurnId,
  previousTurnStatus,
  state,
  agentState,
  wsState,
  metadata,
  backendStatus,
  onReconnect,
}) {
  const getAgentBadgeClass = () => {
    if (agentState === 'INTERRUPTING') return 'badge-interrupting';
    if (agentState === 'LISTENING') return 'badge-recording';
    if (agentState === 'TRANSCRIBING' || agentState === 'THINKING' || agentState === 'SYNTHESIZING') return 'badge-loading';
    if (agentState === 'PLAYING' || state === PlaybackState.PLAYING) return 'badge-playing';
    if (state === PlaybackState.STOPPED) return 'badge-stopped';
    if (state === PlaybackState.ERROR || agentState === 'ERROR') return 'badge-error';
    return 'badge-idle';
  };

  const getWsBadgeClass = () => {
    if (wsState === WebSocketState.CONNECTED) return 'badge-connected';
    if (wsState === WebSocketState.CONNECTING) return 'badge-connecting';
    return 'badge-disconnected';
  };

  const getPreviousTurnBadgeClass = () => {
    if (!previousTurnStatus) return 'badge-idle';
    if (previousTurnStatus === 'INTERRUPTED') return 'badge-interrupting';
    if (previousTurnStatus === 'CANCELLED' || previousTurnStatus === 'SUPERSEDED') return 'badge-stopped';
    if (previousTurnStatus === 'COMPLETED') return 'badge-completed';
    return 'badge-idle';
  };

  return (
    <div className="status-panel glass-card">
      <div className="status-grid">
        <div className="status-item">
          <span className="status-caption">Connection State</span>
          <div className="status-value-row">
            <span className={`status-badge ${getWsBadgeClass()}`}>
              {wsState || 'DISCONNECTED'}
            </span>
            {wsState === WebSocketState.DISCONNECTED && onReconnect && (
              <button
                type="button"
                className="btn-tiny btn-reconnect"
                onClick={onReconnect}
                title="Reconnect WebSocket"
              >
                Reconnect
              </button>
            )}
          </div>
        </div>

        <div className="status-item">
          <span className="status-caption">Voice Agent State</span>
          <span className={`status-badge ${getAgentBadgeClass()}`}>
            {agentState === 'PLAYING' ? 'SPEAKING' : (agentState || state || 'IDLE')}
          </span>
        </div>

        <div className="status-item">
          <span className="status-caption">Authoritative Turn</span>
          <div className="status-value-row">
            <span className="status-value highlight mono">T#{activeTurnId}</span>
            <span className="badge-authoritative">AUTHORITATIVE</span>
          </div>
        </div>

        <div className="status-item">
          <span className="status-caption">Previous Turn Status</span>
          <div className="status-value-row">
            <span className="status-value mono">
              {previousTurnId > 0 ? `T#${previousTurnId}` : 'None'}
            </span>
            {previousTurnId > 0 && (
              <span className={`status-badge ${getPreviousTurnBadgeClass()}`}>
                {previousTurnStatus || 'SUPERSEDED'}
              </span>
            )}
          </div>
        </div>

        <div className="status-item">
          <span className="status-caption">Session ID</span>
          <span className="status-value mono truncate-text" title={sessionId}>
            {sessionId ? sessionId.slice(0, 16) + '...' : 'Initializing...'}
          </span>
        </div>

        <div className="status-item">
          <span className="status-caption">Rime TTS Runtime</span>
          <span className="status-value mono rime-tag">
            coda &bull; {metadata?.speaker || 'celeste'} &bull; mp3
          </span>
        </div>
      </div>
    </div>
  );
}
