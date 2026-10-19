import WaveSurfer from '/vendor/wavesurfer/wavesurfer.esm.js';
import RegionsPlugin from '/vendor/wavesurfer/plugins/regions.esm.js';
import TimelinePlugin from '/vendor/wavesurfer/plugins/timeline.esm.js';
import HoverPlugin from '/vendor/wavesurfer/plugins/hover.esm.js';
import { AuthorizedImportQueue } from '/assets/import-queue.js?v=20260930-1';
import { createApiClient } from './api-client.js';
import {
  $,
  $$,
  apiErrorMessage,
  captureTextFilter,
  clock,
  composeFrontendServices,
  confirmAction,
  descriptorChipsMarkup,
  descriptorEditorMarkup,
  escapeHtml,
  fraction,
  inferDescriptorEditor,
  notify,
  openDescriptorEditorDialog,
  operationReceiptText,
  option,
  pct,
  renderTrackPagination,
  reportDate,
  saveDescriptorEditor,
  startKeyAnalysis,
  syncControlUnlessEditing,
} from './shared-components.js?v=20261013-1';
import {
  bindCompactAudio,
  bindLazyAudio,
  closeDownloadedInspector,
  compactAudioIsWithin,
  compactAudioMarkup,
  stopCompactAudio,
  stopNativeAudio,
} from './playback.js';
import {
  LIBRARY_ROLE_INFO,
  camelotKey,
  compatibility,
  createDjLibraryFeature,
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
} from './dj-library.js?v=20261013-1';
import { createMusicFilesFeature, createMusicFilesUiState } from './music-files.js?v=20261013-1';
import { createRequestStateController } from './request-state-controller.js';
import { createReportingFeature } from './reporting.js?v=20261013-1';
import { createSetBuilderFeature } from './set-builder.js?v=20261019-1';
import { createSettingsFeature, libraryAvailabilityView } from './settings.js?v=20261013-1';
import { createAuthorizedImportFeature, createImportWorkspaceApi } from './import-workspace.js';
import { createBackgroundTaskController } from './background-task-controller.js';
import { createImportIssuesFeature } from './import-issues.js';
import { createLocalAudioImportFeature } from './local-audio-import.js';
import { createPlaylistImportFeature } from './playlist-import.js';
import {
  annotateProcessingJobs,
  createProcessingWorkspaceApi,
  createProcessingWorkspaceController,
} from './processing-workspace.js';
import { createProcessingWorkspaceView } from './processing-workspace-view.js';
import { createCandidateReviewFeature } from './candidate-review.js';
import { createSearchableSelectController } from './searchable-selects.js';
import { createTrackMetadataUi, ELECTRONIC_GENRE_CATEGORIES, LATIN_GENRE_CATEGORIES } from './track-metadata-ui.js';
import { createProcessingJobDetail } from './processing-job-detail.js';
import { createNavigationController } from './navigation-controller.js';

const navigation = createNavigationController({
  loadView: (id) => loadView(id),
  onError: (error) => notify(error.message || 'This view could not be loaded. Please try again.', 'danger'),
});
const api = createApiClient();
const importWorkspaceApi = createImportWorkspaceApi(api);
const processingWorkspaceApi = createProcessingWorkspaceApi(api);
// Keep legacy call sites non-blocking and visually consistent while workflows migrate
// to structured inline messages and richer recovery actions.
window.alert = (message) => notify(message, 'danger');
const searchableSelectController = createSearchableSelectController();
searchableSelectController.start();
const refreshSearchableSelects = () => searchableSelectController.refresh();
const form = $('#upload-form');
const fileInput = $('#files');
const dropZone = $('#drop-zone');
const jobsRoot = $('#jobs');
const template = $('#job-template');
let processingWorkspaceController = null;
let processingWorkspaceView = null;
let candidateReviewFeature = null;
let appConfig = null;
let stagedFiles = [];
let workspaceMode = 'analyze';
const downloadedUiState = createMusicFilesUiState();
const downloadedSelection = new Map();
let downloadedLoadedAt = 0;
let libraryLoadedAt = 0;
const libraryUiState = createLibraryUiState();
const downloadedRequestState = createRequestStateController({
  namespace: 'music',
  state: downloadedUiState,
  defaults: createMusicFilesUiState(downloadedUiState.pageSize),
  debounceMs: 220,
  onLoading: (loading) => $('#downloads-view')?.classList.toggle('view-refreshing', loading),
});
const libraryRequestState = createRequestStateController({
  namespace: 'dj',
  state: libraryUiState,
  defaults: createLibraryUiState(libraryUiState.pageSize),
  debounceMs: 240,
  onLoading: (loading) => $('#library-view')?.classList.toggle('view-refreshing', loading),
});
const VIEW_CACHE_MS = 30000;
const backgroundTaskController = createBackgroundTaskController({
  loadJson: (url, signal) => api.get(url, { cache: 'no-store', signal }, 'Background task status is unavailable.'),
});

