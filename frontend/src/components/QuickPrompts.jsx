import React from 'react';
import { IconSparkles } from './Icons.jsx';

const SUGGESTIONS = [
  "Explain this",
  "Summarize",
  "Search web",
  "Compare",
  "Tell me more",
  "Translate",
  "Help me plan",
];

export default function QuickPrompts({ onSelectPrompt, disabled }) {
  return (
    <div className="quick-prompts-section">
      <span className="quick-prompts-title">Quick Suggestions:</span>
      <div className="quick-prompts-list">
        {SUGGESTIONS.map((promptText, idx) => (
          <button
            key={idx}
            type="button"
            className="chip-suggestion"
            onClick={() => onSelectPrompt(promptText)}
            disabled={disabled}
          >
            <span className="chip-icon"><IconSparkles size={14} color="#06b6d4" /></span>
            <span>{promptText}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

