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
  let proposalSwitchNonce = 0;
  let activePlanningJobId = '';
  let planningController = null;
  let currentPlanningReceipt = null;
  let currentPreferenceProfile = null;
  let currentSetDecision = 'unreviewed';
  const trackReviewDraft = new Map();
  const transitionReviewDraft = new Map();
  let currentTransitionProfile = { activeSignals: [] };
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
  function preferenceContext() {
    return $('#set-vibe')?.value || 'balanced';
  }
  function preferenceFeatures(track) {
    const energy = songEnergy(track),
      bpm = Number(track.bpm || 0);
    return {
      genre: [track._genre, ...setTrackDetailedGenres(track)].filter(Boolean),
      descriptor: (track._descriptors || []).map((item) => item.value).filter(Boolean),
      artist: track.artist || '',
      vocals: setVocalProfile(track),
      energy: energy < 0.4 ? 'low' : energy >= 0.7 ? 'high' : 'medium',
      bpm: bpm ? `${Math.floor(bpm / 10) * 10}s` : 'unknown',
    };
  }
  function preferenceAdjustment(track) {
    if (!currentPreferenceProfile?.enabled) return 0;
    const features = preferenceFeatures(track);
    const total = (currentPreferenceProfile.activeSignals || []).reduce((sum, signal) => {
      const values = Array.isArray(features[signal.dimension])
        ? features[signal.dimension]
        : [features[signal.dimension]];
      return values.map((value) => String(value).toLowerCase()).includes(String(signal.value).toLowerCase())
        ? sum + Number(signal.adjustment || 0)
        : sum;
    }, 0);
    return Math.max(-8, Math.min(8, total * 0.5));
  }
  function preferenceEventId() {
    return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }
  async function recordPreference(action, tracks) {
    const items = (Array.isArray(tracks) ? tracks : [tracks]).filter(Boolean);
    if (!items.length) return;
    try {
      const result = await setBuilderApi.recordPreference(
        items.map((track) => ({
          id: preferenceEventId(),
          action,
          trackId: setTrackId(track),
          context: preferenceContext(),
          features: preferenceFeatures(track),
        })),
      );
      currentPreferenceProfile = result.profile;
      renderPreferenceProfile();
    } catch (error) {
      console.warn('Set preference feedback failed:', error);
    }
  }
  function renderPreferenceProfile() {
    const profile = currentPreferenceProfile,
      status = $('#set-preference-status'),
      summary = $('#set-preference-summary'),
      toggle = $('#set-personalization-enabled');
    if (!profile || !status || !summary || !toggle) return;
    toggle.checked = Boolean(profile.enabled);
    const active = profile.activeSignals || [],
      pending = profile.pendingSignals || [];
    status.textContent = profile.enabled
      ? `${active.length} active · ${profile.eventCount} local choices`
      : 'Personalization paused';
    summary.innerHTML = active.length
      ? active
          .slice(0, 8)
          .map(
            (signal) =>
              `<span><b>${escapeHtml(signal.value)}</b> · ${signal.adjustment > 0 ? '+' : ''}${signal.adjustment} ranking · ${signal.evidenceCount} tracks <button type="button" data-dismiss-signal="${escapeHtml(signal.dimension)}" data-signal-value="${escapeHtml(signal.value)}" aria-label="Dismiss ${escapeHtml(signal.value)}">×</button></span>`,
          )
          .join('')
      : `<span>${pending.length ? 'Learning from more distinct tracks before changing rankings.' : 'No feedback recorded yet.'}</span>`;
    summary.querySelectorAll('[data-dismiss-signal]').forEach(
      (button) =>
        (button.onclick = async () => {
          try {
            currentPreferenceProfile = await setBuilderApi.dismissPreference(
              button.dataset.dismissSignal,
              button.dataset.signalValue,
            );
            renderPreferenceProfile();
          } catch (error) {
            console.warn('Set preference dismissal failed:', error);
          }
        }),
    );
  }
  async function loadPreferenceProfile() {
    try {
      currentPreferenceProfile = await setBuilderApi.preferenceProfile(preferenceContext());
      renderPreferenceProfile();
    } catch (error) {
      console.warn('Set preference profile failed:', error);
      const status = $('#set-preference-status');
      if (status) status.textContent = 'Local preferences unavailable';
    }
  }
  function transitionReviewFeatures(left, right, index) {
    const match = compatibility(left, right),
      settings = transitionSettings(index),
      difference = Number(right.bpm || 0) - Number(left.bpm || 0);
    return {
      bpmMovement: Math.abs(difference) < 2 ? 'steady' : difference > 0 ? 'rising' : 'falling',
      keyCompatibility: match.components.key >= 31 ? 'strong' : match.components.key >= 20 ? 'workable' : 'weak',
      vocalOverlap:
        setVocalProfile(left) === 'vocal-forward' && setVocalProfile(right) === 'vocal-forward'
          ? 'both-vocal'
          : 'spaced',
      energyMovement:
        songEnergy(right) - songEnergy(left) > 0.12
          ? 'rising'
          : songEnergy(left) - songEnergy(right) > 0.12
            ? 'falling'
            : 'steady',
      bars: String(settings.bars || 16),
      technique: settings.technique || 'crossfade',
    };
  }
  function renderCalibrationReport(report) {
    const root = $('#set-calibration-summary');
    if (!root || !report) return;
    const tracks = report.tracks || {},
      transition = report.transitionProfile || {};
    currentTransitionProfile = transition;
    root.innerHTML = `<p><b>${tracks.reviewed || 0} tracks reviewed</b> · ${tracks.accepted || 0} accepted · ${tracks.rejected || 0} rejected · ${tracks.changedByPersonalization || 0} changed rank</p><p>Personalized acceptance ${tracks.personalizedAcceptanceRate == null ? 'not enough evidence' : `${Math.round(tracks.personalizedAcceptanceRate * 100)}%`} · neutral ${tracks.neutralAcceptanceRate == null ? 'not enough evidence' : `${Math.round(tracks.neutralAcceptanceRate * 100)}%`} · ${transition.activeSignals?.length || 0} active transition preferences</p>${(report.recommendations || []).map((item) => `<p class="set-relaxation-warning">${escapeHtml(item.message)}</p>`).join('')}`;
  }
  function transitionPreferenceAdjustment(features) {
    return Math.max(
      -8,
      Math.min(
        8,
        (currentTransitionProfile.activeSignals || []).reduce(
          (sum, signal) =>
            String(features[signal.dimension] || '').toLowerCase() === String(signal.value || '').toLowerCase()
              ? sum + Number(signal.adjustment || 0)
              : sum,
          0,
        ),
      ),
    );
  }
  async function loadSetReviewReport() {
    try {
      renderCalibrationReport(await setBuilderApi.reviewReport(preferenceContext()));
    } catch (error) {
      console.warn('Set review report failed:', error);
    }
  }
  async function submitSetReview() {
    if (!state.plan.length) return;
    const button = $('#submit-set-review');
    button.disabled = true;
    button.textContent = 'Saving…';
    const transitions = state.plan.slice(1).map((track, index) => {
      const left = state.plan[index],
        pairId = `${setCatalogTrackId(left)}→${setCatalogTrackId(track)}`;
      return {
        pairId,
        rating: transitionReviewDraft.get(pairId) || 3,
        features: transitionReviewFeatures(left, track, index + 1),
      };
    });
    const tracks = state.plan.map((track) => {
      const metrics = track._candidateMetrics || {};
      const review = trackReviewDraft.get(setTrackId(track)) || {};
      return {
        trackId: setCatalogTrackId(track),
        title: track.source_name.replace(/\.[^.]+$/, ''),
        decision: review.decision || 'unreviewed',
        reason: review.reason || '',
        features: preferenceFeatures(track),
        technicalScore: metrics.technicalScore || 0,
        preferenceAdjustment: metrics.preferenceAdjustment || 0,
        rankDelta: metrics.rankDelta || 0,
        matchTier: metrics.matchTier || 'unknown',
      };
    });
    try {
      const result = await setBuilderApi.submitReview({
        setId: $('#saved-set-select').value || `draft-${Date.now()}`,
        setName: setBrief().name,
        context: preferenceContext(),
        overallDecision: currentSetDecision,
        notes: $('#set-review-notes').value,
        tracks,
        transitions,
        evaluation: currentPlanningReceipt?.evaluation || {},
        comparison: currentPlanningReceipt?.comparison || {},
      });
      currentPreferenceProfile = result.preferenceProfile;
      renderPreferenceProfile();
      renderCalibrationReport(result.report);
      $('#set-review-status').textContent = 'Review saved locally and preference evidence updated.';
    } catch (error) {
      $('#set-review-status').textContent = error.message || String(error);
    } finally {
      button.disabled = false;
      button.textContent = 'Save review';
    }
  }
  function resetSetReviewDraft() {
    currentSetDecision = 'unreviewed';
    trackReviewDraft.clear();
    transitionReviewDraft.clear();
    $$('[data-set-decision]').forEach((button) => button.classList.remove('active'));
    const notes = $('#set-review-notes');
    if (notes) notes.value = '';
  }
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
  async function generateDeterministicSetPlan() {
    const brief = setBrief();
    const eligiblePool = eligibleSetTracks(brief);
    const requiredIds = new Set(state.requiredIds);
    const intendedGenres = [...(brief.identity?.requestedGenres || []), ...(brief.identity?.optionalGenres || [])];
    const coarseScore = (track) =>
      intentionEvaluation(track, brief).score +
      (intendedGenres.some((term) => trackMatchesIntendedGenre(track, term)) ? 40 : 0) -
      Math.abs(songEnergy(track) - targetSetEnergy(0, 2, brief)) * 12;
    const shortlistLimit = 800;
    const pool =
      eligiblePool.length <= shortlistLimit
        ? eligiblePool
        : [...eligiblePool].sort((a, b) => coarseScore(b) - coarseScore(a)).slice(0, shortlistLimit);
    eligiblePool
      .filter((track) => requiredIds.has(setTrackId(track)) && !pool.includes(track))
      .forEach((track) => pool.push(track));
    if (pool.length < 2) {
      $('#set-builder-message').textContent =
        `Only ${pool.length} analyzed track${pool.length === 1 ? '' : 's'} passed the hard filters. Check BPM, vocals, timing, exclusions, and manually selected genres.`;
      return;
    }
    const averageSeconds =
      pool.reduce((sum, track) => sum + Math.max(90, Number(track.duration_seconds || 210) - 30), 0) / pool.length;
    const count = Math.max(2, Math.min(pool.length, Math.ceil((brief.length * 60) / averageSeconds)));
    const required = pool.filter((track) => state.requiredIds.has(setTrackId(track)));
    const genreTargets = genreAllocationTargets(brief.genres, brief.genreWeights, count);
    const previousPlan = state.plan;
    const buildVariation = (strategy, generatedTrackIds) => {
      const remaining = new Map(pool.map((track) => [setTrackId(track), track]));
      const nextPlan = [];
      const genreUsage = Object.fromEntries((brief.genres || []).map((genre) => [genre, 0]));
      const previousPlanIds = new Set(previousPlan.map(setTrackId));
      let failed = false;
      const recordGenre = (track) => {
        const matches = (brief.genres || []).filter((genre) => trackMatchesSetGenre(track, genre));
        if (!matches.length) return;
        const genre = matches.sort(
          (a, b) => (genreTargets[b] || 0) - (genreUsage[b] || 0) - ((genreTargets[a] || 0) - (genreUsage[a] || 0)),
        )[0];
        genreUsage[genre] = (genreUsage[genre] || 0) + 1;
      };
      const nextGenre = () => {
        const configuredOrder = state.genreSelectionOrder
          .filter((genre) => (brief.genres || []).includes(genre))
          .concat((brief.genres || []).filter((genre) => !state.genreSelectionOrder.includes(genre)));
        const open = configuredOrder.filter(
          (genre) =>
            (genreUsage[genre] || 0) < (genreTargets[genre] || 0) &&
            [...remaining.values()].some((track) => trackMatchesSetGenre(track, genre)),
        );
        if (!open.length) return '';
        return open.sort((a, b) => {
          const deficitA = (genreTargets[a] || 0) - (genreUsage[a] || 0),
            deficitB = (genreTargets[b] || 0) - (genreUsage[b] || 0);
          if (brief.genreFlow === 'blend')
            return deficitB / Math.max(1, genreTargets[b] || 0) - deficitA / Math.max(1, genreTargets[a] || 0);
          return configuredOrder.indexOf(a) - configuredOrder.indexOf(b);
        })[0];
      };
      state.generationNonce += 1;
      Array.from({ length: count }, (_, index) => {
        if (failed) return;
        const locked = previousPlan[index];
        if (locked && state.lockedIds.has(setTrackId(locked)) && remaining.has(setTrackId(locked))) {
          remaining.delete(setTrackId(locked));
          nextPlan.push(locked);
          recordGenre(locked);
          return;
        }
        const requiredIndex = required.length ? Math.round((index * (required.length + 1)) / count) - 1 : -1;
        const forced = required[requiredIndex];
        if (forced && remaining.has(setTrackId(forced))) {
          remaining.delete(setTrackId(forced));
          nextPlan.push(forced);
          recordGenre(forced);
          return;
        }
        const previous = nextPlan[index - 1] || null;
        const targetGenre = nextGenre();
        const identityTarget = intendedGenreForPosition(brief.identity, index, count);
        const available = [...remaining.values()];
        const identityTargeted = identityTarget
          ? available.filter((track) => trackMatchesIntendedGenre(track, identityTarget))
          : [];
        const targeted = targetGenre
          ? available.filter((track) => trackMatchesSetGenre(track, targetGenre))
          : available;
        const candidatePool = identityTargeted.length ? identityTargeted : targeted.length ? targeted : available;
        const ranked = candidatePool
          .map((track) => {
            const id = setTrackId(track),
              wasSamePosition = Boolean(previousPlan[index]) && setTrackId(previousPlan[index]) === id,
              wasInPrevious = previousPlanIds.has(id);
            return {
              track,
              score:
                setCandidateScore(track, previous, index, count, brief, strategy, generatedTrackIds) -
                (wasSamePosition ? 12 : wasInPrevious ? 3 : 0),
            };
          })
          .sort((a, b) => b.score - a.score);
        if (!ranked.length) {
          failed = true;
          return;
        }
        const competitive = ranked.filter((item) => item.score >= ranked[0].score - 18).slice(0, 18);
        const weights = competitive.map((item) => Math.exp((item.score - competitive.at(-1).score) / 5));
        const total = weights.reduce((sum, value) => sum + value, 0);
        let pick = Math.abs(Math.sin(state.generationNonce * 9283 + index * 3343)) * total,
          choice = competitive[0]?.track;
        for (let option = 0; option < competitive.length; option += 1) {
          pick -= weights[option];
          if (pick <= 0) {
            choice = competitive[option].track;
            break;
          }
        }
        if (choice) {
          remaining.delete(setTrackId(choice));
          nextPlan.push(choice);
          recordGenre(choice);
        }
      });
      required.forEach((track) => {
        if (!nextPlan.some((item) => setTrackId(item) === setTrackId(track))) nextPlan.push(track);
      });
      intendedGenres.forEach((term) => {
        if (nextPlan.some((track) => trackMatchesIntendedGenre(track, term))) return;
        const replacement = [...remaining.values()]
          .filter((track) => trackMatchesIntendedGenre(track, term))
          .sort((a, b) => coarseScore(b) - coarseScore(a))[0];
        if (!replacement) return;
        const replaceIndex = nextPlan
          .map((track, index) => ({
            track,
            index,
            score: setCandidateScore(
              track,
              nextPlan[index - 1] || null,
              index,
              count,
              brief,
              strategy,
              generatedTrackIds,
            ),
          }))
          .filter(
            (item) =>
              item.index > 0 &&
              !state.lockedIds.has(setTrackId(item.track)) &&
              !state.requiredIds.has(setTrackId(item.track)),
          )
          .sort((a, b) => a.score - b.score)[0]?.index;
        if (replaceIndex == null) return;
        remaining.set(setTrackId(nextPlan[replaceIndex]), nextPlan[replaceIndex]);
        remaining.delete(setTrackId(replacement));
        nextPlan[replaceIndex] = replacement;
      });
      return failed ? [] : nextPlan;
    };
    const result = await classicPlanner.generate({
      count,
      minimumHealth: brief.minimumHealth,
      buildVariation,
      improveOrder: (plan) => improveSetOrder(plan, brief),
      evaluate: setHealth,
      trackId: setTrackId,
      snapshot: (plan) => ({ tracks: plan.map(setTrackId), locked: [...state.lockedIds], transitions: {} }),
    });
    if (!result.accepted.length) {
      const issues = setHealthIssues(result.best.health, brief.minimumHealth);
      $('#set-builder-message').textContent =
        `No direction was applied. The best search reached ${result.best.health.score}/100, below your ${brief.minimumHealth} target. ${issues.slice(0, 2).join(' · ') || 'Relax a constraint or lower the health floor.'}`;
      return;
    }
    if (state.plan.length) pushSetHistory();
    state.proposals = result.proposals;
    const preferred = result.preferred;
    state.activeProposal = preferred.id;
    restoreSetSnapshot(preferred.snapshot, false);
    $('#set-builder-message').textContent =
      `Built ${result.accepted.length} distinct direction${result.accepted.length === 1 ? '' : 's'}. Optimizing transition techniques for ${preferred.label}…`;
    await autoOptimizeSetTransitions();
    preferred.snapshot = setPlanSnapshot();
    preferred.health = setHealth();
    currentPlanningReceipt = {
      version: 1,
      mode: $('#set-planning-mode').value === 'classic' ? 'classic' : 'ai-interpreted',
      provider: brief.identity?.provider || 'offline',
      model: null,
      summary: `${preferred.label} selected from ${result.accepted.length} deterministic direction${result.accepted.length === 1 ? '' : 's'}.`,
      warnings: [],
      evaluation: null,
      candidatePool: null,
      planningDurationMs: null,
      generatedAt: new Date().toISOString(),
    };
    renderSetPlan();
    $('#set-builder-message').textContent =
      `${result.accepted.length} distinct direction${result.accepted.length === 1 ? '' : 's'} ready · ${preferred.label} applied at ${preferred.health.score}/100. Switch directions below to compare.`;
  }
  function planningJourney(brief) {
    if (brief.identity?.journey?.sections?.length) return brief.identity.journey;
    const genres = [...brief.detailedGenres, ...brief.genres];
    const energy = { rise: [3.5, 7.5], 'peak-release': [4, 8], waves: [4.5, 7], steady: [5.5, 5.5] }[brief.curve] || [
      4.5, 6.5,
    ];
    return {
      version: 1,
      summary: 'Single editable journey derived from the structured set brief.',
      durationMinutes: brief.length,
      sections: [
        {
          id: 'section-1',
          name: 'Full set',
          durationPercent: 100,
          energyStart: energy[0],
          energyEnd: energy[1],
          genres,
          characteristics: [brief.vibe, brief.curve].filter(Boolean),
          purpose: 'Honor the structured brief while maintaining a playable flow.',
        },
      ],
    };
  }
  function planningTrackCount(brief) {
    const pool = eligibleSetTracks(brief);
    if (pool.length < 2)
      throw new Error(
        `Only ${pool.length} analyzed track${pool.length === 1 ? '' : 's'} passed the hard filters. Check BPM, vocals, timing, exclusions, and manually selected genres.`,
      );
    const averageSeconds =
      pool.reduce((sum, track) => sum + Math.max(90, Number(track.duration_seconds || 210) - 30), 0) / pool.length;
    const protectedCount = new Set([...state.requiredIds, ...state.lockedIds]).size;
    if (protectedCount > 100) throw new Error('AI Planned mode supports at most 100 required or locked tracks.');
    return Math.max(2, protectedCount, Math.min(pool.length, Math.ceil((brief.length * 60) / averageSeconds)));
  }
  function catalogIds(ids) {
    const bySetId = new Map(state.library.map((track) => [setTrackId(track), setCatalogTrackId(track)]));
    return [...ids].map((id) => bySetId.get(id)).filter(Boolean);
  }
  async function cancelAITrackPlan() {
    planningController?.abort();
    const jobId = activePlanningJobId;
    activePlanningJobId = '';
    if (jobId) await planningClient.cancel(jobId).catch(() => null);
  }
  async function loadAIObservability() {
    const status = $('#set-ai-operations-status'),
      root = $('#set-ai-operations-summary');
    if (!status || !root) return;
    try {
      const report = await planningClient.observability();
      status.textContent = `${report.completedCount} completed · ${report.failedCount} failed · ${report.canceledCount} canceled`;
      root.innerHTML = aiObservabilityCards(report, escapeHtml);
    } catch (error) {
      status.textContent = error.message || String(error);
      root.innerHTML = '';
    }
  }
  async function generateAITrackPlan() {
    await cancelAITrackPlan();
    const brief = setBrief(),
      journey = planningJourney(brief),
      targetTrackCount = planningTrackCount(brief);
    planningController = new AbortController();
    const started = await planningClient.start({
      brief,
      journey,
      target_duration_minutes: brief.length,
      target_track_count: targetTrackCount,
      required_track_ids: catalogIds(state.requiredIds),
      excluded_track_ids: catalogIds(state.excludedIds),
      locked_track_ids: catalogIds(state.lockedIds),
      per_section_limit: Math.min(100, Math.max(30, targetTrackCount)),
      total_limit: 100,
    });
    activePlanningJobId = started.jobId;
    $('#set-cancel-planning').hidden = false;
    const result = await planningClient.wait(started.jobId, {
      signal: planningController.signal,
      onProgress: (state) => {
        $('#set-builder-message').textContent = `${state.stage} · ${state.progress || 0}%`;
      },
    });
    activePlanningJobId = '';
    planningController = null;
    $('#set-cancel-planning').hidden = true;
    const byCatalogId = new Map(state.library.map((track) => [setCatalogTrackId(track), track]));
    const selected = result.plan.map((item) => {
      const track = byCatalogId.get(item.id);
      if (!track) throw new Error(`Validated catalog track ${item.id} is not loaded in the browser.`);
      track._aiSelectionReason = item.selectionReason;
      track._planSectionId = item.sectionId;
      track._candidateMetrics = {
        technicalScore: item.technicalScore || 0,
        preferenceAdjustment: item.preferenceAdjustment || 0,
        baselineRank: item.baselineRank || 0,
        personalizedRank: item.personalizedRank || 0,
        rankDelta: item.rankDelta || 0,
        matchTier: item.matchTier || 'unknown',
      };
      return track;
    });
    if (state.plan.length) pushSetHistory();
    state.plan = improveSetOrder(selected, brief);
    resetSetReviewDraft();
    state.proposals = [];
    state.activeProposal = '';
    state.transitionSettings = {};
    currentPlanningReceipt = {
      version: 1,
      mode: result.mode,
      provider: result.provider,
      model: result.model,
      summary: result.summary,
      warnings: result.warnings || [],
      evaluation: result.evaluation || null,
      comparison: result.comparison || null,
      modelRepairs: result.modelRepairs || [],
      candidatePool: result.candidatePool || null,
      fallbackReason: result.fallbackReason || null,
      planningDurationMs: result.planningDurationMs ?? null,
      generatedAt: new Date().toISOString(),
    };
    currentPlanningReceipt.observability = result.observability || null;
    void loadAIObservability();
    $('#set-builder-message').textContent = 'Validated track order ready. Optimizing transition techniques…';
    await autoOptimizeSetTransitions();
    renderSetPlan();
    const mixHealth = setHealth();
    const warningCount = result.warnings?.length || 0;
    const source =
      result.mode === 'ai-planned' ? `${result.provider} · ${result.model}` : 'deterministic safety fallback';
    $('#set-builder-message').textContent =
      mixHealth.score >= brief.minimumHealth
        ? `${result.summary} ${selected.length} tracks · ${source} · ${mixHealth.score}/100 mix health.`
        : `${result.summary} Draft retained for repair · ${mixHealth.score}/100 mix health is below your ${brief.minimumHealth} target · ${warningCount} validation warning${warningCount === 1 ? '' : 's'}.`;
  }
  function setPlanSnapshot() {
    return snapshotSetPlan(state, setTrackId);
  }
  function restoreSetSnapshot(snapshot, render = true) {
    restoreSetPlan(state, snapshot, state.library, setTrackId);
    if (render) renderSetPlan();
  }
  async function selectSetProposal(id) {
    const next = state.proposals.find((proposal) => proposal.id === id && proposal.accepted);
    if (!next || id === state.activeProposal) return;
    const current = state.proposals.find((proposal) => proposal.id === state.activeProposal);
    if (current) {
      current.snapshot = setPlanSnapshot();
      current.health = setHealth();
    }
    stopTransitionPreview();
    pushSetHistory();
    state.activeProposal = id;
    restoreSetSnapshot(next.snapshot, false);
    const switchNonce = ++proposalSwitchNonce;
    const needsOptimization = !Object.keys(state.transitionSettings).length;
    renderSetPlan();
    $('#set-builder-message').textContent = needsOptimization
      ? `${next.label} applied · ${setHealth().score}/100 health. Optimizing its transitions in the background…`
      : `${next.label} applied · ${setHealth().score}/100 health. Your edits to the other directions are saved.`;
    if (!needsOptimization) return;
    try {
      const optimized = await autoOptimizeSetTransitions();
      if (switchNonce !== proposalSwitchNonce || state.activeProposal !== id) return;
      next.snapshot = setPlanSnapshot();
      next.health = setHealth();
      renderSetPlan();
      $('#set-builder-message').textContent =
        `${next.label} applied · ${next.health.score}/100 health · ${optimized} transition${optimized === 1 ? '' : 's'} optimized. Your edits to the other directions are saved.`;
    } catch (error) {
      if (switchNonce !== proposalSwitchNonce || state.activeProposal !== id) return;
      console.error('Set proposal optimization failed', error);
      $('#set-builder-message').textContent =
        `${next.label} is ready, but automatic transition optimization failed: ${error?.message || error}. You can still edit each mix manually.`;
      notify('The set direction changed, but some transitions could not be optimized.', 'danger');
    }
  }
  function renderSetProposals() {
    const root = $('#set-proposals');
    if (!root) return;
    root.innerHTML = setProposalMarkup(state.proposals, state.activeProposal, escapeHtml);
    root.querySelectorAll('[data-proposal]').forEach((button) => {
      button.onclick = () => selectSetProposal(button.dataset.proposal);
      button.onkeydown = (event) => {
        if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
        event.preventDefault();
        const available = [...root.querySelectorAll('[data-proposal]:not(:disabled)')];
        const offset = ['ArrowRight', 'ArrowDown'].includes(event.key) ? 1 : -1;
        const next = available[(available.indexOf(button) + offset + available.length) % available.length];
        next?.focus();
        next?.click();
      };
    });
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
  const transitionEditor = createSetTransitionEditor({
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
      getPlanningReceipt: () => currentPlanningReceipt,
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
      getPlanningReceipt: () => currentPlanningReceipt,
      setPlanningReceipt: (receipt) => {
        currentPlanningReceipt = receipt;
      },
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
        currentPreferenceProfile = await setBuilderApi.setPersonalization(event.currentTarget.checked);
        renderPreferenceProfile();
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
        currentPreferenceProfile = await setBuilderApi.resetPreferences();
        renderPreferenceProfile();
        $('#set-builder-message').textContent = 'Learned Set Builder preferences reset.';
      } catch (error) {
        notify(error.message, 'danger');
      }
    };
    $$('[data-set-decision]').forEach(
      (button) =>
        (button.onclick = () => {
          currentSetDecision = button.dataset.setDecision;
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
import { createSetPlanView } from './set-builder-plan-view.js';
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
