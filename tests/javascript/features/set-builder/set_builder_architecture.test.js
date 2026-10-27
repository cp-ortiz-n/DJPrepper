import test from 'node:test';
import assert from 'node:assert/strict';

import { createApiClient } from '../../../../frontend/core/api-client.js';
import { createSetBuilderApi } from '../../../../frontend/features/set-builder/api.js';
import {
  createClassicSetPlanner,
  optimizePlanOrder,
} from '../../../../frontend/features/set-builder/classic-planner.js';
import { createSetEditCommands } from '../../../../frontend/features/set-builder/commands.js';
import { createSetBuilderFeedback } from '../../../../frontend/features/set-builder/feedback.js';
import {
  canonicalGenreNames,
  catalogGenreMentions,
  createCatalogGenreVocabulary,
  mergeCatalogGenreVocabulary,
} from '../../../../frontend/features/set-builder/genre-vocabulary.js';
import {
  excludedGenreMentions,
  reconcileInterpretedGenreAuthority,
  repairJourneyGenrePolicy,
  reviewJourneyGenrePolicy,
} from '../../../../frontend/features/set-builder/journey-policy.js';
import { interpretSetIntention } from '../../../../frontend/features/set-builder/policy.js';
import { createSetPlanView } from '../../../../frontend/features/set-builder/plan-view.js';
import {
  applyExplicitSetPlanChoice,
  recoverSavedSetPlan,
  requireUniqueSetPlan,
} from '../../../../frontend/features/set-builder/plan-integrity.js';
import { createSetPlanningSession } from '../../../../frontend/features/set-builder/planning-session.js';
import {
  assignPlanSections,
  lockedTrackSections,
  planningJourney,
} from '../../../../frontend/features/set-builder/planning-request.js';
import {
  comparePlanRevisions,
  createSetRegenerationCommand,
  revisionComparisonLabel,
} from '../../../../frontend/features/set-builder/regeneration.js';
import {
  deduplicateSetRecordings,
  reconcileSetRecordingFamilies,
  recordingVersionAlternatives,
  recordingVersionLabel,
  setRecordingKey,
} from '../../../../frontend/features/set-builder/recording-identity.js';
import {
  buildVersionAwareReplacementCatalog,
  defaultVersionAwareReplacements,
  searchVersionAwareReplacements,
} from '../../../../frontend/features/set-builder/version-alternatives.js';
import {
  formatProgressElapsed,
  normalizeProgressPercent,
  progressMarkup,
} from '../../../../frontend/features/set-builder/progress-view.js';
import {
  buildSetCsv,
  buildSetM3u,
  createSavedSetController,
} from '../../../../frontend/features/set-builder/saved-sets.js';
import {
  advanceSetPlanRevision,
  createSetBuilderStore,
  resetSetBuilderWorkspace,
  restoreSetPlan,
  snapshotSetPlan,
} from '../../../../frontend/features/set-builder/state.js';
import { createSetTransitionEditor } from '../../../../frontend/features/set-builder/transition-editor.js';
import { createTrackDecisionStore } from '../../../../frontend/features/set-builder/track-decision-store.js';
import { selectValidatedReplacement } from '../../../../frontend/features/set-builder/track-rejection.js';
import {
  bindTrackReordering,
  dropDestinationIndex,
} from '../../../../frontend/features/set-builder/track-reordering.js';
import {
  compactTrackSummaryMarkup,
  trackStateChips,
  workspaceIdentity,
} from '../../../../frontend/features/set-builder/workspace-shell.js';
import {
  aiObservabilityCards,
  fallbackPolicyMarkup,
  intentionProviderView,
  journeyEnergyRange,
  journeyEvidenceLabel,
  planActionAvailability,
  setProposalMarkup,
} from '../../../../frontend/features/set-builder/view-model.js';
import {
  SET_BRIEF_MODES,
  SET_TRACK_PLANNERS,
  allowsCandidateGenre,
  createSetIntentionController,
  createSetWorkflowController,
  inferSetWorkflow,
  offlineJourneyFromInterpretation,
  passesSetCandidateHardFilters,
  requiresStrictGenreEligibility,
  resolveStructuredGenreFilters,
  resolveSetPlanningMode,
  setBriefModeMessage,
  setPlanningPresentation,
} from '../../../../frontend/features/set-builder/workflow.js';

const trackId = (track) => track.id;
const response = (payload, { ok = true, status = 200 } = {}) => ({ ok, status, json: async () => payload });
const escapeHtml = (value) => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');

function transitionEditorFor(state, overrides = {}) {
  return createSetTransitionEditor({
    state,
    setBuilderApi: {},
    $: (selector) => (selector === '#set-transition-bars' ? { value: '16' } : null),
    $$: () => [],
    notify() {},
    escapeHtml,
    clock: { currentTime: 0 },
    WaveSurfer: {},
    compatibility: () => ({ score: 80, components: { tempo: 8, key: 20 }, difference: 0, key: 'compatible' }),
    harmonicCompatibility: () => ({}),
    songEnergy: (track) => track.energy || 0.5,
    targetSetEnergy: () => 0.5,
    intendedGenreForPosition: () => '',
    trackMatchesIntendedGenre: () => true,
    identityTermMatches: () => false,
    optimizePlanOrder: (plan) => plan,
    setTrackId: trackId,
    setVocalProfile: (track) => track.vocals || 'instrumental',
    timingProfile: () => 'steady',
    stopCompactAudio() {},
    transitionReviewFeatures: () => ({}),
    transitionPreferenceAdjustment: () => 0,
    ...overrides,
  });
}

function savedSetControllerFor({ state, elements, api, recordPreference = async () => {} }) {
  return createSavedSetController({
    state,
    dom: {
      $: (selector) => elements.get(selector),
      $$: () => [],
      option: (value, label) => ({ value, label }),
      escapeHtml,
      notify() {},
    },
    api,
    storageKeys: { SET_STORAGE_KEY: 'sets', SET_STORAGE_MIGRATION_KEY: 'sets-migrated' },
    authoring: {
      inferSetWorkflow: () => ({ trackPlanner: 'deterministic', authoringMode: 'manual' }),
      interpretSetIntention: () => ({}),
      applyIntentionInterpretation() {},
      populateSetDetailedGenres() {},
      renderSetGenreMix() {},
      renderSetDetailedGenres() {},
      renderExcludedSetGenres() {},
      workflow: { applyBriefMode() {}, syncPlanningMode() {} },
    },
    plan: {
      setBrief: () => ({ name: 'Night, Set', edits: 'original' }),
      setTrackId: trackId,
      getPlanningReceipt: () => ({ source: 'deterministic' }),
      setPlanningReceipt() {},
      renderSetRules() {},
      autoOptimizeSetTransitions: async () => 0,
      renderSetPlan() {},
      transitionSettings: () => ({
        mixIn: 8,
        mixOut: 180,
        bars: 16,
        curve: 'smooth',
        technique: 'crossfade',
        tempoSync: true,
        notes: 'Blend, then lift',
      }),
    },
    music: {
      compatibility: () => ({ score: 84 }),
      trackMatchesSetGenre: () => true,
      camelotKey: () => '8A',
      energyBand: () => 'high',
      songEnergy: () => 0.8,
      libraryRoles: () => ['peak-time'],
    },
    feedback: { recordPreference },
  });
}

function planningSessionFor({ state, elements, planningClient, classicPlanner, overrides = {} }) {
  const snapshots = [];
  const session = createSetPlanningSession({
    state,
    dom: {
      $: (selector) => elements.get(selector),
      escapeHtml,
      notify() {},
    },
    clients: { planningClient, classicPlanner },
    policy: {
      genreAllocationTargets: () => ({}),
      intendedGenreForPosition: () => '',
      intentionEvaluation: () => ({ score: 0 }),
      setCandidateScore: () => 50,
      setCatalogTrackId: (track) => track.catalogId,
      setTrackId: trackId,
      songEnergy: () => 0.5,
      targetSetEnergy: () => 0.5,
      trackMatchesIntendedGenre: () => false,
      trackMatchesSetGenre: () => true,
      ...overrides.policy,
    },
    transitions: {
      autoOptimizeSetTransitions: async () => 0,
      improveSetOrder: (plan) => plan,
      setHealth: () => ({ score: 82, transitions: [], vocalClashes: 0 }),
      setHealthIssues: () => [],
      stopTransitionPreview() {},
      ...overrides.transitions,
    },
    lifecycle: {
      eligibleSetTracks: () => state.library,
      pushSetHistory() {},
      requireUniquePlan: (plan, source) =>
        requireUniqueSetPlan(plan, {
          preferredTrackIds: new Set([...state.lockedIds, ...state.requiredIds]),
          trackId,
          recordingKey: (track) => track.recordingKey || `track:${track.id}`,
          source,
        }),
      renderSetPlan() {},
      resetSetReviewDraft() {},
      restoreSetSnapshot(snapshot) {
        state.plan = state.library.filter((track) => snapshot.tracks.includes(track.id));
      },
      setBrief: () => ({
        length: 10,
        genres: [],
        detailedGenres: [],
        genreWeights: {},
        genreFlow: 'blend',
        minimumHealth: 65,
        curve: 'steady',
        identity: {},
      }),
      setPlanSnapshot() {
        const snapshot = { tracks: state.plan.map(trackId), locked: [], transitions: {} };
        snapshots.push(snapshot);
        return snapshot;
      },
      ...overrides.lifecycle,
    },
    view: {
      aiObservabilityCards: () => '<article>observability</article>',
      setProposalMarkup: () => '',
    },
  });
  return { session, snapshots };
}

test('brief preparation returns both results without requesting a second journey', async () => {
  let requests = 0;
  const controller = createSetIntentionController({
    api: {
      prepareBrief: async () => {
        requests += 1;
        return { interpretation: { preferred: ['groovy'] }, journey: { sections: [] }, cache: { hit: true } };
      },
    },
    vocabulary: () => ['House'],
    durationMinutes: () => 60,
  });
  const result = await controller.interpretAndPlan('Groovy House');
  assert.equal(requests, 1);
  assert.deepEqual(result.preferred, ['groovy']);
  assert.deepEqual(result.journey, { sections: [] });
  assert.equal(result.cache.hit, true);
});

test('recording identity collapses family members and safe title-spacing variants', () => {
  const original = { source_name: 'Funkytown.wav', artist: 'Lipps Inc', _recordingCode: 'DSC-000001' };
  const remix = { source_name: 'Funky Town (Remix).wav', artist: 'Lipps Inc', _recordingCode: 'DSC-000001' };
  const other = { source_name: 'Born to Be Alive.wav', artist: 'Patrick', _recordingCode: 'DSC-000002' };
  assert.equal(setRecordingKey(original), 'recording:DSC-000001');
  assert.deepEqual(deduplicateSetRecordings([original, remix, other]), [original, other]);
  assert.equal(
    setRecordingKey({ source_name: 'Funky Town.wav', artist: 'Lipps Inc' }),
    setRecordingKey({ source_name: 'Funkytown.wav', artist: 'Lipps Inc' }),
  );
  assert.equal(
    setRecordingKey({ source_name: 'Rasputin.wav', artist: 'Majestic' }),
    setRecordingKey({ source_name: 'Rasputin - Majestic Club.wav', artist: 'Majestic' }),
  );
});

test('recording deduplication honors an explicitly preferred catalog entry', () => {
  const original = { source_name: 'Funkytown.wav', _recordingCode: 'DSC-000001' };
  const remix = { source_name: 'Funkytown Remix.wav', _recordingCode: 'DSC-000001' };
  assert.deepEqual(deduplicateSetRecordings([original, remix], new Set(['funkytown remix.wav'])), [remix]);
});

test('recording-family reconciliation reports removals and keeps the explicitly protected version in plan order', () => {
  const original = { source_name: 'Funkytown.wav', _recordingCode: 'DSC-000001' };
  const bridge = { source_name: 'Born to Be Alive.wav', _recordingCode: 'DSC-000002' };
  const remix = { source_name: 'Funkytown Remix.wav', _recordingCode: 'DSC-000001' };

  const result = reconcileSetRecordingFamilies([original, bridge, remix], {
    preferredTrackIds: new Set(['funkytown remix.wav']),
  });

  assert.deepEqual(result.plan, [bridge, remix]);
  assert.deepEqual(result.removed, [original]);
  assert.equal(result.valid, false);
  assert.deepEqual(result.duplicateFamilies, [
    {
      recordingKey: 'recording:DSC-000001',
      keptTrackId: 'funkytown remix.wav',
      removedTrackIds: ['funkytown.wav'],
      preferredTrackIds: ['funkytown remix.wav'],
    },
  ]);
});