$$('.import-method').forEach((method) =>
  method.addEventListener('toggle', () => {
    if (!method.open) return;
    $$('.import-method').forEach((other) => {
      if (other !== method) other.open = false;
    });
  }),
);

const runBackgroundTask = (options) => backgroundTaskController.run(options);
const stopBackgroundTask = (key) => backgroundTaskController.stop(key);
const trackMetadataUi = createTrackMetadataUi({ escapeHtml, apiErrorMessage, notify, operationReceiptText });
const {
  bindGenreEditor,
  bindGenreFolderState,
  collapsedGenreFolders,
  detailedGenreSummary,
  genreEditorMarkup,
  genreFolderTree,
  metadataEditorMarkup,
  normalizedGenreCategory,
} = trackMetadataUi;

async function decodedAudio(url, cache, key) {
  if (!cache[key]) {
    const AudioEngine = window.AudioContext || window.webkitAudioContext;
    cache.context ||= new AudioEngine();
    await cache.context.resume();
    cache[key] = fetch(url).then(async (response) => {
      if (!response.ok) throw new Error('Audio unavailable');
      return cache.context.decodeAudioData(await response.arrayBuffer());
    });
  }
  return cache[key];
}

async function loadConfig() {
  const config = await fetch('/api/config').then((r) => r.json());
  appConfig = config;
  ['preset', 'setting-preset'].forEach((id) => {
    const select = $('#' + id);
    select.replaceChildren();
    config.presets.forEach((value) => select.append(option(value, value === 'auto' ? 'Auto detect' : value)));
  });
  ['intro-bars', 'outro-bars'].forEach((id) => {
    const select = $('#' + id);
    select.replaceChildren();
    select.append(option('auto', 'Auto'));
    config.bar_counts.forEach((value) => select.append(option(value, value === 0 ? 'None' : `${value} bars`)));
  });
  [
    ['setting-intro', 'intro_bars'],
    ['setting-outro', 'outro_bars'],
  ].forEach(([id]) => {
    const select = $('#' + id);
    select.replaceChildren();
    config.bar_counts.forEach((value) => select.append(option(value, value === 0 ? 'None' : `${value} bars`)));
  });
  applyEffectiveSettings(config.effective);
  refreshSearchableSelects();
  ['preset-intro', 'preset-outro'].forEach((id) => {
    const select = $('#' + id);
    select.replaceChildren(...config.bar_counts.map((value) => option(value, value === 0 ? 'None' : `${value} bars`)));
  });
}

let presetLibrary = [];
function editPreset(preset = null) {
  $('#preset-original-name').value = preset?.name || '__new__';
  $('#preset-name').value = preset?.name || '';
  $('#preset-intro').value = preset?.intro_bars ?? 8;
  $('#preset-outro').value = preset?.outro_bars ?? 8;
  $('#preset-quality').value = preset?.minimum_loop_quality ?? 65;
  $('#preset-copies').value = preset?.maximum_repetitions ?? 2;
  $('#preset-stems').checked = Boolean(preset?.use_stems);
  $('#delete-preset').hidden = !preset;
  $('#preset-message').textContent = preset
    ? `${preset.built_in ? 'Built-in' : 'Custom'} preset${preset.modified ? ' · customized' : ''}`
    : 'Creating a new preset';
  document
    .querySelectorAll('.preset-item')
    .forEach((item) => item.classList.toggle('selected', item.dataset.name === preset?.name));
}

async function loadPresets() {
  const payload = await fetch('/api/presets').then((response) => response.json());
  presetLibrary = payload.presets || [];
  $('#preset-list').innerHTML =
    presetLibrary
      .map(
        (preset) =>
          `<button class="preset-item" type="button" data-name="${escapeHtml(preset.name)}"><strong>${escapeHtml(preset.name)}</strong><span>${preset.intro_bars} intro · ${preset.outro_bars} outro · ${Math.round(preset.minimum_loop_quality)}% floor</span><small>${preset.use_stems ? 'Demucs' : 'Full mix'} · max ${preset.maximum_repetitions} copies${preset.modified ? ' · customized' : preset.built_in ? ' · built-in' : ' · custom'}</small></button>`,
      )
      .join('') || '<p class="empty">No presets available.</p>';
  document
    .querySelectorAll('.preset-item')
    .forEach(
      (item) => (item.onclick = () => editPreset(presetLibrary.find((preset) => preset.name === item.dataset.name))),
    );
  if (!$('#preset-name').value && presetLibrary.length) editPreset(presetLibrary[0]);
}

