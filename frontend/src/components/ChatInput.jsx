import React from 'react';
import QuickPrompts from './QuickPrompts.jsx';
import RoundAiButton from './RoundAiButton.jsx';
import { PlaybackState } from '../services/audio.js';
import { IconSend } from './Icons.jsx';

export default function ChatInput({
  text,
  setText,
  onSend,
  onToggleVoice,
  onStopAudio,
  isRecording,
  isProcessing,
  isLoading,
  isVADActive,
  playbackState,
  agentState,
  micLevel = 0,
  onSelectQuickPrompt,
  lastTurnLatency = null,
}) {
  const isPlaying = playbackState === PlaybackState.PLAYING || agentState === 'PLAYING';
  const isThinking = isProcessing || isLoading || agentState === 'THINKING' || agentState === 'TRANSCRIBING' || agentState === 'SYNTHESIZING';
  const isListening = isRecording || agentState === 'LISTENING';
  const isInterrupting = agentState === 'INTERRUPTING';

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (text.trim() && !isThinking) {
        onSend();
      }
    }
  };

  const getPlaceholder = () => {
    if (isVADActive) {
      if (isListening) return 'Listening... Speak naturally (barge-in enabled)';
      if (isThinking) return 'Thinking & synthesizing voice...';
      if (isPlaying) return 'Speaking... Speak anytime to interrupt';
      return 'Voice Session Active — Speak naturally or type here...';
    }
    return 'Type a prompt or tap the round AI button to speak...';
  };

  return (
    <div className="chat-input-wrapper">
      {/* 1. Primary Listening & Voice AI Controller (Round AI Button) */}
      <RoundAiButton
        agentState={agentState}
        isVADActive={isVADActive}
        isListening={isListening}
        isThinking={isThinking}
        isPlaying={isPlaying}
        isInterrupting={isInterrupting}
        micLevel={micLevel}
        onToggleVoice={onToggleVoice}
        onStopAudio={onStopAudio}
      />

      {/* 2. Quick Suggestions (7 core prompts) */}
      <QuickPrompts
        onSelectPrompt={onSelectQuickPrompt}
        disabled={isThinking}
      />

      {/* 3. Text Input & Manual Fallback Bar */}
      <div className="chat-input-bar">
        <input
          id="tts-text-input"
          type="text"
          className="chat-text-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={getPlaceholder()}
        />

        <button
          type="button"
          id="btn-synthesize-play"
          className="input-send-btn"
          onClick={() => onSend()}
          disabled={isThinking || !text.trim()}
          title="Send text prompt"
        >
          <span>Send</span>
          <IconSend size={16} className="send-icon" />
        </button>
      </div>

      <div className="input-disclaimer">
        <span>Real-Time Streaming Voice AI &bull; Instant VAD Auto-Endpointing &bull; Genuine Rime Labs TTS</span>
      </div>
    </div>
  );
}



