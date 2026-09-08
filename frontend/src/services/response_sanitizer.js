/**
 * Frontend Defense-in-Depth Final Response Sanitizer
 * 
 * Guarantees that internal reasoning, planning, unclosed thinking tags,
 * numbered deliberation steps, and tool evaluation traces NEVER reach the UI.
 */

export const FORBIDDEN_REASONING_MARKERS = [
  'analyze user input',
  'available tools',
  'check available tools',
  'check constraints',
  'determine factual need',
  'draft response',
  'thinking process',
  'mental draft',
  'formulate response',
  'formulate a response',
  'no markdown',
  'tts friendly',
  'wait, do i have tools',
  'no tools are provided',
  'internal reasoning',
  'step-by-step',
  'system instructions',
  'developer instructions',
];

export function sanitizeFinalResponse(rawText) {
  if (!rawText || typeof rawText !== 'string') return '';
  let text = rawText.trim();

  // If unclosed or closed <think> tag exists
  if (text.includes('<think>')) {
    if (text.includes('</think>')) {
      text = text.split('</think>').pop().trim();
    } else {
      text = text.split('<think>')[0].trim();
    }
  }

  // Extract explicit final answer marker if present
  const markerRegex = /\b(?:final answer|final response|spoken answer|assistant response)\s*:\s*/i;
  if (markerRegex.test(text)) {
    const parts = text.split(markerRegex);
    text = parts[parts.length - 1].trim();
  }

  // Remove markdown symbols
  text = text.replace(/```(?:text)?[\s\S]*?```/g, '');
  text = text.replace(/[*_#`]/g, '').trim();

  // Filter lines that are internal planning/reasoning
  const lines = text.split('\n').map((l) => l.trim()).filter(Boolean);
  const cleanLines = lines.filter((line) => {
    const lower = line.toLowerCase();
    if (FORBIDDEN_REASONING_MARKERS.some((m) => lower.includes(m))) return false;
    if (
      /^\s*(?:\d+[\.\)]|[-*•]|step\s*\d+:?)\s*/i.test(line) &&
      /tool|check|answer|input|prompt|response|draft|constraint|yes|no/i.test(lower)
    ) {
      return false;
    }
    return true;
  }).map((line) => line.replace(/^\s*(?:\d+[\.\)]|[-*•])\s*/, '').trim());

  let result = cleanLines.join(' ').replace(/\s+/g, ' ').trim();
  result = result.replace(/^(?:final polish|final response|answer|response)\s*:\s*/i, '').trim();
  return result;
}
