import React from 'react';
import { WebSocketState } from '../services/websocket.js';
import { PlaybackState } from '../services/audio.js';
import { IconZap, IconMic, IconBrain, IconVolume, IconRefresh, IconAlert, IconBot } from './Icons.jsx';

export default function StatusChips({ agentState, playbackState, wsState, onReconnect }) {
  const getActiveChip = () => {
    if (agentState === 'INTERRUPTING') {
      return { label: 'Interrupted', icon: <IconZap size={14} color="#f59e0b" />, cls: 'chip-interrupted' };
    }
    if (agentState === 'LISTENING') {
      return { label: 'Listening', icon: <IconMic size={14} color="#06b6d4" />, cls: 'chip-listening' };
    }
    if (agentState === 'TRANSCRIBING' || agentState === 'THINKING' || agentState === 'SYNTHESIZING') {
      return { label: 'Processing', icon: <IconBrain size={14} color="#8b5cf6" />, cls: 'chip-processing' };
    }
    if (agentState === 'PLAYING' || playbackState === PlaybackState.PLAYING) {
      return { label: 'Speaking', icon: <IconVolume size={14} color="#10b981" />, cls: 'chip-speaking' };
    }
    if (agentState === 'RECOVERING') {
      return { label: 'Recovering', icon: <IconRefresh size={14} color="#3b82f6" />, cls: 'chip-recovering' };
    }
    if (agentState === 'ERROR' || playbackState === PlaybackState.ERROR) {
      return { label: 'Error', icon: <IconAlert size={14} color="#ef4444" />, cls: 'chip-error' };
    }
    return { label: 'Idle', icon: <IconBot size={14} color="#94a3b8" />, cls: 'chip-idle' };
  };

  const chip = getActiveChip();
  const isConnected = wsState === WebSocketState.CONNECTED;

  return (
    <div className="status-chips-bar">
      <div className="connection-badge-wrap">
        <span className={`status-badge-small ${isConnected ? 'badge-connected' : 'badge-disconnected'}`}>
          <span className="dot-indicator"></span>
          {isConnected ? 'Connected' : 'Disconnected'}
        </span>
        {!isConnected && onReconnect && (
          <button type="button" className="btn-tiny btn-reconnect-small" onClick={onReconnect}>
            Reconnect
          </button>
        )}
      </div>

      <div className={`status-chip ${chip.cls}`}>
        <span className="chip-icon">{chip.icon}</span>
        <span className="chip-label">{chip.label}</span>
      </div>
    </div>
  );
}