test('recording-family reconciliation is stable for conflicting preferences and incomplete metadata', () => {
  const firstLocked = { source_name: 'Rasputin.wav', artist: 'Majestic' };
  const secondLocked = { source_name: 'Rasputin Remix.wav', artist: 'Majestic' };
  const unknownOne = { _downloadedId: 10 };
  const unknownTwo = { _downloadedId: 11 };

  const result = reconcileSetRecordingFamilies([firstLocked, secondLocked, unknownOne, unknownTwo], {
    preferredTrackIds: new Set(['rasputin.wav', 'rasputin remix.wav']),
  });

  assert.deepEqual(result.plan, [firstLocked, unknownOne, unknownTwo]);
  assert.deepEqual(result.duplicateFamilies[0].preferredTrackIds, ['rasputin.wav', 'rasputin remix.wav']);
  assert.notEqual(setRecordingKey(unknownOne), setRecordingKey(unknownTwo));
  assert.notEqual(
    setRecordingKey({ source_name: 'One More Time.wav', artist: 'Daft Punk' }),
    setRecordingKey({ source_name: 'One More Time.wav', artist: 'Another Artist' }),
  );
});

test('manual Add or Replace keeps the chosen version unless another version is protected', () => {
  const original = { source_name: 'Funkytown.wav', _recordingCode: 'DSC-000001' };
  const bridge = { source_name: 'Born to Be Alive.wav', _recordingCode: 'DSC-000002' };
  const remix = { source_name: 'Funkytown Remix.wav', _recordingCode: 'DSC-000001' };
  const editable = {
    plan: [original, bridge, remix],
    lockedIds: new Set(),
    requiredIds: new Set(),
  };

  const chosen = applyExplicitSetPlanChoice(editable, remix);

  assert.deepEqual(editable.plan, [bridge, remix]);
  assert.deepEqual(chosen.removed, [original]);

  const protectedPlan = {
    plan: [original, bridge, remix],
    lockedIds: new Set(['funkytown.wav']),
    requiredIds: new Set(),
  };
  const protectedResult = applyExplicitSetPlanChoice(protectedPlan, remix);

  assert.deepEqual(protectedPlan.plan, [original, bridge]);
  assert.deepEqual(protectedResult.removed, [remix]);
  assert.deepEqual([...protectedPlan.lockedIds], ['funkytown.wav']);
});

test('reject replacement respects exclusions, occupied families, and adjacent transition fit', () => {
  const current = { id: 'current', family: 'family-current' };
  const occupied = { id: 'occupied', family: 'family-used' };
  const duplicate = { id: 'duplicate', family: 'family-used', fit: 100 };
  const excluded = { id: 'excluded', family: 'family-free-1', fit: 90 };
  const selected = { id: 'selected', family: 'family-free-2', fit: 70 };
  const result = selectValidatedReplacement({
    state: { plan: [occupied, current] },
    index: 1,
    candidates: [duplicate, excluded, selected],
    excludedIds: new Set(['excluded']),
    setTrackId: (track) => track.id,
    setRecordingKey: (track) => track.family,
    setCandidateScore: (track) => track.fit,
    compatibility: () => ({ score: 0 }),
    brief: {},
  });

  assert.equal(result, selected);
});

test('reject replacement preserves strict journey-section genre authority', () => {
  const current = { id: 'current', family: 'current', _planSectionId: 'warmup' };
  const latinHouse = { id: 'latin-house', family: 'house', genre: 'Latin House', fit: 30 };
  const peakTechno = { id: 'peak-techno', family: 'techno', genre: 'Techno', fit: 100 };
  const result = selectValidatedReplacement({
    state: { plan: [current] },
    index: 0,
    candidates: [peakTechno, latinHouse],
    excludedIds: new Set(),
    setTrackId: (track) => track.id,
    setRecordingKey: (track) => track.family,
    trackMatchesIntendedGenre: (track, genre) => track.genre === genre,
    setCandidateScore: (track) => track.fit,
    compatibility: () => ({ score: 0 }),
    brief: {
      identity: {
        journey: {
          genrePolicy: { mode: 'strict' },
          sections: [{ id: 'warmup', genres: ['Latin House'] }],
        },
      },
    },
  });

  assert.equal(result, latinHouse);
  assert.equal(
    selectValidatedReplacement({
      state: { plan: [current] },
      index: 0,
      candidates: [peakTechno],
      excludedIds: new Set(),
      setTrackId: (track) => track.id,
      setRecordingKey: (track) => track.family,
      trackMatchesIntendedGenre: (track, genre) => track.genre === genre,
      setCandidateScore: (track) => track.fit,
      compatibility: () => ({ score: 0 }),
      brief: {
        identity: {
          journey: {
            genrePolicy: { mode: 'strict' },
            sections: [{ id: 'warmup', genres: ['Latin House'] }],
          },
        },
      },
    }),
    undefined,
  );
});

test('durable track decisions reuse event IDs and reconcile Undo and Redo idempotently', async () => {
  const calls = [];
  const api = {
    recordPreference: async (events) => {
      calls.push(['record', events]);
      return { profile: {} };
    },
    deletePreferenceEvent: async (id) => calls.push(['delete', id]),
  };
  const store = createTrackDecisionStore({
    api,
    context: () => 'peak-time',
    features: () => ({ genre: ['Disco'] }),
    trackId: (track) => track.id,
    recordingKey: (track) => track.family,
    setIdentity: () => ({ setId: 'set-1', revisionId: 'revision-2' }),
    refresh: async () => {},
  });
  const track = { id: 'track-1', family: 'recording:one' };
  const review = await store.record(track, {
    decision: 'reject',
    reason: 'wrong-energy',
    scope: 'recording-family',
    eventId: 'decision-1',
  });

  await store.reconcile(new Map([['track-1', review]]), new Map());
  await store.reconcile(new Map(), new Map([['track-1', review]]));

  assert.equal(review.eventId, 'decision-1');
  assert.deepEqual(calls.map(([action]) => action), ['record', 'delete', 'record']);
  assert.equal(calls[0][1][0].recordingKey, 'recording:one');
  assert.equal(calls[0][1][0].scope, 'recording-family');
});

test('Keep remains durable preference feedback without becoming a structural lock', async () => {
  const calls = [];
  const store = createTrackDecisionStore({
    api: {
      recordPreference: async (events) => calls.push(events),
      deletePreferenceEvent: async () => {},
    },
    context: () => 'warm-up',
    features: () => ({ genre: ['House'] }),
    trackId: (track) => track.id,
    recordingKey: (track) => track.family,
    setIdentity: () => ({ setId: 'set-keep', revisionId: 'revision-4' }),
    refresh: async () => {},
  });

  const review = await store.record(
    { id: 'track-kept', family: 'recording:kept' },
    { decision: 'accept', eventId: 'keep-1' },
  );

  assert.deepEqual(review, {
    decision: 'accept',
    reason: '',
    scope: 'version',
    saved: true,
    eventId: 'keep-1',
    eventPayload: calls[0][0],
  });
  assert.deepEqual(calls[0][0], {
    id: 'keep-1',
    action: 'keep',
    trackId: 'track-kept',
    context: 'warm-up',
    features: { genre: ['House'] },
    reason: '',
    scope: 'version',
    recordingKey: 'recording:kept',
    setId: 'set-keep',
    revisionId: 'revision-4',
  });
});

test('recording families retain alternate versions for explicit substitution', () => {
  const original = {
    source_name: 'Funkytown.wav',
    _downloadedId: 1,
    _recordingCode: 'DSC-000001',
    _versionCode: 'ORG',
  };
  const remix = {
    source_name: 'Funkytown Remix.wav',
    _downloadedId: 2,
    _recordingCode: 'DSC-000001',
    _versionCode: 'RMX01',
  };
  const other = {
    source_name: 'Born to Be Alive.wav',
    _downloadedId: 3,
    _recordingCode: 'DSC-000002',
    _versionCode: 'ORG',
  };

  assert.deepEqual(recordingVersionAlternatives(original, [original, remix, other]), [remix]);
  assert.equal(recordingVersionLabel(original), 'Original');
  assert.equal(recordingVersionLabel(remix), 'Remix');
});

test('version-aware replacement choices separate family versions from different songs', () => {
  const original = {
    source_name: 'Funkytown.wav',
    _downloadedId: 1,
    _recordingCode: 'DSC-000001',
    _versionCode: 'ORG',
    _genre: 'Disco',
  };
  const remix = {
    source_name: 'Funkytown Remix.wav',
    _downloadedId: 2,
    _recordingCode: 'DSC-000001',
    _versionCode: 'RMX01',
    _genre: 'Disco',
  };
  const other = {
    source_name: 'Born to Be Alive.wav',
    _downloadedId: 3,
    _recordingCode: 'DSC-000002',
    _versionCode: 'ORG',
    _genre: 'Disco',
  };
  const catalog = buildVersionAwareReplacementCatalog({
    current: original,
    library: [original, remix, other],
    usedRecordingKeys: new Set(),
    recommendedTracks: [original, other],
    rankTrack: (track) => ({ track, score: track === remix ? 91 : 82 }),
  });

  assert.deepEqual(
    catalog.versionChoices.map(({ track }) => track),
    [remix],
  );
  assert.deepEqual(
    catalog.recommendedSongs.map(({ track }) => track),
    [other],
  );
  assert.deepEqual(
    defaultVersionAwareReplacements(catalog.versionChoices, catalog.recommendedSongs).map(({ group }) => group),
    ['Other versions of this song', 'Recommended different songs'],
  );
  assert.deepEqual(
    searchVersionAwareReplacements(catalog.searchable, 'remix', '').map(({ track }) => track),
    [remix],
  );
});

test('failed brief preparation does not launch more slow AI requests', async () => {
  const controller = createSetIntentionController({
    api: {
      prepareBrief: async () => {
        throw Object.assign(new Error('timeout'), { status: 502 });
      },
    },
    vocabulary: () => ['House'],
    durationMinutes: () => 60,
    offlineInterpret: () => ({ requestedGenres: ['house'] }),
  });
  const result = await controller.interpretAndPlan('House');
  assert.equal(result.provider, 'offline');
  assert.deepEqual(result.requestedGenres, ['house']);
  assert.equal(result.journey.sections.length, 3);
  assert.deepEqual(
    result.journey.sections.map((section) => section.genres),
    [['house'], ['house'], ['house']],
  );
});

test('offline journey preserves exact genres and a complete editable duration', () => {
  const journey = offlineJourneyFromInterpretation(
    { requestedGenres: ['latin techno'], genreSequence: ['latin techno'], optionalGenres: [], drift: 'none' },
    90,
  );
  assert.equal(journey.genrePolicy.mode, 'strict');
  assert.equal(
    journey.sections.reduce((total, section) => total + section.durationPercent, 0),
    100,
  );
  assert.deepEqual(
    journey.sections.flatMap((section) => section.genres),
    ['latin techno', 'latin techno', 'latin techno'],
  );
});

test('written genre brief removes nested parents and unrequested AI neighbors', () => {
  const interpreted = reconcileInterpretedGenreAuthority(
    {
      text: 'Create a Latin Techno set',
      requestedGenres: ['latin techno', 'techno'],
      optionalGenres: ['latin house', 'latin pop'],
      genreSequence: ['latin techno', 'techno'],
    },
    ['latin techno', 'techno', 'latin house', 'latin pop'],
  );
  assert.deepEqual(interpreted.requestedGenres, ['latin techno']);
  assert.deepEqual(interpreted.optionalGenres, []);
  assert.deepEqual(interpreted.genreSequence, ['latin techno']);
});

test('written disco brief restores one canonical core genre from an empty model interpretation', () => {
  const vocabulary = createCatalogGenreVocabulary([
    { _genre: 'Disco & Funk', _detailedGenre: 'Disco' },
    { _genre: 'Disco & Funk', _detailedGenre: 'Nu Disco' },
  ]);
  const interpreted = reconcileInterpretedGenreAuthority(
    {
      text: 'Create a disco set',
      requestedGenres: ['disco'],
      optionalGenres: [],
      genreSequence: [],
    },
    vocabulary,
  );
  assert.deepEqual(interpreted.requestedGenres, ['disco & funk']);
  assert.deepEqual(interpreted.optionalGenres, []);
  assert.deepEqual(interpreted.genreSequence, ['disco & funk']);
  assert.deepEqual(vocabulary, [
    {
      canonical: 'disco & funk',
      aliases: ['disco & funk', 'nu disco', 'disco', 'funk'],
      count: 2,
      aliasCounts: { 'disco & funk': 2, disco: 2, funk: 2, 'nu disco': 1 },
    },
  ]);
  assert.deepEqual(
    reconcileInterpretedGenreAuthority(
      { text: 'Create a disco set', requestedGenres: [], optionalGenres: [], genreSequence: [] },
      [],
    ).requestedGenres,
    [],
  );
});

