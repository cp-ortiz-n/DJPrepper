export const SET_BRIEF_MODES = Object.freeze({
  AI: 'ai',
  MANUAL: 'manual',
});

export const SET_TRACK_PLANNERS = Object.freeze({
  AI: 'ai',
  DETERMINISTIC: 'deterministic',
});

export function resolveSetPlanningMode(authoringMode, trackPlanner) {
  if (trackPlanner === SET_TRACK_PLANNERS.AI) return 'ai-planned';
  return authoringMode === SET_BRIEF_MODES.AI ? 'interpreted' : 'classic';
}

export function inferSetWorkflow(planningMode, hasIntention = false) {
  const mode = String(planningMode || '');
  return {
    authoringMode: mode === 'interpreted' || hasIntention ? SET_BRIEF_MODES.AI : SET_BRIEF_MODES.MANUAL,
    trackPlanner: mode === 'ai-planned' ? SET_TRACK_PLANNERS.AI : SET_TRACK_PLANNERS.DETERMINISTIC,
  };
}

export function setBriefModeMessage(authoringMode) {
  return authoringMode === SET_BRIEF_MODES.MANUAL
    ? 'Choose the musical direction yourself. These controls become the set brief.'
    : 'Describe the outcome. Local AI will translate it into a brief you can review.';
}

export function resolveStructuredGenreFilters(authoringMode, { genres, detailedGenres, excludedGenres, weights }) {
  if (authoringMode === SET_BRIEF_MODES.AI) {
    return { genres: [], detailedGenres: [], excludedGenres: [], weights: {} };
  }
  return {
    genres: [...genres],
    detailedGenres: [...detailedGenres],
    excludedGenres: [...excludedGenres],
    weights: { ...weights },
  };
}

export function requiresStrictGenreEligibility(authoringMode) {
  return authoringMode === SET_BRIEF_MODES.MANUAL;
}

export function allowsCandidateGenre({
  authoringMode,
  directGenre,
  requestedGenreMatch,
  hasInterpretedIdentity,
  drift,
  preferredIdentityMatches,
}) {
  if (!requiresStrictGenreEligibility(authoringMode)) return true;
  return (
    (directGenre && requestedGenreMatch) || (hasInterpretedIdentity && drift === 'wide' && preferredIdentityMatches > 0)
  );
}

export function passesSetCandidateHardFilters({
  explicitlyExcluded,
  genreEligible,
  detailedGenreEligible,
  excludedGenreMatch,
  bpmEligible,
  vocalEligible,
  timingEligible,
}) {
  return (
    !explicitlyExcluded &&
    genreEligible &&
    detailedGenreEligible &&
    !excludedGenreMatch &&
    bpmEligible &&
    vocalEligible &&
    timingEligible
  );
}

export function createSetWorkflowController({ $, $$ }) {
  const briefMode = () => $('[name="set-brief-mode"]:checked')?.value || SET_BRIEF_MODES.AI;
  const trackPlanner = () => $('[name="set-track-planner"]:checked')?.value || SET_TRACK_PLANNERS.AI;
  const syncPlanningMode = () => {
    const mode = resolveSetPlanningMode(briefMode(), trackPlanner());
    $('#set-planning-mode').value = mode;
    return mode;
  };
  const applyBriefMode = (mode, { announce = true } = {}) => {
    const normalized = mode === SET_BRIEF_MODES.MANUAL ? SET_BRIEF_MODES.MANUAL : SET_BRIEF_MODES.AI;
    $('#set-builder-form').dataset.briefMode = normalized;
    $('#set-ai-brief').hidden = normalized !== SET_BRIEF_MODES.AI;
    $('#set-manual-brief').hidden = normalized !== SET_BRIEF_MODES.MANUAL;
    $$('[name="set-brief-mode"]').forEach((input) => {
      input.checked = input.value === normalized;
    });
    $('#set-brief-mode-help').textContent = setBriefModeMessage(normalized);
    syncPlanningMode();
    if (announce)
      $('#set-builder-message').textContent =
        normalized === SET_BRIEF_MODES.AI
          ? 'Describe the set, then review the direction before building it.'
          : 'Manual brief enabled. Configure the direction, then choose how tracks should be planned.';
    return normalized;
  };
  return { applyBriefMode, briefMode, syncPlanningMode, trackPlanner };
}

export function createSetIntentionController({ $, api, providerView, offlineInterpret, vocabulary, durationMinutes }) {
  const showProvider = (status) => {
    const badge = $('#set-provider-status');
    if (!badge) return;
    const view = providerView(status);
    Object.assign(badge, { className: view.className, textContent: view.text, title: view.title });
  };
  const refreshProviderStatus = async () => {
    const badge = $('#set-provider-status');
    if (badge) Object.assign(badge, { className: 'set-provider-status checking', textContent: 'Checking local AI…' });
    try {
      showProvider(await api.providerStatus());
    } catch (_) {
      showProvider({ available: false, provider: 'offline' });
    }
  };
  const interpret = async (text) => {
    try {
      return { ...(await api.interpretIntention(text, vocabulary())), text };
    } catch (_) {
      return { ...offlineInterpret(text, vocabulary()), text, provider: 'offline' };
    }
  };
  const interpretAndPlan = async (text) => {
    try {
      const prepared = await api.prepareBrief({
        brief: text,
        catalogVocabulary: vocabulary(),
        durationMinutes: durationMinutes(),
      });
      return { ...prepared.interpretation, text, journey: prepared.journey, cache: prepared.cache };
    } catch (error) {
      if (![404, 503].includes(error.status)) {
        console.warn('Brief preparation failed; using offline interpretation:', error);
        return { ...offlineInterpret(text, vocabulary()), text, provider: 'offline' };
      }
      console.warn('Combined brief preparation failed; using compatibility workflow:', error);
    }
    const interpreted = await interpret(text);
    try {
      interpreted.journey = await api.planJourney({
        brief: text,
        interpretedIntention: interpreted,
        catalogVocabulary: vocabulary(),
        durationMinutes: durationMinutes(),
      });
    } catch (error) {
      console.warn('Journey planning failed:', error);
    }
    return interpreted;
  };
  return { interpretAndPlan, refreshProviderStatus, showProvider };
}
