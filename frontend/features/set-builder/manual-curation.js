/** Manual, evidence-rich catalog browsing for track-by-track Set Builder authoring. */

import { applyExplicitSetPlanChoice } from './plan-integrity.js';
import { setTrackAudioUrl } from './track-media.js';

const SEARCH_WEIGHTS = Object.freeze({
  title: 30,
  artist: 24,
  playlist: 22,
  descriptor: 20,
  identity: 18,
  genre: 16,
  role: 14,
  metadata: 8,
});
const RESULT_LIMIT = 12;

export function nextManualResultLimit(current, total, batchSize = RESULT_LIMIT) {
  const batch = Math.max(1, Number(batchSize) || RESULT_LIMIT);
  return Math.min(Math.max(0, Number(total) || 0), Math.max(batch, (Number(current) || 0) + batch));
}

export function normalizeManualSearchText(value) {
  return String(value || '')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[_/|]+/g, ' ')
    .replace(/[^a-z0-9&+.-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function manualSearchTerms(query) {
  const terms = [];
  const source = String(query || '');
  const matcher = /"([^"]+)"|([^,\s]+)/g;
  for (const match of source.matchAll(matcher)) {
    const normalized = normalizeManualSearchText(match[1] || match[2]);
    if (normalized && !terms.includes(normalized)) terms.push(normalized);
  }
  return terms;
}

function evidenceEntry(source, label, value) {
  const normalized = normalizeManualSearchText(value);
  return normalized ? { source, label, value: String(value).trim(), normalized } : null;
}

export function manualTrackSearchEvidence(track, { identityTerms = [], roles = [], metadata = [] } = {}) {
  const descriptors = Array.isArray(track?._descriptors) ? track._descriptors : [];
  const playlists = Array.isArray(track?._playlistIdentity) ? track._playlistIdentity : [];
  return [
    evidenceEntry('title', 'Title', String(track?.source_name || track?.title || '').replace(/\.[^.]+$/, '')),
    evidenceEntry('artist', 'Artist', track?.artist),
    evidenceEntry('genre', 'Genre', track?._genre),
    evidenceEntry('genre', 'Detailed genre', track?._detailedGenre),
    ...descriptors.flatMap((item) => [
      evidenceEntry('descriptor', item?.category ? `Tag · ${item.category}` : 'Tag', item?.value),
      evidenceEntry('descriptor', 'Tag category', item?.category),
    ]),
    ...playlists.flatMap((item) => [
      evidenceEntry('playlist', 'Playlist', item?.value || item?.name || item),
      evidenceEntry('playlist', 'Playlist source', item?.source),
    ]),
    ...identityTerms.map((value) => evidenceEntry('identity', 'Identity', value)),
    ...roles.map((value) => evidenceEntry('role', 'Role / vibe', value)),
    ...metadata.map((value) => evidenceEntry('metadata', 'Audio profile', value)),
  ].filter(Boolean);
}

export function scoreManualTrackSearch(track, query, options = {}) {
  const terms = manualSearchTerms(query);
  const evidence = manualTrackSearchEvidence(track, options);
  if (!terms.length) return { matched: true, score: 0, matchedTerms: [], evidence: [] };
  const matches = terms.map((term) => {
    const entries = evidence.filter((item) => item.normalized.includes(term));
    return { term, entries };
  });
  const matchedTerms = matches.filter((match) => match.entries.length).map((match) => match.term);
  const matched = options.requireAll ? matchedTerms.length === terms.length : Boolean(matchedTerms.length);
  if (!matched) return { matched: false, score: 0, matchedTerms, evidence: [] };
  const uniqueEvidence = [];
  let score = 0;
  matches.forEach(({ term, entries }) => {
    const strongest = entries.sort((left, right) => SEARCH_WEIGHTS[right.source] - SEARCH_WEIGHTS[left.source])[0];
    if (!strongest) return;
    score += SEARCH_WEIGHTS[strongest.source];
    if (strongest.normalized === term) score += 6;
    if (!uniqueEvidence.some((item) => item.source === strongest.source && item.value === strongest.value))
      uniqueEvidence.push(strongest);
  });
  const phrase = normalizeManualSearchText(query);
  if (phrase && evidence.some((item) => item.normalized.includes(phrase))) score += 18;
  score += matchedTerms.length * matchedTerms.length * 5;
  return { matched: true, score, matchedTerms, evidence: uniqueEvidence };
}