async function loadPerformanceDiagnostics() {
  const body = $('#performance-diagnostics-body');
  const summary = $('#performance-diagnostics-summary');
  if (!body || !summary) return;
  summary.textContent = 'Refreshing measurements…';
  try {
    const response = await fetch('/api/diagnostics/performance');
    if (!response.ok) throw new Error('Diagnostics are unavailable');
    const payload = await response.json();
    summary.innerHTML = `<span><b>${payload.window_size}</b> of ${payload.window_limit} requests sampled</span><span><b>${Number(payload.overall_average_ms).toFixed(1)} ms</b> overall average</span><span><b>${payload.operations.length}</b> operations measured</span>`;
    body.innerHTML = payload.operations.length
      ? payload.operations
          .map(
            (item) =>
              `<tr><td>${escapeHtml(item.operation)}</td><td>${item.count}</td><td>${Number(item.average_ms).toFixed(1)} ms</td><td class="${item.p95_ms >= 250 ? 'diagnostic-warning' : ''}">${Number(item.p95_ms).toFixed(1)} ms</td><td>${Number(item.maximum_ms).toFixed(1)} ms</td><td class="${item.failures ? 'diagnostic-error' : ''}">${item.failures}</td></tr>`,
          )
          .join('')
      : '<tr><td colspan="6">Use the app, then refresh to see timings.</td></tr>';
    $('#performance-cache-stats').innerHTML = payload.cache
      .map(
        (item) =>
          `<article><strong>${escapeHtml(item.name.replaceAll('_', ' '))}</strong><b>${item.hit_rate == null ? 'No data' : `${Number(item.hit_rate).toFixed(1)}% hit rate`}</b><small>${item.hits} hits · ${item.misses} misses</small></article>`,
      )
      .join('');
    $('#performance-slow-operations').innerHTML = payload.recent_slow_operations.length
      ? payload.recent_slow_operations
          .map(
            (item) =>
              `<article><span>${escapeHtml(`${item.method} ${item.path}`)}</span><b>${Number(item.duration_ms).toFixed(1)} ms</b><small>${escapeHtml(new Date(item.timestamp).toLocaleTimeString())}</small></article>`,
          )
          .join('')
      : '<p>No slow operations in this sample.</p>';
  } catch (error) {
    summary.textContent = error.message;
    body.innerHTML = '<tr><td colspan="6">Could not load diagnostics.</td></tr>';
  }
}

function setNumericInputValue(selector, value) {
  const input = $(selector);
  const numeric = Number(value);
  if (!input || value == null || value === '' || !Number.isFinite(numeric)) return;
  const normalized = String(Math.round((numeric + Number.EPSILON) * 1_000_000) / 1_000_000);
  input.value = normalized;
  input.defaultValue = normalized;
  input.setAttribute('value', normalized);
  input.dataset.lastValidValue = normalized;
}

function settingNumber(selector, key) {
  const input = $(selector);
  const entered = input?.value?.trim();
  const numeric = entered === '' ? Number.NaN : Number(entered);
  if (Number.isFinite(numeric)) return numeric;
  return Number(appConfig?.effective?.[key]);
}

function finiteNumericControlValue(input) {
  if (!(input instanceof HTMLInputElement) || input.value.trim() === '') return null;
  const value = Number(input.value);
  return Number.isFinite(value) ? value : null;
}

function applyEffectiveSettings(values) {
  $('#setting-library-path').value = values.music_library_path || '';
  $('#preset').value = values.preset;
  $('#intro-bars').value = 'auto';
  $('#outro-bars').value = 'auto';
  $('#use-stems').checked = values.use_stems;
  $('#intro-bars').options[0].textContent = `Auto (${values.intro_bars} bars default)`;
  $('#outro-bars').options[0].textContent = `Auto (${values.outro_bars} bars default)`;
  $('#batch-intro-quality').value = values.minimum_intro_loop_quality;
  $('#batch-outro-quality').value = values.minimum_outro_loop_quality;
  $('#batch-repetitions').value = values.maximum_repetitions;
  $('#batch-crossfade').value = values.crossfade_ms;
  $('#batch-bits').value = values.pcm_bits;
  $('#batch-preview').value = values.preview_seconds;
  $('#batch-auto-bars').checked = values.auto_bars;
  $('#batch-cues').checked = values.export_cues;
  $('#batch-candidate-count').value = values.candidate_count;
  setNumericInputValue('#batch-intro-search', values.intro_search_seconds);
  setNumericInputValue('#batch-outro-search', values.outro_search_seconds);
  setNumericInputValue('#batch-vocal-coverage', values.maximum_vocal_coverage_percent);
  setNumericInputValue('#batch-vocal-risk', values.maximum_vocal_boundary_risk_percent);
  setNumericInputValue('#batch-buildup-risk', values.maximum_buildup_risk_percent);
  setNumericInputValue('#batch-bass-risk', values.maximum_bass_reset_risk_percent);
  setNumericInputValue('#batch-stem-reliability', values.minimum_stem_reliability_percent);
  $('#workspace-default-summary').textContent =
    `${values.minimum_intro_loop_quality}%/${values.minimum_outro_loop_quality}% quality · max ${values.maximum_repetitions} copies · ${values.crossfade_ms} ms fade`;
  $('#setting-preset').value = values.preset;
  $('#setting-intro').value = values.intro_bars;
  $('#setting-outro').value = values.outro_bars;
  $('#setting-stems').checked = values.use_stems;
  $('#setting-auto-bars').checked = values.auto_bars;
  $('#setting-intro-quality').value = values.minimum_intro_loop_quality;
  $('#setting-outro-quality').value = values.minimum_outro_loop_quality;
  $('#setting-bits').value = values.pcm_bits;
  $('#setting-preview').value = values.preview_seconds;
  $('#setting-cues').checked = values.export_cues;
  $('#setting-repetitions').value = values.maximum_repetitions;
  $('#setting-crossfade').value = values.crossfade_ms;
  $('#setting-candidate-count').value = values.candidate_count;
  setNumericInputValue('#setting-intro-search', values.intro_search_seconds);
  setNumericInputValue('#setting-outro-search', values.outro_search_seconds);
  setNumericInputValue('#setting-vocal-coverage', values.maximum_vocal_coverage_percent);
  setNumericInputValue('#setting-vocal-risk', values.maximum_vocal_boundary_risk_percent);
  setNumericInputValue('#setting-buildup-risk', values.maximum_buildup_risk_percent);
  setNumericInputValue('#setting-bass-risk', values.maximum_bass_reset_risk_percent);
  setNumericInputValue('#setting-stem-reliability', values.minimum_stem_reliability_percent);
  $('#settings-form')
    .querySelectorAll('input[type="number"], input[data-numeric-setting]')
    .forEach((input) => {
      if (finiteNumericControlValue(input) != null) {
        input.defaultValue = input.value;
        input.setAttribute('value', input.value);
        input.dataset.lastValidValue = input.value;
      }
    });
  $('#setting-page-size').value = localStorage.getItem('music-files-page-size') || '50';
  $('#setting-key-display').value = libraryKeyMode();
}

