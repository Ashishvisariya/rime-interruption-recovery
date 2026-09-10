/**
 * Conversation History Storage Layer (ChatGPT-style multi-conversation manager)
 * 
 * Provides robust, independent conversation lifecycle management:
 * - One conversation = One unique ID = One independent message history
 * - Multi-conversation persistence (survives browser refresh, app reopening)
 * - Automatic title generation from first meaningful user prompt
 * - Relative timestamp calculation ("Just now", "5 min ago", "2 hours ago", "Yesterday")
 * - Backward-compatible migration from legacy storage keys
 */

export const CONVERSATIONS_STORAGE_KEY = 'voice_conversations_v1';
export const LEGACY_SESSIONS_KEY = 'rime_voice_sessions';
export const LEGACY_CHATS_KEY = 'rime_voice_chats';
export const ACTIVE_SESSION_KEY = 'rime_voice_active_session';

/**
 * Format relative time strings from timestamp.
 * 
 * @param {number|string|Date} timestamp
 * @returns {string} e.g. "Just now", "5 min ago", "2 hours ago", "Yesterday"
 */
export function formatRelativeTime(timestamp) {
  if (!timestamp) return 'Just now';
  const time = typeof timestamp === 'number' ? timestamp : new Date(timestamp).getTime();
  if (isNaN(time)) return 'Just now';

  const now = Date.now();
  const diffMs = now - time;
  if (diffMs < 0 || diffMs < 45 * 1000) {
    return 'Just now';
  }

  const mins = Math.floor(diffMs / 60000);
  if (mins < 60) {
    return `${mins} min ago`;
  }

  const hours = Math.floor(mins / 60);
  if (hours === 1) {
    return '1 hour ago';
  }
  if (hours < 24) {
    return `${hours} hours ago`;
  }

  const days = Math.floor(hours / 24);
  if (days === 1) {
    return 'Yesterday';
  }
  if (days < 7) {
    return `${days} days ago`;
  }

  return new Date(time).toLocaleDateString([], { month: 'short', day: 'numeric' });
}

/**
 * Generate a clean title from the user's first prompt.
 * 
 * @param {string} prompt 
 * @returns {string} Clean title (up to 32 characters)
 */
export function generateTitleFromPrompt(prompt) {
  if (!prompt || typeof prompt !== 'string' || !prompt.trim()) {
    return 'New Chat';
  }
  const clean = prompt.trim();
  // Strip trailing punctuation
  const stripped = clean.replace(/[?.!]+$/, '');
  if (stripped.length <= 32) {
    return stripped.charAt(0).toUpperCase() + stripped.slice(1);
  }
  return stripped.slice(0, 30).trim() + '...';
}

/**
 * Extract latest message preview from an array of turns or messages.
 * 
 * @param {Array} turns 
 * @returns {string}
 */
export function extractLatestPreview(turns) {
  if (!turns || !Array.isArray(turns) || turns.length === 0) {
    return '';
  }
  for (let i = turns.length - 1; i >= 0; i--) {
    const turn = turns[i];
    if (!turn) continue;

    // Check assistant response
    if (typeof turn.assistantResponse === 'string' && turn.assistantResponse.trim()) {
      return turn.assistantResponse.trim();
    }
    // Check message content if in {role, content} format
    if (turn.role === 'assistant' && typeof turn.content === 'string' && turn.content.trim()) {
      return turn.content.trim();
    }
    // Check user prompt
    if (typeof turn.userPrompt === 'string' && turn.userPrompt.trim()) {
      return turn.userPrompt.trim();
    }
    if (turn.role === 'user' && typeof turn.content === 'string' && turn.content.trim()) {
      return turn.content.trim();
    }
  }
  return '';
}

/**
 * Map turn objects into structured messages [{role, content, timestamp}].
 * 
 * @param {Array} turns 
 * @returns {Array}
 */
export function turnsToMessages(turns) {
  if (!turns || !Array.isArray(turns)) return [];
  const messages = [];
  for (const t of turns) {
    if (!t) continue;
    if (t.userPrompt && typeof t.userPrompt === 'string') {
      messages.push({
        role: 'user',
        content: t.userPrompt.trim(),
        timestamp: t.timestamp || Date.now(),
      });
    }
    if (t.assistantResponse && typeof t.assistantResponse === 'string') {
      messages.push({
        role: 'assistant',
        content: t.assistantResponse.trim(),
        timestamp: t.timestamp || Date.now(),
      });
    }
  }
  return messages;
}

/**
 * Migrate legacy localStorage data if voice_conversations_v1 is not present.
 */
function migrateLegacyStorage() {
  if (typeof window === 'undefined' || !window.localStorage) return [];
  try {
    const rawSessions = localStorage.getItem(LEGACY_SESSIONS_KEY);
    const rawChats = localStorage.getItem(LEGACY_CHATS_KEY);
    if (!rawSessions && !rawChats) return [];

    const sessions = rawSessions ? JSON.parse(rawSessions) : [];
    const chatsMap = rawChats ? JSON.parse(rawChats) : {};

    const migrated = [];
    for (const s of sessions) {
      if (!s || !s.id) continue;
      const turns = Array.isArray(chatsMap[s.id]) ? chatsMap[s.id] : [];
      const preview = extractLatestPreview(turns);
      migrated.push({
        id: s.id,
        title: s.title && !s.title.startsWith('Voice Session #') ? s.title : (generateTitleFromPrompt(preview) || 'Conversation'),
        createdAt: s.createdAt || Date.now(),
        updatedAt: s.updatedAt || Date.now(),
        preview: preview || '',
        messages: turnsToMessages(turns),
        turns: turns,
      });
    }

    if (migrated.length > 0) {
      localStorage.setItem(CONVERSATIONS_STORAGE_KEY, JSON.stringify(migrated));
    }
    return migrated;
  } catch (err) {
    console.warn('Legacy conversation migration note:', err);
    return [];
  }
}

