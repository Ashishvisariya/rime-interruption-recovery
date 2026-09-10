import React, { useEffect, useRef } from 'react';
import { IconUser, IconBot, IconZap, IconSparkles } from './Icons.jsx';

export default function ChatThread({
  conversationTurns = [],
  currentTranscript = '',
  streamingAssistantText = '',
  isListening,
  isProcessing,
  agentState,
  activeTurnId,
}) {
  const scrollRef = useRef(null);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    } else if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [conversationTurns, currentTranscript, streamingAssistantText, isListening, isProcessing, agentState]);

  const hasTurns = conversationTurns && conversationTurns.length > 0;
  const hasStreamingText = Boolean(streamingAssistantText && streamingAssistantText.trim().length > 0);
  const isPendingTurn =
    Boolean(isListening) ||
    Boolean(isProcessing) ||
    ['LISTENING', 'TRANSCRIBING', 'THINKING', 'SYNTHESIZING'].includes(agentState) ||
    Boolean(currentTranscript && currentTranscript.trim().length > 0) ||
    hasStreamingText;

  const getAssistantStatusLabel = () => {
    switch (agentState) {
      case 'TRANSCRIBING':
        return 'Transcribing...';
      case 'THINKING':
        return 'Thinking...';
      case 'SYNTHESIZING':
        return 'Synthesizing voice...';
      case 'PLAYING':
        return 'Speaking...';
      default:
        return isListening ? 'Listening...' : 'Processing...';
    }
  };

  const getAssistantProcessingMessage = () => {
    switch (agentState) {
      case 'TRANSCRIBING':
        return 'Transcribing speech...';
      case 'THINKING':
        return 'Generating response...';
      case 'SYNTHESIZING':
        return 'Synthesizing voice via Rime TTS...';
      case 'PLAYING':
        return 'Speaking...';
      default:
        return isListening ? 'Listening to speech...' : 'Processing...';
    }
  };

  return (
    <div className="chat-thread-container" ref={scrollRef}>
      {!hasTurns && !isPendingTurn ? (
        <div className="empty-thread-welcome">
          <div className="welcome-icon-box">
            <IconBot size={48} color="#06b6d4" />
          </div>
          <h2>Voice AI Assistant</h2>
          <p>Ultra-Low Latency Conversational Voice powered by Rime Labs TTS.</p>
          <p className="welcome-hint">Click the Microphone or type a message below to start.</p>
        </div>
      ) : (
        <div className="chat-messages-list">
          {conversationTurns.map((turn, idx) => {
            const isInterrupted = turn.status === 'INTERRUPTED' || turn.status === 'CANCELLED';
            const isSpeaking = agentState === 'PLAYING' && (turn.turnId === activeTurnId || idx === conversationTurns.length - 1);

            return (
              <div key={turn.turnId || idx} className="chat-turn-group">
                {/* User Message */}
                {turn.userPrompt && (
                  <div className="chat-msg user-msg">
                    <div className="msg-avatar user-avatar">
                      <IconUser size={18} />
                    </div>
                    <div className="msg-bubble user-bubble-content">
                      <div className="msg-header">
                        <span className="msg-author">You</span>
                        <span className="msg-turn-tag">Turn #{turn.turnId}</span>
                      </div>
                      <div className="msg-text">{turn.userPrompt}</div>
                    </div>
                  </div>
                )}

                {/* Assistant Message */}
                <div className={`chat-msg assistant-msg ${isInterrupted ? 'msg-interrupted' : ''}`}>
                  <div className="msg-avatar assistant-avatar">
                    <IconBot size={18} />
                  </div>
                  <div className="msg-bubble assistant-bubble-content">
                    <div className="msg-header">
                      <span className="msg-author">Voice Assistant · Rime</span>
                      {turn.searchUsed && (
                        <span className="turn-status-tag tag-authoritative" title="Real-time web search results from Tavily were incorporated">
                          🔍 Web Search
                        </span>
                      )}
                      {isInterrupted && (
                        <span className="turn-status-tag tag-interrupted">
                          <span className="tag-bolt">⚡</span> INTERRUPTED
                        </span>
                      )}
                      {isSpeaking && !isInterrupted && (
                        <span className="turn-status-tag tag-speaking">
                          🔊 Speaking...
                        </span>
                      )}
                    </div>
                    <div className="msg-text">
                      {turn.assistantResponse || (isInterrupted ? '[Speech Halted Promptly on Barge-In]' : '')}
                    </div>
                    {turn.searchSources && turn.searchSources.length > 0 && (
                      <div className="msg-sources" style={{ marginTop: '4px', fontSize: '11px', color: '#94a3b8' }}>
                        <span>Sources: </span>
                        {turn.searchSources.slice(0, 3).map((src, sIdx) => {
                          let hostname = src;
                          try { hostname = new URL(src).hostname.replace('www.', ''); } catch (e) {}
                          return (
                            <a
                              key={sIdx}
                              href={src}
                              target="_blank"
                              rel="noreferrer noopener"
                              style={{ color: '#06b6d4', marginRight: '8px', textDecoration: 'underline' }}
                            >
                              {hostname}
                            </a>
                          );
                        })}
                      </div>
                    )}

                    {/* Small inline row for latency - Matching screenshot */}
                    {turn.latencyBreakdown && turn.latencyBreakdown.totalMs ? (
                      <div className="msg-latency-row">
                        <span className="latency-icon">⚡</span>
                        <span className="latency-total">{(turn.latencyBreakdown.totalMs / 1000).toFixed(2)}s</span>
                        {turn.latencyBreakdown.sttMs !== undefined && turn.latencyBreakdown.sttMs > 0 && (
                          <span className="latency-part"> · STT {(turn.latencyBreakdown.sttMs / 1000).toFixed(2)}s</span>
                        )}
                        {turn.latencyBreakdown.llmMs !== undefined && turn.latencyBreakdown.llmMs > 0 && (
                          <span className="latency-part"> · LLM {(turn.latencyBreakdown.llmMs / 1000).toFixed(2)}s</span>
                        )}
                        {turn.latencyBreakdown.ttsMs !== undefined && turn.latencyBreakdown.ttsMs > 0 && (
                          <span className="latency-part"> · Rime {(turn.latencyBreakdown.ttsMs / 1000).toFixed(2)}s</span>
                        )}
                      </div>
                    ) : turn.latencyMs ? (
                      <div className="msg-latency-row">
                        <span className="latency-icon">⚡</span>
                        <span className="latency-total">{(turn.latencyMs / 1000).toFixed(2)}s</span>
                        {turn.sttLatencyMs ? (
                          <span className="latency-part"> · STT {(turn.sttLatencyMs / 1000).toFixed(2)}s</span>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
            );
          })}

          {/* Pending In-Flight Turn (Live Transcribing / Speaking / Thinking) */}
          {isPendingTurn && (
            <div className="chat-turn-group pending-turn-group">
              <div className="chat-msg user-msg">
                <div className="msg-avatar user-avatar">
                  <IconUser size={18} />
                </div>
                <div className="msg-bubble user-bubble-content">
                  <div className="msg-header">
                    <span className="msg-author">You</span>
                    {activeTurnId && <span className="msg-turn-tag">Turn #{activeTurnId}</span>}
                  </div>
                  <div className="msg-text">
                    {currentTranscript && currentTranscript.trim().length > 0 ? (
                      currentTranscript
                    ) : (
                      <span className="live-transcribing-placeholder">
                        <span className="live-pulse-dot"></span> Listening...
                      </span>
                    )}
                  </div>
                </div>
              </div>

              <div className="chat-msg assistant-msg">
                <div className="msg-avatar assistant-avatar pulse-orb">
                  <IconSparkles size={18} />
                </div>
                <div className="msg-bubble assistant-bubble-content">
                  <div className="msg-header">
                    <span className="msg-author">Voice Assistant · Rime</span>
                    <span className={`turn-status-tag ${agentState === 'PLAYING' ? 'tag-speaking' : 'tag-live-state'}`}>
                      {getAssistantStatusLabel()}
                    </span>
                  </div>
                  <div className={`msg-text ${hasStreamingText ? 'streaming-text-active' : 'processing-text'}`}>
                    {hasStreamingText ? (
                      <span className="streaming-text-content">
                        {streamingAssistantText}
                        <span className="streaming-cursor"></span>
                      </span>
                    ) : (
                      <span className="typing-dots">
                        {getAssistantProcessingMessage()}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      )}
    </div>
  );
}