const frontendServices = composeFrontendServices(api);
const importIssuesFeature = createImportIssuesFeature({ services: frontendServices, escapeHtml });
const { load: loadImportFailures } = importIssuesFeature;
createAuthorizedImportFeature({
  services: frontendServices,
  importApi: importWorkspaceApi,
  Queue: AuthorizedImportQueue,
  clock,
  loadJobs,
  stopTask: stopBackgroundTask,
  escapeHtml,
}).bind();
createPlaylistImportFeature({
  services: frontendServices,
  importApi: importWorkspaceApi,
  runTask: runBackgroundTask,
  clock,
  escapeHtml,
  loadImportFailures,
}).bind();

const musicFilesFeature = createMusicFilesFeature({
  services: frontendServices,
  appConfig,
  downloadedUiState,
  downloadedSelection,
  downloadedRequestState,
  getLoadedAt: () => downloadedLoadedAt,
  setLoadedAt: (value) => {
    downloadedLoadedAt = value;
  },
  invalidateLibrary: () => {
    libraryLoadedAt = 0;
  },
  VIEW_CACHE_MS,
  escapeHtml,
  genreFolderTree,
  detailedGenreSummary,
  compactAudioMarkup,
  genreEditorMarkup,
  metadataEditorMarkup,
  option,
  syncControlUnlessEditing,
  refreshSearchableSelects,
  runBackgroundTask,
  loadLibrary: (...args) => loadLibrary(...args),
  renderTrackPagination,
  captureTextFilter,
  bindGenreEditor,
  startKeyAnalysis,
  showView,
  loadJobs,
  closeDownloadedInspector,
  clock,
  stopNativeAudio,
  bindCompactAudio,
  bindLazyAudio,
  compactAudioIsWithin,
  stopCompactAudio,
  collapsedGenreFolders,
  bindGenreFolderState,
});
const { loadDownloadedLibrary } = musicFilesFeature;
const localAudioImportFeature = createLocalAudioImportFeature({
  services: frontendServices,
  importApi: importWorkspaceApi,
  runTask: runBackgroundTask,
  stopTask: stopBackgroundTask,
  escapeHtml,
  showMusicFiles: () => showView('downloads-view'),
  clearWorkspaceFiles: () => {
    stagedFiles = [];
    describeFiles();
  },
  loadMusicFiles: loadDownloadedLibrary,
});
localAudioImportFeature.bind();
const djLibraryFeature = createDjLibraryFeature({
  services: frontendServices,
  getAppConfig: () => appConfig,
  libraryUiState,
  libraryRequestState,
  getLoadedAt: () => libraryLoadedAt,
  setLoadedAt: (value) => {
    libraryLoadedAt = value;
  },
  invalidateMusicFiles: () => {
    downloadedLoadedAt = 0;
  },
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
  loadReports: (...args) => loadReports(...args),
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
  loadAnalysis: (...args) => loadAnalysis(...args),
  jobAction: (...args) => jobAction(...args),
  jobElement: (...args) => jobElement(...args),
});
const { loadLibrary, renderLibraryIntelligence } = djLibraryFeature;
const reportingFeature = createReportingFeature({
  services: frontendServices,
  loadJobs,
  renderLibraryIntelligence,
  startKeyAnalysis,
});
const { loadAnalysis, loadReports } = reportingFeature;
const processingJobDetail = createProcessingJobDetail({
  WaveSurfer,
  RegionsPlugin,
  TimelinePlugin,
  HoverPlugin,
  clock,
  escapeHtml,
});
const { hydrate: hydrateCompletedJob, renderArrangementTimeline } = processingJobDetail;
processingWorkspaceView = createProcessingWorkspaceView({
  services: frontendServices,
  template,
  jobsRoot,
  action: jobAction,
  remove: removeJob,
  move: moveJob,
  hydrate: hydrateCompletedJob,
  showView,
  loadLibrary,
});
processingWorkspaceController = createProcessingWorkspaceController({
  workspaceApi: processingWorkspaceApi,
  render: processingWorkspaceView.render,
  onAnalysisRefresh: (jobs) => loadAnalysis(jobs),
  clock: window,
  documentRef: document,
});
processingWorkspaceView.bindFilters(processingWorkspaceController);
candidateReviewFeature = createCandidateReviewFeature({
  services: frontendServices,
  processingWorkspaceApi,
  annotateJobs: annotateProcessingJobs,
  decodedAudio,
  renderArrangementTimeline,
  WaveSurfer,
  RegionsPlugin,
  TimelinePlugin,
  jobAction,
  loadJobs,
  showView,
});
const setBuilderFeature = createSetBuilderFeature({
  services: frontendServices,
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
});
const { loadSetBuilder } = setBuilderFeature;

