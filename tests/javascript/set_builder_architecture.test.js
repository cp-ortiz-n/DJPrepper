import test from 'node:test';
import assert from 'node:assert/strict';

import { createApiClient } from '../../web/api-client.js';
import { createSetBuilderApi } from '../../web/set-builder-api.js';
import { createClassicSetPlanner, optimizePlanOrder } from '../../web/set-builder-classic-planner.js';
import { createSetEditCommands } from '../../web/set-builder-commands.js';
import { createSetBuilderFeedback } from '../../web/set-builder-feedback.js';
import { createSetPlanView } from '../../web/set-builder-plan-view.js';
import { createSetPlanningSession } from '../../web/set-builder-planning-session.js';
import { buildSetCsv, buildSetM3u, createSavedSetController } from '../../web/set-builder-saved-sets.js';
import { createSetBuilderStore, restoreSetPlan, snapshotSetPlan } from '../../web/set-builder-state.js';
import { createSetTransitionEditor } from '../../web/set-builder-transition-editor.js';
import {
  aiObservabilityCards,
  fallbackPolicyMarkup,
  journeyEvidenceLabel,
  setProposalMarkup,
} from '../../web/set-builder-view-model.js';
import {
  SET_BRIEF_MODES,
  SET_TRACK_PLANNERS,
  allowsCandidateGenre,
  createSetIntentionController,
  createSetWorkflowController,
  inferSetWorkflow,
  passesSetCandidateHardFilters,
  requiresStrictGenreEligibility,
  resolveStructuredGenreFilters,
  resolveSetPlanningMode,
  setBriefModeMessage,
} from '../../web/set-builder-workflow.js';

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
});

test('Set Builder store snapshots and restores plan identity, locks, and transitions', () => {
  const storage = { getItem: () => 'true' };
  const store = createSetBuilderStore({ storage });
  const library = [{ id: 'a' }, { id: 'b' }];
  store.plan = [...library];
  store.lockedIds.add('a');
  store.transitionSettings['a→b'] = { bars: 16 };

  const snapshot = snapshotSetPlan(store, trackId);
  store.plan = [];
  store.lockedIds.clear();
  store.transitionSettings['a→b'].bars = 8;
  restoreSetPlan(store, snapshot, library, trackId);

  assert.equal(store.compactMode, true);
  assert.deepEqual(store.plan, library);
  assert.deepEqual([...store.lockedIds], ['a']);
  assert.deepEqual(store.transitionSettings, { 'a→b': { bars: 16 } });
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

test('AI-authored genres rank candidates without becoming hard catalog filters', () => {
  assert.equal(
    allowsCandidateGenre({
      authoringMode: SET_BRIEF_MODES.AI,
      directGenre: false,
      requestedGenreMatch: false,
      hasInterpretedIdentity: true,
      drift: 'none',
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

test('workflow controller updates mode surfaces without clearing authored values', () => {
  const elements = new Map([
    ['#set-builder-form', { dataset: {} }],
    ['#set-ai-brief', { hidden: false }],
    ['#set-manual-brief', { hidden: true }],
    ['#set-brief-mode-help', { textContent: '' }],
    ['#set-planning-mode', { value: '' }],
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
  const { session } = planningSessionFor({ state, elements, planningClient: {}, classicPlanner });

  await session.generateDeterministicSetPlan();

  assert.equal(state.plan.length, 3);
  assert.equal(state.activeProposal, 'balanced');
  assert.equal(session.receipt().mode, 'classic');
  assert.match(elements.get('#set-builder-message').textContent, /Balanced applied at 82\/100/);
  assert.equal(Object.isFrozen(session), true);
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
        { id: 1, technicalScore: 81 },
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
  assert.match(elements.get('#set-builder-message').textContent, /deterministic safety fallback/);
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
    state: { plan },
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
  const state = {
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
  };
  const controller = savedSetControllerFor({
    state,
    elements,
    api: {
      saveSet: async (record) => calls.push(['set', record]),
      savePlaylist: async (payload) => {
        calls.push(['playlist', payload]);
        return { path: '/playlists/Night Set.m3u8' };
      },
    },
  });

  try {
    await controller.saveCurrentSet();

    assert.equal(controller.savedSets().length, 1);
    assert.deepEqual(controller.savedSets()[0].tracks, ['track-1']);
    assert.equal(JSON.parse(storage.get('sets')).length, 1);
    assert.equal(calls[1][1].tracks[0].path, '/music/Opening.wav');
    assert.match(message.textContent, /playlist written to \/playlists\/Night Set\.m3u8/);
    assert.equal(selected.value, controller.savedSets()[0].id);
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