test('catalog genre matching prefers the canonical family over an unrelated prevalent parent', () => {
  const vocabulary = [
    { canonical: 'house', aliases: ['house', 'disco'], count: 500 },
    { canonical: 'disco & funk', aliases: ['disco & funk', 'disco'], count: 20 },
  ];
  assert.deepEqual(catalogGenreMentions('Disco set', vocabulary), ['disco & funk']);
  assert.deepEqual(canonicalGenreNames(vocabulary), ['house', 'disco & funk']);
});

test('catalog genre matrix resolves families, detailed aliases, nesting, and requested order', () => {
  const tracks = [
    { _genre: 'Disco & Funk', _detailedGenre: 'Disco, Funk' },
    { _genre: 'Electronic / House / House', _detailedGenre: 'Disco' },
    { _genre: 'Electronic / House / House', _detailedGenre: 'Disco' },
    { _genre: 'Rock & Alternative', _detailedGenre: 'Alternative' },
    { _genre: 'Hip-Hop & Rap', _detailedGenre: 'Rock, Afropop' },
    { _genre: 'Electronic / House / Afro House', _detailedGenre: 'Afropop' },
    { _genre: 'Electronic / House / Afro House', _detailedGenre: 'Afropop' },
    { _genre: 'Afro & Amapiano', _detailedGenre: 'Afropop' },
    { _genre: 'Electronic / Techno / Techno', _detailedGenre: 'Techno' },
    { _genre: 'Electronic / Techno / Hard Techno', _detailedGenre: 'Hard Techno' },
    { _genre: 'Other', _detailedGenre: 'Latin Techno' },
  ];
  const vocabulary = createCatalogGenreVocabulary(tracks);
  const cases = new Map([
    ['Disco set', ['disco & funk']],
    ['Funk set', ['disco & funk']],
    ['Rock set', ['rock & alternative']],
    ['Alternative set', ['rock & alternative']],
    ['Afropop set', ['afro house']],
    ['Techno set', ['techno']],
    ['Hard Techno set', ['hard techno']],
    ['Latin Techno set', ['latin techno']],
    ['Start with house, move to disco, finish with hard techno', ['house', 'disco & funk', 'hard techno']],
  ]);
  for (const [brief, expected] of cases) assert.deepEqual(catalogGenreMentions(brief, vocabulary), expected, brief);
  for (const canonical of canonicalGenreNames(vocabulary))
    assert.deepEqual(catalogGenreMentions(`${canonical} set`, vocabulary), [canonical], canonical);
});

test('catalog vocabulary exposes playlist-supported musical identities', () => {
  const vocabulary = createCatalogGenreVocabulary([
    {
      _genre: 'Latin / Reggaeton',
      _detailedGenre: 'Neoperreo',
      _playlistIdentity: [{ value: 'latin techno', source: 'Latin Techno crate' }],
    },
  ]);

  assert.deepEqual(catalogGenreMentions('Build a Latin Techno set', vocabulary), ['latin techno']);
});

test('server catalog vocabulary remains authoritative over stale loaded tracks', () => {
  const vocabulary = mergeCatalogGenreVocabulary(
    [{ canonical: 'latin techno', aliases: ['latin techno'], count: 12 }],
    [{ _genre: 'House' }],
  );
  assert.deepEqual(canonicalGenreNames(vocabulary), ['latin techno']);
});

test('server interpretation survives a stale non-empty browser vocabulary', () => {
  const interpreted = reconcileInterpretedGenreAuthority(
    {
      text: 'Create a latin techno set, latin house to warmup',
      requestedGenres: ['latin techno', 'latin house'],
      optionalGenres: [],
      genreSequence: ['latin house', 'latin techno'],
    },
    ['house'],
  );

  assert.deepEqual(interpreted.requestedGenres, ['latin techno', 'latin house']);
  assert.deepEqual(interpreted.genreSequence, ['latin house', 'latin techno']);
});

test('trailing warmup cue assigns only the nearest preceding genre', () => {
  const interpreted = reconcileInterpretedGenreAuthority(
    {
      text: 'Create a latin techno set, latin house to warmup',
      requestedGenres: ['latin techno', 'latin house'],
      optionalGenres: [],
      genreSequence: ['latin techno', 'latin house'],
    },
    ['latin techno', 'latin house'],
  );

  assert.deepEqual(interpreted.genreSequence, ['latin house', 'latin techno']);
});

test('catalog vocabulary exposes inferred cultural identities without rewriting genre', () => {
  const vocabulary = createCatalogGenreVocabulary([
    {
      _genre: 'International / Bollywood',
      _descriptors: [{ category: 'cultural', value: 'Indian / South Asian' }],
    },
  ]);
  assert.deepEqual(catalogGenreMentions('Build an Indian party set', vocabulary), ['indian south asian']);
});

test('brief policy handles negation, warmup order, and sustained energy across a prompt matrix', () => {
  const vocabulary = [
    { canonical: 'disco & funk', aliases: ['disco', 'funk'] },
    'latin techno',
    'latin house',
    { canonical: 'indian south asian', aliases: ['indian', 'south asian'] },
    { canonical: 'hip hop & rap', aliases: ['hip hop', 'rap'] },
    'afro house',
    'schranz',
    'techno',
  ];
  const cases = [
    ['Create a latin disco set, high energy.', ['disco & funk'], [], 'peak-time'],
    ['Create a latin techno set, latin house to warmup', ['latin house', 'latin techno'], [], 'warm-up'],
    [
      'Implement a high energy disco techno, latin techno set',
      ['disco & funk', 'techno', 'latin techno'],
      [],
      'peak-time',
    ],
    [
      'Create an indian party song set, high energy all around. No rap',
      ['indian south asian'],
      ['hip hop & rap'],
      'peak-time',
    ],
    ['Create a disco set without techno', ['disco & funk'], ['techno'], null],
    ['Start with Afro House, then Techno', ['afro house', 'techno'], [], null],
    ['Build a Latin House set, no Schranz', ['latin house'], ['schranz'], null],
  ];
  for (const [brief, sequence, excluded, vibe] of cases) {
    const interpreted = interpretSetIntention(brief, vocabulary);
    assert.deepEqual(interpreted.genreSequence, sequence, brief);
    assert.deepEqual(interpreted.excludedGenres, excluded, brief);
    assert.equal(interpreted.vibe, vibe, brief);
  }
  assert.deepEqual(excludedGenreMentions('House without techno or schranz', vocabulary), ['techno', 'schranz']);

  const journey = offlineJourneyFromInterpretation(
    interpretSetIntention('Indian party set, high energy throughout. No rap', vocabulary),
  );
  assert.ok(journey.sections.every((section) => section.energyStart >= 8 && section.energyEnd >= 8));
});

test('strict journey policy repairs AI genre drift and retains it only as suggestions', () => {
  const interpreted = {
    requestedGenres: ['latin techno'],
    optionalGenres: [],
    genreSequence: ['latin techno'],
    drift: 'none',
  };
  const result = repairJourneyGenrePolicy(
    {
      genrePolicy: { mode: 'strict' },
      sections: [
        { id: 'opening', name: 'Opening', genres: ['latin techno'] },
        { id: 'build', name: 'Build', genres: ['latin house', 'techno'] },
        { id: 'closing', name: 'Closing', genres: ['latin pop', 'latin r&b'] },
      ],
    },
    interpreted,
  );
  assert.deepEqual(
    result.journey.sections.map((section) => section.genres),
    [['latin techno'], ['latin techno'], ['latin techno']],
  );
  assert.deepEqual(result.journey.sections[1].suggestedGenres, ['latin house', 'techno']);
  assert.deepEqual(result.journey.sections[2].suggestedGenres, ['latin pop', 'latin r&b']);
  assert.deepEqual(result.repairs, ['build', 'closing']);
  assert.equal(reviewJourneyGenrePolicy(result.journey, interpreted).valid, true);
});

test('strict journey policy blocks a manually reintroduced neighbor until related genres are enabled', () => {
  const interpreted = {
    requestedGenres: ['latin techno'],
    optionalGenres: [],
    genreSequence: ['latin techno'],
    drift: 'none',
  };
  const journey = {
    genrePolicy: { mode: 'strict' },
    sections: [{ id: 'build', name: 'Build', genres: ['latin techno', 'latin house'] }],
  };
  const review = reviewJourneyGenrePolicy(journey, interpreted);
  assert.equal(review.valid, false);
  assert.deepEqual(review.unapprovedGenres, ['latin house']);
  assert.deepEqual(
    review.violations.map(({ name }) => name),
    ['Build'],
  );
  assert.equal(reviewJourneyGenrePolicy({ ...journey, genrePolicy: { mode: 'related' } }, interpreted).valid, true);
});

test('Set Builder store snapshots and restores plan identity, locks, and transitions', () => {
  const storage = { getItem: () => 'true' };
  const store = createSetBuilderStore({ storage });
  const library = [
    { id: 'a', _planSectionId: 'opening' },
    { id: 'b', _planSectionId: 'closing' },
  ];
  store.plan = [...library];
  store.lockedIds.add('a');
  store.transitionSettings['a→b'] = { bars: 16 };
  store.revisionComparison = { stayed: 1, changedTrackIds: ['b'] };

  const snapshot = snapshotSetPlan(store, trackId);
  store.plan = [];
  store.lockedIds.clear();
  store.transitionSettings['a→b'].bars = 8;
  store.revisionComparison = null;
  library.forEach((track) => {
    track._planSectionId = 'wrong';
  });
  restoreSetPlan(store, snapshot, library, trackId);

  assert.equal(store.compactMode, true);
  assert.deepEqual(store.plan, library);
  assert.deepEqual([...store.lockedIds], ['a']);
  assert.deepEqual(store.transitionSettings, { 'a→b': { bars: 16 } });
  assert.deepEqual(store.revisionComparison, { stayed: 1, changedTrackIds: ['b'] });
  assert.deepEqual(
    store.plan.map((track) => track._planSectionId),
    ['opening', 'closing'],
  );
});

test('restoring a legacy snapshot keeps one recording version and honors its locked preference', () => {
  const store = createSetBuilderStore({ storage: { getItem: () => null } });
  const original = { id: 'original', family: 'family-1' };
  const bridge = { id: 'bridge', family: 'family-2' };
  const remix = { id: 'remix', family: 'family-1' };

  restoreSetPlan(
    store,
    { tracks: ['original', 'bridge', 'remix'], locked: ['remix'], transitions: {} },
    [original, bridge, remix],
    trackId,
    (track) => track.family,
  );

  assert.deepEqual(store.plan, [bridge, remix]);
  assert.deepEqual([...store.lockedIds], ['remix']);
});

test('Set Builder keeps stable draft and plan revision identities until an explicit reset', () => {
  let sequence = 0;
  const createId = (prefix) => `${prefix}-${++sequence}`;
  const store = createSetBuilderStore({ storage: { getItem: () => null }, createId });
  const library = [{ id: 'a' }];
  store.plan = [...library];

  assert.equal(store.draftId, 'draft-1');
  const first = advanceSetPlanRevision(store, { createId, now: () => '2026-10-21T12:00:00Z' });
  const snapshot = snapshotSetPlan(store, trackId);
  const second = advanceSetPlanRevision(store, { createId, now: () => '2026-10-21T12:01:00Z' });

  assert.deepEqual(first, {
    id: 'revision-2',
    number: 1,
    parentId: null,
    createdAt: '2026-10-21T12:00:00Z',
  });
  assert.equal(second.parentId, first.id);
  assert.equal(second.number, 2);

  restoreSetPlan(store, snapshot, library, trackId);
  assert.deepEqual(store.planRevision, first);
  assert.equal(store.draftId, 'draft-1');

  resetSetBuilderWorkspace(store, { createId });
  assert.equal(store.draftId, 'draft-4');
  assert.equal(store.planRevision, null);
  assert.equal(store.plan.length, 0);
  assert.equal(store.activeSavedSetId, '');
  assert.equal(store.selectedTrackId, '');
});

