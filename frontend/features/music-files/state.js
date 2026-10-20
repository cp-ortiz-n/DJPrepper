const FILTER_DEFAULTS = Object.freeze({
  search: '',
  genre: 'all',
  detailedGenre: 'all',
  playlist: 'all',
  analysis: 'all',
  artwork: 'all',
  quality: 'all',
  sort: 'newest',
  page: 1,
});

const FILTER_LABELS = Object.freeze({
  search: 'Search',
  genre: 'Parent genre',
  detailedGenre: 'Detailed genre',
  playlist: 'Playlist',
  analysis: 'Analysis',
  artwork: 'Artwork',
  quality: 'Audio quality',
});

export function createMusicFilesUiState(
  pageSize = Number(globalThis.localStorage?.getItem('music-files-page-size') || 50),
) {
  return { ...FILTER_DEFAULTS, pageSize };
}

export function musicFilesQuery(state) {
  return new URLSearchParams({
    paged: 'true',
    page: String(state.page),
    page_size: String(state.pageSize),
    search: state.search,
    genre: state.genre,
    detailed_genre: state.detailedGenre,
    playlist: state.playlist,
    analysis: state.analysis,
    artwork: state.artwork,
    quality: state.quality,
    sort: state.sort,
  });
}

export function resetMusicFilesFilters(state) {
  Object.assign(state, FILTER_DEFAULTS);
  return state;
}

export function clearMusicFilesFilter(state, key) {
  if (!Object.hasOwn(FILTER_LABELS, key)) return state;
  state[key] = FILTER_DEFAULTS[key];
  if (key === 'genre') state.detailedGenre = FILTER_DEFAULTS.detailedGenre;
  state.page = 1;
  return state;
}

export function activeMusicFilesFilters(state, displayValues = {}) {
  return Object.entries(FILTER_LABELS).flatMap(([key, label]) => {
    const value = state[key];
    if (value === FILTER_DEFAULTS[key]) return [];
    const displayValue = displayValues[key] || value;
    return [{ key, label, value: displayValue }];
  });
}

export function musicFilesSelectionSummary(tracks) {
  const selected = [...tracks];
  const downloadable = selected.filter((track) => track.available);
  const missingArtwork = selected.filter((track) => !track.artwork_available);
  const analyzable = downloadable.filter(
    (track) => !['queued', 'processing', 'complete'].includes(track.analysis_status),
  );
  return {
    selected,
    downloadable,
    missingArtwork,
    analyzable,
    label: `${selected.length} selected${selected.length ? ` · ${missingArtwork.length} need artwork` : ''}`,
  };
}

export { FILTER_DEFAULTS as MUSIC_FILES_FILTER_DEFAULTS };