/**
 * Load all stored conversations, sorted by most recently updated.
 * 
 * @returns {Array<Object>}
 */
export function loadAllConversations() {
  if (typeof window === 'undefined' || !window.localStorage) return [];
  try {
    const raw = localStorage.getItem(CONVERSATIONS_STORAGE_KEY);
    if (!raw) {
      return migrateLegacyStorage();
    }
    const list = JSON.parse(raw);
    if (!Array.isArray(list)) return [];
    
    // Sort descending by updatedAt
    return list.sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
  } catch (err) {
    console.error('Failed to load conversations from storage:', err);
    return [];
  }
}

/**
 * Save the entire list of conversations to localStorage.
 * Synchronizes legacy keys for backward compatibility.
 * 
 * @param {Array<Object>} conversations 
 */
export function saveAllConversations(conversations) {
  if (typeof window === 'undefined' || !window.localStorage) return;
  try {
    localStorage.setItem(CONVERSATIONS_STORAGE_KEY, JSON.stringify(conversations));

    // Backward compatibility sync
    const legacySessions = conversations.map((c) => ({
      id: c.id,
      title: c.title,
      date: formatRelativeTime(c.updatedAt || c.createdAt),
      preview: c.preview || '',
      createdAt: c.createdAt,
      updatedAt: c.updatedAt,
    }));
    localStorage.setItem(LEGACY_SESSIONS_KEY, JSON.stringify(legacySessions));

    const legacyChatsMap = {};
    for (const c of conversations) {
      legacyChatsMap[c.id] = c.turns || [];
    }
    localStorage.setItem(LEGACY_CHATS_KEY, JSON.stringify(legacyChatsMap));
  } catch (err) {
    console.error('Failed to save conversations to storage:', err);
  }
}

/**
 * Get a single conversation by ID.
 * 
 * @param {string} id 
 * @returns {Object|null}
 */
export function getStoredConversation(id) {
  if (!id) return null;
  const all = loadAllConversations();
  return all.find((c) => c.id === id) || null;
}

/**
 * Create and persist a brand new conversation item.
 * 
 * @param {string} id - Unique session/conversation ID
 * @param {string} [title] - Optional initial title
 * @returns {Object} Newly created conversation object
 */
export function createNewConversationRecord(id, title = 'New Chat') {
  const all = loadAllConversations();
  // Check if conversation already exists
  const existing = all.find((c) => c.id === id);
  if (existing) return existing;

  const now = Date.now();
  const newConv = {
    id,
    title,
    createdAt: now,
    updatedAt: now,
    preview: '',
    messages: [],
    turns: [],
  };

  const updated = [newConv, ...all.filter((c) => c.id !== id)];
  saveAllConversations(updated);
  return newConv;
}

/**
 * Save or update an existing conversation's turns and metadata.
 * Automatically updates:
 * - title (if it's the first message and title is default)
 * - preview (latest non-empty message)
 * - updatedAt (timestamp)
 * - messages array
 * 
 * @param {string} id - Unique conversation ID
 * @param {Array} turns - Array of turn objects
 * @param {string} [titleOverride] - Optional title override
 * @returns {Object} Updated conversation object
 */
export function persistConversationTurns(id, turns, titleOverride = null) {
  if (!id) return null;
  const all = loadAllConversations();
  const cleanTurns = Array.isArray(turns) ? turns : [];
  const now = Date.now();

  let conv = all.find((c) => c.id === id);
  const preview = extractLatestPreview(cleanTurns);

  if (!conv) {
    // Generate title from first user prompt if available
    const firstPrompt = cleanTurns.find((t) => t.userPrompt)?.userPrompt;
    const initialTitle = titleOverride || (firstPrompt ? generateTitleFromPrompt(firstPrompt) : 'New Chat');
    conv = {
      id,
      title: initialTitle,
      createdAt: now,
      updatedAt: now,
      preview: preview || '',
      messages: turnsToMessages(cleanTurns),
      turns: cleanTurns,
    };
    const updated = [conv, ...all];
    saveAllConversations(updated);
    return conv;
  }

  // Update existing conversation
  let currentTitle = conv.title;
  if (titleOverride) {
    currentTitle = titleOverride;
  } else if (!currentTitle || currentTitle === 'New Chat' || currentTitle.startsWith('Voice Session #')) {
    const firstPrompt = cleanTurns.find((t) => t.userPrompt)?.userPrompt;
    if (firstPrompt) {
      currentTitle = generateTitleFromPrompt(firstPrompt);
    }
  }

  conv.title = currentTitle;
  conv.updatedAt = now;
  conv.preview = preview || conv.preview || '';
  conv.turns = cleanTurns;
  conv.messages = turnsToMessages(cleanTurns);

  // Keep list sorted by updatedAt descending
  const updated = [conv, ...all.filter((c) => c.id !== id)];
  saveAllConversations(updated);
  return conv;
}
