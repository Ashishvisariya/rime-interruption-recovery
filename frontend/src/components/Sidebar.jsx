import React from 'react';
import { IconPlus, IconChat, IconSettings, IconUser } from './Icons.jsx';
import { getSessionPreview } from '../services/session_utils.js';
import { formatRelativeTime } from '../services/conversation_storage.js';

export default function Sidebar({
  sessions = [],
  activeSessionId,
  onSelectSession,
  onNewChat,
  isDevMode,
  onToggleDevMode,
  isOpen,
  onToggleSidebar,
}) {
  return (
    <aside className={`chat-sidebar ${isOpen ? 'open' : 'collapsed'}`}>
      <div className="sidebar-header">
        <button type="button" className="btn-new-chat" onClick={onNewChat}>
          <IconPlus size={18} />
          <span className="btn-text">New Chat</span>
        </button>
        <button
          type="button"
          className="btn-sidebar-toggle"
          onClick={onToggleSidebar}
          title={isOpen ? 'Collapse Sidebar' : 'Expand Sidebar'}
        >
          {isOpen ? '◀' : '▶'}
        </button>
      </div>

      <div className="sidebar-section">
        <span className="section-label">Recent Conversations</span>
        <div className="sessions-list">
          {sessions.length === 0 ? (
            <div className="session-item active">
              <IconChat size={16} className="session-icon" />
              <div className="session-info">
                <div className="session-title-row">
                  <span className="session-title">Current Voice Chat</span>
                </div>
                <span className="session-preview empty">No messages yet</span>
              </div>
            </div>
          ) : (
            sessions.map((sess, idx) => {
              const preview = sess.preview || getSessionPreview(sess);
              const relativeTime = formatRelativeTime(sess.updatedAt || sess.createdAt || sess.date);
              return (
                <button
                  key={sess.id || idx}
                  type="button"
                  className={`session-item ${sess.id === activeSessionId ? 'active' : ''}`}
                  onClick={() => onSelectSession(sess.id)}
                  title={`${sess.title || 'Conversation'}${preview ? `\n\n${preview}` : ''}`}
                >
                  <IconChat size={16} className="session-icon" />
                  <div className="session-info">
                    <div className="session-title-row">
                      <span className="session-title">{sess.title || `Chat ${sess.id.slice(0, 8)}...`}</span>
                      <span className="session-date">{relativeTime}</span>
                    </div>
                    {preview ? (
                      <span className="session-preview">{preview}</span>
                    ) : (
                      <span className="session-preview empty">No messages yet</span>
                    )}
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>

      <div className="sidebar-footer">
        <button
          type="button"
          className={`btn-dev-mode ${isDevMode ? 'active' : ''}`}
          onClick={onToggleDevMode}
        >
          <IconSettings size={16} className="icon" />
          <span className="label">Developer Mode</span>
          <span className="badge">{isDevMode ? 'ON' : 'OFF'}</span>
        </button>

        <div className="user-profile">
          <div className="avatar">
            <IconUser size={18} />
          </div>
          <div className="user-details">
            <span className="user-name">Voice AI Assistant</span>
            <span className="user-plan">Rime Labs Ultra-Low Latency</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
