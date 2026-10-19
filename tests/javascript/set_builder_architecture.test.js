import test from 'node:test';
import assert from 'node:assert/strict';

import { createApiClient } from '../../web/api-client.js';
import { createSetBuilderApi } from '../../web/set-builder-api.js';
import { createClassicSetPlanner, optimizePlanOrder } from '../../web/set-builder-classic-planner.js';
import { createSetEditCommands } from '../../web/set-builder-commands.js';
import { createSetBuilderStore, restoreSetPlan, snapshotSetPlan } from '../../web/set-builder-state.js';
import { aiObservabilityCards, fallbackPolicyMarkup, setProposalMarkup } from '../../web/set-builder-view-model.js';
import {
  SET_BRIEF_MODES,
  SET_TRACK_PLANNERS,
  createSetWorkflowController,
  inferSetWorkflow,
  resolveSetPlanningMode,
  setBriefModeMessage,
} from '../../web/set-builder-workflow.js';

const trackId = (track) => track.id;
const response = (payload, { ok = true, status = 200 } = {}) => ({ ok, status, json: async () => payload });
const escapeHtml = (value) => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');

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
      '/api/set-builder/interpret-intention',
      '/api/set-builder/plan-journey',
      '/api/set-builder/export-preflight',
      '/api/set-builder/sets',
      '/api/set-builder/sets/set%2Fone',
      '/api/set-builder/sets/set%2Fone',
      '/api/set-builder/sets/migrate-v1',
    ],
  );
  assert.deepEqual(JSON.parse(calls[1].options.body), {
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