function showView(id) {
  navigation.show(id);
}
async function loadView(id) {
  window.scrollTo({ top: 0, behavior: 'smooth' });
  if (!compactAudioIsWithin(`#${id}`)) stopCompactAudio();
  document.querySelectorAll('audio').forEach((audio) => {
    if (!audio.closest(`#${id}`) && !audio.paused) audio.pause();
  });
  if (id === 'reports-view') await loadReports();
  if (id === 'review-view') await loadReviews();
  if (id === 'downloads-view' && Date.now() - downloadedLoadedAt > VIEW_CACHE_MS) await loadDownloadedLibrary();
  if (id === 'library-view' && Date.now() - libraryLoadedAt > VIEW_CACHE_MS) await loadLibrary();
  if (id === 'set-builder-view') await loadSetBuilder();
  if (id === 'import-view') await loadImportFailures();
  if (id === 'settings-view') {
    await Promise.all([
      loadPresets(),
      loadLibraryHealth(),
      loadPerformanceDiagnostics(),
      loadStorageManager(),
      loadBackups(),
    ]);
  }
}
$('#refresh-performance-diagnostics')?.addEventListener('click', loadPerformanceDiagnostics);

// Native media elements do not coordinate playback by themselves. Keep the app
// DJ-friendly by allowing only one audition, source, or edit to play at a time.
document.addEventListener(
  'play',
  (event) => {
    if (!(event.target instanceof HTMLMediaElement)) return;
    stopCompactAudio();
    stopNativeAudio(event.target);
  },
  true,
);

function describeFiles() {
  const count = stagedFiles.length;
  $('#file-count').textContent = count ? `${count} track${count === 1 ? '' : 's'} selected` : 'No tracks selected';
  const root = $('#staged-tracks');
  root.hidden = !count;
  root.innerHTML = stagedFiles
    .map(
      (file, index) =>
        `<article><span class="staged-index">${index + 1}</span><div><strong>${escapeHtml(file.name)}</strong><small>${(file.size / 1024 / 1024).toFixed(1)} MB</small></div><button type="button" data-index="${index}" aria-label="Remove ${escapeHtml(file.name)}">×</button></article>`,
    )
    .join('');
  root.querySelectorAll('button').forEach(
    (button) =>
      (button.onclick = () => {
        stagedFiles.splice(Number(button.dataset.index), 1);
        describeFiles();
      }),
  );
}
function stageFiles(files) {
  const supported = new Set(['mp3', 'm4a', 'aac', 'ogg', 'opus', 'wav', 'flac', 'aif', 'aiff']);
  const rejected = [];
  let added = 0;
  [...files].forEach((file) => {
    const extension = file.name.split('.').pop().toLowerCase();
    const identity = `${file.name.toLowerCase()}:${file.size}:${file.lastModified}`;
    if (!supported.has(extension)) {
      rejected.push(file.name);
      return;
    }
    if (stagedFiles.some((item) => `${item.name.toLowerCase()}:${item.size}:${item.lastModified}` === identity)) return;
    stagedFiles.push(file);
    added++;
  });
  describeFiles();
  if (rejected.length) $('#upload-message').textContent = `Skipped unsupported files: ${rejected.join(', ')}`;
  else if (added) $('#upload-message').textContent = `${added} track${added === 1 ? '' : 's'} added to this batch.`;
}
fileInput.addEventListener('change', () => {
  stageFiles(fileInput.files);
  fileInput.value = '';
});
['dragenter', 'dragover'].forEach((event) =>
  dropZone.addEventListener(event, (e) => {
    e.preventDefault();
    dropZone.classList.add('dragging');
  }),
);
['dragleave', 'drop'].forEach((event) =>
  dropZone.addEventListener(event, (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragging');
  }),
);
dropZone.addEventListener('drop', (e) => stageFiles(e.dataTransfer.files));

