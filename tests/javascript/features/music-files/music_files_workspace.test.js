import test from 'node:test';
import assert from 'node:assert/strict';

import {
  activeMusicFilesFilters,
  clearMusicFilesFilter,
  createMusicFilesUiState,
  musicFilesQuery,
  musicFilesSelectionSummary,
  resetMusicFilesFilters,
} from '../../../../frontend/features/music-files/state.js';

test('Music Files state starts with a stable browse request', () => {
  const state = createMusicFilesUiState(25);

  assert.deepEqual(state, {
    search: '',
    genre: 'all',
    detailedGenre: 'all',
    playlist: 'all',
    analysis: 'all',
    artwork: 'all',
    quality: 'all',
    sort: 'newest',
    page: 1,
    pageSize: 25,
  });
  assert.deepEqual(Object.fromEntries(musicFilesQuery(state)), {
    paged: 'true',
    page: '1',
    page_size: '25',
    search: '',
    genre: 'all',
    detailed_genre: 'all',
    playlist: 'all',
    analysis: 'all',
    artwork: 'all',
    quality: 'all',
    sort: 'newest',
  });
});

test('active Music Files filters describe only non-default constraints', () => {
  const state = createMusicFilesUiState(50);
  state.search = 'night drive';
  state.genre = 'Electronic / House';
  state.analysis = 'complete';
  state.sort = 'title';

  assert.deepEqual(
    activeMusicFilesFilters(state, {
      genre: 'House',
      analysis: 'Analyzed',
    }),
    [
      { key: 'search', label: 'Search', value: 'night drive' },
      { key: 'genre', label: 'Parent genre', value: 'House' },
      { key: 'analysis', label: 'Analysis', value: 'Analyzed' },
    ],
  );
});

test('clearing a parent genre also clears its dependent detailed genre', () => {
  const state = createMusicFilesUiState(100);
  Object.assign(state, {
    genre: 'Electronic / House',
    detailedGenre: 'Disco House',
    page: 4,
  });

  clearMusicFilesFilter(state, 'genre');

  assert.equal(state.genre, 'all');
  assert.equal(state.detailedGenre, 'all');
  assert.equal(state.page, 1);
  assert.equal(state.pageSize, 100);
});

test('resetting Music Files filters preserves the chosen page size', () => {
  const state = createMusicFilesUiState(100);
  Object.assign(state, {
    search: 'classic',
    playlist: 'Favorites',
    artwork: 'missing',
    sort: 'artist',
    page: 7,
  });

  resetMusicFilesFilters(state);

  assert.equal(state.search, '');
  assert.equal(state.playlist, 'all');
  assert.equal(state.artwork, 'all');
  assert.equal(state.sort, 'newest');
  assert.equal(state.page, 1);
  assert.equal(state.pageSize, 100);
});

test('selection summary exposes capabilities without mixing maintenance scope', () => {
  const summary = musicFilesSelectionSummary([
    { id: 1, available: true, artwork_available: false, analysis_status: 'pending' },
    { id: 2, available: true, artwork_available: true, analysis_status: 'complete' },
    { id: 3, available: false, artwork_available: false, analysis_status: 'failed' },
  ]);

  assert.equal(summary.label, '3 selected · 2 need artwork');
  assert.deepEqual(
    summary.downloadable.map((track) => track.id),
    [1, 2],
  );
  assert.deepEqual(
    summary.missingArtwork.map((track) => track.id),
    [1, 3],
  );
  assert.deepEqual(
    summary.analyzable.map((track) => track.id),
    [1],
  );
});
