import assert from 'node:assert/strict';
import test from 'node:test';

import {
  formatManualFitScore,
  manualPlanEnergyFit,
  manualSearchTerms,
  manualTrackSearchEvidence,
  nextManualResultLimit,
  normalizeManualSearchText,
  scoreManualTrackSearch,
  searchManualCatalog,
  suggestManualPlanOrder,
} from '../../../../frontend/features/set-builder/manual-curation.js';
import { optimizeManualEnergyOrder } from '../../../../frontend/features/set-builder/manual-order-optimizer.js';
import { createTrackIdentityStore } from '../../../../frontend/features/set-builder/track-identity-store.js';

const catalog = [
  {
    id: 'latin-techno',
    source_name: 'Fuego Ritual.wav',
    artist: 'Luna Roja',
    _genre: 'Electronic / Techno',
    _detailedGenre: 'Driving Techno',
    _descriptors: [{ category: 'percussion', value: 'Latin percussion' }],
    _playlistIdentity: [{ source: 'rekordbox', value: 'Techno_Latino' }],
  },
  {
    id: 'disco',
    source_name: 'Fuego Disco.wav',
    artist: 'Studio Band',
    _genre: 'Disco & Funk',
    _descriptors: [{ category: 'mood', value: 'feel good' }],
    _playlistIdentity: [{ source: 'rekordbox', value: 'Saturday_Disco' }],
  },
];

const options = (track, requireAll = false) => ({
  requireAll,
  identityTerms: track.id === 'latin-techno' ? ['Spanish vocals', 'tribal groove'] : ['party classic'],
  roles: track.id === 'latin-techno' ? ['peak-time', 'bridge'] : ['warm-up'],
  metadata: track.id === 'latin-techno' ? ['high energy', 'steady timing'] : ['medium energy'],
});

test('manual catalog search normalizes punctuation and preserves quoted phrases', () => {
  assert.equal(normalizeManualSearchText('  LATIN_bounce/Techno  '), 'latin bounce techno');
  assert.deepEqual(manualSearchTerms('"latin techno", percussion  percussion'), [
    'latin techno',
    'percussion',
  ]);
});

test('manual catalog search matches playlist, descriptor, role, identity, title, artist, and genre evidence', () => {
  const track = catalog[0];
  const cases = [
    ['techno latino', 'playlist'],
    ['latin percussion', 'descriptor'],
    ['peak-time', 'role'],
    ['spanish vocals', 'identity'],
    ['fuego ritual', 'title'],
    ['luna roja', 'artist'],
    ['driving techno', 'genre'],
    ['high energy', 'metadata'],
  ];
  cases.forEach(([query, source]) => {
    const result = scoreManualTrackSearch(track, query, options(track, true));
    assert.equal(result.matched, true, query);
    assert.ok(result.evidence.some((item) => item.source === source), `${query} should cite ${source}`);
  });
});

test('manual catalog keyword sets rank broader evidence and can require every term', () => {
  const loose = catalog
    .map((track) => ({ track, ...scoreManualTrackSearch(track, 'latin techno disco', options(track)) }))
    .filter((result) => result.matched)
    .sort((left, right) => right.score - left.score);
  assert.equal(loose.length, 2);
  assert.equal(loose[0].track.id, 'latin-techno');

  const strict = catalog.map((track) => scoreManualTrackSearch(track, 'latin techno disco', options(track, true)));
  assert.deepEqual(strict.map((result) => result.matched), [false, false]);
});

test('manual catalog search is stable for empty and missing identity metadata', () => {
  const results = searchManualCatalog([{ id: 'empty' }, ...catalog], 'fuego');
  assert.deepEqual(results.map((result) => result.track.id), ['disco', 'latin-techno']);
  assert.deepEqual(manualTrackSearchEvidence(null), []);
  assert.equal(scoreManualTrackSearch({}, '', {}).matched, true);
});

test('manual catalog result batches grow predictably and stop at the match count', () => {
  assert.equal(nextManualResultLimit(12, 1034), 24);
  assert.equal(nextManualResultLimit(24, 27), 27);
  assert.equal(nextManualResultLimit(0, 3), 3);
  assert.equal(nextManualResultLimit(12, 1034, 24), 36);
});

test('manual catalog fit labels stay within their documented percentage range', () => {
  assert.equal(formatManualFitScore(116.4), 100);
  assert.equal(formatManualFitScore(-9), 0);
  assert.equal(formatManualFitScore(58.6), 59);
  assert.equal(formatManualFitScore(Number.NaN), 0);
});

test('manual order suggestion previews an improved order without mutating the current plan', () => {
  const original = [{ id: 'high' }, { id: 'low' }];
  const result = suggestManualPlanOrder(original, {
    brief: { curve: 'rise' },
    improveOrder: (plan) => [...plan].reverse(),
    health: (plan) => ({ score: plan[0].id === 'low' ? 86 : 64 }),
    energyFit: (plan) => (plan[0].id === 'low' ? 91 : 52),
    trackId: (track) => track.id,
  });
  assert.equal(result.changed, true);
  assert.equal(result.currentHealth, 64);
  assert.equal(result.suggestedHealth, 86);
  assert.equal(result.currentEnergyFit, 52);
  assert.equal(result.suggestedEnergyFit, 91);
  assert.deepEqual(result.suggested.map((track) => track.id), ['low', 'high']);
  assert.deepEqual(original.map((track) => track.id), ['high', 'low']);
});