function setWorkspaceMode(mode) {
  workspaceMode = mode;
  $$('.workspace-action').forEach((button) => {
    const active = button.dataset.mode === mode;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
  $$('.extension-settings').forEach((element) => {
    element.hidden = mode === 'analyze' || mode === 'import';
  });
  $('.analysis-submit').hidden = mode !== 'analyze';
  $('.workspace-import-settings').hidden = mode !== 'import';
  $('#review-candidates').checked = mode === 'review';
  $('#submit').textContent = mode === 'review' ? 'Generate candidates' : 'Create edit';
  $('#workspace-mode-label').textContent =
    mode === 'analyze' ? 'ANALYZE FOR LIBRARY' : mode === 'import' ? 'CONVERT AND ORGANIZE' : 'CREATE EXTENDED EDIT';
  $('#upload-message').textContent =
    mode === 'analyze'
      ? 'Analysis preserves the original audio and adds the track to Library.'
      : mode === 'import'
        ? 'Files will be converted to WAV, classified, and added to Music Files without analysis.'
        : mode === 'review'
          ? 'The job will pause after analysis so you can choose or build candidates.'
          : 'Automatic ranking will create the best available extended edit.';
}
$$('.workspace-action').forEach((button) => (button.onclick = () => setWorkspaceMode(button.dataset.mode)));
$('#review-candidates').addEventListener('change', (event) => {
  $('#submit').textContent = event.target.checked ? 'Generate candidates' : 'Create edit';
  $('#upload-message').textContent = event.target.checked
    ? 'The job will pause after analysis so you can choose or build candidates.'
    : 'Automatic ranking will create the best available extended edit.';
});
$('#choose-downloads').onclick = () => showView('downloads-view');
setWorkspaceMode('analyze');

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!stagedFiles.length) {
    $('#upload-message').textContent = 'Choose at least one track.';
    return;
  }
  if (workspaceMode === 'import') {
    await localAudioImportFeature.startWorkspace(stagedFiles, $('#workspace-import-playlist').value);
    return;
  }
  const data = new FormData();
  stagedFiles.forEach((file) => data.append('files', file));
  data.append('preset', $('#preset').value);
  data.append('intro_bars', $('#intro-bars').value);
  data.append('outro_bars', $('#outro-bars').value);
  data.append('use_stems', $('#use-stems').checked ? 'true' : 'false');
  data.append('review_candidates', $('#review-candidates').checked ? 'true' : 'false');
  data.append('analysis_only', workspaceMode === 'analyze' ? 'true' : 'false');
  data.append('auto_bars', $('#batch-auto-bars').checked ? 'true' : 'false');
  data.append('minimum_intro_loop_quality', $('#batch-intro-quality').value);
  data.append('minimum_outro_loop_quality', $('#batch-outro-quality').value);
  data.append('maximum_repetitions', $('#batch-repetitions').value);
  data.append('crossfade_ms', $('#batch-crossfade').value);
  data.append('pcm_bits', $('#batch-bits').value);
  data.append('preview_seconds', $('#batch-preview').value);
  data.append('export_cues', $('#batch-cues').checked ? 'true' : 'false');
  data.append('candidate_count', $('#batch-candidate-count').value);
  data.append('intro_search_seconds', $('#batch-intro-search').value);
  data.append('outro_search_seconds', $('#batch-outro-search').value);
  data.append('maximum_vocal_coverage_percent', $('#batch-vocal-coverage').value);
  data.append('maximum_vocal_boundary_risk_percent', $('#batch-vocal-risk').value);
  data.append('maximum_buildup_risk_percent', $('#batch-buildup-risk').value);
  data.append('maximum_bass_reset_risk_percent', $('#batch-bass-risk').value);
  data.append('minimum_stem_reliability_percent', $('#batch-stem-reliability').value);
  $('#submit').disabled = true;
  $('#upload-message').textContent = 'Copying tracks to the local queue…';
  try {
    const response = await fetch('/api/jobs', { method: 'POST', body: data });
    const payload = await response.json();
    if (!response.ok) throw new Error(apiErrorMessage(payload, 'Upload failed'));
    $('#upload-message').textContent =
      `${payload.job_ids.length} track${payload.job_ids.length === 1 ? '' : 's'} added.`;
    form.reset();
    stagedFiles = [];
    applyEffectiveSettings(appConfig.effective);
    describeFiles();
    await loadJobs();
  } catch (error) {
    $('#upload-message').textContent = error.message;
  } finally {
    $('#submit').disabled = false;
  }
});
document.addEventListener('click', (event) => {
  document.querySelectorAll('.downloaded-actions[open],.library-row-actions[open]').forEach((menu) => {
    if (!menu.contains(event.target)) menu.open = false;
  });
  const inspector = $('#downloaded-inspector');
  if (!inspector.hidden && !inspector.contains(event.target) && !event.target.closest('.inspect-downloaded'))
    closeDownloadedInspector();
});
document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape' || !$('#downloads-view')?.classList.contains('active')) return;
  document.querySelectorAll('.downloaded-actions[open]').forEach((menu) => (menu.open = false));
  closeDownloadedInspector({ restoreFocus: true });
});

