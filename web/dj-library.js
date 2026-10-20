import { useFrontendServices } from './frontend-services.js';
import { createDjLibraryFilters } from './dj-library-filters.js';
import { createDjLibraryIntelligence } from './dj-library-intelligence.js';
import { createDjLibrarySelection } from './dj-library-selection.js';
import { createDjLibraryView } from './dj-library-view.js';

import {
  LIBRARY_ROLE_INFO,
  MUSICAL_PROFILE_VERSION,
  camelotKey,
  compatibility,
  createLibraryUiState,
  effectivePreset,
  energyBand,
  formatLibraryKey,
  harmonicCompatibility,
  libraryKeyMode,
  libraryQuery,
  libraryRoles,
  normalizedKey,
  songEnergy,
  timingProfile,
  vocalProfile,
} from './dj-library-model.js';

export {
  LIBRARY_ROLE_INFO,
  MUSICAL_PROFILE_VERSION,
  camelotKey,
  compatibility,
  createLibraryUiState,
  effectivePreset,
  energyBand,
  formatLibraryKey,
  harmonicCompatibility,
  libraryKeyMode,
  libraryQuery,
  libraryRoles,
  normalizedKey,
  songEnergy,
  timingProfile,
  vocalProfile,
} from './dj-library-model.js';

export function createDjLibraryFeature({
  services,
  getAppConfig,
  libraryUiState,
  libraryRequestState,
  getLoadedAt,
  setLoadedAt,
  invalidateMusicFiles,
  VIEW_CACHE_MS,
  escapeHtml,
  genreFolderTree,
  bindGenreFolderState,
  option,
  refreshSearchableSelects,
  compactAudioMarkup,
  genreEditorMarkup,
  bindGenreEditor,
  bindCompactAudio,
  renderTrackPagination,
  clock,
  pct,
  loadJobs,
  loadDownloadedLibrary,
  loadReports,
  showView,
  startKeyAnalysis,
  compactAudioIsWithin,
  stopCompactAudio,
  normalizedGenreCategory,
  ELECTRONIC_GENRE_CATEGORIES,
  LATIN_GENRE_CATEGORIES,
  libraryReprocessForm,
  reportDate,
  bindLazyAudio,
  syncControlUnlessEditing,
  captureTextFilter,
  loadAnalysis,
  jobAction,
  jobElement,
}) {
  const { api, $, $$, notify, confirmAction, descriptorChipsMarkup, descriptorEditorMarkup, saveDescriptorEditor } =
    useFrontendServices(services);
  async function revealLibraryTrack(jobId, sourceName) {
    let card = document.querySelector(`.library-card[data-job-id="${jobId}"]`);
    if (!card) {
      libraryRequestState.reset();
      libraryRequestState.update({ search: String(sourceName || '').replace(/\.[^.]+$/, ''), page: 1 });
      await loadLibrary();
      card = document.querySelector(`.library-card[data-job-id="${jobId}"]`);
    }
    if (!card) {
      notify(
        `Could not reveal ${String(sourceName || 'that track').replace(/\.[^.]+$/, '')}. Reset the Library filters and try again.`,
        'danger',
      );
      return;
    }
    card.scrollIntoView({ behavior: 'smooth', block: 'start' });
    card.querySelector('.library-compact-row')?.focus();
  }

  const filters = createDjLibraryFilters({
    $,
    state: libraryUiState,
    requestState: libraryRequestState,
    option,
    escapeHtml,
    syncControlUnlessEditing,
    captureTextFilter,
    renderTrackPagination,
    reload: () => loadLibrary(),
  });
  const selection = createDjLibrarySelection({
    services,
    loadLibrary: () => loadLibrary(),
    loadDownloadedLibrary,
    loadAnalysis,
    loadReports,
    loadJobs,
    showView,
    startKeyAnalysis,
    setLoadedAt,
    invalidateMusicFiles,
  });
  const intelligence = createDjLibraryIntelligence({
    $,
    option,
    escapeHtml,
    revealTrack: revealLibraryTrack,
  });
  const renderLibraryIntelligence = (songs, latestByName) => intelligence.render(songs, latestByName);
  const view = createDjLibraryView({
    services,
    getAppConfig,
    libraryUiState,
    escapeHtml,
    genreFolderTree,
    bindGenreFolderState,
    compactAudioMarkup,
    genreEditorMarkup,
    bindGenreEditor,
    bindCompactAudio,
    pct,
    compactAudioIsWithin,
    stopCompactAudio,
    normalizedGenreCategory,
    libraryReprocessForm,
    reportDate,
    bindLazyAudio,
    invalidateMusicFiles,
    showView,
    jobAction,
    jobElement,
    loadAnalysis,
    loadReports,
    reload: () => loadLibrary(),
    filters,
    selection,
  });

  async function loadLibrary() {
    let catalog;
    try {
      const result = await libraryRequestState.request(`/api/library/catalog?${libraryQuery(libraryUiState)}`, {
        errorMessage: 'DJ Library could not be loaded.',
      });
      if (result.status !== 'applied') return;
      catalog = result.payload;
      libraryRequestState.setPage(Number(catalog.page || 1));
      setLoadedAt(Date.now());
    } catch (error) {
      $('#library-list').innerHTML =
        `<div class="empty danger-text">${escapeHtml(error.message || 'DJ Library could not be loaded.')} <button type="button" class="button secondary library-retry">Retry</button></div>`;
      $('#library-list .library-retry')?.addEventListener('click', loadLibrary);
      return;
    }
    const allJobs = (catalog.tracks || []).map((track) => track.job);
    const report = {
      songs: Object.fromEntries((catalog.tracks || []).map((track, index) => [index, track.analysis || {}])),
    };
    const downloadedTracks = (catalog.tracks || []).map((track) => track.downloaded).filter(Boolean);
    selection.setVisibleTracks(downloadedTracks);
    const downloaded = { tracks: downloadedTracks, genres: catalog.facets?.categories || {} };
    const downloadedByJob = new Map(
      (downloaded.tracks || [])
        .filter((track) => track.completed_library_job_id)
        .map((track) => [Number(track.completed_library_job_id), track]),
    );
    $('#library-genre-options').replaceChildren(
      ...[
        ...new Set([
          ...Object.keys(downloaded.genres || {}),
          ...ELECTRONIC_GENRE_CATEGORIES,
          ...LATIN_GENRE_CATEGORIES,
        ]),
      ]
        .sort()
        .map((name) => option(name, name)),
    );
    const jobs = allJobs.filter((job) => job.status === 'complete');
    const analysisByTrack = new Map(
      Object.values(report.songs || {}).map((song) => [String(song.source_name || '').toLowerCase(), song]),
    );
    const grouped = new Map();
    [...jobs].reverse().forEach((job) => {
      const key = job.source_name.toLowerCase();
      const versions = grouped.get(key) || [];
      job._generation = Number(job.generation_count || versions.length + 1);
      versions.push(job);
      grouped.set(key, versions);
    });
    const latestByName = new Map([...grouped.entries()].map(([name, versions]) => [name, versions.at(-1)]));
    const intelligenceSongs = (catalog.intelligence || [])
      .map((item) => item.analysis)
      .filter((song) => song?.source_name);
    const intelligenceJobs = new Map(
      (catalog.intelligence || []).map((item) => [String(item.source_name || '').toLowerCase(), { id: item.job_id }]),
    );
    renderLibraryIntelligence(intelligenceSongs, intelligenceJobs);
    await view.render({ catalog, grouped, jobs, analysisByTrack, downloadedByJob });
  }

  return { loadLibrary, renderLibraryIntelligence };
}
