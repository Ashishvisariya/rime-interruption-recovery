import React from 'react';
import { PlaybackState } from '../services/audio.js';

export default function SpeakingIndicator({ state, currentAudio }) {
  const isPlaying = state === PlaybackState.PLAYING;
  const isLoading = state === PlaybackState.LOADING;
  const isStopped = state === PlaybackState.STOPPED;

  return (
    <div className={`speaking-visualizer ${isPlaying ? 'active' : ''} ${isLoading ? 'loading' : ''}`}>
      <div className="visualizer-orb">
        <div className="wave-ring ring-1"></div>
        <div className="wave-ring ring-2"></div>
        <div className="wave-ring ring-3"></div>
        <div className="orb-core">
          {isLoading ? (
            <span className="orb-icon spin">⏳</span>
          ) : isPlaying ? (
            <span className="orb-icon pulse">🔊</span>
          ) : isStopped ? (
            <span className="orb-icon">⏹</span>
          ) : (
            <span className="orb-icon">🎙️</span>
          )}
        </div>
      </div>

      <div className="waveform-bars">
        {[40, 70, 95, 60, 85, 100, 75, 90, 50, 65, 80, 45].map((height, idx) => (
          <span
            key={idx}
            className="bar"
            style={{
              height: isPlaying ? `${height}%` : '15%',
              animationDelay: `${idx * 0.08}s`,
            }}
          />
        ))}
      </div>

      <div className="speaking-status-text">
        {isLoading && <span className="status-label loading">Synthesizing & Buffering Rime Audio...</span>}
        {isPlaying && (
          <span className="status-label playing">
            Speaking Turn #{currentAudio?.turnId} via Rime ({currentAudio?.metadata?.speaker || 'celeste'})
          </span>
        )}
        {isStopped && <span className="status-label stopped">Speech Halted (Immediate Stop / Interruption)</span>}
        {state === PlaybackState.IDLE && <span className="status-label idle">Audio Pipeline Ready</span>}
        {state === PlaybackState.ERROR && <span className="status-label error">Playback Error</span>}
      </div>
    </div>
  );
}
