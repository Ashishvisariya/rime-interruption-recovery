import React from 'react';
import { PlaybackState } from '../services/audio.js';

export default function SpeakingIndicator({ state, agentState, currentAudio }) {
  const isPlaying = state === PlaybackState.PLAYING;
  const isLoading = state === PlaybackState.LOADING || agentState === 'SYNTHESIZING';
  const isThinking = agentState === 'THINKING';
  const isTranscribing = agentState === 'TRANSCRIBING';
  const isListening = agentState === 'LISTENING';
  const isInterrupting = agentState === 'INTERRUPTING';
  const isStopped = state === PlaybackState.STOPPED;

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
    if (isInterrupting) return { text: 'Interruption Detected! Monotonic turn transitioning...', cls: 'interrupting' };
    if (isListening) return { text: 'Listening to your voice...', cls: 'recording' };
    if (isTranscribing) return { text: 'Transcribing speech via Groq Whisper...', cls: 'loading' };
    if (isThinking) return { text: 'Reasoning & Generating response via Groq LLM (qwen/qwen3.6-27b)...', cls: 'thinking' };
    if (isLoading) return { text: 'Synthesizing expressive speech via Rime Labs (coda/celeste)...', cls: 'loading' };
    if (isPlaying) {
      return {
        text: `Speaking Turn #${currentAudio?.turnId} via Rime Labs (${currentAudio?.metadata?.speaker || 'celeste'})`,
        cls: 'playing',
      };
    }
    if (isStopped) return { text: 'Speech Halted (Immediate Interruption / Cutoff)', cls: 'stopped' };
    if (agentState === 'ERROR' || state === PlaybackState.ERROR) return { text: 'Pipeline Error occurred', cls: 'error' };
    return { text: 'Voice Agent Ready — Press Push-to-Talk or Speak to Barge-In', cls: 'idle' };
  };

  const statusInfo = getStatusLabel();

  return (
    <div className={`speaking-visualizer ${isPlaying ? 'active' : ''} ${isLoading || isThinking || isTranscribing ? 'loading' : ''} ${isListening ? 'listening' : ''}`}>
      <div className="visualizer-orb">
        <div className="wave-ring ring-1"></div>
        <div className="wave-ring ring-2"></div>
        <div className="wave-ring ring-3"></div>
        <div className="orb-core">
          <span className={`orb-icon ${isLoading || isThinking ? 'spin' : isPlaying ? 'pulse' : ''}`}>
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
              height: isPlaying ? `${height}%` : isListening ? `${height * 0.6}%` : '15%',
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