test('compact workspace presentation exposes plan identity and concise track states', () => {
  assert.deepEqual(workspaceIdentity({ activeSavedSetId: '', planRevision: null }), {
    stateLabel: 'Draft plan',
    revisionLabel: 'Unversioned draft',
  });
  assert.deepEqual(workspaceIdentity({ activeSavedSetId: 'saved-1', planRevision: { number: 3 } }), {
    stateLabel: 'Saved plan',
    revisionLabel: 'Revision 3',
  });
  assert.deepEqual(trackStateChips({ locked: true, decision: 'reject', changed: true }), [
    { kind: 'locked', label: 'Locked' },
    { kind: 'rejected', label: 'Rejected' },
    { kind: 'changed', label: 'Changed' },
  ]);
  const markup = compactTrackSummaryMarkup({
    track: { _genre: 'House', bpm: 124, key: 'Am' },
    transition: { score: 58 },
    locked: false,
    review: { decision: 'accept' },
    formatKey: () => '8A',
    energyLabel: 'high',
    healthThreshold: 65,
    escapeHtml,
  });
  assert.match(markup, /House/);
  assert.match(markup, /124\.0 BPM/);
  assert.match(markup, /58% match/);
  assert.match(markup, /class="warning"/);
  assert.match(markup, /Kept/);
});

test('draft persistence stays available when release checks block export', () => {
  assert.deepEqual(planActionAvailability({ planLength: 17, healthAccepted: false, healthThreshold: 65 }), {
    saveDisabled: false,
    saveTitle: 'Save this draft. Export will remain unavailable until release checks pass.',
    exportDisabled: true,
    exportTitle: 'Save this draft now, then raise mix health to 65 before exporting.',
    exportReason: 'Save this draft now, then raise mix health to 65 before exporting.',
  });
  assert.match(
    planActionAvailability({
      planLength: 17,
      healthAccepted: false,
      unresolvedRejection: true,
      healthThreshold: 65,
    }).exportReason,
    /resolve rejected tracks/,
  );
  assert.equal(planActionAvailability({ planLength: 17, healthAccepted: true }).exportDisabled, false);
  assert.equal(planActionAvailability().saveDisabled, true);
});

test('planning requests derive stable journey sections and preserve explicit locked placements', () => {
  const journey = planningJourney({
    length: 60,
    genres: ['House'],
    detailedGenres: [],
    curve: 'waves',
    vibe: 'dance',
    identity: {
      journey: {
        sections: [
          { id: 'opening', durationPercent: 40 },
          { id: 'peak', durationPercent: 60 },
        ],
      },
    },
  });
  const plan = [
    { id: 'a', catalogId: 'downloaded:1', _planSectionId: 'opening' },
    { id: 'b', catalogId: 'downloaded:2' },
    { id: 'c', catalogId: 'downloaded:3' },
  ];
  assignPlanSections(plan, journey, new Set(['a']), trackId);
  assert.deepEqual(
    plan.map((track) => track._planSectionId),
    ['opening', 'peak', 'peak'],
  );
  assert.deepEqual(
    lockedTrackSections({
      plan,
      lockedIds: new Set(['a', 'c']),
      journey,
      setTrackId: trackId,
      setCatalogTrackId: (track) => track.catalogId,
    }),
    { 'downloaded:1': 'opening', 'downloaded:3': 'peak' },
  );
});

test('regeneration compares revisions, preserves locked tracks, and creates one undoable revision', async () => {
  const library = [{ id: 'locked' }, { id: 'old' }, { id: 'new' }];
  const state = {
    plan: library.slice(0, 2),
    lockedIds: new Set(['locked']),
    requiredIds: new Set(),
    excludedIds: new Set(),
    transitionSettings: {},
    planRevision: { id: 'revision-1', number: 1 },
    revisionComparison: null,
    history: [],
    future: [],
  };
  let receipt = { planRevision: state.planRevision };
  const snapshot = () => ({ ...snapshotSetPlan(state, trackId), planningReceipt: receipt });
  const restore = (value) => {
    restoreSetPlan(state, value, library, trackId);
    receipt = value.planningReceipt;
  };
  const commands = createSetEditCommands({ store: state, snapshot, restore, render() {} });
  const regenerate = createSetRegenerationCommand({
    state,
    snapshot,
    restore,
    generate: async () => {
      commands.checkpoint();
      state.plan = [library[0], library[2]];
      state.planRevision = { id: 'revision-2', number: 2, parentId: 'revision-1' };
      receipt = { planRevision: state.planRevision };
    },
    render() {},
    getReceipt: () => receipt,
    setReceipt: (value) => {
      receipt = value;
    },
  });

  const comparison = await regenerate();
  assert.deepEqual(
    { stayed: comparison.stayed, changed: comparison.changed, lockedPreserved: comparison.lockedPreserved },
    { stayed: 1, changed: 1, lockedPreserved: 1 },
  );
  assert.equal(revisionComparisonLabel(comparison), 'Revision 2 · 1 stayed · 1 changed · 1/1 locked preserved');
  assert.equal(commands.undo(), true);
  assert.deepEqual(state.plan.map(trackId), ['locked', 'old']);
  assert.equal(state.planRevision.number, 1);
  assert.equal(receipt.planRevision.number, 1);
});

test('failed regeneration rolls every partial plan mutation back to the stable revision', async () => {
  const library = [{ id: 'locked' }, { id: 'old' }, { id: 'partial' }];
  const state = {
    plan: library.slice(0, 2),
    lockedIds: new Set(['locked']),
    requiredIds: new Set(),
    excludedIds: new Set(),
    transitionSettings: { 'locked→old': { bars: 16 } },
    planRevision: { id: 'revision-1', number: 1 },
    revisionComparison: null,
    history: [],
    future: [],
  };
  let receipt = { planRevision: state.planRevision };
  const snapshot = () => ({ ...snapshotSetPlan(state, trackId), planningReceipt: receipt });
  const restore = (value) => {
    restoreSetPlan(state, value, library, trackId);
    receipt = value.planningReceipt;
  };
  const regenerate = createSetRegenerationCommand({
    state,
    snapshot,
    restore,
    generate: async () => {
      state.history.push(snapshot());
      state.plan = [library[2]];
      state.transitionSettings = {};
      receipt = { planRevision: { id: 'partial', number: 2 } };
      throw new Error('validation failed');
    },
    render() {},
    getReceipt: () => receipt,
    setReceipt: (value) => {
      receipt = value;
    },
  });

  await assert.rejects(regenerate(), /validation failed/);
  assert.deepEqual(state.plan.map(trackId), ['locked', 'old']);
  assert.deepEqual(state.transitionSettings, { 'locked→old': { bars: 16 } });
  assert.equal(state.planRevision.number, 1);
  assert.equal(state.history.length, 0);
  assert.equal(receipt.planRevision.number, 1);
});

test('provider labels never expose a missing model as undefined', () => {
  assert.deepEqual(intentionProviderView({ available: true, provider: 'ollama' }), {
    className: 'set-provider-status ready',
    text: 'Local AI ready',
    title: 'Ollama is available for local language interpretation.',
  });
  assert.equal(intentionProviderView({ available: true, provider: 'openai' }).text, 'Cloud AI ready');
  assert.equal(
    intentionProviderView({ available: true, provider: 'ollama', model: 'qwen' }).text,
    'Local AI ready · qwen',
  );
});

test('brief authoring and track planning remain independent choices', () => {
  assert.equal(resolveSetPlanningMode(SET_BRIEF_MODES.AI, SET_TRACK_PLANNERS.AI), 'ai-planned');
  assert.equal(resolveSetPlanningMode(SET_BRIEF_MODES.MANUAL, SET_TRACK_PLANNERS.AI), 'ai-planned');
  assert.equal(resolveSetPlanningMode(SET_BRIEF_MODES.AI, SET_TRACK_PLANNERS.DETERMINISTIC), 'interpreted');
  assert.equal(resolveSetPlanningMode(SET_BRIEF_MODES.MANUAL, SET_TRACK_PLANNERS.DETERMINISTIC), 'classic');
  assert.match(setBriefModeMessage(SET_BRIEF_MODES.AI), /Local AI/);
  assert.match(setBriefModeMessage(SET_BRIEF_MODES.MANUAL), /yourself/);
});

test('AI-authored briefs ignore hidden manual genre filters while manual briefs retain them', () => {
  const filters = {
    genres: ['old parent'],
    detailedGenres: ['old detail'],
    excludedGenres: ['old exclusion'],
    weights: { 'old parent': 100 },
  };

  assert.deepEqual(resolveStructuredGenreFilters(SET_BRIEF_MODES.AI, filters), {
    genres: [],
    detailedGenres: [],
    excludedGenres: [],
    weights: {},
  });
  assert.deepEqual(resolveStructuredGenreFilters(SET_BRIEF_MODES.MANUAL, filters), filters);
});

test('genre eligibility stays consistent across every authoring and planner combination', () => {
  const combinations = [
    [SET_BRIEF_MODES.AI, SET_TRACK_PLANNERS.AI, false],
    [SET_BRIEF_MODES.AI, SET_TRACK_PLANNERS.DETERMINISTIC, false],
    [SET_BRIEF_MODES.MANUAL, SET_TRACK_PLANNERS.AI, true],
    [SET_BRIEF_MODES.MANUAL, SET_TRACK_PLANNERS.DETERMINISTIC, true],
  ];

  combinations.forEach(([authoringMode, planner, expected]) => {
    assert.equal(requiresStrictGenreEligibility(authoringMode), expected, `${authoringMode}/${planner}`);
  });
});

test('AI-authored genres become ranking guidance after related genres are authorized', () => {
  assert.equal(
    allowsCandidateGenre({
      authoringMode: SET_BRIEF_MODES.AI,
      directGenre: false,
      requestedGenreMatch: false,
      hasInterpretedIdentity: true,
      drift: 'moderate',
      preferredIdentityMatches: 0,
    }),
    true,
  );
});

test('manual genre filters remain strict while wide identity drift remains available', () => {
  const base = {
    authoringMode: SET_BRIEF_MODES.MANUAL,
    directGenre: false,
    requestedGenreMatch: false,
    hasInterpretedIdentity: false,
    drift: 'none',
    preferredIdentityMatches: 0,
  };
  assert.equal(allowsCandidateGenre(base), false);
  assert.equal(allowsCandidateGenre({ ...base, directGenre: true, requestedGenreMatch: true }), true);
  assert.equal(
    allowsCandidateGenre({
      ...base,
      hasInterpretedIdentity: true,
      drift: 'wide',
      preferredIdentityMatches: 1,
    }),
    true,
  );
});

test('AI-authored exact genre briefs remain strict until related genres are enabled', () => {
  assert.equal(
    allowsCandidateGenre({
      authoringMode: SET_BRIEF_MODES.AI,
      directGenre: true,
      requestedGenreMatch: false,
      hasInterpretedIdentity: true,
      drift: 'none',
      preferredIdentityMatches: 2,
    }),
    false,
  );
  assert.equal(
    allowsCandidateGenre({
      authoringMode: SET_BRIEF_MODES.AI,
      directGenre: true,
      requestedGenreMatch: false,
      hasInterpretedIdentity: true,
      drift: 'moderate',
      preferredIdentityMatches: 0,
    }),
    true,
  );
});

test('candidate hard filters exclude only explicit catalog and mixing constraints', () => {
  const eligible = {
    explicitlyExcluded: false,
    genreEligible: true,
    detailedGenreEligible: true,
    excludedGenreMatch: false,
    bpmEligible: true,
    vocalEligible: true,
    timingEligible: true,
  };
  assert.equal(passesSetCandidateHardFilters(eligible), true);
  Object.keys(eligible).forEach((field) => {
    const failingValue = field === 'explicitlyExcluded' || field === 'excludedGenreMatch';
    assert.equal(passesSetCandidateHardFilters({ ...eligible, [field]: failingValue }), false, field);
  });
});

test('saved planning modes migrate into the two-part workflow without losing intention', () => {
  assert.deepEqual(inferSetWorkflow('interpreted'), {
    authoringMode: SET_BRIEF_MODES.AI,
    trackPlanner: SET_TRACK_PLANNERS.DETERMINISTIC,
  });
  assert.deepEqual(inferSetWorkflow('classic'), {
    authoringMode: SET_BRIEF_MODES.MANUAL,
    trackPlanner: SET_TRACK_PLANNERS.DETERMINISTIC,
  });
  assert.deepEqual(inferSetWorkflow('ai-planned', true), {
    authoringMode: SET_BRIEF_MODES.AI,
    trackPlanner: SET_TRACK_PLANNERS.AI,
  });
});

