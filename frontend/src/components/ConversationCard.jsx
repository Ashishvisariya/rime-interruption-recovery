import React, { useEffect, useRef } from 'react';
import { IconUser, IconBot, IconZap } from './Icons.jsx';

export default function ConversationCard({
  conversationTurns = [],
  currentTranscript = '',
  isListening,
  isProcessing,
  activeTurnId,
}) {
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [conversationTurns, currentTranscript, isListening, isProcessing]);

  const hasCommittedTurns = conversationTurns && conversationTurns.length > 0;
  const isPendingTurnActive = (isListening || isProcessing) && Boolean(currentTranscript.trim());

  return (
    <div className="conversation-card glass-card">
      <div className="card-header-row">
        <h3>Live Conversation</h3>
        <span className="events-count">
          {conversationTurns.length} turn{conversationTurns.length !== 1 ? 's' : ''} recorded
        </span>
      </div>

      <div className="conversation-history-feed" ref={scrollRef}>
        {!hasCommittedTurns && !isPendingTurnActive ? (
          <div className="placeholder-text empty-history">
            No conversation turns recorded yet. Speak or select a prompt to begin.
          </div>
        ) : (
          <>
            {/* Render all previous committed turns chronologically */}
            {conversationTurns.map((turn, idx) => {
              const isInterrupted = turn.status === 'INTERRUPTED' || turn.status === 'CANCELLED';
              return (
                <div
                  key={idx}
                  className={`conversation-turn-item ${isInterrupted ? 'turn-item-interrupted' : ''}`}
                >
                  <div className="turn-card-header">
                    <span className="turn-badge">Turn #{turn.turnId}</span>
                    <span className={`turn-status-tag ${isInterrupted ? 'tag-interrupted' : 'tag-completed'}`}>
                      {isInterrupted ? 'INTERRUPTED' : 'COMPLETED'}
                    </span>
                  </div>

                  <div className="chat-bubble user-bubble">
                    <div className="bubble-header">
                      <span className="role-icon"><IconUser size={16} /></span>
                      <span className="role-name">User Transcript</span>
                    </div>
                    <p className="bubble-text">{turn.userPrompt}</p>
                  </div>

                  <div className="chat-bubble assistant-bubble">
                    <div className="bubble-header">
                      <span className="role-icon"><IconBot size={16} /></span>
                      <span className="role-name">AI Response (Rime {turn.speaker || 'celeste'})</span>
                    </div>
                    <p className={`bubble-text ${isInterrupted ? 'text-interrupted' : ''}`}>
                      {turn.assistantResponse || (isInterrupted ? '[Speech Halted Promptly]' : '')}
                      {isInterrupted && <span className="interrupted-flag"> <IconZap size={14} color="#f59e0b" /> Interrupted</span>}
                    </p>
                  </div>
                </div>
              );
            })}

            {/* Render active in-flight pending turn if processing or listening */}
            {isPendingTurnActive && (
              <div className="conversation-turn-item turn-item-active">
                <div className="turn-card-header">
                  <span className="turn-badge">Turn #{activeTurnId || (conversationTurns.length + 1)}</span>
                  <span className="turn-status-tag tag-authoritative">IN PROGRESS</span>
                </div>

                <div className="chat-bubble user-bubble">
                  <div className="bubble-header">
                    <span className="role-icon"><IconUser size={16} /></span>
                    <span className="role-name">User Transcript</span>
                  </div>
                  <p className="bubble-text">{currentTranscript}</p>
                </div>

                <div className="chat-bubble assistant-bubble">
                  <div className="bubble-header">
                    <span className="role-icon"><IconBot size={16} /></span>
                    <span className="role-name">AI Response (Rime TTS)</span>
                  </div>
                  {isProcessing ? (
                    <p className="bubble-text processing-text">
                      <span className="pulse-dots">Thinking and synthesizing response...</span>
                    </p>
                  ) : (
                    <p className="bubble-text placeholder-text">Listening...</p>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

