import React from 'react';
import { IconMic, IconVolume, IconBrain, IconStop, IconSparkles } from './Icons.jsx';

/**
 * Clean Round AI Button
 * 
 * Replaces waveform visualizers as the primary voice-first listening and state indicator:
 * - IDLE: Sleek circular button ready for tap-to-talk or hands-free activation.
 * - LISTENING: Active cyan pulsing halo & acoustic mic reactivity indicating microphone is hot.
 * - THINKING: Smooth rotating purple/indigo aura while LLM streams.
 * - SPEAKING: Pulsing emerald audio ring while Rime TTS plays (tap to interrupt).
 */
export default function RoundAiButton({
  agentState = 'IDLE',
  isVADActive = false,
  isListening = false,
  isThinking = false,
  isPlaying = false,
  isInterrupting = false,
  micLevel = 0,
  onToggleVoice,
  onStopAudio,
}) {
  let currentState = 'IDLE';
  if (isInterrupting || agentState === 'INTERRUPTING') {
    currentState = 'LISTENING';
  } else if (isPlaying || agentState === 'PLAYING') {
    currentState = 'SPEAKING';
  } else if (isThinking || agentState === 'THINKING' || agentState === 'TRANSCRIBING' || agentState === 'SYNTHESIZING') {
    currentState = 'THINKING';
  } else if (isListening || agentState === 'LISTENING' || isVADActive) {
    currentState = 'LISTENING';
  }

  const dynamicScale = Math.min(1.4, Math.max(1.0, 1.0 + (micLevel || 0) * 2.5));

  const handleClick = (e) => {
    e.preventDefault();
    if (currentState === 'SPEAKING') {
      if (onStopAudio) {
        onStopAudio();
        return;
      }
    }
    if (onToggleVoice) {
      onToggleVoice();
    }
  };

  const renderIcon = () => {
    switch (currentState) {
      case 'LISTENING':
        return <IconMic size={32} color="#06b6d4" className="round-btn-icon pulse-active" />;
      case 'THINKING':
        return <IconBrain size={32} color="#8b5cf6" className="round-btn-icon spin-slow" />;
      case 'SPEAKING':
        return <IconVolume size={32} color="#10b981" className="round-btn-icon wave-active" />;
      default:
        return <IconMic size={32} color="#94a3b8" className="round-btn-icon" />;
    }
  };

  const getStatusText = () => {
    switch (currentState) {
      case 'LISTENING':
        return 'Listening... (Speak anytime)';
      case 'THINKING':
        return 'Thinking & preparing speech...';
      case 'SPEAKING':
        return 'Speaking via Rime · Tap to interrupt';
      default:
        return 'Tap to Start Voice AI';
    }
  };

  return (
    <div className="round-ai-container">
      <div className="round-ai-outer-wrap">
        {/* Acoustic ring for active listening */}
        {currentState === 'LISTENING' && (
          <div
            className="round-ai-halo-listening"
            style={{ transform: `scale(${dynamicScale})` }}
          />
        )}
        {currentState === 'SPEAKING' && (
          <div className="round-ai-halo-speaking" />
        )}
        {currentState === 'THINKING' && (
          <div className="round-ai-halo-thinking" />
        )}

        <button
          type="button"
          id="btn-round-ai-listener"
          className={`round-ai-btn round-ai-${currentState.toLowerCase()}`}
          onClick={handleClick}
          title={
            currentState === 'SPEAKING'
              ? 'Interrupt AI response'
              : currentState === 'LISTENING'
              ? 'Microphone active — tap to end session'
              : 'Start voice session'
          }
        >
          <div className="round-ai-inner-circle">
            {renderIcon()}
          </div>
        </button>
      </div>

      <div className="round-ai-status-label">
        <span className={`status-pill pill-${currentState.toLowerCase()}`}>
          <span className="status-dot" />
          {getStatusText()}
        </span>
      </div>
    </div>
  );
}