test('planning presentation keeps brief provenance separate from track selection', () => {
  assert.deepEqual(setPlanningPresentation(SET_BRIEF_MODES.AI, SET_TRACK_PLANNERS.AI), {
    actionLabel: 'Build AI-curated set',
    summary: 'Direction: AI interpreted · Tracks: AI curated',
  });
  assert.deepEqual(setPlanningPresentation(SET_BRIEF_MODES.MANUAL, SET_TRACK_PLANNERS.DETERMINISTIC), {
    actionLabel: 'Build rules-based set',
    summary: 'Direction: Manual brief · Tracks: Rules-based',
  });
});

test('workflow controller updates mode surfaces without clearing authored values', () => {
  const elements = new Map([
    ['#set-builder-form', { dataset: {} }],
    ['#set-ai-brief', { hidden: false }],
    ['#set-manual-brief', { hidden: true }],
    ['#set-brief-mode-help', { textContent: '' }],
    ['#set-planning-mode', { value: '' }],
    ['#set-planning-summary', { textContent: '' }],
    ['#set-generate', { textContent: '', disabled: false }],
    ['#set-builder-message', { textContent: '' }],
  ]);
  const briefInputs = [
    { value: 'ai', checked: true },
    { value: 'manual', checked: false },
  ];
  const plannerInputs = [
    { value: 'ai', checked: true },
    { value: 'deterministic', checked: false },
  ];
  const $ = (selector) => {
    if (selector === '[name="set-brief-mode"]:checked') return briefInputs.find((item) => item.checked);
    if (selector === '[name="set-track-planner"]:checked') return plannerInputs.find((item) => item.checked);
    return elements.get(selector);
  };
  const $$ = (selector) => (selector.includes('brief-mode') ? briefInputs : plannerInputs);
  const controller = createSetWorkflowController({ $, $$ });

  controller.applyBriefMode('manual');

  assert.equal(elements.get('#set-ai-brief').hidden, true);
  assert.equal(elements.get('#set-manual-brief').hidden, false);
  assert.equal(elements.get('#set-planning-mode').value, 'ai-planned');
  assert.equal(elements.get('#set-planning-summary').textContent, 'Direction: Manual brief · Tracks: AI curated');
  assert.equal(elements.get('#set-generate').textContent, 'Build AI-curated set');
  assert.match(elements.get('#set-brief-mode-help').textContent, /yourself/);
});

test('Set edit commands own checkpoint, move, undo, redo, and bounded history', () => {
  const store = createSetBuilderStore({ storage: null });
  store.plan = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
  let renders = 0;
  const commands = createSetEditCommands({
    store,
    historyLimit: 2,
    snapshot: () => snapshotSetPlan(store, trackId),
    restore: (snapshot) => restoreSetPlan(store, snapshot, [{ id: 'a' }, { id: 'b' }, { id: 'c' }], trackId),
    render: () => {
      renders += 1;
    },
  });

  assert.equal(commands.move(0, 2), true);
  assert.deepEqual(store.plan.map(trackId), ['b', 'c', 'a']);
  assert.equal(commands.undo(), true);
  assert.deepEqual(store.plan.map(trackId), ['a', 'b', 'c']);
  assert.equal(commands.redo(), true);
  assert.deepEqual(store.plan.map(trackId), ['b', 'c', 'a']);
  assert.equal(commands.move(0, 9), false);
  assert.equal(commands.move(-1, 1), false);
  commands.checkpoint();
  commands.checkpoint();
  commands.checkpoint();
  assert.equal(store.history.length, 2);
  assert.equal(renders, 3);
});

test('drag reordering resolves before and after destinations after removing the source', () => {
  assert.equal(dropDestinationIndex(0, 2, false, 4), 1);
  assert.equal(dropDestinationIndex(0, 2, true, 4), 2);
  assert.equal(dropDestinationIndex(3, 1, false, 4), 1);
  assert.equal(dropDestinationIndex(3, 1, true, 4), 2);
  assert.equal(dropDestinationIndex(1, 1, false, 4), 1);
  assert.equal(dropDestinationIndex(-1, 1, false, 4), -1);
  assert.equal(dropDestinationIndex(1, 8, false, 4), -1);
});

test('track reordering binds explicit drag and keyboard interactions', () => {
  const card = (index) => {
    const classes = new Set();
    const handle = {
      listeners: {},
      addEventListener(type, listener) {
        this.listeners[type] = listener;
      },
    };
    return {
      dataset: { index: String(index) },
      handle,
      classList: {
        add: (...names) => names.forEach((name) => classes.add(name)),
        remove: (...names) => names.forEach((name) => classes.delete(name)),
        contains: (name) => classes.has(name),
        toggle: (name, active) => (active ? classes.add(name) : classes.delete(name)),
      },
      querySelector: () => handle,
      getBoundingClientRect: () => ({ top: 0, height: 100 }),
      contains: () => false,
    };
  };
  const cards = [card(0), card(1), card(2)];
  const moves = [];
  let focused = false;
  bindTrackReordering({
    cards,
    planLength: cards.length,
    moveTrack(from, to) {
      moves.push([from, to]);
      return true;
    },
    documentRef: { querySelector: () => ({ focus: () => (focused = true) }) },
    schedule: (callback) => callback(),
  });

  let prevented = false;
  cards[1].handle.listeners.keydown({ key: 'ArrowDown', preventDefault: () => (prevented = true) });
  assert.equal(prevented, true);
  assert.equal(focused, true);
  assert.deepEqual(moves, [[1, 2]]);

  const transfer = { setData() {}, effectAllowed: '', dropEffect: '' };
  cards[0].ondragstart({ target: { closest: () => cards[0].handle }, dataTransfer: transfer });
  cards[2].ondragover({ preventDefault() {}, clientY: 90, dataTransfer: transfer });
  assert.equal(cards[2].classList.contains('drag-after'), true);
  cards[2].ondrop({ preventDefault() {} });
  assert.deepEqual(moves.at(-1), [0, 2]);
  assert.equal(cards[2].classList.contains('drag-after'), false);
});

test('transition editor owns health, runtime, default transition settings, and order optimization', () => {
  const state = {
    plan: [
      { id: 'a', duration_seconds: 200, bpm: 120, vocals: 'vocal-forward' },
      { id: 'b', duration_seconds: 200, bpm: 122, vocals: 'vocal-forward' },
    ],
    lockedIds: new Set(['a']),
    transitionSettings: {},
  };
  let optimization;
  const editor = transitionEditorFor(state, {
    compatibility: () => ({ score: 77, components: { tempo: 4, key: 20 }, difference: 0.01, key: 'compatible' }),
    optimizePlanOrder: (plan, options) => {
      optimization = { plan, options };
      return [...plan].reverse();
    },
  });

  assert.deepEqual(editor.setHealth(), {
    score: 74,
    transitions: [
      {
        score: 77,
        components: { tempo: 4, key: 20 },
        difference: 0.01,
        key: 'compatible',
        from: 0,
        to: 1,
      },
    ],
    vocalClashes: 1,
  });
  assert.equal(editor.setRuntime(), 370);
  assert.deepEqual(editor.setHealthIssues(editor.setHealth(), 80), ['1→2 77% (tempo)', '1 vocal clash']);
  assert.deepEqual(editor.transitionSettings(1), {
    mixOut: 168,
    mixIn: 0,
    bars: 16,
    curve: 'smooth',
    technique: 'crossfade',
    tempoSync: true,
    notes: '',
  });
  assert.deepEqual(editor.improveSetOrder(state.plan, { identity: {} }).map(trackId), ['b', 'a']);
  assert.equal(optimization.options.isFixed(state.plan[0]), true);
  assert.equal(optimization.options.isFixed(state.plan[1]), false);
  assert.equal(Object.isFrozen(editor), true);
});

test('transition editor starts and stops one isolated audio preview', async () => {
  const originals = {
    Audio: globalThis.Audio,
    document: globalThis.document,
    window: globalThis.window,
    requestAnimationFrame: globalThis.requestAnimationFrame,
    cancelAnimationFrame: globalThis.cancelAnimationFrame,
  };
  const audio = [];
  class FakeAudio {
    constructor(src) {
      this.src = src;
      this.readyState = 1;
      this.duration = 240;
      this.currentTime = 0;
      this.volume = 1;
      this.playbackRate = 1;
      this.playCount = 0;
      this.pauseCount = 0;
      audio.push(this);
    }
    async play() {
      this.playCount += 1;
    }
    pause() {
      this.pauseCount += 1;
    }
    removeAttribute(name) {
      if (name === 'src') this.src = '';
    }
  }
  globalThis.Audio = FakeAudio;
  globalThis.document = { querySelectorAll: () => [] };
  globalThis.window = {};
  globalThis.requestAnimationFrame = () => 1;
  globalThis.cancelAnimationFrame = () => {};
  const classes = new Set();
  const button = {
    disabled: false,
    textContent: 'Mix transition',
    closest: () => null,
    classList: {
      add: (...names) => names.forEach((name) => classes.add(name)),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      contains: (name) => classes.has(name),
    },
    style: { setProperty() {}, removeProperty() {} },
  };
  const state = {
    plan: [
      { id: 'a', _job: { id: 11 }, duration_seconds: 220, bpm: 120 },
      { id: 'b', _job: { id: 12 }, duration_seconds: 210, bpm: 124 },
    ],
    lockedIds: new Set(),
    transitionSettings: {},
  };
  try {
    const editor = transitionEditorFor(state);
    await editor.auditionTransition(1, button);

    assert.deepEqual(
      audio.map((item) => item.src),
      ['/api/jobs/11/audio/wav', '/api/jobs/12/audio/wav'],
    );
    assert.equal(audio[0].playCount, 1);
    assert.equal(classes.has('playing'), true);

    editor.stopTransitionPreview();
    assert.equal(
      audio.every((item) => item.pauseCount === 1 && item.src === ''),
      true,
    );
  } finally {
    Object.assign(globalThis, originals);
  }
});

test('planning session builds and receipts an accepted deterministic proposal', async () => {
  const state = {
    library: [
      { id: 'a', catalogId: 1, duration_seconds: 180 },
      { id: 'b', catalogId: 2, duration_seconds: 180 },
      { id: 'c', catalogId: 3, duration_seconds: 180 },
    ],
    plan: [],
    requiredIds: new Set(),
    excludedIds: new Set(),
    lockedIds: new Set(),
    transitionSettings: {},
    proposals: [],
    activeProposal: '',
    genreSelectionOrder: [],
    generationNonce: 0,
  };
  const elements = new Map([
    ['#set-builder-message', { textContent: '' }],
    ['#set-planning-mode', { value: 'classic' }],
  ]);
  const classicPlanner = {
    async generate(options) {
      const plan = options.buildVariation('balanced', new Set());
      const proposal = {
        id: 'balanced',
        label: 'Balanced',
        accepted: true,
        snapshot: options.snapshot(plan),
        health: options.evaluate(plan),
      };
      return { accepted: [proposal], proposals: [proposal], preferred: proposal, best: proposal };
    },
  };
  const { session } = planningSessionFor({
    state,
    elements,
    planningClient: {},
    classicPlanner,
    overrides: {
      lifecycle: {
        advancePlanRevision() {
          state.planRevision = { id: 'revision-1', number: 1 };
          return state.planRevision;
        },
      },
    },
  });

  await session.generateDeterministicSetPlan();

  assert.equal(state.plan.length, 3);
  assert.equal(state.activeProposal, 'balanced');
  assert.equal(session.receipt().mode, 'classic');
  assert.deepEqual(session.receipt().planRevision, { id: 'revision-1', number: 1 });
  assert.match(elements.get('#set-builder-message').textContent, /Balanced applied at 82\/100/);
  assert.equal(Object.isFrozen(session), true);
});

