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

export function createManualCurationController({ state, dom, ui, music, policy, lifecycle }) {
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
  const host = () => $('#set-manual-curation-workspace');

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
    return state.library
      .map((track) => ({ ...scoreManualTrackSearch(track, query, searchOptions(track)), track }))
      .filter((result) => result.matched)
      .map((result) => ({ ...result, fit: recommendationScore(result.track) }))
      .sort((left, right) => right.score - left.score || right.fit - left.fit)
      .slice(0, 40);
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
    const matches = results();
    status.textContent = state.manualSearchQuery
      ? `${matches.length} best match${matches.length === 1 ? '' : 'es'} across titles, artists, genres, playlists, tags, roles, and audio profiles.`
      : `Showing ${matches.length} strong starting points. Type any genre, playlist name, tag, artist, mood, or combination of keywords.`;
    list.innerHTML = matches.length
      ? matches
          .map((result, index) => {
            const { track } = result;
            const used = usedFamilies.has(setRecordingKey(track));
            const source = setTrackAudioUrl(track);
            const preview = source ? compactAudioMarkup(source, track.duration_seconds, true) : '';
            const name = String(track.source_name || track.title || 'Untitled').replace(/\.[^.]+$/, '');
            return `<article class="set-manual-result${used ? ' is-used' : ''}" data-result-index="${index}"><header><div><strong>${escapeHtml(name)}</strong><span>${track.artist ? `${escapeHtml(track.artist)} · ` : ''}${escapeHtml(track._genre || 'Unclassified')}</span></div><em>${Math.round(result.fit)} fit</em></header><p>${Number(track.bpm || 0).toFixed(1)} BPM · ${escapeHtml(formatLibraryKey(track.key))} · ${escapeHtml(energyBand(songEnergy(track)))} energy</p><div class="set-manual-evidence">${evidenceMarkup(result)}</div><footer>${preview || '<span class="set-manual-no-preview">Preview unavailable</span>'}<button type="button" class="button ${used ? 'tertiary' : 'secondary'} add-manual-track" ${used ? 'disabled' : ''}>${used ? 'Song already used' : `Add at ${state.plan.length + 1}`}</button></footer></article>`;
          })
          .join('')
      : '<div class="set-manual-empty"><strong>No tracks match those keywords.</strong><p>Try fewer terms, turn off “Require every keyword,” or search a playlist, artist, role, mood, or descriptor.</p></div>';
    list.querySelectorAll('.add-manual-track:not(:disabled)').forEach((button) => {
      button.onclick = () => addTrack(matches[Number(button.closest('article').dataset.resultIndex)]?.track);
    });
    bindCompactAudio(list);
  }

  function mount() {
    const root = host();
    if (root.dataset.mounted === 'true') return;
    root.dataset.mounted = 'true';
    root.innerHTML = `<header><div><p class="eyebrow">YOUR CATALOG</p><h3 id="set-manual-curation-heading">Find the next track</h3><p>Search the full identity of your music—not only its genre. Results explain whether a title, artist, playlist, tag, role, vibe, or audio profile matched.</p></div><div class="set-manual-tools"><button type="button" class="button secondary suggest-manual-track">Suggest next</button><button type="button" class="button secondary check-manual-transitions">Check transitions</button></div></header><div class="set-manual-search-row"><label><span>Genre, playlist, tag, artist, mood, or keywords</span><input id="set-manual-search" type="search" autocomplete="off" placeholder="Try: latin techno percussion, Disco_Rave, vocal peak-time…"></label><label class="set-manual-match-all"><input id="set-manual-match-all" type="checkbox"><span><strong>Require every keyword</strong><small>Useful when a broad search returns too many tracks.</small></span></label></div><div class="set-manual-search-meta"><p class="set-manual-search-status" role="status" aria-live="polite"></p><button type="button" class="button tertiary clear-manual-search">Clear search</button></div><div class="set-manual-results"></div>`;
    const input = $('#set-manual-search');
    input.value = state.manualSearchQuery;
    input.oninput = () => {
      state.manualSearchQuery = input.value;
      renderResults();
    };
    $('#set-manual-match-all').checked = state.manualSearchRequireAll;
    $('#set-manual-match-all').onchange = (event) => {
      state.manualSearchRequireAll = event.currentTarget.checked;
      renderResults();
    };
    root.querySelector('.clear-manual-search').onclick = () => {
      state.manualSearchQuery = '';
      input.value = '';
      renderResults();
      input.focus();
    };
    root.querySelector('.suggest-manual-track').onclick = () => {
      state.manualSearchQuery = '';
      input.value = '';
      renderResults();
      listFirstResult(root)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    };
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

  function listFirstResult(root) {
    return root.querySelector('.set-manual-result');
  }

  function syncPlanShell() {
    const empty = !state.plan.length;
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
    renderSetPlan();
    host()?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    $('#set-builder-message').textContent =
      'Manual catalog ready. Search any genre, playlist, tag, artist, role, vibe, or combination of keywords.';
    return true;
  }

  return Object.freeze({ render, start });
}
