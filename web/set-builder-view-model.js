export const SET_PROPOSAL_STRATEGIES = [
  {
    id: 'safe',
    label: 'Safe Flow',
    summary: 'Smooth, dependable transitions',
    detail: 'Prioritizes tempo, harmony, vocal space, and consistent mixability.',
  },
  {
    id: 'journey',
    label: 'Energy Journey',
    summary: 'A deliberate rise, peak, and release',
    detail: 'Follows the requested energy curve while preserving workable transitions.',
  },
  {
    id: 'adventurous',
    label: 'Adventurous Mix',
    summary: 'Bolder contrasts and less obvious choices',
    detail: 'Rewards variety, genre movement, and surprising but defensible transitions.',
  },
];

export function journeyDurationStatus(sections, durationMinutes) {
  const values = sections || [];
  const total = values.reduce((sum, section) => sum + Number(section.durationPercent || 0), 0);
  return {
    total,
    valid: Math.abs(total - 100) <= 0.01,
    text: `${values.length} sections · ${total}% of ${Number(durationMinutes)} minutes · edits drive track placement`,
  };
}

export function intentionProviderView(status = {}) {
  const provider = status.provider || 'offline';
  const ready = Boolean(status.available);
  return {
    className: `set-provider-status ${ready ? 'ready' : 'offline'}`,
    text:
      provider === 'ollama' && ready
        ? `Local AI ready · ${status.model}`
        : provider === 'openai' && ready
          ? `Cloud AI ready · ${status.model}`
          : 'Offline rules · Ollama unavailable',
    title:
      provider === 'ollama'
        ? `Ollama is answering with ${status.model}.`
        : provider === 'openai'
          ? 'Ollama is unavailable; the configured cloud fallback is active.'
          : 'Start Ollama to enable local language interpretation.',
  };
}