test('deterministic planning fills tracks from each confirmed journey section', async () => {
  const state = {
    library: [
      { id: 'house-1', catalogId: 1, duration_seconds: 180, genres: ['house'] },
      { id: 'house-2', catalogId: 2, duration_seconds: 180, genres: ['house'] },
      { id: 'house-3', catalogId: 3, duration_seconds: 180, genres: ['house'] },
      { id: 'house-4', catalogId: 4, duration_seconds: 180, genres: ['house'] },
      { id: 'techno-1', catalogId: 5, duration_seconds: 180, genres: ['latin techno', 'techno'] },
      { id: 'techno-2', catalogId: 6, duration_seconds: 180, genres: ['latin techno', 'techno'] },
    ],
    plan: [],
    requiredIds: new Set(),
    excludedIds: new Set(),
    lockedIds: new Set(),
    transitionSettings: {},
    proposals: [],
    activeProposal: '',
    genreSelectionOrder: [],
    generationNonce: 0,
  };
  const elements = new Map([
    ['#set-builder-message', { textContent: '' }],
    ['#set-planning-mode', { value: 'classic' }],
  ]);
  const classicPlanner = {
    async generate(options) {
      const plan = options.buildVariation('balanced', new Set());
      const proposal = {
        id: 'balanced',
        label: 'Balanced',
        accepted: true,
        snapshot: options.snapshot(plan),
        health: options.evaluate(plan),
      };
      return { accepted: [proposal], proposals: [proposal], preferred: proposal, best: proposal };
    },
  };
  const journey = {
    genrePolicy: { mode: 'strict' },
    sections: [
      { id: 'warm-up', name: 'Warm-up', durationPercent: 33, genres: ['house'] },
      { id: 'opening', name: 'Opening', durationPercent: 34, genres: ['house', 'latin techno'] },
      { id: 'closing', name: 'Closing', durationPercent: 33, genres: ['techno'] },
    ],
  };
  const { session } = planningSessionFor({
    state,
    elements,
    classicPlanner,
    planningClient: {},
    overrides: {
      policy: {
        trackMatchesIntendedGenre: (track, genre) => track.genres.includes(genre),
        trackMatchesSetGenre: (track, genre) => track.genres.includes(genre),
      },
      lifecycle: {
        setBrief: () => ({
          length: 15,
          genres: ['house', 'techno'],
          detailedGenres: [],
          genreWeights: { house: 50, techno: 50 },
          genreFlow: 'chapters',
          minimumHealth: 65,
          curve: 'rise',
          identity: { journey },
        }),
        restoreSetSnapshot(snapshot) {
          const byId = new Map(state.library.map((track) => [track.id, track]));
          state.plan = snapshot.tracks.map((id) => byId.get(id));
        },
      },
    },
  });

  await session.generateDeterministicSetPlan();

  assert.deepEqual(
    state.plan.slice(0, 2).map((track) => track.genres[0]),
    ['house', 'house'],
  );
  assert.deepEqual(
    state.plan.slice(2, 4).map((track) => track.genres[0]),
    ['house', 'house'],
  );
  assert.deepEqual(
    state.plan.slice(4).map((track) => track.genres.at(-1)),
    ['techno', 'techno'],
  );
  assert.deepEqual(
    state.plan.map((track) => track._planSectionId),
    ['warm-up', 'warm-up', 'opening', 'opening', 'closing', 'closing'],
  );
});

test('strict deterministic planning reports section scarcity instead of drifting genres', async () => {
  const state = {
    library: [
      { id: 'house-1', catalogId: 1, duration_seconds: 180, genres: ['house'] },
      { id: 'house-2', catalogId: 2, duration_seconds: 180, genres: ['house'] },
      { id: 'house-3', catalogId: 3, duration_seconds: 180, genres: ['house'] },
      { id: 'techno-1', catalogId: 4, duration_seconds: 180, genres: ['techno'] },
    ],
    plan: [],
    requiredIds: new Set(),
    excludedIds: new Set(),
    lockedIds: new Set(),
    transitionSettings: {},
    proposals: [],
    activeProposal: '',
    genreSelectionOrder: [],
    generationNonce: 0,
  };
  const elements = new Map([
    ['#set-builder-message', { textContent: '' }],
    ['#set-planning-mode', { value: 'classic' }],
  ]);
  let plannerCalled = false;
  const journey = {
    genrePolicy: { mode: 'strict' },
    sections: [
      { id: 'opening', name: 'Opening', durationPercent: 50, genres: ['house'] },
      { id: 'closing', name: 'Closing', durationPercent: 50, genres: ['techno'] },
    ],
  };
  const { session } = planningSessionFor({
    state,
    elements,
    classicPlanner: {
      async generate() {
        plannerCalled = true;
        throw new Error('planner should not run');
      },
    },
    planningClient: {},
    overrides: {
      policy: {
        trackMatchesIntendedGenre: (track, genre) => track.genres.includes(genre),
      },
      lifecycle: {
        setBrief: () => ({
          length: 10,
          genres: ['house', 'techno'],
          detailedGenres: [],
          genreWeights: { house: 50, techno: 50 },
          genreFlow: 'chapters',
          minimumHealth: 65,
          curve: 'rise',
          identity: { journey },
        }),
      },
    },
  });

  await session.generateDeterministicSetPlan();

  assert.equal(plannerCalled, false);
  assert.equal(state.plan.length, 0);
  assert.match(elements.get('#set-builder-message').textContent, /Closing needs 2 unique tracks matching techno/);
  assert.match(elements.get('#set-builder-message').textContent, /only 1 analyzed track is available/);
});

test('planning session cancels the active AI job and aborts its pending result', async () => {
  const state = {
    library: [
      { id: 'a', catalogId: 1, duration_seconds: 180 },
      { id: 'b', catalogId: 2, duration_seconds: 180 },
    ],
    plan: [],
    requiredIds: new Set(),
    excludedIds: new Set(),
    lockedIds: new Set(),
    transitionSettings: {},
    proposals: [],
    activeProposal: '',
  };
  const elements = new Map([
    ['#set-builder-message', { textContent: '' }],
    ['#set-cancel-planning', { hidden: true }],
  ]);
  const canceled = [];
  let waitSignal;
  const planningClient = {
    start: async () => ({ jobId: 'job-7' }),
    wait: (_jobId, options) => {
      waitSignal = options.signal;
      return new Promise((resolve, reject) => {
        options.signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
      });
    },
    cancel: async (jobId) => canceled.push(jobId),
  };
  const { session } = planningSessionFor({ state, elements, planningClient, classicPlanner: {} });
  const generation = session.generateAITrackPlan().catch((error) => error);
  await new Promise((resolve) => setTimeout(resolve, 0));

  await session.cancelAITrackPlan();
  const error = await generation;

  assert.equal(waitSignal.aborted, true);
  assert.deepEqual(canceled, ['job-7']);
  assert.equal(error.message, 'aborted');
  assert.equal(state.plan.length, 0);
  assert.equal(elements.get('#set-cancel-planning').hidden, true);
});

test('planning session releases its cancel surface after a failed AI wait', async () => {
  const state = {
    library: [
      { id: 'a', catalogId: 1, duration_seconds: 180 },
      { id: 'b', catalogId: 2, duration_seconds: 180 },
    ],
    plan: [],
    requiredIds: new Set(),
    excludedIds: new Set(),
    lockedIds: new Set(),
    transitionSettings: {},
    proposals: [],
    activeProposal: '',
  };
  const elements = new Map([
    ['#set-builder-message', { textContent: '' }],
    ['#set-cancel-planning', { hidden: true }],
  ]);
  const planningClient = {
    start: async () => ({ jobId: 'job-failed' }),
    wait: async () => {
      throw new Error('planning failed');
    },
    cancel: async () => {},
  };
  const { session } = planningSessionFor({ state, elements, planningClient, classicPlanner: {} });

  await assert.rejects(session.generateAITrackPlan(), /planning failed/);

  assert.equal(elements.get('#set-cancel-planning').hidden, true);
  await session.cancelAITrackPlan();
  assert.equal(state.plan.length, 0);
});

test('planning session retains a validated deterministic safety fallback from the AI lifecycle', async () => {
  const state = {
    library: [
      { id: 'a', catalogId: 1, duration_seconds: 180 },
      { id: 'b', catalogId: 2, duration_seconds: 180 },
    ],
    plan: [],
    requiredIds: new Set(),
    excludedIds: new Set(),
    lockedIds: new Set(),
    transitionSettings: {},
    proposals: [],
    activeProposal: '',
  };
  const elements = new Map([
    ['#set-builder-message', { textContent: '' }],
    ['#set-cancel-planning', { hidden: true }],
  ]);
  const planningClient = {
    start: async () => ({ jobId: 'job-8' }),
    wait: async () => ({
      mode: 'deterministic-fallback',
      provider: 'ollama',
      model: 'qwen3.5:4b',
      summary: 'Safety fallback retained.',
      warnings: ['AI plan rejected'],
      fallbackReason: 'quality threshold',
      plan: [
        {
          id: 1,
          technicalScore: 81,
          reasons: [
            {
              evidence: 'estimated',
              text: 'Playlist/crate identity matches: latin techno from LATIN_bounce_TECHNO_Rave_Edition.',
            },
          ],
        },
        { id: 2, technicalScore: 79 },
      ],
    }),
    cancel: async () => {},
    observability: async () => ({ completedCount: 1, failedCount: 0, canceledCount: 0 }),
  };
  const { session } = planningSessionFor({ state, elements, planningClient, classicPlanner: {} });

  await session.generateAITrackPlan();

  assert.deepEqual(state.plan.map(trackId), ['a', 'b']);
  assert.equal(session.receipt().mode, 'deterministic-fallback');
  assert.equal(session.receipt().fallbackReason, 'quality threshold');
  assert.match(state.plan[0]._candidateReasons[0].text, /LATIN_bounce_TECHNO_Rave_Edition/);
  assert.match(elements.get('#set-builder-message').textContent, /deterministic safety fallback/);
});

test('planning session refuses a supposedly validated plan containing two versions of one song', async () => {
  const stable = { id: 'stable', catalogId: 3, recordingKey: 'recording:stable' };
  const state = {
    library: [
      { id: 'original', catalogId: 1, recordingKey: 'recording:duplicate' },
      { id: 'remix', catalogId: 2, recordingKey: 'recording:duplicate' },
      stable,
    ],
    plan: [stable],
    requiredIds: new Set(),
    excludedIds: new Set(),
    lockedIds: new Set(),
    transitionSettings: {},
    proposals: [],
    activeProposal: '',
  };
  const elements = new Map([
    ['#set-builder-message', { textContent: '' }],
    ['#set-cancel-planning', { hidden: true }],
  ]);
  const planningClient = {
    start: async () => ({ jobId: 'job-duplicate' }),
    wait: async () => ({
      mode: 'ai-planned',
      provider: 'ollama',
      model: 'qwen3.5:4b',
      summary: 'Invalid duplicate family.',
      plan: [{ id: 1 }, { id: 2 }],
    }),
    cancel: async () => {},
  };
  const { session } = planningSessionFor({ state, elements, planningClient, classicPlanner: {} });

  await assert.rejects(session.generateAITrackPlan(), /duplicate song version/);

  assert.deepEqual(state.plan, [stable]);
  assert.equal(elements.get('#set-cancel-planning').hidden, true);
});

test('AI regeneration request carries its base revision and section-aware locked-track contract', async () => {
  const state = {
    library: [
      { id: 'a', catalogId: 'downloaded:1', duration_seconds: 180, _planSectionId: 'opening' },
      { id: 'b', catalogId: 'downloaded:2', duration_seconds: 180, _planSectionId: 'peak' },
    ],
    plan: [],
    requiredIds: new Set(),
    excludedIds: new Set(),
    lockedIds: new Set(['a']),
    transitionSettings: {},
    proposals: [],
    activeProposal: '',
    planRevision: { id: 'revision-4', number: 4 },
  };
  state.plan = [...state.library];
  const elements = new Map([
    ['#set-builder-message', { textContent: '' }],
    ['#set-cancel-planning', { hidden: true }],
  ]);
  let request;
  const planningClient = {
    start: async (value) => {
      request = value;
      return { jobId: 'job-regenerate' };
    },
    wait: async () => ({
      mode: 'ai-planned',
      provider: 'ollama',
      model: 'qwen3.5:4b',
      summary: 'Regenerated safely.',
      warnings: [],
      plan: [
        { id: 'downloaded:1', sectionId: 'opening' },
        { id: 'downloaded:2', sectionId: 'peak' },
      ],
      basePlanRevision: { id: 'revision-4', number: 4 },
    }),
    cancel: async () => {},
    observability: async () => ({ completedCount: 1, failedCount: 0, canceledCount: 0 }),
  };
  const { session } = planningSessionFor({
    state,
    elements,
    planningClient,
    classicPlanner: {},
    overrides: {
      lifecycle: {
        setBrief: () => ({
          length: 10,
          genres: [],
          detailedGenres: [],
          minimumHealth: 65,
          identity: {
            journey: {
              sections: [
                { id: 'opening', durationPercent: 50 },
                { id: 'peak', durationPercent: 50 },
              ],
            },
          },
        }),
      },
    },
  });

  await session.generateAITrackPlan();

  assert.deepEqual(request.base_plan_revision, { id: 'revision-4', number: 4 });
  assert.deepEqual(request.locked_track_ids, ['downloaded:1']);
  assert.deepEqual(request.locked_track_sections, { 'downloaded:1': 'opening' });
  assert.deepEqual(session.receipt().basePlanRevision, { id: 'revision-4', number: 4 });
});