export function searchManualCatalog(tracks, query, options = {}) {
  return (tracks || [])
    .map((track) => ({ track, ...scoreManualTrackSearch(track, query, options) }))
    .filter((result) => result.matched)
    .sort(
      (left, right) =>
        right.score - left.score ||
        String(left.track?.source_name || '').localeCompare(String(right.track?.source_name || '')),
    );
}

export function suggestManualPlanOrder(plan, { brief, improveOrder, health, trackId }) {
  const current = [...(plan || [])];
  if (current.length < 2) return null;
  const suggested = improveOrder(current, brief);
  const currentIds = current.map(trackId);
  const suggestedIds = suggested.map(trackId);
  return {
    currentHealth: health(current).score,
    suggestedHealth: health(suggested).score,
    changed: currentIds.some((id, index) => id !== suggestedIds[index]),
    currentFingerprint: currentIds.join('|'),
    suggested,
  };
}

export function createManualCurationController({ state, dom, ui, music, policy, transitions, lifecycle }) {
  const { $, escapeHtml } = dom;
  const { bindCompactAudio, compactAudioMarkup } = ui;
  const { energyBand, formatLibraryKey, libraryRoles, songEnergy, timingProfile, vocalProfile } = music;
  const { setCandidateScore, setRecordingKey, setTrackId, trackIdentity } = policy;
  const {
    advancePlanRevision,
    confirmAction,
    pushSetHistory,
    renderSetPlan,
    resetWorkspace,
    setBrief,
    setPlanningReceipt,
  } = lifecycle;
  const { improveSetOrder, setHealth } = transitions;
  const host = () => $('#set-manual-curation-workspace');
  const runningOrder = () => document.querySelector('.set-running-order-workspace');
  let searchTimer = 0;
  let orderSuggestion = null;
  let visibleResultLimit = RESULT_LIMIT;

  function resetVisibleResults() {
    visibleResultLimit = RESULT_LIMIT;
  }

  function presentRunningOrder(active) {
    const layout = $('#set-manual-curation-layout');
    const order = runningOrder();
    if (!layout || !order) return;
    if (active) {
      $('#set-manual-running-order-slot')?.append(order);
      layout.hidden = false;
    } else {
      const anchor = $('#set-running-order-anchor');
      if (anchor && order.previousElementSibling !== anchor) anchor.after(order);
      layout.hidden = true;
    }
  }

  function refreshRunningOrderCount() {
    const count = $('#set-manual-running-order-count');
    if (count) count.textContent = `${state.plan.length} track${state.plan.length === 1 ? '' : 's'}`;
  }

  function planFingerprint() {
    return state.plan.map(setTrackId).join('|');
  }

  function trackName(track) {
    return String(track?.source_name || track?.title || 'Untitled').replace(/\.[^.]+$/, '');
  }

  function renderCoach() {
    const root = $('#set-manual-coach');
    if (!root) return;
    if (orderSuggestion && orderSuggestion.currentFingerprint !== planFingerprint()) orderSuggestion = null;
    const health = state.plan.length > 1 ? setHealth(state.plan).score : null;
    root.querySelector('.set-manual-coach-health').textContent =
      health == null ? `${state.plan.length} track${state.plan.length === 1 ? '' : 's'}` : `${health}/100 mix health`;
    const status = $('#set-manual-coach-status');
    if (!orderSuggestion) {
      status.innerHTML =
        state.plan.length < 2
          ? '<p>Add at least two tracks to compare possible running orders. Next-track suggestions are available now.</p>'
          : '<p>Your current order is ready to evaluate. Locked tracks and journey sections will stay in place.</p>';
      return;
    }
    if (!orderSuggestion.changed) {
      status.innerHTML = `<p><strong>Current order looks strongest.</strong> Mix health is ${orderSuggestion.currentHealth}/100. Try next-track suggestions if you want another direction.</p>`;
      return;
    }
    const names = orderSuggestion.suggested.map((track, index) => `<li><b>${index + 1}</b>${escapeHtml(trackName(track))}</li>`).join('');
    const delta = orderSuggestion.suggestedHealth - orderSuggestion.currentHealth;
    const explanation =
      delta > 0
        ? `Mix health improves by ${delta} point${delta === 1 ? '' : 's'}.`
        : 'Mix health is preserved while energy and genre placement improve.';
    status.innerHTML = `<div class="set-manual-order-proposal"><p><strong>Suggested order</strong><span>${orderSuggestion.currentHealth} → ${orderSuggestion.suggestedHealth} mix health · ${explanation}</span></p><ol>${names}</ol><div><button type="button" class="button tertiary dismiss-manual-order">Dismiss</button><button type="button" class="button primary apply-manual-order">Apply order</button></div></div>`;
    status.querySelector('.dismiss-manual-order').onclick = () => {
      orderSuggestion = null;
      renderCoach();
    };
    status.querySelector('.apply-manual-order').onclick = () => {
      pushSetHistory();
      state.plan = [...orderSuggestion.suggested];
      orderSuggestion = null;
      advancePlanRevision();
      renderSetPlan();
      $('#set-builder-message').textContent = 'Suggested running order applied. Undo is available if you prefer the previous order.';
    };
  }

  function suggestOrder() {
    if (state.plan.length < 2) {
      $('#set-builder-message').textContent = 'Add at least two tracks before asking Set Coach to compare orders.';
      renderCoach();
      return;
    }
    orderSuggestion = suggestManualPlanOrder(state.plan, {
      brief: setBrief(),
      improveOrder: improveSetOrder,
      health: setHealth,
      trackId: setTrackId,
    });
    renderCoach();
  }

  function showNextSuggestions() {
    const root = host();
    state.manualSearchQuery = '';
    state.manualSuggestionsRequested = true;
    resetVisibleResults();
    $('#set-manual-search').value = '';
    root.querySelector('.set-manual-search-status').textContent = 'Finding the strongest next-track options…';
    requestAnimationFrame(() => {
      renderResults();
      root.querySelector('.set-manual-results')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  function searchOptions(track) {
    const energy = energyBand(songEnergy(track));
    return {
      requireAll: state.manualSearchRequireAll,
      identityTerms: trackIdentity(track),
      roles: libraryRoles(track),
      metadata: [
        `${energy} energy`,
        vocalProfile(track),
        timingProfile(track),
        track.key,
        track.bpm ? `${Math.round(Number(track.bpm))} bpm` : '',
      ].filter(Boolean),
    };
  }

  function recommendationScore(track) {
    const previous = state.plan.at(-1) || null;
    try {
      return setCandidateScore(track, previous, state.plan.length, state.plan.length + 1, setBrief());
    } catch (_) {
      return 0;
    }
  }

  function results() {
    const query = state.manualSearchQuery;
    if (!query.trim() && !state.manualSuggestionsRequested) return { idle: true, items: [], total: 0 };
    const matches = state.library
      .map((track) => ({ ...scoreManualTrackSearch(track, query, searchOptions(track)), track }))
      .filter((result) => result.matched);
    const total = matches.length;
    if (!query.trim()) {
      const items = matches
        .map((result) => ({ ...result, fit: recommendationScore(result.track) }))
        .sort((left, right) => right.fit - left.fit)
        .slice(0, visibleResultLimit);
      return { idle: false, items, total };
    }
    const items = matches
      .sort((left, right) => right.score - left.score)
      .slice(0, Math.max(RESULT_LIMIT * 5, visibleResultLimit * 3))
      .map((result) => ({ ...result, fit: recommendationScore(result.track) }))
      .sort((left, right) => right.score - left.score || right.fit - left.fit)
      .slice(0, visibleResultLimit);
    return { idle: false, items, total };
  }

  function evidenceMarkup(result) {
    const evidence = result.evidence.length
      ? result.evidence.slice(0, 4)
      : manualTrackSearchEvidence(result.track, searchOptions(result.track))
          .filter((item) => ['playlist', 'descriptor', 'genre', 'role'].includes(item.source))
          .slice(0, 3);
    return evidence
      .map((item) => `<span><b>${escapeHtml(item.label)}</b> · ${escapeHtml(item.value)}</span>`)
      .join('');
  }

  function addTrack(track) {
    if (!track) return;
    if (state.plan.some((item) => setRecordingKey(item) === setRecordingKey(track))) {
      $('#set-builder-message').textContent = 'That song family is already represented. Choose another recording.';
      return;
    }
    pushSetHistory();
    orderSuggestion = null;
    state.plan.push(track);
    applyExplicitSetPlanChoice(state, track);
    advancePlanRevision();
    renderSetPlan();
    $('#set-builder-message').textContent =
      `${String(track.source_name || 'Track').replace(/\.[^.]+$/, '')} added at position ${state.plan.length}.`;
  }

  function renderResults() {
    const root = host();
    if (!root || root.hidden) return;
    const list = root.querySelector('.set-manual-results');
    const status = root.querySelector('.set-manual-search-status');
    const usedFamilies = new Set(state.plan.map(setRecordingKey));
    const { idle, items: matches, total } = results();
    const hiddenCount = Math.max(0, total - matches.length);
    status.textContent = idle
      ? 'Search your catalog by any identity signal, or ask for compatibility-ranked suggestions.'
      : state.manualSearchQuery
        ? `${matches.length} of ${total} results · matched across title, artist, genre, playlist, tags, roles, and audio profile.`
        : `${matches.length} of ${total} compatibility-ranked suggestions for position ${state.plan.length + 1}.`;
    list.innerHTML = idle
      ? '<div class="set-manual-empty"><strong>Your catalog is ready.</strong><p>Type any genre, playlist, tag, artist, mood, or keyword combination—or choose “Suggest next.”</p></div>'
      : matches.length
        ? matches
            .map((result, index) => {
              const { track } = result;
              const used = usedFamilies.has(setRecordingKey(track));
              const source = setTrackAudioUrl(track);
              const preview = source ? compactAudioMarkup(source, track.duration_seconds, true) : '';
              const name = String(track.source_name || track.title || 'Untitled').replace(/\.[^.]+$/, '');
              return `<article class="set-manual-result${used ? ' is-used' : ''}" data-result-index="${index}" tabindex="-1"><header><div><strong>${escapeHtml(name)}</strong><span class="set-manual-result-artist">${escapeHtml(track.artist || 'Unknown artist')}</span><span class="set-manual-result-genre">${escapeHtml(track._genre || 'Unclassified')}</span></div><em><b>${Math.round(result.fit)}</b><span>fit</span></em></header><ul class="set-manual-result-facts"><li>${Number(track.bpm || 0).toFixed(1)} BPM</li><li>${escapeHtml(formatLibraryKey(track.key))}</li><li>${escapeHtml(energyBand(songEnergy(track)))} energy</li></ul><div class="set-manual-evidence">${evidenceMarkup(result)}</div><footer>${preview || '<span class="set-manual-no-preview">Preview unavailable</span>'}<button type="button" class="button ${used ? 'tertiary' : 'secondary'} add-manual-track" ${used ? 'disabled' : ''}>${used ? 'Already in set' : `Add at ${state.plan.length + 1}`}</button></footer></article>`;
            })
            .join('') +
          (hiddenCount
            ? `<div class="set-manual-results-more"><span><b>${matches.length}</b> visible · ${hiddenCount} more match${hiddenCount === 1 ? '' : 'es'}</span><button type="button" class="button secondary load-more-manual-results">Show ${Math.min(RESULT_LIMIT, hiddenCount)} more</button></div>`
            : '')
        : '<div class="set-manual-empty"><strong>No tracks match those keywords.</strong><p>Try fewer terms, turn off “Require every keyword,” or search a playlist, artist, role, mood, or descriptor.</p></div>';
    list.querySelectorAll('.add-manual-track:not(:disabled)').forEach((button) => {
      button.onclick = () => addTrack(matches[Number(button.closest('article').dataset.resultIndex)]?.track);
    });
    list.querySelector('.load-more-manual-results')?.addEventListener('click', () => {
      const previousCount = matches.length;
      visibleResultLimit = nextManualResultLimit(visibleResultLimit, total);
      renderResults();
      list.querySelector(`.set-manual-result[data-result-index="${previousCount}"]`)?.focus();
    });
    bindCompactAudio(list);
  }

  function mount() {
    const root = host();
    if (root.dataset.mounted === 'true') return;
    root.dataset.mounted = 'true';
    root.innerHTML = `<header><div><p class="eyebrow">YOUR CATALOG</p><h3 id="set-manual-curation-heading">Find the next track</h3><p>Search the full identity of your music—not only its genre. Results explain whether a title, artist, playlist, tag, role, vibe, or audio profile matched.</p></div><div class="set-manual-tools"><button type="button" class="button secondary check-manual-transitions">Check transitions</button></div></header><div class="set-manual-search-row"><label><span>Genre, playlist, tag, artist, mood, or keywords</span><input id="set-manual-search" type="search" autocomplete="off" placeholder="Try: latin techno percussion, Disco_Rave, vocal peak-time…"></label><label class="set-manual-match-all"><input id="set-manual-match-all" type="checkbox"><span><strong>Require every keyword</strong><small>Useful when a broad search returns too many tracks.</small></span></label></div><div class="set-manual-search-meta"><p class="set-manual-search-status" role="status" aria-live="polite"></p><button type="button" class="button tertiary clear-manual-search">Clear search</button></div><div class="set-manual-results"></div>`;
    const input = $('#set-manual-search');
    input.value = state.manualSearchQuery;
    input.oninput = () => {
      state.manualSearchQuery = input.value;
      state.manualSuggestionsRequested = false;
      resetVisibleResults();
      clearTimeout(searchTimer);
      root.querySelector('.set-manual-search-status').textContent = input.value.trim()
        ? 'Searching titles, artists, playlists, tags, roles, and audio profiles…'
        : 'Search your catalog by any identity signal, or ask for compatibility-ranked suggestions.';
      searchTimer = setTimeout(renderResults, 120);
    };
    $('#set-manual-match-all').checked = state.manualSearchRequireAll;
    $('#set-manual-match-all').onchange = (event) => {
      state.manualSearchRequireAll = event.currentTarget.checked;
      resetVisibleResults();
      renderResults();
    };
    root.querySelector('.clear-manual-search').onclick = () => {
      state.manualSearchQuery = '';
      state.manualSuggestionsRequested = false;
      resetVisibleResults();
      input.value = '';
      renderResults();
      input.focus();
    };
    $('#set-manual-coach').querySelector('.suggest-manual-order').onclick = suggestOrder;
    $('#set-manual-coach').querySelector('.suggest-manual-next').onclick = showNextSuggestions;
    root.querySelector('.check-manual-transitions').onclick = () => {
      const health = $('#set-health');
      if (state.plan.length < 2) {
        $('#set-builder-message').textContent = 'Add at least two tracks before checking transitions.';
        return;
      }
      health.hidden = false;
      health.open = true;
      health.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    };
  }

  function syncPlanShell() {
    const empty = !state.plan.length;
    refreshRunningOrderCount();
    renderCoach();
    $('#set-result').classList.toggle('manual-curation-empty', empty);
    const selectors = ['#set-health', '#set-selection-summary', '#set-review-panel', '.set-journey', '#set-export-status'];
    selectors.forEach((selector) => {
      const element = $(selector);
      if (element) element.hidden = empty;
    });
    if (!empty) return;
    $('#set-result-summary').textContent = '0 tracks · start by searching your catalog below';
    $('#set-track-list').innerHTML =
      '<div class="empty"><strong>Your running order is empty.</strong><p>Preview a catalog result, then add it as the first track.</p></div>';
    $('#set-warnings').replaceChildren();
    $('#save-set').disabled = true;
    ['#export-set-csv', '#export-set-m3u'].forEach((selector) => {
      $(selector).disabled = true;
    });
  }

  function render() {
    const root = host();
    if (!root) return;
    root.hidden = !state.manualCurationActive;
    presentRunningOrder(state.manualCurationActive);
    if (root.hidden) {
      $('.set-workspace-title .eyebrow').textContent = 'GENERATED RUNNING ORDER';
      $('.set-workspace-action-bar strong').textContent = 'Shape this revision';
      $('.set-workspace-action-bar span').textContent =
        'Lock what works, then regenerate only the remaining tracks.';
      $('#set-result').classList.remove('manual-curation-empty');
      if (state.plan.length) syncPlanShell();
      return;
    }
    $('.set-workspace-title .eyebrow').textContent = 'CURATED RUNNING ORDER';
    $('.set-workspace-action-bar strong').textContent = 'Curate this set';
    $('.set-workspace-action-bar span').textContent = 'Preview, reorder, and check each transition as you build.';
    mount();
    const input = $('#set-manual-search');
    if (document.activeElement !== input) input.value = state.manualSearchQuery;
    $('#set-manual-match-all').checked = state.manualSearchRequireAll;
    renderResults();
    syncPlanShell();
  }

  async function start() {
    if (state.manualCurationActive) {
      host()?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      $('#set-manual-search')?.focus({ preventScroll: true });
      $('#set-builder-message').textContent = 'Manual catalog is open and ready to search.';
      return true;
    }
    if (state.plan.length && !state.manualCurationActive) {
      const replace = await confirmAction(
        'Start a new track-by-track set? The current unsaved running order will be replaced.',
        { title: 'Start manual curation', acceptLabel: 'Start new set' },
      );
      if (!replace) return false;
    }
    if (!state.manualCurationActive) resetWorkspace();
    state.manualCurationActive = true;
    setPlanningReceipt({
      mode: 'manual-curation',
      provider: 'manual',
      summary: 'Tracks selected directly from the catalog by the DJ.',
    });
    $('#set-builder-message').textContent = 'Opening the manual catalog…';
    renderSetPlan();
    await new Promise((resolve) => requestAnimationFrame(resolve));
    host()?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    $('#set-manual-search')?.focus({ preventScroll: true });
    $('#set-builder-message').textContent =
      'Manual catalog ready. Search any genre, playlist, tag, artist, role, vibe, or combination of keywords.';
    return true;
  }

  return Object.freeze({ render, start });
}
