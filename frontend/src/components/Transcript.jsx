import React from 'react';

export default function Transcript({ events, text, setText, conversationTurns = [] }) {
  return (
    <div className="transcript-panel glass-card">
      <div className="input-section">
        <label htmlFor="tts-text-input" className="input-label">
          Active Turn Input / Prompt:
        </label>
        <div className="input-wrapper">
          <input
            id="tts-text-input"
            type="text"
            className="text-input"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Type prompt for Voice Agent or speak via microphone..."
          />
        </div>
      </div>

      {conversationTurns && conversationTurns.length > 0 && (
        <div className="conversation-section">
          <div className="events-header">
            <h3>Authoritative Conversation Turns</h3>
            <span className="events-count">{conversationTurns.length} turns completed</span>
          </div>
          <div className="conversation-history">
            {conversationTurns.map((turn, idx) => (
              <div key={idx} className="conversation-turn-card">
                <div className="turn-badge">Turn #{turn.turnId}</div>
                <div className="turn-message user-msg">
                  <span className="msg-role">User:</span>
                  <span className="msg-content">{turn.userPrompt}</span>
                </div>
                <div className="turn-message assistant-msg">
                  <span className="msg-role">Assistant (Rime {turn.speaker}):</span>
                  <span className="msg-content">{turn.assistantResponse}</span>
                </div>
                {turn.latencyMs && (
                  <div className="turn-meta mono">Latency: {turn.latencyMs}ms</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="events-section">
        <div className="events-header">
          <h3>Playback & State Audit Stream</h3>
          <span className="events-count">{events.length} events</span>
        </div>

        <div className="events-list">
          {events.length === 0 ? (
            <div className="events-empty">No lifecycle events recorded yet.</div>
          ) : (
            events.map((evt, idx) => (
              <div key={idx} className={`event-row event-${evt.event_type.toLowerCase()}`}>
                <span className="event-time mono">
                  {new Date(evt.timestamp_ms).toISOString().slice(11, 23)}
                </span>
                <span className="event-turn mono">T#{evt.turn_id}</span>
                <span className="event-type">{evt.event_type}</span>
                <span className="event-details mono">
                  {JSON.stringify(evt.details)}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
