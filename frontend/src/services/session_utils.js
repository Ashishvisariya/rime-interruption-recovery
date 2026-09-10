/**
 * Session & Conversation History Utilities
 * 
 * Provides extraction of conversation previews from stored conversation turns,
 * supporting adaptive display of recent user prompts and assistant responses.
 */

/**
 * Extracts a 1-2 line preview of the latest available message in a conversation.
 * Scans backward from the most recent turn, checking assistant responses first,
 * then user prompts, ensuring that empty messages fall back to the most recent available text.
 * 
 * @param {Array} turns - Array of conversation turn objects
 * @returns {string} - Clean preview text or empty string if no messages
 */
export function getLatestMessagePreview(turns) {
  if (!turns || !Array.isArray(turns) || turns.length === 0) {
    return '';
  }

  for (let i = turns.length - 1; i >= 0; i--) {
    const turn = turns[i];
    if (!turn) continue;

    // Prefer assistant response if completed
    const assistant = typeof turn.assistantResponse === 'string' ? turn.assistantResponse.trim() : '';
    if (assistant) {
      return assistant;
    }

    // Fall back to user prompt if assistant response is empty or pending
    const user = typeof turn.userPrompt === 'string' ? turn.userPrompt.trim() : '';
    if (user) {
      return user;
    }
  }

  return '';
}

/**
 * Safely retrieves the stored chats map from localStorage.
 * 
 * @returns {Object} Map of sessionId -> turns array
 */
export function getStoredChatsMap() {
  if (typeof window === 'undefined' || !window.localStorage) {
    return {};
  }
  try {
    const raw = localStorage.getItem('rime_voice_chats');
    return raw ? JSON.parse(raw) : {};
  } catch (err) {
    console.error('Failed to parse rime_voice_chats from localStorage:', err);
    return {};
  }
}

/**
 * Resolves the preview text for a specific session object.
 * 
 * @param {Object} session - Session object { id, title, preview, ... }
 * @param {Object} [chatsMap] - Optional map of sessionId -> turns
 * @returns {string} Clean preview text
 */
export function getSessionPreview(session, chatsMap = null) {
  if (!session || !session.id) return '';
  if (session.preview && typeof session.preview === 'string' && session.preview.trim()) {
    return session.preview.trim();
  }
  const map = chatsMap || getStoredChatsMap();
  const turns = map[session.id] || [];
  return getLatestMessagePreview(turns);
}
