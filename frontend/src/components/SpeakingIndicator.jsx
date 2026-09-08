import React from 'react';
import { PlaybackState } from '../services/audio.js';

export default function SpeakingIndicator({ state, agentState, currentAudio, interruptionInfo, errorMessage, micLevel = 0 }) {
  const isPlaying = state === PlaybackState.PLAYING || agentState === 'PLAYING';
  const isLoading = state === PlaybackState.LOADING || agentState === 'SYNTHESIZING';
  const isThinking = agentState === 'THINKING';
  const isTranscribing = agentState === 'TRANSCRIBING';
  const isListening = agentState === 'LISTENING';
  const isInterrupting = agentState === 'INTERRUPTING';
  const isStopped = state === PlaybackState.STOPPED;

  const dynamicScale = Math.min(1.0, Math.max(0.18, (micLevel || 0) * 10));

  const getOrbIcon = () => {
    if (isInterrupting) return '⚡';
    if (isListening) return '🎙️';
    if (isTranscribing) return '📝';
    if (isThinking) return '🧠';
    if (isLoading) return '⚡';
    if (isPlaying) return '🔊';
    if (isStopped) return '⏹';
    if (agentState === 'ERROR' || state === PlaybackState.ERROR) return '⚠️';
    return '🤖';
  };

  const getStatusLabel = () => {
    if (isInterrupting) {
      return {
        text: `Barge-In Interruption Detected! Turn #${interruptionInfo?.previousTurnId || ''} speech halted promptly (${interruptionInfo?.stopLatencyMs?.toFixed(2) || '< 0.2'} ms).`,
        cls: 'interrupting',
      };
    }
    if (isListening) {
      const isVoiceActive = micLevel > 0.015;
      return {
        text: isVoiceActive
          ? 'Listening... (Voice detected, speak freely)'
          : 'Listening... (Speak into your microphone)',
        cls: 'recording',
      };
    }
    if (isTranscribing) return { text: 'Transcribing speech via Groq Whisper (whisper-large-v3)...', cls: 'loading' };
    if (isThinking) return { text: 'Generating response via Groq LLM (qwen/qwen3.6-27b)...', cls: 'thinking' };
    if (isLoading) return { text: 'Synthesizing conversational voice via Rime Labs (coda / celeste)...', cls: 'loading' };
    if (isPlaying) {
      return {
        text: `Speaking Turn #${currentAudio?.turnId || ''} via Rime Labs (${currentAudio?.metadata?.speaker || 'celeste'})`,
        cls: 'playing',
      };
    }
    if (isStopped) return { text: 'Audio Playback Stopped (Buffer Purged)', cls: 'stopped' };
    if (agentState === 'ERROR' || state === PlaybackState.ERROR) {
      return { text: errorMessage || 'Pipeline Error encountered', cls: 'error' };
    }
    return { text: 'Voice Assistant Ready — Speak or click Talk to begin', cls: 'idle' };
  };

  const statusInfo = getStatusLabel();

  return (
    <div
      className={`speaking-visualizer ${isPlaying ? 'active' : ''} ${isLoading || isThinking || isTranscribing ? 'loading' : ''} ${isListening ? 'listening' : ''} ${isInterrupting ? 'interrupting' : ''}`}
    >
      <div className="visualizer-orb" style={isListening && dynamicScale > 0.3 ? { transform: `scale(${1 + dynamicScale * 0.15})` } : undefined}>
        <div className="wave-ring ring-1"></div>
        <div className="wave-ring ring-2"></div>
        <div className="wave-ring ring-3"></div>
        <div className="orb-core">
          <span className={`orb-icon ${isLoading || isThinking ? 'spin' : isPlaying ? 'pulse' : isInterrupting ? 'flash' : ''}`}>
            {getOrbIcon()}
          </span>
        </div>
      </div>

      <div className="waveform-bars">
        {[40, 70, 95, 60, 85, 100, 75, 90, 50, 65, 80, 45].map((height, idx) => (
          <span
            key={idx}
            className="bar"
            style={{
              height: isPlaying
                ? `${height}%`
                : isListening
                ? `${Math.round(height * dynamicScale)}%`
                : isInterrupting
                ? '10%'
                : '15%',
              animationDelay: `${idx * 0.08}s`,
            }}
          />
        ))}
      </div>

      <div className="speaking-status-text">
        <span className={`status-label ${statusInfo.cls}`}>
          {statusInfo.text}
        </span>
      </div>
    </div>
  );
}