$('#restore-batch-defaults').addEventListener('click', () => {
  applyEffectiveSettings(appConfig.effective);
  $('#upload-message').textContent = 'Saved processing defaults restored for this batch.';
});

function jobElement(job) {
  return processingWorkspaceView.jobElement(job);
}

async function jobAction(id, action, body = null) {
  try {
    await processingWorkspaceApi.action(id, action, body || undefined);
    await loadJobs();
    return true;
  } catch (error) {
    alert(error.message || `Could not ${action} job.`);
    return false;
  }
}
async function removeJob(id) {
  if (
    !(await confirmAction('Remove this queue entry? Audio files will remain in output.', {
      title: 'Remove queue entry',
      acceptLabel: 'Remove',
      danger: true,
    }))
  )
    return;
  await processingWorkspaceApi.remove(id);
  await loadJobs();
}
$('#clear-queue').addEventListener('click', async () => {
  if (
    !(await confirmAction(
      'Clear queued and dismissed entries? A track currently processing will continue, and completed audio remains in Library.',
      { title: 'Clear queue history', acceptLabel: 'Clear', danger: true },
    ))
  )
    return;
  const button = $('#clear-queue');
  button.disabled = true;
  button.textContent = 'Clearing…';
  try {
    await processingWorkspaceApi.clear();
    await Promise.all([loadJobs(), loadAnalysis()]);
  } catch (error) {
    alert(error.message);
  } finally {
    button.textContent = 'Clear queue';
  }
});
async function moveJob(id, offset) {
  const jobs = annotateProcessingJobs(await processingWorkspaceApi.list());
  const queued = jobs.filter((job) => job.status === 'queued').sort((a, b) => a.queue_index - b.queue_index);
  const index = queued.findIndex((job) => job.id === id);
  const target = index + offset;
  if (index < 0 || target < 0 || target >= queued.length) return;
  [queued[index], queued[target]] = [queued[target], queued[index]];
  await processingWorkspaceApi.reorder(queued.map((job) => job.id));
  await loadJobs();
}

document.addEventListener('visibilitychange', () => {
  processingWorkspaceController?.refreshWhenVisible();
});
async function loadJobs() {
  return processingWorkspaceController?.load() || [];
}
async function loadReviews() {
  return candidateReviewFeature?.load();
}