test('planning session switches proposals while preserving edits made to the prior direction', async () => {
  const state = {
    library: [
      { id: 'a', catalogId: 1 },
      { id: 'b', catalogId: 2 },
    ],
    plan: [{ id: 'a', catalogId: 1 }],
    requiredIds: new Set(),
    excludedIds: new Set(),
    lockedIds: new Set(),
    transitionSettings: { 'a→b': { bars: 16 } },
    proposals: [
      { id: 'first', label: 'First', accepted: true, snapshot: { tracks: ['a'] } },
      { id: 'second', label: 'Second', accepted: true, snapshot: { tracks: ['b'] } },
    ],
    activeProposal: 'first',
  };
  const elements = new Map([['#set-builder-message', { textContent: '' }]]);
  const { session } = planningSessionFor({ state, elements, planningClient: {}, classicPlanner: {} });

  await session.selectSetProposal('second');

  assert.equal(state.activeProposal, 'second');
  assert.deepEqual(state.plan.map(trackId), ['b']);
  assert.deepEqual(state.proposals[0].snapshot.tracks, ['a']);
  assert.match(elements.get('#set-builder-message').textContent, /edits to the other directions are saved/);
});

test('feedback controller loads ranking signals and submits review evidence with the planning receipt', async () => {
  const status = { textContent: '' };
  const summary = { innerHTML: '', querySelectorAll: () => [] };
  const toggle = { checked: false };
  const calibration = { innerHTML: '' };
  const reviewStatus = { textContent: '' };
  const elements = new Map([
    ['#set-vibe', { value: 'dance-party' }],
    ['#set-preference-status', status],
    ['#set-preference-summary', summary],
    ['#set-personalization-enabled', toggle],
    ['#set-calibration-summary', calibration],
    ['#submit-set-review', { disabled: false, textContent: 'Save review' }],
    ['#saved-set-select', { value: 'set-1' }],
    ['#set-review-notes', { value: 'Great flow' }],
    ['#set-review-status', reviewStatus],
  ]);
  const plan = [
    { id: 'a', catalogId: 1, source_name: 'Intro.wav', bpm: 120, _genre: 'House', energy: 0.5 },
    { id: 'b', catalogId: 2, source_name: 'Peak.wav', bpm: 124, _genre: 'House', energy: 0.8 },
  ];
  let submitted;
  const profile = {
    enabled: true,
    eventCount: 8,
    activeSignals: [{ dimension: 'genre', value: 'House', adjustment: 6, evidenceCount: 4 }],
    pendingSignals: [],
  };
  const report = { tracks: { reviewed: 2, accepted: 2 }, transitionProfile: { activeSignals: [] } };
  const feedback = createSetBuilderFeedback({
    state: { plan, draftId: 'draft-stable', activeSavedSetId: '' },
    dom: { $: (selector) => elements.get(selector), $$: () => [], escapeHtml },
    api: {
      preferenceProfile: async () => profile,
      submitReview: async (payload) => {
        submitted = payload;
        return { preferenceProfile: profile, report };
      },
    },
    music: {
      compatibility: () => ({ components: { key: 31 } }),
      setTrackDetailedGenres: () => [],
      setTrackId: trackId,
      setCatalogTrackId: (track) => track.catalogId,
      setVocalProfile: () => 'instrumental',
      songEnergy: (track) => track.energy,
    },
    planning: {
      setBrief: () => ({ name: 'Night Set' }),
      getPlanningReceipt: () => ({ evaluation: { score: 82 }, comparison: { winner: 'deterministic' } }),
      transitionSettings: () => ({ bars: 16, technique: 'crossfade' }),
    },
    review: { trackReviewDraft: new Map(), transitionReviewDraft: new Map() },
  });

  await feedback.loadPreferenceProfile();
  feedback.setOverallDecision('accept');
  await feedback.submitSetReview();

  assert.equal(toggle.checked, true);
  assert.equal(feedback.preferenceAdjustment(plan[0]), 3);
  assert.equal(submitted.overallDecision, 'accept');
  assert.equal(submitted.setId, 'draft-stable');
  assert.deepEqual(submitted.evaluation, { score: 82 });
  assert.equal(submitted.transitions[0].features.technique, 'crossfade');
  assert.match(reviewStatus.textContent, /Review saved locally/);
});

test('plan view renders required and excluded rules through its focused boundary', () => {
  const ruleCount = { textContent: '' };
  const ruleChips = { innerHTML: '', querySelectorAll: () => [] };
  const elements = new Map([
    ['#set-rule-count', ruleCount],
    ['#set-rule-chips', ruleChips],
  ]);
  const state = {
    library: [
      { id: 'required', source_name: 'Required Track' },
      { id: 'excluded', source_name: 'Excluded Track' },
    ],
    requiredIds: new Set(['required']),
    excludedIds: new Set(['excluded']),
  };
  const planView = createSetPlanView({
    state,
    dom: { $: (selector) => elements.get(selector), $$: () => [], escapeHtml },
    ui: {
      notify() {},
      descriptorEditorMarkup() {},
      saveDescriptorEditor() {},
      inferDescriptorEditor() {},
      bindCompactAudio() {},
      compactAudioMarkup() {},
      stopCompactAudio() {},
    },
    music: {
      compatibility() {},
      energyBand() {},
      formatLibraryKey() {},
      LIBRARY_ROLE_INFO: {},
      libraryRoles() {},
      songEnergy() {},
      timingProfile() {},
    },
    policy: {
      SET_IDENTITY_STORAGE_KEY: 'identity',
      eligibleSetTracks() {},
      genreAllocationTargets() {},
      identityStore() {},
      intentionEvaluation() {},
      preferenceAdjustment() {},
      parseIdentityTerms() {},
      saveManualTrackIdentity() {},
      setCatalogTrackId: trackId,
      setCandidateScore() {},
      setTrackId: trackId,
      setVocalProfile() {},
      targetSetEnergy() {},
      trackIdentity() {},
      trackMatchesSetDetailedGenre() {},
      trackMatchesSetGenre() {},
    },
    transitions: {
      auditionTransition() {},
      closeTransitionEditors() {},
      openTransitionEditor() {},
      setHealth() {},
      setRuntime() {},
      setSvgCurve() {},
      transitionSettings() {},
    },
    lifecycle: {
      editCommands: {},
      getPlanningReceipt() {},
      pushSetHistory() {},
      recordPreference() {},
      renderSetProposals() {},
      setBrief() {},
      setPlanSnapshot() {},
      updateSetHistoryButtons() {},
    },
    review: { trackReviewDraft: new Map(), transitionReviewDraft: new Map() },
  });

  planView.renderSetRules();

  assert.equal(ruleCount.textContent, '2 rules');
  assert.match(ruleChips.innerHTML, /Required · Required Track/);
  assert.match(ruleChips.innerHTML, /Excluded · Excluded Track/);
  assert.equal(Object.isFrozen(planView), true);
});

test('saved-set export serializers preserve transition and playlist details', () => {
  const tracks = [
    { id: 'a', source_name: 'Intro "Edit".wav', artist: 'DJ One', bpm: 120, key: 'Am', _genre: 'House' },
    { id: 'b', source_name: 'Peak.wav', artist: '', bpm: 124, key: 'Cm', _genre: 'Techno' },
  ];
  const csv = buildSetCsv({
    plan: tracks,
    compatibility: () => ({ score: 84 }),
    transitionSettings: () => ({
      mixIn: 8,
      mixOut: 180,
      bars: 16,
      curve: 'smooth',
      technique: 'crossfade',
      tempoSync: true,
      notes: 'Blend, then lift',
    }),
    camelotKey: () => '8A',
    energyBand: () => 'high',
    songEnergy: () => 0.8,
    libraryRoles: () => ['peak-time'],
  });
  assert.match(csv, /"Intro ""Edit""\.wav"/);
  assert.match(csv, /"84","8","180","16","smooth","crossfade","yes","Blend, then lift"/);

  const m3u = buildSetM3u([
    { track: { source_name: 'Intro.wav', artist: 'DJ One', duration_seconds: 121.6 }, path: '/music/Intro.wav' },
  ]);
  assert.equal(m3u, '#EXTM3U\r\n#EXTINF:122,DJ One - Intro\r\n/music/Intro.wav');
});

test('saved-set export serializers never emit two versions of one recording family', () => {
  const original = {
    source_name: 'Funkytown.wav',
    artist: 'Lipps Inc',
    _recordingCode: 'DSC-1',
    _genre: 'Disco',
  };
  const remix = {
    source_name: 'Funkytown Remix.wav',
    artist: 'Lipps Inc',
    _recordingCode: 'DSC-1',
    _genre: 'Disco',
  };
  const csv = buildSetCsv({
    plan: [original, remix],
    compatibility: () => ({ score: 80 }),
    transitionSettings: () => ({}),
    camelotKey: () => '',
    energyBand: () => '',
    songEnergy: () => 0.5,
    libraryRoles: () => [],
  });
  const m3u = buildSetM3u([
    { track: original, path: '/music/Funkytown.wav' },
    { track: remix, path: '/music/Funkytown Remix.wav' },
  ]);

  assert.equal(csv.match(/Funkytown/g)?.length, 1);
  assert.equal(m3u.match(/Funkytown/g)?.length, 2);
  assert.doesNotMatch(m3u, /Remix/);
});

test('legacy saved-set reconciliation drops duplicate versions and retains the locked version', () => {
  const original = { id: 'original', family: 'recording:DSC-1' };
  const bridge = { id: 'bridge', family: 'recording:DSC-2' };
  const remix = { id: 'remix', family: 'recording:DSC-1' };

  const result = recoverSavedSetPlan({
    record: { tracks: ['original', 'bridge', 'missing', 'remix'], locked: ['remix'], trackDetails: [] },
    library: [original, bridge, remix],
    trackId,
    recordingKey: (track) => track.family,
    recoveryScore: () => 0,
  });

  assert.deepEqual(result.plan, [bridge, remix]);
  assert.equal(result.duplicatesRemoved, 1);
});

test('saved-set controller loads durable records and falls back to the browser recovery cache', async () => {
  const storage = new Map([['sets', JSON.stringify([{ id: 'legacy', name: 'Legacy', tracks: [] }])]]);
  const originalStorage = globalThis.localStorage;
  globalThis.localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
  };
  try {
    const elements = new Map();
    const durable = savedSetControllerFor({
      state: { plan: [], library: [] },
      elements,
      api: {
        savedSets: async () => ({ sets: [{ id: 'durable', name: 'Durable', tracks: [] }] }),
        migrateSavedSets: async () => ({ document: { sets: [{ id: 'migrated', name: 'Migrated', tracks: [] }] } }),
      },
    });
    await durable.loadSavedSets();
    assert.deepEqual(
      durable.savedSets().map((set) => set.id),
      ['migrated'],
    );
    assert.equal(storage.get('sets-migrated'), 'true');

    storage.delete('sets-migrated');
    const fallback = savedSetControllerFor({
      state: { plan: [], library: [] },
      elements,
      api: { savedSets: async () => Promise.reject(new Error('offline')) },
    });
    await fallback.loadSavedSets();
    assert.deepEqual(
      fallback.savedSets().map((set) => set.id),
      ['migrated'],
    );
  } finally {
    globalThis.localStorage = originalStorage;
  }
});

test('saved-set deletion reports whether the deleted record owns the active workspace', async () => {
  const storage = new Map();
  const originalStorage = globalThis.localStorage;
  globalThis.localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
  };
  const selected = { value: 'set-1', replaceChildren() {} };
  const elements = new Map([['#saved-set-select', selected]]);
  const state = { plan: [], library: [], activeSavedSetId: 'set-1' };
  const deleted = [];
  const controller = savedSetControllerFor({
    state,
    elements,
    api: {
      savedSets: async () => ({ sets: [{ id: 'set-1', name: 'Current', tracks: [] }] }),
      deleteSet: async (id) => {
        deleted.push(id);
        return { deleted: true, id };
      },
    },
  });

  try {
    await controller.loadSavedSets();
    const result = await controller.deleteSavedSet('set-1');

    assert.deepEqual(deleted, ['set-1']);
    assert.equal(result.wasActive, true);
    assert.equal(controller.savedSets().length, 0);
    assert.equal(JSON.parse(storage.get('sets')).length, 0);
  } finally {
    globalThis.localStorage = originalStorage;
  }
});

