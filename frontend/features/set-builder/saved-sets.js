/** Durable saved-set loading, recovery, persistence, and export ownership. */

import {
  createSavedSetLifecycle,
  restoreSavedSetIdentity,
  savedSetRecordIdentity,
} from './saved-set-lifecycle.js';
export function buildSetCsv({
  plan,
  compatibility,
  transitionSettings,
  camelotKey,
  energyBand,
  songEnergy,
  libraryRoles,
}) {
  const rows = [
    [
      'Position',
      'Track',
      'BPM',
      'Key',
      'Camelot',
      'Energy',
      'Genre',
      'Roles',
      'Transition Match',
      'Mix In',
      'Mix Out',
      'Transition Bars',
      'Fade Curve',
      'Technique',
      'Tempo Sync',
      'Transition Notes',
    ],
  ];
  plan.forEach((track, index) => {
    const match = index ? compatibility(plan[index - 1], track) : null;
    const settings = index ? transitionSettings(index) : {};
    rows.push([
      index + 1,
      track.source_name,
      Number(track.bpm || 0).toFixed(1),
      track.key || '',
      camelotKey(track.key),
      energyBand(songEnergy(track)),
      track._genre,
      libraryRoles(track).join('; '),
      match?.score ?? '',
      index ? settings.mixIn : (track.mix_in ?? ''),
      index ? settings.mixOut : (track.mix_out ?? ''),
      settings.bars || '',
      settings.curve || '',
      settings.technique || '',
      index ? (settings.tempoSync ? 'yes' : 'no') : '',
      settings.notes || '',
    ]);
  });
  return rows.map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(',')).join('\n');
}

export function buildSetM3u(entries) {
  return [
    '#EXTM3U',
    ...entries.flatMap(({ track, path }) => [
      `#EXTINF:${Math.round(track.duration_seconds || 0)},${track.artist ? `${track.artist} - ` : ''}${track.source_name.replace(/\.[^.]+$/, '')}`,
      path,
    ]),
  ].join('\r\n');
}

