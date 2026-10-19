import {
  DEFAULT_SET_FALLBACK_POLICY,
  SET_IDENTITY_STORAGE_KEY,
  SET_STORAGE_KEY,
  SET_STORAGE_MIGRATION_KEY,
  genreAllocationTargets,
  inferredTrackIdentity,
  intendedGenreForPosition,
  interpretSetIntention,
  parseIdentityTerms,
  setCatalogTrackId,
  setTrackDetailedGenres,
  setTrackId,
  targetSetEnergy,
  trackMatchesIntendedGenre,
  trackMatchesSetDetailedGenre,
  trackMatchesSetGenre,
} from './set-builder-policy.js';
import {
  SET_BRIEF_MODES,
  SET_TRACK_PLANNERS,
  allowsCandidateGenre,
  createSetIntentionController,
  createSetWorkflowController,
  inferSetWorkflow,
  passesSetCandidateHardFilters,
  resolveStructuredGenreFilters,
} from './set-builder-workflow.js';

export {
  DEFAULT_SET_FALLBACK_POLICY,
  SET_IDENTITY_STORAGE_KEY,
  SET_STORAGE_KEY,
  SET_STORAGE_MIGRATION_KEY,
  genreAllocationTargets,
  inferredTrackIdentity,
  intendedGenreForPosition,
  interpretSetIntention,
  parseIdentityTerms,
  setCatalogTrackId,
  setTrackDetailedGenres,
  setTrackId,
  targetSetEnergy,
  trackMatchesIntendedGenre,
  trackMatchesSetDetailedGenre,
  trackMatchesSetGenre,
} from './set-builder-policy.js';
export function createSetBuilderFeature({
  services,
  option,
  escapeHtml,
  clock,
  decodedAudio,
  WaveSurfer,
  compatibility,
  harmonicCompatibility,
  camelotKey,
  formatLibraryKey,
  energyBand,
  songEnergy,
  LIBRARY_ROLE_INFO,
  libraryRoles,
  timingProfile,
  vocalProfile,
  bindCompactAudio,
  compactAudioMarkup,
  stopNativeAudio,
  stopCompactAudio,
}) {
  const { api, $, $$, notify, confirmAction, descriptorEditorMarkup, saveDescriptorEditor, inferDescriptorEditor } =
    useFrontendServices(services);
  const state = createSetBuilderStore();
  const workflow = createSetWorkflowController({ $, $$ });
  const trackReviewDraft = new Map();
  const transitionReviewDraft = new Map();
  const setBuilderApi = createSetBuilderApi({ api });
  const intentionController = createSetIntentionController({
    $,
    api: setBuilderApi,
    providerView: intentionProviderView,
    offlineInterpret: interpretSetIntention,
    vocabulary: intentionVocabulary,
    durationMinutes: () => Number($('#set-length').value),
  });
  const planningClient = setBuilderApi.planning;
  const classicPlanner = createClassicSetPlanner({
    strategies: SET_PROPOSAL_STRATEGIES,
    schedule: () => new Promise((resolve) => requestAnimationFrame(() => resolve())),
  });
  const editCommands = createSetEditCommands({
    store: state,
    snapshot: () => setPlanSnapshot(),
    restore: (snapshot) => restoreSetSnapshot(snapshot, false),
    render: () => renderSetPlan(),
  });
  function identityStore() {
    try {
      return JSON.parse(localStorage.getItem(SET_IDENTITY_STORAGE_KEY) || '{}');
    } catch (_) {
      return {};
    }
  }
  function intentionVocabulary() {
    return [
      ...new Set(
        state.library
          .flatMap((track) => [
            ...String(track._genre || '')
              .split('/')
              .map((value) => value.trim()),
            ...setTrackDetailedGenres(track),
            ...(track._descriptors || []).map((item) => item.value),
          ])
          .filter(Boolean),
      ),
    ];
  }
  function manualTrackIdentity(track) {
    return identityStore()[setTrackId(track)] || [];
  }
  function saveManualTrackIdentity(track, terms) {
    const store = identityStore();
    store[setTrackId(track)] = parseIdentityTerms(terms);
    localStorage.setItem(SET_IDENTITY_STORAGE_KEY, JSON.stringify(store));
    track._manualIdentity = store[setTrackId(track)];
  }
  function trackIdentity(track) {
    return inferredTrackIdentity(track, track._manualIdentity || manualTrackIdentity(track));
  }
  function identityTermMatches(track, term) {
    const normalized = String(term || '').toLowerCase(),
      tags = trackIdentity(track);
    if (normalized === 'latin rhythmic identity')
      return tags.some((tag) => ['dembow', 'latin percussion', 'latin identity'].includes(tag));
    if (normalized === 'generic instrumental techno')
      return (
        tags.includes('techno foundation') &&
        !tags.includes('spanish vocals') &&
        !tags.includes('latin percussion') &&
        !tags.includes('recognizable material')
      );
    if (normalized === 'dance-friendly') return songEnergy(track) >= 0.5;
    if (normalized === 'chill kickback') return songEnergy(track) <= 0.68 || tags.includes('chill kickback');
    return tags.some((tag) => tag === normalized || tag.includes(normalized) || normalized.includes(tag));
  }
  function intentionEvaluation(track, brief) {
    const identity = brief.identity || { required: [], preferred: [], avoided: [] };
    const required = (identity.required || []).filter((term) => identityTermMatches(track, term)),
      preferred = (identity.preferred || []).filter((term) => identityTermMatches(track, term)),
      avoided = (identity.avoided || []).filter((term) => identityTermMatches(track, term));
    const missingRequired = (identity.required || []).filter((term) => !required.includes(term));
    return {
      required,
      preferred,
      avoided,
      missingRequired,
      score: preferred.length * 14 + required.length * 22 - avoided.length * 35 - missingRequired.length * 45,
    };
  }
  function currentJourney() {
    const root = $('#set-journey-preview');
    if (!root || root.hidden) return null;
    const sections = [...root.querySelectorAll('.set-journey-section')].map((row, index) => ({
      id: row.dataset.id || `section-${index + 1}`,
      name: row.querySelector('.journey-name').value.trim() || `Section ${index + 1}`,
      durationPercent: Number(row.querySelector('.journey-duration').value || 0),
      energyStart: Number(row.querySelector('.journey-energy-start').value || 5),
      energyEnd: Number(row.querySelector('.journey-energy-end').value || 5),
      genres: parseIdentityTerms(row.querySelector('.journey-genres input').value),
      characteristics: parseIdentityTerms(row.querySelector('.journey-characteristics').value),
      purpose: row.querySelector('.journey-purpose input').value.trim(),
    }));
    const duration = journeyDurationStatus(sections, Number($('#set-length').value));
    if (!duration.valid)
      throw new Error(`Journey section durations total ${duration.total}%. Adjust them to 100% before generating.`);
    return {
      version: 1,
      summary: $('#set-journey-summary').textContent,
      durationMinutes: Number($('#set-length').value),
      sections,
    };
  }
  function currentIntention() {
    const usesAIBrief = workflow.briefMode() === SET_BRIEF_MODES.AI,
      text = usesAIBrief ? $('#set-intention').value.trim() : '',
      panel = $('#set-intention-interpretation'),
      parsed = interpretSetIntention(text, intentionVocabulary());
    let interpreted = {};
    try {
      if (usesAIBrief && panel.dataset.source === text) interpreted = JSON.parse(panel.dataset.interpretation || '{}');
    } catch (_) {}
    const journey = usesAIBrief ? currentJourney() : null;
    const journeySequence = journey?.sections.flatMap((section) => section.genres) || [];
    return {
      text,
      required: parseIdentityTerms($('#set-intention-required').value),
      preferred: parseIdentityTerms($('#set-intention-preferred').value),
      avoided: parseIdentityTerms($('#set-intention-avoided').value),
      requestedGenres: interpreted.requestedGenres || parsed.requestedGenres || [],
      optionalGenres: interpreted.optionalGenres || [],
      genreSequence: journeySequence.length ? journeySequence : interpreted.genreSequence || parsed.genreSequence || [],
      journey,
      opening: interpreted.opening || parsed.opening || null,
      ending: interpreted.ending || null,
      provider: interpreted.provider || 'offline',
      drift: $('#set-intention-drift').value,
      fallbackPolicy: [...DEFAULT_SET_FALLBACK_POLICY],
    };
  }
  function renderFallbackPolicy(policy = DEFAULT_SET_FALLBACK_POLICY) {
    $('#set-fallback-policy').innerHTML = fallbackPolicyMarkup(policy, escapeHtml);
  }
  function renderJourney(journey) {
    const root = $('#set-journey-preview'),
      container = $('#set-journey-sections');
    root.hidden = false;
    root.dataset.journey = JSON.stringify(journey);
    $('#set-journey-summary').textContent = journey.summary || 'Review the planned journey before generating.';
    $('#set-journey-evidence').textContent = journeyEvidenceLabel(journey);
    container.innerHTML = (journey.sections || [])
      .map(
        (section, index) =>
          `<article class="set-journey-section" data-id="${escapeHtml(section.id || `section-${index + 1}`)}"><span class="journey-step" aria-hidden="true">${index + 1}</span><div class="journey-primary"><label>Section<input class="journey-name" value="${escapeHtml(section.name || `Section ${index + 1}`)}"></label><label class="journey-duration-label">Duration<input class="journey-duration" type="number" min="1" max="100" step="1" value="${Number(section.durationPercent || 0)}"><span>%</span></label><label class="journey-energy">Energy <span class="journey-energy-value">${Number(section.energyStart || 5)} → ${Number(section.energyEnd || 5)}</span><span class="journey-energy-inputs"><input class="journey-energy-start" aria-label="Starting energy" type="number" min="1" max="10" step=".5" value="${Number(section.energyStart || 5)}"><i>to</i><input class="journey-energy-end" aria-label="Ending energy" type="number" min="1" max="10" step=".5" value="${Number(section.energyEnd || 5)}"></span></label></div><div class="journey-details"><label class="journey-genres">Genres<input value="${escapeHtml((section.genres || []).join(', '))}" placeholder="Catalog genres"></label><label>Character<input class="journey-characteristics" value="${escapeHtml((section.characteristics || []).join(', '))}" placeholder="melodic, warm-up"></label><label class="journey-purpose">Purpose<input value="${escapeHtml(section.purpose || '')}"></label></div></article>`,
      )
      .join('');
    const refresh = () => {
      const total = [...container.querySelectorAll('.journey-duration')].reduce(
          (sum, input) => sum + Number(input.value || 0),
          0,
        ),
        status = $('#set-journey-total');
      status.textContent = `${journey.sections.length} sections · ${total}% of ${Number($('#set-length').value)} minutes · edits drive track placement`;
      status.classList.toggle('invalid', Math.abs(total - 100) > 0.01);
      container.querySelectorAll('.set-journey-section').forEach((row) => {
        const values = [...row.querySelectorAll('.journey-energy-start,.journey-energy-end')].map((input) =>
          Number(input.value || 5),
        );
        row.querySelector('.journey-energy-value').textContent = `${values[0]} → ${values[1]}`;
      });
    };
    container.querySelectorAll('input').forEach((input) => input.addEventListener('input', refresh));
    refresh();
  }
  function applyIntentionInterpretation(interpreted, { announce = true } = {}) {
    const panel = $('#set-intention-interpretation');
    panel.hidden = false;
    panel.dataset.source = interpreted.text || '';
    panel.dataset.interpretation = JSON.stringify(interpreted);
    $('#set-intention-required').value = (interpreted.required || []).join(', ');
    $('#set-intention-preferred').value = (interpreted.preferred || []).join(', ');
    $('#set-intention-avoided').value = (interpreted.avoided || []).join(', ');
    $('#set-intention-drift').value = interpreted.drift || 'moderate';
    if (interpreted.vibe) $('#set-vibe').value = interpreted.vibe;
    if (interpreted.curve) $('#set-curve').value = interpreted.curve;
    renderFallbackPolicy(interpreted.fallbackPolicy || DEFAULT_SET_FALLBACK_POLICY);
    if (interpreted.journey) renderJourney(interpreted.journey);
    intentionController.showProvider({
      available: interpreted.provider !== 'offline',
      provider: interpreted.provider,
      model: interpreted.model,
    });
    if (announce) {
      const source =
        interpreted.provider === 'ollama'
          ? `Local AI · ${interpreted.model}`
          : interpreted.provider === 'openai'
            ? `Cloud AI · ${interpreted.model}`
            : 'offline rules';
      $('#set-intention-status').textContent =
        `Interpreted with ${source}. Found ${(interpreted.required || []).length} requirement${(interpreted.required || []).length === 1 ? '' : 's'}, ${(interpreted.preferred || []).length} preference${(interpreted.preferred || []).length === 1 ? '' : 's'}, and ${(interpreted.avoided || []).length} limit${(interpreted.avoided || []).length === 1 ? '' : 's'}. Edit anything before generating.`;
    }
  }
  function selectedSetGenres() {
    return [...$('#set-genre').selectedOptions]
      .map((option) => option.value)
      .filter((value) => value && value !== 'all');
  }
  function selectedSetDetailedGenres() {
    return [...$('#set-detailed-genres').selectedOptions]
      .map((option) => option.value)
      .filter((value) => value && value !== 'all');
  }
  function selectedExcludedSetGenres() {
    return [...$('#set-excluded-genres').selectedOptions].map((option) => option.value).filter(Boolean);
  }
  function renderExcludedSetGenres() {
    const selected = selectedExcludedSetGenres();
    const chips = $('#set-excluded-genre-chips');
    chips.replaceChildren(
      ...selected.map((genre) => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.textContent = `${genre} ×`;
        chip.onclick = () => {
          const option = [...$('#set-excluded-genres').options].find((item) => item.value === genre);
          if (option) option.selected = false;
          $('#set-excluded-genres').dispatchEvent(new Event('change', { bubbles: true }));
        };
        return chip;
      }),
    );
  }
  function renderSetDetailedGenres() {
    const selected = selectedSetDetailedGenres(),
      chips = $('#set-detailed-genre-chips');
    chips.replaceChildren(
      ...selected.map((genre) => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.textContent = `${genre} ×`;
        chip.onclick = () => {
          const option = [...$('#set-detailed-genres').options].find((item) => item.value === genre);
          if (option) option.selected = false;
          $('#set-detailed-genres').dispatchEvent(new Event('change', { bubbles: true }));
        };
        return chip;
      }),
    );
  }
  function populateSetDetailedGenres(restore = []) {
    const parents = selectedSetGenres();
    const select = $('#set-detailed-genres');
    const current = restore.length ? restore : selectedSetDetailedGenres();
    const choices = [
      ...new Set(
        state.library
          .filter((track) => !parents.length || parents.some((parent) => trackMatchesSetGenre(track, parent)))
          .flatMap(setTrackDetailedGenres),
      ),
    ].sort((a, b) => a.localeCompare(b));
    select.replaceChildren(option('all', 'Any detailed genre'), ...choices.map((value) => option(value, value)));
    [...select.options].forEach((item) => {
      item.selected = current.length ? current.includes(item.value) : item.value === 'all';
    });
    if (!select.selectedOptions.length) select.querySelector('option[value="all"]').selected = true;
    renderSetDetailedGenres();
  }
  function renderSetGenreMix() {
    const genres = selectedSetGenres();
    const chips = $('#set-genre-chips');
    const weights = $('#set-genre-weights');
    const existing = new Map([...weights.querySelectorAll('input')].map((input) => [input.dataset.genre, input.value]));
    const countChanged = Number(weights.dataset.count || 0) !== genres.length;
    weights.dataset.count = String(genres.length);
    chips.replaceChildren();
    weights.replaceChildren();
    weights.hidden = !genres.length;
    genres.forEach((genre) => {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.textContent = `${genre} ×`;
      chip.onclick = () => {
        const option = [...$('#set-genre').options].find((item) => item.value === genre);
        if (option) option.selected = false;
        state.genreSelectionOrder = state.genreSelectionOrder.filter((value) => value !== genre);
        if (!selectedSetGenres().length) $('#set-genre').querySelector('option[value="all"]').selected = true;
        $('#set-genre').dispatchEvent(new Event('change', { bubbles: true }));
      };
      chips.append(chip);
      const row = document.createElement('label');
      const input = document.createElement('input');
      input.type = 'number';
      input.min = '0';
      input.max = '100';
      input.step = '1';
      input.value =
        !countChanged && existing.has(genre) ? existing.get(genre) : String(Math.round(100 / genres.length));
      input.dataset.genre = genre;
      row.append(document.createTextNode(genre), input);
      const suffix = document.createElement('span');
      suffix.textContent = '%';
      row.append(suffix);
      weights.append(row);
    });
  }
  function setBrief() {
    const authoringMode = workflow.briefMode();
    const structuredGenres = resolveStructuredGenreFilters(authoringMode, {
      genres: selectedSetGenres(),
      detailedGenres: selectedSetDetailedGenres(),
      excludedGenres: selectedExcludedSetGenres(),
      weights: Object.fromEntries(
        [...$('#set-genre-weights').querySelectorAll('input')].map((input) => [
          input.dataset.genre,
          Math.max(0, Number(input.value || 0)),
        ]),
      ),
    });
    return {
      authoringMode,
      trackPlanner: workflow.trackPlanner(),
      name: $('#set-name').value.trim() || 'New DJ Set',
      length: Number($('#set-length').value),
      genres: structuredGenres.genres,
      detailedGenres: structuredGenres.detailedGenres,
      excludedGenres: structuredGenres.excludedGenres,
      genreWeights: structuredGenres.weights,
      genreFlow: $('#set-genre-flow').value,
      vibe: $('#set-vibe').value,
      curve: $('#set-curve').value,
      bpmMin: Number($('#set-bpm-min').value || 0),
      bpmMax: Number($('#set-bpm-max').value || Infinity),
      keyStrictness: $('#set-key-strictness').value,
      vocals: $('#set-vocals').value,
      timing: $('#set-timing').value,
      edits: $('#set-edits').value,
      minimumHealth: Number($('#set-minimum-health').value || 65),
      identity: currentIntention(),
    };
  }
  function setCandidateScore(
    track,
    previous,
    index,
    count,
    brief,
    strategy = 'balanced',
    usedByOtherProposals = new Set(),
  ) {
    const energyFit = Math.max(0, 45 * (1 - Math.abs(songEnergy(track) - targetSetEnergy(index, count, brief)) / 0.7));
    const roles = libraryRoles(track);
    const vibeFit =
      brief.vibe === 'balanced' ||
      roles.includes(brief.vibe) ||
      (brief.vibe === 'dance-party' && songEnergy(track) >= 0.58)
        ? 15
        : 0;
    const transition = previous ? compatibility(previous, track) : null;
    let transitionScore = transition ? transition.score * 0.7 : 25;
    if (brief.keyStrictness === 'strict' && transition && transition.components.key < 20) transitionScore -= 35;
    if (brief.keyStrictness === 'adventurous' && transition)
      transitionScore = transition.components.tempo * 0.65 + transition.components.energy * 1.2;
    const editFit = brief.edits === 'either' ? 0 : (brief.edits === 'extended') === track._hasExtended ? 6 : -3;
    const matchingGenres = (brief.genres || []).filter((genre) => trackMatchesSetGenre(track, genre));
    const totalWeight = Math.max(
      1,
      Object.values(brief.genreWeights || {}).reduce((sum, value) => sum + value, 0),
    );
    let genreFit = matchingGenres.length
      ? 18 * Math.max(...matchingGenres.map((genre) => (brief.genreWeights[genre] || 0) / totalWeight))
      : 0;
    if (brief.genres?.length > 1 && brief.genreFlow !== 'blend') {
      const order = state.genreSelectionOrder
        .filter((genre) => brief.genres.includes(genre))
        .concat(brief.genres.filter((genre) => !state.genreSelectionOrder.includes(genre)));
      const progress = (index + 0.5) / Math.max(1, count);
      let target = order[Math.min(order.length - 1, Math.floor(progress * order.length))];
      if (brief.genreFlow === 'chapters') {
        let cursor = 0;
        for (const genre of order) {
          cursor += (brief.genreWeights[genre] || 0) / totalWeight;
          if (progress <= cursor) {
            target = genre;
            break;
          }
        }
      }
      if (trackMatchesSetGenre(track, target)) genreFit += 22;
    }
    let strategyFit = 0;
    if (strategy === 'safe')
      strategyFit =
        (transition?.score || 65) * 0.48 +
        (setVocalProfile(track) === 'vocal-forward' && previous && setVocalProfile(previous) === 'vocal-forward'
          ? -28
          : 8) -
        Math.abs(songEnergy(track) - (previous ? songEnergy(previous) : songEnergy(track))) * 18;
    if (strategy === 'energy')
      strategyFit =
        energyFit * 0.8 -
        Math.abs(songEnergy(track) - targetSetEnergy(index, count, brief)) * 34 +
        (previous ? Math.min(12, Math.abs(songEnergy(track) - songEnergy(previous)) * 14) : 0) -
        (usedByOtherProposals.has(setTrackId(track)) ? 8 : 0);
    if (strategy === 'adventurous') {
      const genreChange = previous && track._genre !== previous._genre ? 18 : 0;
      const roleChange = previous
        ? libraryRoles(track).filter((role) => !libraryRoles(previous).includes(role)).length * 6
        : 8;
      const harmonicColor = transition && transition.components.key < 31 && transition.components.key >= 20 ? 10 : 0;
      strategyFit = genreChange + roleChange + harmonicColor - (usedByOtherProposals.has(setTrackId(track)) ? 18 : 0);
    }
    const intentionFit = intentionEvaluation(track, brief).score;
    const intendedGenres = [...(brief.identity?.requestedGenres || []), ...(brief.identity?.optionalGenres || [])];
    const requestedGenreFit = intendedGenres.some((term) => trackMatchesIntendedGenre(track, term)) ? 32 : 0;
    const positionalGenre = intendedGenreForPosition(brief.identity, index, count);
    const positionalGenreFit =
      positionalGenre && trackMatchesIntendedGenre(track, positionalGenre) ? 68 : positionalGenre ? -24 : 0;
    const openingSection = index < Math.max(1, Math.ceil(count * 0.18));
    const openingFit =
      openingSection && String(brief.identity?.opening || '').includes('melodic')
        ? identityTermMatches(track, 'melodic')
          ? 42
          : -18
        : 0;
    return (
      energyFit +
      vibeFit +
      transitionScore +
      editFit +
      genreFit +
      strategyFit +
      intentionFit +
      requestedGenreFit +
      positionalGenreFit +
      openingFit +
      preferenceAdjustment(track)
    );
  }
  function setVocalProfile(track) {
    return track.intro || track.outro || track.stem_reliability != null ? vocalProfile(track) : 'mixed';
  }
  function eligibleSetTracks(brief) {
    return state.library.filter((track) => {
      const bpm = Number(track.bpm || 0);
      const id = setTrackId(track);
      const intention = intentionEvaluation(track, brief);
      const requestedGenres = brief.identity?.requestedGenres || [],
        optionalGenres = brief.identity?.optionalGenres || [],
        allIntendedGenres = [...requestedGenres, ...optionalGenres];
      const requestedGenreMatch =
        !allIntendedGenres.length || allIntendedGenres.some((term) => trackMatchesIntendedGenre(track, term));
      const directGenre = !brief.genres.length || brief.genres.some((genre) => trackMatchesSetGenre(track, genre));
      const drift = brief.identity?.drift || 'none';
      const identityEligible = allowsCandidateGenre({
        authoringMode: brief.authoringMode,
        directGenre,
        requestedGenreMatch,
        hasInterpretedIdentity: Boolean(brief.identity?.text),
        drift,
        preferredIdentityMatches: intention.preferred.length,
      });
      return passesSetCandidateHardFilters({
        explicitlyExcluded: state.excludedIds.has(id),
        genreEligible: identityEligible,
        detailedGenreEligible:
          !(brief.detailedGenres || []).length ||
          brief.detailedGenres.some((genre) => trackMatchesSetDetailedGenre(track, genre)),
        excludedGenreMatch: (brief.excludedGenres || []).some((genre) => trackMatchesSetGenre(track, genre)),
        bpmEligible:
          (!brief.bpmMin || bpm >= brief.bpmMin) &&
          (!Number.isFinite(brief.bpmMax) || !brief.bpmMax || bpm <= brief.bpmMax),
        vocalEligible: brief.vocals === 'all' || setVocalProfile(track) === brief.vocals,
        timingEligible: brief.timing === 'all' || timingProfile(track) === brief.timing,
      });
    });
  }
  function setPlanSnapshot() {
    return snapshotSetPlan(state, setTrackId);
  }
  function restoreSetSnapshot(snapshot, render = true) {
    restoreSetPlan(state, snapshot, state.library, setTrackId);
    if (render) renderSetPlan();
  }
  function pushSetHistory() {
    editCommands.checkpoint();
    updateSetHistoryButtons();
  }
  function updateSetHistoryButtons() {
    const undo = $('#set-undo'),
      redo = $('#set-redo');
    if (undo) undo.disabled = !state.history.length;
    if (redo) redo.disabled = !state.future.length;
  }
  function undoSetEdit() {
    if (editCommands.undo()) updateSetHistoryButtons();
  }
  function redoSetEdit() {
    if (editCommands.redo()) updateSetHistoryButtons();
  }
  let transitionEditor;
  let planningSession;
  const feedbackController = createSetBuilderFeedback({
    state,
    dom: { $, $$, escapeHtml },
    api: setBuilderApi,
    music: {
      compatibility,
      setTrackDetailedGenres,
      setTrackId,
      setCatalogTrackId,
      setVocalProfile,
      songEnergy,
    },
    planning: {
      setBrief,
      getPlanningReceipt: () => planningSession.receipt(),
      transitionSettings: (index) => transitionEditor.transitionSettings(index),
    },
    review: { trackReviewDraft, transitionReviewDraft },
  });
  const {
    loadPreferenceProfile,
    loadSetReviewReport,
    preferenceAdjustment,
    recordPreference,
    resetPreferences,
    resetSetReviewDraft,
    setOverallDecision,
    setPersonalizationEnabled,
    submitSetReview,
    transitionPreferenceAdjustment,
    transitionReviewFeatures,
  } = feedbackController;
  transitionEditor = createSetTransitionEditor({
    state,
    setBuilderApi,
    $,
    $$,
    notify,
    escapeHtml,
    clock,
    WaveSurfer,
    compatibility,
    harmonicCompatibility,
    songEnergy,
    targetSetEnergy,
    intendedGenreForPosition,
    trackMatchesIntendedGenre,
    identityTermMatches,
    optimizePlanOrder,
    setTrackId,
    setVocalProfile,
    timingProfile,
    stopCompactAudio,
    transitionReviewFeatures,
    transitionPreferenceAdjustment,
  });
  const {
    autoOptimizeSetTransitions,
    auditionTransition,
    closeTransitionEditors,
    improveSetOrder,
    openTransitionEditor,
    setHealth,
    setHealthIssues,
    setRuntime,
    setSvgCurve,
    stopTransitionPreview,
    transitionSettings,
  } = transitionEditor;
  planningSession = createSetPlanningSession({
    state,
    dom: { $, escapeHtml, notify },
    clients: { planningClient, classicPlanner },
    policy: {
      genreAllocationTargets,
      intendedGenreForPosition,
      intentionEvaluation,
      setCandidateScore,
      setCatalogTrackId,
      setTrackId,
      songEnergy,
      targetSetEnergy,
      trackMatchesIntendedGenre,
      trackMatchesSetGenre,
    },
    transitions: transitionEditor,
    lifecycle: {
      eligibleSetTracks,
      pushSetHistory,
      renderSetPlan: () => renderSetPlan(),
      resetSetReviewDraft,
      restoreSetSnapshot,
      setBrief,
      setPlanSnapshot,
    },
    view: { aiObservabilityCards, setProposalMarkup },
  });
  const {
    cancelAITrackPlan,
    generateAITrackPlan,
    generateDeterministicSetPlan,
    loadAIObservability,
    renderSetProposals,
  } = planningSession;
  const planView = createSetPlanView({
    state,
    dom: { $, $$, escapeHtml },
    ui: {
      notify,
      descriptorEditorMarkup,
      saveDescriptorEditor,
      inferDescriptorEditor,
      bindCompactAudio,
      compactAudioMarkup,
    },
    music: {
      compatibility,
      energyBand,
      formatLibraryKey,
      LIBRARY_ROLE_INFO,
      libraryRoles,
      songEnergy,
      timingProfile,
    },
    policy: {
      SET_IDENTITY_STORAGE_KEY,
      eligibleSetTracks,
      genreAllocationTargets,
      identityStore,
      intentionEvaluation,
      preferenceAdjustment,
      parseIdentityTerms,
      saveManualTrackIdentity,
      setCatalogTrackId,
      setCandidateScore,
      setTrackId,
      setVocalProfile,
      targetSetEnergy,
      trackIdentity,
      trackMatchesSetDetailedGenre,
      trackMatchesSetGenre,
    },
    transitions: transitionEditor,
    lifecycle: {
      editCommands,
      getPlanningReceipt: () => planningSession.receipt(),
      pushSetHistory,
      recordPreference,
      renderSetProposals,
      setBrief,
      setPlanSnapshot,
      updateSetHistoryButtons,
    },
    review: { trackReviewDraft, transitionReviewDraft },
  });
  const { addSetTrack, renderSetPlan, renderSetRules } = planView;
  const savedSetController = createSavedSetController({
    state,
    dom: { $, $$, option, escapeHtml, notify },
    api: setBuilderApi,
    storageKeys: { SET_STORAGE_KEY, SET_STORAGE_MIGRATION_KEY },
    authoring: {
      inferSetWorkflow,
      interpretSetIntention,
      applyIntentionInterpretation,
      populateSetDetailedGenres,
      renderSetGenreMix,
      renderSetDetailedGenres,
      renderExcludedSetGenres,
      workflow,
    },
    plan: {
      setBrief,
      setTrackId,
      getPlanningReceipt: () => planningSession.receipt(),
      setPlanningReceipt: (receipt) => planningSession.setReceipt(receipt),
      renderSetRules,
      autoOptimizeSetTransitions,
      renderSetPlan,
      transitionSettings,
    },
    music: {
      compatibility,
      trackMatchesSetGenre,
      camelotKey,
      energyBand,
      songEnergy,
      libraryRoles,
    },
    feedback: { recordPreference },
  });
  const {
    cacheSavedSets,
    exportSetCsv,
    exportSetM3u,
    loadSavedSet,
    loadSavedSets,
    renderSavedSets,
    saveCurrentSet,
    savedSets,
  } = savedSetController;
  async function loadSetBuilder() {
    intentionController.refreshProviderStatus();
    bindSetBuilder();
    await loadPreferenceProfile();
    await loadSetReviewReport();
    await loadAIObservability();
    const catalog = await setBuilderApi.catalog();
    const identities = identityStore();
    state.library = (catalog.tracks || []).map((item) => {
      const song = item.analysis || {};
      const job = item.job || {};
      const hasExtended = Boolean(job.extended_path) && !JSON.parse(job.config_json || '{}').analysis_only;
      const preferred = $('#set-edits').value;
      const libraryPath = job.library_path || song.file_path || song.wav_path || job.wav_path;
      const track = {
        ...song,
        _job: job,
        _genre: item.genre || song.detected_style || 'Other',
        _detailedGenre: item.detailed_genre || '',
        _hasExtended: hasExtended,
        _libraryPath: libraryPath,
        _selectedPath: preferred === 'original' ? libraryPath : hasExtended ? job.extended_path : libraryPath,
        _downloadedId: item.downloaded_id || null,
        _descriptors: item.descriptors || [],
      };
      track._manualIdentity = [
        ...new Set([
          ...(track._descriptors || []).map((descriptor) => descriptor.value),
          ...(identities[setTrackId(track)] || []),
        ]),
      ];
      return track;
    });
    const names = state.library.slice().sort((a, b) => a.source_name.localeCompare(b.source_name));
    const trackOptions = names.map((track) => option(setTrackId(track), track.source_name.replace(/\.[^.]+$/, '')));
    $('#set-required').replaceChildren(
      option('', 'Choose a track'),
      ...trackOptions.map((item) => item.cloneNode(true)),
    );
    $('#set-excluded').replaceChildren(option('', 'Choose a track'), ...trackOptions);
    const leafGenres = [...new Set(state.library.map((track) => track._genre))].sort();
    const genre = $('#set-genre');
    const excluded = $('#set-excluded-genres');
    const current = selectedSetGenres();
    const currentDetailed = selectedSetDetailedGenres();
    const currentExcluded = selectedExcludedSetGenres();
    const choices = new Map();
    leafGenres.forEach((name) => {
      const parts = name.split(' / ');
      for (let index = 1; index < parts.length; index += 1) {
        const parent = parts.slice(0, index).join(' / ');
        choices.set(parent, `All ${parent}`);
      }
      choices.set(name, name);
    });
    const sortedChoices = [...choices].sort((a, b) => a[0].localeCompare(b[0]));
    genre.replaceChildren(
      option('all', 'Any parent genre'),
      ...sortedChoices.map(([value, label]) => option(value, label)),
    );
    excluded.replaceChildren(...sortedChoices.map(([value, label]) => option(value, label)));
    [...genre.options].forEach((item) => {
      item.selected = current.length ? current.includes(item.value) : item.value === 'all';
    });
    populateSetDetailedGenres(currentDetailed);
    [...excluded.options].forEach((item) => {
      item.selected = currentExcluded.includes(item.value);
    });
    if (current.length)
      state.genreSelectionOrder = state.genreSelectionOrder
        .filter((value) => current.includes(value))
        .concat(current.filter((value) => !state.genreSelectionOrder.includes(value)));
    await loadSavedSets();
    renderFallbackPolicy();
    renderSetGenreMix();
    renderSetDetailedGenres();
    renderExcludedSetGenres();
    renderSavedSets();
    renderSetRules();
    if (state.plan.length) renderSetPlan();
  }
  function bindSetBuilder() {
    if (state.bound) return;
    state.bound = true;
    $('#set-builder-form').onsubmit = async (event) => {
      event.preventDefault();
      const intentionText = $('#set-intention').value.trim(),
        interpretation = $('#set-intention-interpretation'),
        button = $('#set-generate'),
        briefMode = workflow.briefMode(),
        mode = workflow.syncPlanningMode();
      button.disabled = true;
      try {
        if (briefMode === SET_BRIEF_MODES.AI && !intentionText) {
          throw new Error('Describe the set you want, or switch to Build manually.');
        }
        if (
          briefMode === SET_BRIEF_MODES.AI &&
          intentionText &&
          (interpretation.hidden || interpretation.dataset.source !== intentionText)
        ) {
          button.textContent = 'Planning journey…';
          applyIntentionInterpretation(await intentionController.interpretAndPlan(intentionText));
        }
        button.textContent = mode === 'ai-planned' ? 'AI planning tracks…' : 'Building and optimizing…';
        $('#set-builder-message').textContent =
          mode === 'ai-planned'
            ? 'Retrieving a safe catalog candidate pool…'
            : 'Ranking compatible tracks and shaping the energy journey…';
        await new Promise((resolve) => requestAnimationFrame(resolve));
        if (mode === 'ai-planned') await generateAITrackPlan();
        else await generateDeterministicSetPlan();
      } catch (error) {
        if (error instanceof SetPlanningCanceled) {
          $('#set-builder-message').textContent = 'Set planning canceled. Your current set and brief were not changed.';
        } else {
          console.error('Set generation failed:', error);
          $('#set-builder-message').textContent =
            `Set generation failed: ${error?.message || error}. Your set brief was preserved; adjust it or try again.`;
          notify('The set could not be generated. Your set brief was preserved.', 'danger');
        }
      } finally {
        button.disabled = false;
        button.textContent = 'Build this set';
        $('#set-cancel-planning').hidden = true;
      }
    };
    $('#set-cancel-planning').onclick = async () => {
      await cancelAITrackPlan();
      $('#set-builder-message').textContent = 'Cancel requested. Your current set will remain unchanged.';
    };
    $('#refresh-set-ai-operations').onclick = () => void loadAIObservability();
    $('#interpret-set-intention').onclick = async (event) => {
      const text = $('#set-intention').value.trim(),
        button = event.currentTarget;
      if (!text) {
        $('#set-intention-interpretation').hidden = true;
        $('#set-journey-preview').hidden = true;
        $('#set-builder-message').textContent = 'Describe the set first, then interpret it.';
        return;
      }
      button.disabled = true;
      button.textContent = 'Planning journey…';
      try {
        applyIntentionInterpretation(await intentionController.interpretAndPlan(text));
      } finally {
        button.disabled = false;
        button.textContent = 'Review set direction';
      }
    };
    $$('[name="set-brief-mode"]').forEach((input) => {
      input.addEventListener('change', () => workflow.applyBriefMode(input.value));
    });
    $$('[name="set-track-planner"]').forEach((input) => {
      input.addEventListener('change', () => {
        workflow.syncPlanningMode();
        $('#set-builder-message').textContent =
          input.value === SET_TRACK_PLANNERS.AI
            ? 'AI will choose and order tracks from a validated catalog candidate pool.'
            : 'Compatibility rules will choose and order tracks without an AI planning call.';
      });
    });
    const briefName = $('#set-name'),
      resultName = $('#set-result-name');
    briefName.addEventListener('input', () => {
      if (document.activeElement !== resultName) resultName.value = briefName.value;
    });
    resultName.addEventListener('input', () => {
      briefName.value = resultName.value;
    });
    resultName.addEventListener('blur', () => {
      const name = resultName.value.trim() || 'New DJ Set';
      resultName.value = name;
      briefName.value = name;
    });
    $('#add-required-track').onclick = () => {
      const id = $('#set-required').value;
      if (id) {
        state.requiredIds.add(id);
        state.excludedIds.delete(id);
        renderSetRules();
      }
    };
    $('#add-excluded-track').onclick = () => {
      const id = $('#set-excluded').value;
      if (id) {
        state.excludedIds.add(id);
        state.requiredIds.delete(id);
        renderSetRules();
      }
    };
    $('#set-genre').addEventListener('change', () => {
      const selected = selectedSetGenres();
      state.genreSelectionOrder = state.genreSelectionOrder
        .filter((value) => selected.includes(value))
        .concat(selected.filter((value) => !state.genreSelectionOrder.includes(value)));
      renderSetGenreMix();
      populateSetDetailedGenres();
    });
    $('#set-detailed-genres').addEventListener('change', renderSetDetailedGenres);
    $('#set-excluded-genres').addEventListener('change', renderExcludedSetGenres);
    $('#set-vibe').addEventListener('change', () => void loadPreferenceProfile());
    $('#set-personalization-enabled').addEventListener('change', async (event) => {
      try {
        await setPersonalizationEnabled(event.currentTarget.checked);
      } catch (error) {
        notify(error.message, 'danger');
      }
    });
    $('#reset-set-preferences').onclick = async () => {
      if (
        !(await confirmAction('Reset all learned Set Builder preferences? Your sets and catalog will not change.', {
          title: 'Reset learned preferences',
          acceptLabel: 'Reset',
        }))
      )
        return;
      try {
        await resetPreferences();
        $('#set-builder-message').textContent = 'Learned Set Builder preferences reset.';
      } catch (error) {
        notify(error.message, 'danger');
      }
    };
    $$('[data-set-decision]').forEach(
      (button) =>
        (button.onclick = () => {
          setOverallDecision(button.dataset.setDecision);
          $$('[data-set-decision]').forEach((item) => item.classList.toggle('active', item === button));
        }),
    );
    $('#submit-set-review').onclick = submitSetReview;
    $('#reset-set-brief').onclick = () => {
      $('#set-builder-form').reset();
      workflow.applyBriefMode(SET_BRIEF_MODES.AI, { announce: false });
      $('#set-intention-interpretation').hidden = true;
      $('#set-journey-preview').hidden = true;
      renderFallbackPolicy();
      [...$('#set-genre').options].forEach((option) => {
        option.selected = option.value === 'all';
      });
      populateSetDetailedGenres();
      [...$('#set-excluded-genres').options].forEach((option) => {
        option.selected = false;
      });
      state.genreSelectionOrder = [];
      renderSetGenreMix();
      renderSetDetailedGenres();
      renderExcludedSetGenres();
      state.requiredIds.clear();
      state.excludedIds.clear();
      state.lockedIds.clear();
      state.proposals = [];
      state.activeProposal = '';
      renderSetRules();
      renderSetProposals();
      $('#set-builder-message').textContent = 'Set brief reset.';
    };
    $('#set-undo').onclick = undoSetEdit;
    $('#set-redo').onclick = redoSetEdit;
    $('#set-compact').onclick = () => {
      state.compactMode = !state.compactMode;
      localStorage.setItem('set-builder-compact', String(state.compactMode));
      renderSetPlan();
    };
    $('#add-set-track').onclick = () => addSetTrack();
    $('#save-set').onclick = saveCurrentSet;
    $('#export-set-csv').onclick = exportSetCsv;
    $('#export-set-m3u').onclick = exportSetM3u;
    document.addEventListener('keydown', (event) => {
      if (
        !$('#set-builder-view').classList.contains('active') ||
        !(event.metaKey || event.ctrlKey) ||
        event.key.toLowerCase() !== 'z'
      )
        return;
      event.preventDefault();
      event.shiftKey ? redoSetEdit() : undoSetEdit();
    });
    $('#load-set').onclick = () => loadSavedSet(savedSets().find((set) => set.id === $('#saved-set-select').value));
    $('#duplicate-set').onclick = async () => {
      const record = savedSets().find((set) => set.id === $('#saved-set-select').value);
      if (!record) return;
      const copy = {
        ...record,
        id: String(Date.now()),
        name: `${record.name} Copy`,
        brief: { ...record.brief, name: `${record.name} Copy` },
        updatedAt: new Date().toISOString(),
      };
      try {
        await setBuilderApi.saveSet(copy);
        cacheSavedSets([copy, ...savedSets()]);
        $('#saved-set-select').value = copy.id;
        loadSavedSet(copy);
      } catch (error) {
        notify(error.message || String(error), 'danger');
      }
    };
    $('#delete-set').onclick = async () => {
      const id = $('#saved-set-select').value;
      if (
        !id ||
        !(await confirmAction('Delete this saved set plan? Audio and Library tracks will not be removed.', {
          title: 'Delete saved set',
          acceptLabel: 'Delete',
          danger: true,
        }))
      )
        return;
      try {
        await setBuilderApi.deleteSet(id);
        cacheSavedSets(savedSets().filter((set) => set.id !== id));
      } catch (error) {
        notify(error.message || String(error), 'danger');
      }
    };
  }

  return { loadSetBuilder };
}
import { SetPlanningCanceled } from './set-planning-client.js';
import { createSetBuilderApi } from './set-builder-api.js';
import { createClassicSetPlanner, optimizePlanOrder } from './set-builder-classic-planner.js';
import { createSetEditCommands } from './set-builder-commands.js';
import { createSetBuilderFeedback } from './set-builder-feedback.js';
import { createSetPlanView } from './set-builder-plan-view.js';
import { createSetPlanningSession } from './set-builder-planning-session.js';
import { createSavedSetController } from './set-builder-saved-sets.js';
import { createSetBuilderStore, restoreSetPlan, snapshotSetPlan } from './set-builder-state.js';
import { createSetTransitionEditor } from './set-builder-transition-editor.js';
import { useFrontendServices } from './frontend-services.js';
import {
  SET_PROPOSAL_STRATEGIES,
  aiObservabilityCards,
  fallbackPolicyMarkup,
  intentionProviderView,
  journeyDurationStatus,
  journeyEvidenceLabel,
  setProposalMarkup,
} from './set-builder-view-model.js';
export { SET_PROPOSAL_STRATEGIES, intentionProviderView, journeyDurationStatus } from './set-builder-view-model.js';
export { createSetBuilderStore, createSetBuilderStore as createSetBuilderState } from './set-builder-state.js';