test('saved-set duplication creates an independent draft and revision lineage', async () => {
  const storage = new Map();
  const originalStorage = globalThis.localStorage;
  globalThis.localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
  };
  const original = {
    id: 'set-1',
    name: 'Current',
    brief: { name: 'Current' },
    tracks: [],
    planRevision: { id: 'revision-set-1', number: 4, parentId: 'revision-set-0' },
  };
  const saved = [];
  const controller = savedSetControllerFor({
    state: { plan: [], library: [], activeSavedSetId: 'set-1' },
    elements: new Map([['#saved-set-select', { value: 'set-1', replaceChildren() {} }]]),
    api: {
      savedSets: async () => ({ sets: [original] }),
      saveSet: async (record) => saved.push(record),
    },
  });

  try {
    await controller.loadSavedSets();
    const copy = await controller.duplicateSavedSet(original);

    assert.equal(saved.length, 1);
    assert.equal(copy.name, 'Current Copy');
    assert.equal(copy.brief.name, 'Current Copy');
    assert.notEqual(copy.id, original.id);
    assert.match(copy.draftId, /^draft-/);
    assert.equal(copy.planRevision.number, 1);
    assert.equal(copy.planRevision.parentId, 'revision-set-1');
    assert.deepEqual(
      controller.savedSets().map((record) => record.id),
      [copy.id, original.id],
    );
  } finally {
    globalThis.localStorage = originalStorage;
  }
});

test('saved-set controller persists the plan, recovery cache, and playlist path', async () => {
  const storage = new Map();
  const originalStorage = globalThis.localStorage;
  globalThis.localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
  };
  const selected = { value: '', replaceChildren() {} };
  const message = { textContent: '' };
  const elements = new Map([
    ['#save-set', { disabled: false, textContent: 'Save set' }],
    ['#saved-set-select', selected],
    ['#set-planning-mode', { value: 'classic' }],
    ['#set-builder-message', message],
  ]);
  const calls = [];
  let failPlaylist = false;
  let failSave = false;
  const state = {
    draftId: 'draft-1',
    activeSavedSetId: '',
    planRevision: { id: 'revision-1', number: 1, parentId: null },
    plan: [
      {
        id: 'track-1',
        source_name: 'Opening.wav',
        artist: 'DJ One',
        bpm: 120,
        key: 'Am',
        _genre: 'House',
        _libraryPath: '/music/Opening.wav',
        duration_seconds: 180,
      },
    ],
    transitionSettings: {},
    lockedIds: new Set(['track-1']),
    requiredIds: new Set(),
    excludedIds: new Set(),
    trackReviews: new Map([
      ['track-1', { decision: 'accept', saved: true, eventId: 'decision-1' }],
    ]),
  };
  const controller = savedSetControllerFor({
    state,
    elements,
    api: {
      saveSet: async (record) => {
        if (failSave) throw new Error('database unavailable');
        calls.push(['set', record]);
      },
      savePlaylist: async (payload) => {
        if (failPlaylist) throw new Error('playlist folder unavailable');
        calls.push(['playlist', payload]);
        return { path: '/playlists/Night Set.m3u8' };
      },
    },
  });

  try {
    await controller.saveCurrentSet();

    assert.equal(controller.savedSets().length, 1);
    assert.deepEqual(controller.savedSets()[0].tracks, ['track-1']);
    assert.equal(controller.savedSets()[0].draftId, 'draft-1');
    assert.deepEqual(controller.savedSets()[0].planRevision, state.planRevision);
    assert.equal(controller.savedSets()[0].trackReviews['track-1'].eventId, 'decision-1');
    assert.equal(state.activeSavedSetId, 'draft-1');
    assert.equal(JSON.parse(storage.get('sets')).length, 1);
    assert.equal(calls[1][1].tracks[0].path, '/music/Opening.wav');
    assert.match(message.textContent, /playlist written to \/playlists\/Night Set\.m3u8/);
    assert.equal(selected.value, controller.savedSets()[0].id);

    failPlaylist = true;
    await controller.saveCurrentSet();
    assert.match(message.textContent, /Set saved durably and will survive restart/);
    assert.match(message.textContent, /playlist folder unavailable/);

    failSave = true;
    await controller.saveCurrentSet();
    assert.match(message.textContent, /Set was not saved: database unavailable/);
    assert.equal(elements.get('#save-set').disabled, false);
    assert.equal(elements.get('#save-set').textContent, 'Save set');
    assert.equal(elements.get('#save-set')['aria-busy'], undefined);
    assert.equal(controller.savedSets().length, 1);
  } finally {
    globalThis.localStorage = originalStorage;
  }
});

test('Set Builder API owns route serialization and exposes planning lifecycle', async () => {
  const calls = [];
  const api = createApiClient({
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return response({ provider: 'offline', tracks: [] });
    },
  });
  const planning = { start: () => 'started' };
  const client = createSetBuilderApi({ api, planningClient: planning });

  await client.prepareBrief({
    brief: 'Latin warm-up',
    catalogVocabulary: ['latin house'],
    durationMinutes: 60,
  });
  await client.interpretIntention('Latin warm-up', ['latin house']);
  await client.planJourney({
    brief: 'Latin warm-up',
    interpretedIntention: { opening: 'melodic' },
    catalogVocabulary: ['latin house'],
    durationMinutes: 60,
  });
  await client.exportPreflight(['/music/a.wav']);
  await client.savedSets();
  await client.saveSet({ id: 'set/one', name: 'Set One', tracks: ['track-1'] });
  await client.deleteSet('set/one');
  await client.migrateSavedSets([{ id: 'legacy', name: 'Legacy', tracks: [] }]);

  assert.equal(client.planning, planning);
  assert.deepEqual(
    calls.map((call) => call.url),
    [
      '/api/set-builder/prepare-brief',
      '/api/set-builder/interpret-intention',
      '/api/set-builder/plan-journey',
      '/api/set-builder/export-preflight',
      '/api/set-builder/sets',
      '/api/set-builder/sets/set%2Fone',
      '/api/set-builder/sets/set%2Fone',
      '/api/set-builder/sets/migrate-v1',
    ],
  );
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    brief: 'Latin warm-up',
    catalog_vocabulary: ['latin house'],
    duration_minutes: 60,
  });
  assert.deepEqual(JSON.parse(calls[2].options.body), {
    brief: 'Latin warm-up',
    interpreted_intention: { opening: 'melodic' },
    catalog_vocabulary: ['latin house'],
    duration_minutes: 60,
  });
});

test('classic planner produces deterministic directions and prefers accepted safe flow', async () => {
  const scheduled = [];
  const strategies = [
    { id: 'safe', label: 'Safe' },
    { id: 'adventurous', label: 'Adventure' },
  ];
  const planner = createClassicSetPlanner({ strategies, schedule: async () => scheduled.push('tick') });
  const result = await planner.generate({
    count: 2,
    minimumHealth: 70,
    buildVariation: (strategy) => [{ id: `${strategy}-1` }, { id: `${strategy}-2` }],
    improveOrder: (plan) => plan,
    evaluate: (plan) => ({ score: plan[0].id.startsWith('safe') ? 82 : 76, transitions: [], vocalClashes: 0 }),
    trackId,
    snapshot: (plan) => ({ tracks: plan.map(trackId), locked: [], transitions: {} }),
  });

  assert.equal(result.accepted.length, 2);
  assert.equal(result.preferred.id, 'safe');
  assert.deepEqual(scheduled, ['tick', 'tick']);
  assert.ok(result.proposals.every((proposal) => proposal.attempts >= 4));
});

test('classic planner reports the strongest rejected fallback without selecting it', async () => {
  const planner = createClassicSetPlanner({
    strategies: [{ id: 'safe' }, { id: 'balanced' }],
    schedule: async () => {},
  });
  const result = await planner.generate({
    count: 1,
    minimumHealth: 90,
    buildVariation: (strategy) => [{ id: strategy }],
    improveOrder: (plan) => plan,
    evaluate: (plan) => ({ score: plan[0].id === 'balanced' ? 82 : 75 }),
    trackId,
    snapshot: (plan) => ({ tracks: plan.map(trackId) }),
  });

  assert.deepEqual(result.accepted, []);
  assert.equal(result.preferred, null);
  assert.equal(result.best.id, 'balanced');
  assert.equal(result.best.attempts, 10);
});

test('final mix optimization improves returned order without moving locked tracks', () => {
  const plan = [
    { id: 'locked', value: 0 },
    { id: 'high', value: 9 },
    { id: 'middle', value: 5 },
  ];
  const optimized = optimizePlanOrder(plan, {
    fitness: (candidate) => -Math.abs(candidate[1].value - 5) - Math.abs(candidate[2].value - 9),
    isFixed: (track) => track.id === 'locked',
  });

  assert.equal(optimized[0].id, 'locked');
  assert.deepEqual(
    optimized.slice(1).map((track) => track.id),
    ['middle', 'high'],
  );
  assert.deepEqual(
    plan.map((track) => track.id),
    ['locked', 'high', 'middle'],
  );
});

test('final mix optimization never moves tracks across confirmed journey sections', () => {
  const plan = [
    { id: 'opening-high', energy: 0.9, _planSectionId: 'opening' },
    { id: 'opening-low', energy: 0.1, _planSectionId: 'opening' },
    { id: 'closing-low', energy: 0.1, _planSectionId: 'closing' },
    { id: 'closing-high', energy: 0.9, _planSectionId: 'closing' },
  ];
  const editor = transitionEditorFor(
    { plan, lockedIds: new Set(), transitionSettings: {} },
    {
      optimizePlanOrder,
      songEnergy: (track) => track.energy,
      targetSetEnergy: (index) => (index < 2 ? 0.1 : 0.9),
    },
  );

  const optimized = editor.improveSetOrder(plan, { identity: {} });

  assert.deepEqual(
    optimized.map((track) => track._planSectionId),
    ['opening', 'opening', 'closing', 'closing'],
  );
});

test('Set Builder view helpers escape content and expose planning evidence', () => {
  assert.equal(journeyEvidenceLabel({ evidence: 'ai-interpreted', model: 'qwen' }), 'AI interpreted · qwen');
  assert.equal(journeyEvidenceLabel({ evidence: 'ai-planned', model: 'qwen' }), 'AI planned · qwen');
  assert.equal(journeyEvidenceLabel({ evidence: 'deterministic-fallback' }), 'Offline plan');
  assert.equal(
    fallbackPolicyMarkup(['Direct <match>'], escapeHtml),
    '<li><strong>1.</strong> Direct &lt;match&gt;</li>',
  );
  assert.match(
    setProposalMarkup(
      [{ id: 'safe', label: '<Safe>', summary: 'Flow', detail: 'Detail', accepted: true, health: { score: 90 } }],
      'safe',
      escapeHtml,
    ),
    /&lt;Safe&gt;/,
  );
  assert.match(
    aiObservabilityCards(
      { aiSelectedCount: 3, fallbackRate: 0.25, repairedCount: 1, averageDurationMs: 1200 },
      escapeHtml,
    ),
    /Safety fallback/,
  );
});

test('journey energy ranges replace missing or invalid endpoints with a playable value', () => {
  assert.deepEqual(journeyEnergyRange({ energyStart: 6, energyEnd: '?' }), [6, 6]);
  assert.deepEqual(journeyEnergyRange({ energyStart: 7, energyEnd: '' }), [7, 7]);
  assert.deepEqual(journeyEnergyRange({ energyStart: 'invalid', energyEnd: 8 }), [5, 8]);
  assert.deepEqual(journeyEnergyRange({ energyStart: 0, energyEnd: 14 }), [1, 10]);
});

test('Set Builder progress presentation is bounded, escaped, and stage-aware', () => {
  assert.equal(normalizeProgressPercent(-4), 0);
  assert.equal(normalizeProgressPercent(105), 100);
  assert.equal(normalizeProgressPercent('unknown'), null);
  assert.equal(formatProgressElapsed(65.8), '1:05');
  const markup = progressMarkup(
    {
      title: '<Planning>',
      detail: 'Catalog & validation',
      stages: ['Retrieve', 'Validate', 'Finish'],
      activeStep: 1,
      percent: 42,
      elapsedSeconds: 9,
    },
    escapeHtml,
  );
  assert.match(markup, /&lt;Planning&gt;/);
  assert.match(markup, /42% complete/);
  assert.match(markup, /class="complete"/);
  assert.match(markup, /class="active"/);
  assert.match(markup, /0:09/);
});