export function createSavedSetController({ state, dom, api, storageKeys, authoring, plan, music, feedback }) {
  const { $, $$, option, escapeHtml, notify } = dom;
  const { SET_STORAGE_KEY, SET_STORAGE_MIGRATION_KEY } = storageKeys;
  const {
    inferSetWorkflow,
    interpretSetIntention,
    applyIntentionInterpretation,
    populateSetDetailedGenres,
    renderSetGenreMix,
    renderSetDetailedGenres,
    renderExcludedSetGenres,
    workflow,
  } = authoring;
  const {
    setBrief,
    setTrackId,
    setRecordingKey = setTrackId,
    getPlanningReceipt,
    setPlanningReceipt,
    renderSetRules,
    autoOptimizeSetTransitions,
    renderSetPlan,
    transitionSettings,
  } = plan;
  const { compatibility, trackMatchesSetGenre, camelotKey, energyBand, songEnergy, libraryRoles } = music;
  const { recordPreference } = feedback;
  let savedSetRecords = [];
  const setBuilderApi = api;

  function cachedSavedSets() {
    try {
      return JSON.parse(localStorage.getItem(SET_STORAGE_KEY) || '[]');
    } catch (_) {
      return [];
    }
  }
  function savedSets() {
    return savedSetRecords;
  }
  function cacheSavedSets(sets) {
    savedSetRecords = sets;
    localStorage.setItem(SET_STORAGE_KEY, JSON.stringify(sets));
    renderSavedSets();
  }
  const lifecycle = createSavedSetLifecycle({ state, api: setBuilderApi, savedSets, cacheSavedSets });
  async function loadSavedSets() {
    const legacy = cachedSavedSets(),
      needsMigration = localStorage.getItem(SET_STORAGE_MIGRATION_KEY) !== 'true';
    try {
      let result = await setBuilderApi.savedSets();
      if (needsMigration && legacy.length) result = (await setBuilderApi.migrateSavedSets(legacy)).document;
      savedSetRecords = result.sets || [];
      localStorage.setItem(SET_STORAGE_KEY, JSON.stringify(savedSetRecords));
      localStorage.setItem(SET_STORAGE_MIGRATION_KEY, 'true');
    } catch (error) {
      savedSetRecords = legacy;
      console.warn('Durable saved sets unavailable; using browser recovery cache:', error);
    }
  }
  function renderSavedSets() {
    const select = $('#saved-set-select');
    const current = select.value;
    const sets = savedSets();
    select.replaceChildren(
      option('', 'Choose a saved set'),
      ...sets.map((set) => option(set.id, `${set.name} · ${set.tracks.length} tracks`)),
    );
    select.value = sets.some((set) => set.id === current) ? current : '';
  }
  async function saveCurrentSet() {
    if (!state.plan.length) return;
    const button = $('#save-set');
    const sets = [...savedSets()];
    const identity = savedSetRecordIdentity(state, $('#saved-set-select').value);
    const { id } = identity;
    const record = {
      ...identity,
      name: setBrief().name,
      brief: setBrief(),
      planningMode: $('#set-planning-mode').value,
      planningReceipt: getPlanningReceipt(),
      tracks: state.plan.map(setTrackId),
      trackDetails: state.plan.map((track) => ({
        id: setTrackId(track),
        source_name: track.source_name,
        artist: track.artist || '',
        genre: track._genre,
        bpm: Number(track.bpm || 0),
        key: track.key || '',
        selectionReason: track._aiSelectionReason || null,
        sectionId: track._planSectionId || null,
      })),
      transitions: structuredClone(state.transitionSettings),
      locked: [...state.lockedIds],
      required: [...state.requiredIds],
      excluded: [...state.excludedIds],
      updatedAt: new Date().toISOString(),
    };
    button.disabled = true;
    button.textContent = 'Saving…';
    try {
      await setBuilderApi.saveSet(record);
      const existing = sets.findIndex((set) => set.id === id);
      existing >= 0 ? sets.splice(existing, 1, record) : sets.unshift(record);
      cacheSavedSets(sets);
      void recordPreference('save', state.plan);
      state.activeSavedSetId = id;
      $('#saved-set-select').value = id;
      renderSetPlan();
      const entries = setM3uEntries();
      try {
        const result = await setBuilderApi.savePlaylist({
          name: record.name,
          tracks: entries.map(({ track, path }) => ({
            path,
            title: `${track.artist ? `${track.artist} - ` : ''}${track.source_name.replace(/\.[^.]+$/, '')}`,
            duration_seconds: Number(track.duration_seconds || 0),
          })),
        });
        $('#set-builder-message').textContent = `Set saved durably · playlist written to ${result.path}`;
      } catch (error) {
        $('#set-builder-message').textContent =
          `Set saved durably and will survive restart. The optional playlist file needs attention: ${error.message || error}`;
      }
    } catch (error) {
      $('#set-builder-message').textContent = `Set was not saved: ${error.message || error}`;
      notify('The set could not be saved. Your current draft remains open.', 'danger');
    } finally {
      button.disabled = false;
      button.textContent = 'Save set';
    }
  }
  function recoveryScore(candidate, detail, previous) {
    const wanted = String(detail?.source_name || detail?.id || '')
      .toLowerCase()
      .replace(/\.[^.]+$/, '');
    const words = wanted.split(/\W+/).filter((word) => word.length > 2);
    const haystack = `${candidate.source_name} ${candidate.artist || ''}`.toLowerCase();
    const titleScore = words.length ? (words.filter((word) => haystack.includes(word)).length / words.length) * 45 : 0;
    const genreScore = detail?.genre && trackMatchesSetGenre(candidate, detail.genre) ? 25 : 0;
    const bpmScore = detail?.bpm ? Math.max(0, 20 - Math.abs(Number(candidate.bpm || 0) - Number(detail.bpm))) : 0;
    return titleScore + genreScore + bpmScore + (previous ? compatibility(previous, candidate).score * 0.15 : 0);
  }
  async function loadSavedSet(record) {
    if (!record) return;
    const byId = new Map(state.library.map((track) => [setTrackId(track), track]));
    const brief = record.brief || {};
    Object.entries(brief).forEach(([key, value]) => {
      if (['genres', 'detailedGenres', 'excludedGenres', 'genreWeights', 'identity'].includes(key)) return;
      const element = $(`#set-${key.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)}`);
      if (element && value !== Infinity && !Array.isArray(value)) element.value = value;
    });
    const savedIdentity = brief.identity || interpretSetIntention('');
    $('#set-intention').value = savedIdentity.text || '';
    if (
      savedIdentity.text ||
      savedIdentity.required?.length ||
      savedIdentity.preferred?.length ||
      savedIdentity.avoided?.length
    )
      applyIntentionInterpretation(savedIdentity, { announce: false });
    else $('#set-intention-interpretation').hidden = true;
    const savedGenres = brief.genres || (brief.genre && brief.genre !== 'all' ? [brief.genre] : []);
    [...$('#set-genre').options].forEach((option) => {
      option.selected = savedGenres.length ? savedGenres.includes(option.value) : option.value === 'all';
    });
    populateSetDetailedGenres(brief.detailedGenres || []);
    [...$('#set-excluded-genres').options].forEach((option) => {
      option.selected = (brief.excludedGenres || []).includes(option.value);
    });
    state.genreSelectionOrder = [...savedGenres];
    renderSetGenreMix();
    renderSetDetailedGenres();
    renderExcludedSetGenres();
    Object.entries(brief.genreWeights || {}).forEach(([genre, value]) => {
      const input = [...$('#set-genre-weights').querySelectorAll('input')].find((item) => item.dataset.genre === genre);
      if (input) input.value = value;
    });
    $('#set-genre').dispatchEvent(new Event('change', { bubbles: true }));
    $('#set-detailed-genres').dispatchEvent(new Event('change', { bubbles: true }));
    $('#set-excluded-genres').dispatchEvent(new Event('change', { bubbles: true }));
    const details = new Map((record.trackDetails || []).map((item) => [item.id, item]));
    const used = new Set();
    const recoveredPlan = [];
    let recovered = 0;
    (record.tracks || []).forEach((id) => {
      let track = byId.get(id);
      if (track && used.has(setRecordingKey(track))) track = null;
      if (!track) {
        track = state.library
          .filter((candidate) => !used.has(setRecordingKey(candidate)))
          .map((candidate) => ({
            candidate,
            score: recoveryScore(candidate, details.get(id) || { id }, recoveredPlan.at(-1)),
          }))
          .sort((a, b) => b.score - a.score)[0]?.candidate;
        if (track) recovered += 1;
      }
      if (track) {
        const detail = details.get(id);
        track._aiSelectionReason = detail?.selectionReason || null;
        track._planSectionId = detail?.sectionId || null;
        used.add(setRecordingKey(track));
        recoveredPlan.push(track);
      }
    });
    state.plan = recoveredPlan;
    setPlanningReceipt(record.planningReceipt || null);
    state.revisionComparison = record.planningReceipt?.regeneration || null;
    restoreSavedSetIdentity(state, record);
    $('#saved-set-select').value = record.id;
    const savedWorkflow = inferSetWorkflow(record.planningMode, Boolean(savedIdentity.text));
    $$('[name="set-track-planner"]').forEach((input) => {
      input.checked = input.value === savedWorkflow.trackPlanner;
    });
    workflow.applyBriefMode(brief.authoringMode || savedWorkflow.authoringMode, { announce: false });
    workflow.syncPlanningMode();
    state.lockedIds = new Set(record.locked || []);
    state.requiredIds = new Set(record.required || []);
    state.excludedIds = new Set(record.excluded || []);
    state.transitionSettings = record.transitions || {};
    state.proposals = [];
    state.activeProposal = '';
    state.history = [];
    state.future = [];
    renderSetRules();
    const optimized = await autoOptimizeSetTransitions();
    renderSetPlan();
    $('#set-builder-message').textContent =
      (recovered
        ? `Loaded set and recovered ${recovered} unavailable track${recovered === 1 ? '' : 's'} with the closest Library matches.`
        : 'Saved set loaded with every track available.') +
      (optimized
        ? ` Optimized ${optimized} transition${optimized === 1 ? '' : 's'} that previously used defaults.`
        : '');
  }

  function downloadSetText(filename, text, type = 'text/plain') {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function safeSetFilename() {
    return (setBrief().name || 'DJ Set').replace(/[^\w .-]+/g, '').trim() || 'DJ Set';
  }
  function exportSetCsv() {
    downloadSetText(
      `${safeSetFilename()}.csv`,
      buildSetCsv({
        plan: state.plan,
        compatibility,
        transitionSettings,
        camelotKey,
        energyBand,
        songEnergy,
        libraryRoles,
      }),
      'text/csv',
    );
    void recordPreference('export', state.plan);
  }
  function setM3uEntries() {
    const preference = setBrief().edits;
    return state.plan.map((track) => {
      const extended = track._hasExtended ? track._job?.extended_path : '';
      const original =
        track._libraryPath ||
        track._job?.library_path ||
        track.file_path ||
        track.wav_path ||
        track._job?.wav_path ||
        track.output_path;
      return { track, path: preference === 'original' ? original : extended || original };
    });
  }
  function downloadSetM3uEntries(entries) {
    downloadSetText(`${safeSetFilename()}.m3u8`, buildSetM3u(entries), 'audio/x-mpegurl;charset=utf-8');
    void recordPreference(
      'export',
      entries.map((entry) => entry.track),
    );
  }
  async function exportSetM3u() {
    const button = $('#export-set-m3u');
    const status = $('#set-export-status');
    const entries = setM3uEntries();
    button.disabled = true;
    button.textContent = 'Checking paths…';
    status.className = 'set-export-status checking';
    status.innerHTML = `<span>Checking ${entries.length} tracks on disk…</span>`;
    try {
      const result = await setBuilderApi.exportPreflight(entries.map((entry) => entry.path || ''));
      const validEntries = entries.filter((entry, index) => result.items[index]?.exists);
      if (result.ready) {
        status.className = 'set-export-status ready';
        status.innerHTML = `<strong>Ready for Rekordbox: ${result.valid}/${result.total} tracks</strong><span>All audio files were found. Downloading the playlist now.</span>`;
        downloadSetM3uEntries(validEntries);
      } else {
        const missing = entries.filter((entry, index) => !result.items[index]?.exists);
        status.className = 'set-export-status warning';
        status.innerHTML = `<strong>${result.missing} of ${result.total} tracks need attention</strong><span>The playlist was not downloaded because these files are unavailable:</span><ul>${missing.map(({ track, path }) => `<li><b>${escapeHtml(track.source_name.replace(/\.[^.]+$/, ''))}</b><small>${escapeHtml(path || 'No file path')}</small></li>`).join('')}</ul>${validEntries.length ? '<button type="button" class="button secondary export-valid-only">Export valid tracks only</button>' : ''}`;
        status
          .querySelector('.export-valid-only')
          ?.addEventListener('click', () => downloadSetM3uEntries(validEntries));
      }
    } catch (error) {
      status.className = 'set-export-status warning';
      status.innerHTML = `<strong>Could not validate the playlist</strong><span>${escapeHtml(error.message || String(error))}</span>`;
    } finally {
      button.disabled = false;
      button.textContent = 'Export M3U8';
    }
  }

  return Object.freeze({
    deleteSavedSet: lifecycle.deleteSavedSet,
    duplicateSavedSet: lifecycle.duplicateSavedSet,
    exportSetCsv,
    exportSetM3u,
    loadSavedSet,
    loadSavedSets,
    renderSavedSets,
    saveCurrentSet,
    savedSets,
  });
}