function libraryReprocessForm(job, config) {
  const selected = (value, current) => (String(value) === String(current) ? ' selected' : '');
  const presets = appConfig.presets
    .map(
      (value) =>
        `<option value="${value}"${selected(value, job.preset)}>${value === 'auto' ? 'Auto detect' : value}</option>`,
    )
    .join('');
  const bars = (position) => {
    const analysisOnly = Boolean(config.analysis_only);
    const current = analysisOnly ? Number(appConfig.effective[`${position}_bars`]) : Number(job[`${position}_bars`]);
    const automatic = analysisOnly || Boolean(config[`${position}_bars_auto`]);
    return `<option value="auto"${automatic ? ' selected' : ''}>Auto (${current} bars currently)</option>${appConfig.bar_counts.map((value) => `<option value="${value}"${!automatic && current === Number(value) ? ' selected' : ''}>${value === 0 ? 'Preserve original' : `${value} bars`}</option>`).join('')}`;
  };
  const presetRepetitions = appConfig.preset_details?.[job.preset]?.maximum_repetitions;
  const inherited = (key) => config[key] ?? appConfig.effective[key];
  const stableSnapshot = ['minimum_intro_loop_quality', 'candidate_count', 'pcm_bits', 'preview_seconds'].every(
    (key) => key in config,
  );
  return `<form class="library-reprocess-form" hidden>
    <div class="reprocess-heading"><div><strong>Configure the next generation</strong><small>${stableSnapshot ? `Exact settings snapshot from generation ${job._generation}.` : `Generation ${job._generation} predates full snapshots; saved values are preserved and missing values show current defaults.`} The original source remains unchanged.</small></div><button type="button" class="icon-button close-reprocess" aria-label="Close reprocess settings">×</button></div>
    <div class="reprocess-grid">
      <label>Preset<select name="preset">${presets}</select></label>
      <label>Intro length<select name="intro_bars">${bars('intro')}</select></label>
      <label>Outro length<select name="outro_bars">${bars('outro')}</select></label>
      <label>Stem strategy<select name="use_stems"><option value="false"${job.use_stems ? '' : ' selected'}>Full mix</option><option value="true"${job.use_stems ? ' selected' : ''}>Use Demucs</option></select></label>
      <label>Intro quality floor<input name="minimum_intro_loop_quality" type="number" min="0" max="100" value="${config.minimum_intro_loop_quality ?? appConfig.effective.minimum_intro_loop_quality}"><span class="suffix">%</span></label>
      <label>Outro quality floor<input name="minimum_outro_loop_quality" type="number" min="0" max="100" value="${config.minimum_outro_loop_quality ?? appConfig.effective.minimum_outro_loop_quality}"><span class="suffix">%</span></label>
      <label>Maximum copies<input name="maximum_repetitions" type="number" min="1" max="8" value="${config.maximum_repetitions ?? presetRepetitions ?? appConfig.effective.maximum_repetitions}"></label>
      <label>Crossfade floor<input name="crossfade_ms" type="number" min="1" max="100" value="${config.crossfade_ms ?? appConfig.effective.crossfade_ms}"><span class="suffix">ms</span></label>
    </div>
    <details class="reprocess-expert"><summary>Previous expert analysis settings</summary><div class="reprocess-grid">
      <label>Candidate depth<input name="candidate_count" type="number" min="1" max="8" value="${inherited('candidate_count')}"></label>
      <label>Intro search<input name="intro_search_seconds" type="number" min="15" max="600" value="${inherited('intro_search_seconds')}"><span class="suffix">sec</span></label>
      <label>Outro search<input name="outro_search_seconds" type="number" min="15" max="600" value="${inherited('outro_search_seconds')}"><span class="suffix">sec</span></label>
      <label>Max vocal coverage<input name="maximum_vocal_coverage_percent" type="number" min="0" max="100" value="${inherited('maximum_vocal_coverage_percent')}"><span class="suffix">%</span></label>
      <label>Max vocal splice risk<input name="maximum_vocal_boundary_risk_percent" type="number" min="0" max="100" value="${inherited('maximum_vocal_boundary_risk_percent')}"><span class="suffix">%</span></label>
      <label>Max buildup risk<input name="maximum_buildup_risk_percent" type="number" min="0" max="100" value="${inherited('maximum_buildup_risk_percent')}"><span class="suffix">%</span></label>
      <label>Max bass-reset risk<input name="maximum_bass_reset_risk_percent" type="number" min="0" max="100" value="${inherited('maximum_bass_reset_risk_percent')}"><span class="suffix">%</span></label>
      <label>Min stem reliability<input name="minimum_stem_reliability_percent" type="number" min="0" max="100" value="${inherited('minimum_stem_reliability_percent')}"><span class="suffix">%</span></label>
      <label>WAV bit depth<select name="pcm_bits"><option value="24"${Number(inherited('pcm_bits')) === 24 ? ' selected' : ''}>24-bit</option><option value="16"${Number(inherited('pcm_bits')) === 16 ? ' selected' : ''}>16-bit</option></select></label>
      <label>Preview context<input name="preview_seconds" type="number" min="1" max="60" value="${inherited('preview_seconds')}"><span class="suffix">sec</span></label>
      <label>Rekordbox cues<select name="export_cues"><option value="true"${inherited('export_cues') ? ' selected' : ''}>Export cues</option><option value="false"${inherited('export_cues') ? '' : ' selected'}>Do not export</option></select></label>
    </div></details>
    <label class="reprocess-check"><input name="auto_bars" type="checkbox" ${config.auto_bars === false ? '' : 'checked'}> Automatically shorten either side when a shorter edit is safer</label>
    <div class="reprocess-actions"><span class="reprocess-message"></span><button type="button" class="button secondary reprocess-review">Process for review / custom editor</button><button type="submit">Process automatically</button></div>
  </form>`;
}

const settingsFeature = createSettingsFeature({
  services: frontendServices,
  downloadedUiState,
  setAppConfig: (payload) => {
    appConfig.effective = payload.effective;
    appConfig.overrides = payload.overrides;
  },
  applyEffectiveSettings,
  loadConfig,
  loadPresets,
  editPreset,
  getPresetLibrary: () => presetLibrary,
  loadJobs,
  loadAnalysis,
  loadDownloadedLibrary,
  loadLibrary,
  invalidateCatalogs: () => {
    downloadedLoadedAt = 0;
    libraryLoadedAt = 0;
  },
  loadPerformanceDiagnostics,
  escapeHtml,
  reportDate,
  libraryAvailabilityView,
});
const { loadLibraryHealth, loadLibraryStatus, loadRelocationState, loadBackups, loadStorageManager } = settingsFeature;
async function refresh() {
  const jobs = await loadJobs();
  await loadAnalysis(jobs);
}
settingsFeature.initialize(refresh);
