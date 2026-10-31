import assert from 'node:assert/strict';
import test from 'node:test';

import {
  manualSearchTerms,
  manualTrackSearchEvidence,
  nextManualResultLimit,
  normalizeManualSearchText,
  scoreManualTrackSearch,
  searchManualCatalog,
  suggestManualPlanOrder,
} from '../../../../frontend/features/set-builder/manual-curation.js';
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

test('manual order suggestion previews an improved order without mutating the current plan', () => {
  const original = [{ id: 'high' }, { id: 'low' }];
  const result = suggestManualPlanOrder(original, {
    brief: { curve: 'rise' },
    improveOrder: (plan) => [...plan].reverse(),
    health: (plan) => ({ score: plan[0].id === 'low' ? 86 : 64 }),
    trackId: (track) => track.id,
  });
  assert.equal(result.changed, true);
  assert.equal(result.currentHealth, 64);
  assert.equal(result.suggestedHealth, 86);
  assert.deepEqual(result.suggested.map((track) => track.id), ['low', 'high']);
  assert.deepEqual(original.map((track) => track.id), ['high', 'low']);
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
