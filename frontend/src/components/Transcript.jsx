import React from 'react';

export default function Transcript({
  events,
  text,
  setText,
  conversationTurns = [],
  activeTurnId = 1,
  onLoadNormalDemo,
  onLoadStressDemo,
}) {
  const formatEventName = (evt) => {
    const type = evt.event_type || '';
    const turn = evt.turn_id !== undefined ? `T${evt.turn_id}` : '';

    if (type === 'INTERRUPTION_DETECTED') return `${turn ? turn + ' ' : ''}USER INTERRUPTED`;
    if (type === 'AUDIO_STOP_REQUESTED' || type === 'AUDIO_STOPPED') return `${turn ? turn + ' ' : ''}AUDIO STOPPED`;
    if (type === 'INTERRUPTION_TURN_TRANSITIONED') return `${turn ? turn + ' ' : ''}TURN TRANSITIONED`;
    if (type === 'TURN_STARTED') return `${turn ? turn + ' ' : ''}STARTED`;
    if (type === 'THINKING') return `${turn ? turn + ' ' : ''}THINKING`;
    if (type === 'AUDIO_PLAY_STARTED' || type === 'AUDIO_STARTED') return `${turn ? turn + ' ' : ''}AUDIO PLAYING`;
    if (type === 'AUDIO_PLAY_COMPLETED' || type === 'TURN_COMPLETED') return `${turn ? turn + ' ' : ''}COMPLETED`;
    if (type === 'AUDIO_DISCARDED') return `${turn ? turn + ' ' : ''}STALE RESULT REJECTED`;
    if (type === 'TASK_CANCELLED') return `${turn ? turn + ' ' : ''}TASK CANCELLED`;
    return `${turn ? turn + ' ' : ''}${type.replace(/_/g, ' ')}`;
  };

  return (
    <div className="transcript-panel glass-card">
      <div className="input-section">
        <div className="input-label-row">
          <label htmlFor="tts-text-input" className="input-label">
            Active Turn Prompt / Spoken Input (T#{activeTurnId}):
          </label>
          <div className="quick-demo-buttons">
            <span className="demo-preset-label">Judge Demo Presets:</span>
            <button
              type="button"
              className="btn-tiny btn-preset"
              onClick={onLoadNormalDemo}
              title="Load Normal Demo: Delhi -> Mumbai"
            >
              Normal Demo
            </button>
            <button
              type="button"
              className="btn-tiny btn-preset"
              onClick={onLoadStressDemo}
              title="Load Stress Demo: Flight NYC-Tokyo -> London"
            >
              Stress Demo
            </button>
          </div>
        </div>
        <div className="input-wrapper">
          <input
            id="tts-text-input"
            type="text"
            className="text-input"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Type prompt or speak via microphone..."
          />
        </div>
      </div>

      {conversationTurns && conversationTurns.length > 0 && (
        <div className="conversation-section">
          <div className="events-header">
            <h3>Authoritative Conversation History</h3>
            <span className="events-count">{conversationTurns.length} turns recorded</span>
          </div>
          <div className="conversation-history">
            {conversationTurns.map((turn, idx) => {
              const isInterrupted = turn.status === 'INTERRUPTED' || turn.status === 'CANCELLED';
              const isAuthoritative = turn.turnId === activeTurnId || idx === conversationTurns.length - 1;

              return (
                <div
                  key={idx}
                  className={`conversation-turn-card ${isInterrupted ? 'turn-interrupted' : ''} ${isAuthoritative ? 'turn-authoritative' : ''}`}
                >
                  <div className="turn-card-header">
                    <span className="turn-badge">Turn #{turn.turnId}</span>
                    {isInterrupted ? (
                      <span className="turn-status-tag tag-interrupted">INTERRUPTED / CANCELLED</span>
                    ) : isAuthoritative ? (
                      <span className="turn-status-tag tag-authoritative">LATEST AUTHORITATIVE</span>
                    ) : (
                      <span className="turn-status-tag tag-completed">COMPLETED</span>
                    )}
                  </div>
                  <div className="turn-message user-msg">
                    <span className="msg-role">User:</span>
                    <span className="msg-content">{turn.userPrompt}</span>
                  </div>
                  {turn.assistantResponse && (
                    <div className="turn-message assistant-msg">
                      <span className="msg-role">Assistant (Rime {turn.speaker || 'celeste'}):</span>
                      <span className="msg-content">{turn.assistantResponse}</span>
                    </div>
                  )}
                  {turn.latencyMs && (
                    <div className="turn-meta mono">Turn Latency: {turn.latencyMs}ms</div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="events-section">
        <div className="events-header">
          <h3>Real-Time Event & Cancellation Audit Stream</h3>
          <span className="events-count">{events.length} events logged</span>
        </div>

        <div className="events-list">
          {events.length === 0 ? (
            <div className="events-empty">No lifecycle events recorded yet. Connect or speak to begin.</div>
          ) : (
            events.map((evt, idx) => (
              <div key={idx} className={`event-row event-${(evt.event_type || '').toLowerCase()}`}>
                <span className="event-time mono">
                  {new Date(evt.timestamp_ms || Date.now()).toISOString().slice(11, 23)}
                </span>
                <span className="event-turn mono">{evt.turn_id !== undefined ? `T#${evt.turn_id}` : 'SYS'}</span>
                <span className="event-type">{formatEventName(evt)}</span>
                <span className="event-details mono" title={JSON.stringify(evt.details || {})}>
                  {JSON.stringify(evt.details || {})}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