test('manual energy fit compares every chosen track with the selected journey shape', () => {
  const plan = [{ energy: 0.2 }, { energy: 0.8 }];
  assert.equal(
    manualPlanEnergyFit(plan, { curve: 'rise' }, {
      songEnergy: (track) => track.energy,
      targetEnergy: (index) => (index ? 0.8 : 0.2),
    }),
    100,
  );
  assert.equal(
    manualPlanEnergyFit(plan, { curve: 'steady' }, {
      songEnergy: (track) => track.energy,
      targetEnergy: () => 0.5,
    }),
    70,
  );
  assert.equal(manualPlanEnergyFit([], {}, { songEnergy: () => 0.5, targetEnergy: () => 0.5 }), 100);
  assert.equal(
    manualPlanEnergyFit([{ energy: 0 }, { energy: Number.NaN }], {}, {
      songEnergy: (track) => track.energy,
      targetEnergy: () => 0,
    }),
    75,
  );
});

test('manual order suggestion handles short and already-optimal plans', () => {
  const trackId = (track) => track.id;
  const health = () => ({ score: 80 });
  assert.equal(suggestManualPlanOrder([{ id: 'only' }], { brief: {}, improveOrder: (plan) => plan, health, trackId }), null);
  const result = suggestManualPlanOrder([{ id: 'a' }, { id: 'b' }], {
    brief: {},
    improveOrder: (plan) => plan,
    health,
    trackId,
  });
  assert.equal(result.changed, false);
  assert.equal(result.currentFingerprint, 'a|b');
});

function energyOrderOptions(overrides = {}) {
  return {
    brief: { curve: 'rise', minimumHealth: 65 },
    health: () => ({ score: 80 }),
    energyFit: (plan) =>
      manualPlanEnergyFit(plan, {}, {
        songEnergy: (track) => track.energy,
        targetEnergy: (index, length) => (length === 1 ? 0.5 : 0.2 + (index / (length - 1)) * 0.6),
      }),
    trackId: (track) => track.id,
    songEnergy: (track) => track.energy,
    targetEnergy: (index, length) => (length === 1 ? 0.5 : 0.2 + (index / (length - 1)) * 0.6),
    ...overrides,
  };
}

test('manual energy optimizer reorders existing tracks toward the selected shape', () => {
  const original = [
    { id: 'high', energy: 0.8 },
    { id: 'low', energy: 0.2 },
    { id: 'middle', energy: 0.5 },
  ];
  const result = optimizeManualEnergyOrder(original, energyOrderOptions());
  assert.equal(result.changed, true);
  assert.deepEqual(result.suggested.map((track) => track.id), ['low', 'middle', 'high']);
  assert.ok(result.suggestedEnergyFit > result.currentEnergyFit);
  assert.equal(result.suggestedHealth, 80);
  assert.equal(result.healthGuardrail, 75);
  assert.equal(result.movedCount, 3);
  assert.deepEqual(original.map((track) => track.id), ['high', 'low', 'middle']);
});

test('manual energy optimizer preserves locked positions and journey sections', () => {
  const original = [
    { id: 'a-high', energy: 0.8, section: 'a' },
    { id: 'b-low', energy: 0.2, section: 'b' },
    { id: 'a-low', energy: 0.2, section: 'a' },
    { id: 'b-high', energy: 0.8, section: 'b' },
  ];
  const result = optimizeManualEnergyOrder(
    original,
    energyOrderOptions({
      isFixed: (track) => track.id === 'b-low',
      sectionId: (track) => track.section,
    }),
  );
  assert.equal(result.changed, true);
  assert.equal(result.suggested[1].id, 'b-low');
  assert.deepEqual(result.suggested.map((track) => track.section), ['a', 'b', 'a', 'b']);
  assert.deepEqual(result.suggested.filter((track) => track.section === 'a').map((track) => track.id), [
    'a-low',
    'a-high',
  ]);
});

test('manual energy optimizer uses a mix-health guardrail and reports unsafe improvements', () => {
  const original = [
    { id: 'high', energy: 0.8 },
    { id: 'low', energy: 0.2 },
  ];
  const result = optimizeManualEnergyOrder(
    original,
    energyOrderOptions({
      health: (plan) => ({ score: plan[0].id === 'high' ? 70 : 40 }),
    }),
  );
  assert.equal(result.changed, false);
  assert.equal(result.noSafeImprovement, true);
  assert.equal(result.healthGuardrail, 65);
  assert.deepEqual(result.suggested.map((track) => track.id), ['high', 'low']);
});

test('manual energy optimizer may trade a small health change for a safe energy improvement', () => {
  const original = [
    { id: 'high', energy: 0.8 },
    { id: 'low', energy: 0.2 },
    { id: 'middle', energy: 0.5 },
  ];
  const result = optimizeManualEnergyOrder(
    original,
    energyOrderOptions({
      health: (plan) => ({ score: plan[0].id === 'low' && plan[2].id === 'high' ? 65 : 66 }),
    }),
  );
  assert.equal(result.changed, true);
  assert.equal(result.suggestedHealth, 65);
  assert.equal(result.healthGuardrail, 65);
  assert.ok(result.suggestedEnergyFit > result.currentEnergyFit);
});

test('manual identity recovery storage tolerates corruption and persists normalized terms', () => {
  let value = '{bad json';
  const storage = { getItem: () => value, setItem: (_key, next) => (value = next) };
  const identities = createTrackIdentityStore({
    storage,
    storageKey: 'identities',
    trackId: (track) => track.id,
    parseTerms: (terms) => [...new Set(terms.map((term) => term.trim().toLowerCase()))],
  });
  const track = { id: 'track-1' };
  assert.deepEqual(identities.load(), {});
  assert.deepEqual(identities.save(track, [' Latin ', 'latin', 'Peak']), ['latin', 'peak']);
  assert.deepEqual(identities.terms(track), ['latin', 'peak']);
  assert.deepEqual(track._manualIdentity, ['latin', 'peak']);
});
