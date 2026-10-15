import WaveSurfer from '/vendor/wavesurfer/wavesurfer.esm.js';
import RegionsPlugin from '/vendor/wavesurfer/plugins/regions.esm.js';
import TimelinePlugin from '/vendor/wavesurfer/plugins/timeline.esm.js';
import HoverPlugin from '/vendor/wavesurfer/plugins/hover.esm.js';
import {AuthorizedImportQueue} from '/assets/import-queue.js?v=20260930-1';
import {createApiClient} from './api-client.js';
import {$, $$, apiErrorMessage, captureTextFilter, clock, composeFrontendServices, confirmAction, descriptorChipsMarkup, descriptorEditorMarkup, escapeHtml, fraction, inferDescriptorEditor, notify, openDescriptorEditorDialog, operationReceiptText, option, pct, renderTrackPagination, reportDate, saveDescriptorEditor, startKeyAnalysis, syncControlUnlessEditing} from './shared-components.js?v=20261013-1';
import {bindCompactAudio, bindLazyAudio, closeDownloadedInspector, compactAudioIsWithin, compactAudioMarkup, stopCompactAudio, stopNativeAudio} from './playback.js';
import {LIBRARY_ROLE_INFO, camelotKey, compatibility, createDjLibraryFeature, createLibraryUiState, effectivePreset, energyBand, formatLibraryKey, harmonicCompatibility, libraryKeyMode, libraryQuery, libraryRoles, normalizedKey, songEnergy, timingProfile, vocalProfile} from './dj-library.js?v=20261013-1';
import {createMusicFilesFeature, createMusicFilesUiState} from './music-files.js?v=20261013-1';
import {createRequestStateController} from './request-state-controller.js';
import {createReportingFeature} from './reporting.js?v=20261013-1';
import {createSetBuilderFeature} from './set-builder.js?v=20261013-2';
import {createSettingsFeature, libraryAvailabilityView} from './settings.js?v=20261013-1';
import {createAuthorizedImportFeature, createImportWorkspaceApi} from './import-workspace.js';
import {createBackgroundTaskController} from './background-task-controller.js';
import {createImportIssuesFeature} from './import-issues.js';
import {createLocalAudioImportFeature} from './local-audio-import.js';
import {createPlaylistImportFeature} from './playlist-import.js';
import {annotateProcessingJobs, createProcessingWorkspaceApi, createProcessingWorkspaceController} from './processing-workspace.js';
import {createProcessingWorkspaceView} from './processing-workspace-view.js';
import {createCandidateReviewFeature} from './candidate-review.js';

const api = createApiClient();
const importWorkspaceApi = createImportWorkspaceApi(api);
const processingWorkspaceApi = createProcessingWorkspaceApi(api);
// Keep legacy call sites non-blocking and visually consistent while workflows migrate
// to structured inline messages and richer recovery actions.
window.alert = message => notify(message, 'danger');
let searchableSelectRefreshQueued = false;
let generatedSelectId = 0;
function refreshSearchableSelects() {
  document.querySelectorAll('select').forEach(select => {
    if (!select.id) select.id = `app-select-${++generatedSelectId}`;
    const id = select.id;
    let search = document.getElementById(`${id}-combobox-search`);
    if (!search) {
      let container = select.closest('label');
      if (!container) {
        container = document.createElement('span');
        container.className = 'select-combobox-shell';
        select.before(container);
        container.append(select);
      }
      container.classList.add('has-searchable-select');
      search = document.createElement('input');
      search.id = `${id}-combobox-search`;
      search.type = 'text';
      search.className = 'select-search-input';
      search.autocomplete = 'off';
      search.spellcheck = false;
      search.placeholder = 'Type to search…';
      search.setAttribute('aria-label', `Search ${select.closest('label')?.childNodes[0]?.textContent?.trim() || 'options'}`);
      search.setAttribute('role', 'combobox');
      search.setAttribute('aria-autocomplete', 'list');
      search.setAttribute('aria-expanded', 'false');
      select.before(search);
      const menu = document.createElement('div');
      menu.id = `${id}-combobox-menu`;
      menu.className = 'select-combobox-menu';
      menu.setAttribute('role', 'listbox');
      menu.hidden = true;
      search.setAttribute('aria-controls', menu.id);
      search.after(menu);
      let activeIndex = -1;
      const selectedLabel = () => {
        const selected = [...select.selectedOptions].filter(option => option.value !== 'all');
        if (!select.multiple || selected.length <= 1) return selected[0]?.textContent || select.selectedOptions[0]?.textContent || '';
        return `${selected.length} genres selected`;
      };
      const closeMenu = () => {
        menu.hidden = true;
        activeIndex = -1;
        search.setAttribute('aria-expanded', 'false');
        search.removeAttribute('aria-activedescendant');
      };
      const chooseOption = option => {
        if (select.multiple) {
          const any = select.querySelector('option[value="all"]');
          if (option.value === 'all') {
            [...select.options].forEach(item => { item.selected = item.value === 'all'; });
          } else {
            if (any) any.selected = false;
            option.selected = !option.selected;
            if (![...select.selectedOptions].some(item => item.value !== 'all') && any) any.selected = true;
          }
        } else select.value = option.value;
        search.value = selectedLabel();
        select.dispatchEvent(new Event('change', {bubbles:true}));
        if (select.multiple) search.value = '';
        closeMenu();
      };
      const renderMenu = () => {
        const entered = search.value.trim();
        const query = entered === selectedLabel() ? '' : entered.toLocaleLowerCase();
        const matches = [...select.options].filter(option => !query || option.textContent.toLocaleLowerCase().includes(query));
        search.classList.toggle('no-results', Boolean(query) && matches.length === 0);
        menu.replaceChildren();
        activeIndex = matches.length ? 0 : -1;
        matches.slice(0, 20).forEach((option, index) => {
          const item = document.createElement('button');
          item.type = 'button';
          item.id = `${id}-combobox-option-${index}`;
          item.className = index === activeIndex ? 'active' : '';
          item.setAttribute('role', 'option');
          item.setAttribute('aria-selected', String(option.value === select.value));
          item.textContent = option.textContent;
          item.addEventListener('mousedown', event => event.preventDefault());
          item.addEventListener('click', () => chooseOption(option));
          menu.append(item);
        });
        const summary = document.createElement('small');
        summary.textContent = matches.length ? `${matches.length} option${matches.length === 1 ? '' : 's'}${matches.length > 20 ? ' · keep typing to narrow the list' : ''}` : 'No matching options';
        menu.append(summary);
        menu.hidden = false;
        search.setAttribute('aria-expanded', 'true');
        if (activeIndex >= 0) search.setAttribute('aria-activedescendant', `${id}-combobox-option-${activeIndex}`);
      };
      const moveActive = direction => {
        const items = [...menu.querySelectorAll('button')];
        if (!items.length) return;
        activeIndex = (activeIndex + direction + items.length) % items.length;
        items.forEach((item,index) => item.classList.toggle('active', index === activeIndex));
        search.setAttribute('aria-activedescendant', items[activeIndex].id);
        items[activeIndex].scrollIntoView({block:'nearest'});
      };
      search.addEventListener('focus', () => { if(select.multiple)search.value='';else search.select();renderMenu(); });
      search.addEventListener('click', () => { if(select.multiple&&search.value===selectedLabel()){search.value='';renderMenu();} });
      search.addEventListener('input', renderMenu);
      search.addEventListener('blur', () => setTimeout(() => { search.value = selectedLabel(); search.classList.remove('no-results'); closeMenu(); }, 120));
      search.addEventListener('keydown', event => {
        if (event.key === 'ArrowDown') { event.preventDefault(); if (menu.hidden) renderMenu(); else moveActive(1); }
        else if (event.key === 'ArrowUp') { event.preventDefault(); if (menu.hidden) renderMenu(); else moveActive(-1); }
        else if (event.key === 'Enter' && !menu.hidden && activeIndex >= 0) { event.preventDefault(); menu.querySelectorAll('button')[activeIndex]?.click(); }
        else if (event.key === 'Escape') { event.preventDefault(); search.value = selectedLabel(); closeMenu(); }
      });
      select.addEventListener('change', () => {
        search.value = selectedLabel();
        search.classList.remove('no-results');
        closeMenu();
      });
      search.value = selectedLabel();
    }
    const shouldShow = select.options.length > 0;
    search.hidden = !shouldShow;
    select.classList.toggle('searchable-native-select', shouldShow);
    if (shouldShow && document.activeElement !== search) search.value = select.selectedOptions[0]?.textContent || '';
    if (!shouldShow) {
      search.value = '';
      search.nextElementSibling.hidden = true;
    }
  });
}
new MutationObserver(() => {
  if (searchableSelectRefreshQueued) return;
  searchableSelectRefreshQueued = true;
  queueMicrotask(() => {
    searchableSelectRefreshQueued = false;
    refreshSearchableSelects();
  });
}).observe(document.documentElement, {childList:true, subtree:true});
refreshSearchableSelects();
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
const downloadedRequestState=createRequestStateController({namespace:'music',state:downloadedUiState,defaults:createMusicFilesUiState(downloadedUiState.pageSize),debounceMs:220,onLoading:loading=>$('#downloads-view')?.classList.toggle('view-refreshing',loading)});
const libraryRequestState=createRequestStateController({namespace:'dj',state:libraryUiState,defaults:createLibraryUiState(libraryUiState.pageSize),debounceMs:240,onLoading:loading=>$('#library-view')?.classList.toggle('view-refreshing',loading)});
const VIEW_CACHE_MS = 30000;
const backgroundTaskController = createBackgroundTaskController({
  loadJson: (url, signal) => api.get(url, {cache:'no-store', signal}, 'Background task status is unavailable.'),
});

$$('.import-method').forEach(method => method.addEventListener('toggle', () => {
  if (!method.open) return;
  $$('.import-method').forEach(other => { if (other !== method) other.open = false; });
}));

const runBackgroundTask = options => backgroundTaskController.run(options);
const stopBackgroundTask = key => backgroundTaskController.stop(key);
const LATIN_GENRE_CATEGORIES = ['Latin / Reggaeton','Latin / Salsa','Latin / Cumbia','Latin / Merengue','Latin / Zapateado','Latin / Corridos','Latin / Regional Mexican','Latin / Bachata','Latin / Dembow','Latin / Latin Pop','Latin / Latin Jazz','Latin / Bolero','Latin / Vallenato','Latin / Brazilian','Latin / Flamenco','Latin / Latin Rock','Latin / Latin Indie','Latin / Latin Ska','Latin / Latin Hip-Hop','Latin / Latin R&B','Latin / Other'];
const ELECTRONIC_GENRE_CATEGORIES = [
  'Electronic / Techno / Techno','Electronic / Techno / Schranz','Electronic / Techno / Hard Techno','Electronic / Techno / Acid Techno','Electronic / Techno / Melodic Techno','Electronic / Techno / Minimal Techno','Electronic / Techno / Industrial Techno','Electronic / Techno / Hypnotic Techno','Electronic / Techno / Peak-Time Techno',
  'Electronic / House / House','Electronic / House / Deep House','Electronic / House / Afro House','Electronic / House / Latin House','Electronic / House / Tech House','Electronic / House / Progressive House','Electronic / House / Melodic House','Electronic / House / Organic House','Electronic / House / Bass House','Electronic / House / Soulful House','Electronic / House / Funky House','Electronic / House / Amapiano',
  'Electronic / Bass / Deep Bass','Electronic / Bass / Future Bass','Electronic / Bass / Dubstep','Electronic / Bass / Moombahton','Electronic / Bass / Phonk','Electronic / Drum & Bass / Drum & Bass','Electronic / Drum & Bass / Liquid','Electronic / Drum & Bass / Jungle','Electronic / Trance / Trance','Electronic / Trance / Psytrance','Electronic / Trance / Hard Trance','Electronic / Garage / Garage','Electronic / Garage / UK Garage','Electronic / Breaks / Breakbeat','Electronic / Breaks / Big Beat','Electronic / Downtempo / Trip Hop','Electronic / Hardcore / Hardcore','Electronic / Hardcore / Gabber','Electronic / Hardcore / Hardstyle','Electronic / General','Electronic / Electronic / Electro',
];
const GENRE_CATEGORIES = [...ELECTRONIC_GENRE_CATEGORIES,'Afro & Amapiano','Hip-Hop & Rap','Hip-Hop & Rap / Crunk','Hip-Hop & Rap / Hyphy','R&B & Soul','Disco & Funk','Rock & Alternative','Pop','Pop / Chanson','Ambient & Chill',...LATIN_GENRE_CATEGORIES,'Other'];
const collapsedGenreFolders = new Set(JSON.parse(localStorage.getItem('dj-collapsed-genre-folders') || '[]'));
function normalizedGenreCategory(value) {
  const name=String(value||'Other').trim();
  return ({techno:'Electronic / Techno / Techno',house:'Electronic / House / House',trance:'Electronic / Trance / Trance','drum & bass':'Electronic / Drum & Bass / Drum & Bass',garage:'Electronic / Garage / Garage',breaks:'Electronic / Breaks / Breakbeat',electronic:'Electronic / General','electronic / electronic / electronic':'Electronic / General'})[name.toLowerCase()] || name;
}

function genreFolderTree(entries, buttonClass) {
  const root = {children:new Map(), count:0, selfCount:0};
  entries.forEach(([name,count]) => {
    let node = root; node.count += Number(count);
    String(name).split(' / ').forEach(part => {
      if (!node.children.has(part)) node.children.set(part,{children:new Map(),count:0,selfCount:0,value:''});
      node=node.children.get(part); node.count+=Number(count);
    });
    node.value=name; node.selfCount+=Number(count);
  });
  const render = (node,path=[],depth=0) => [...node.children.entries()].sort(([a],[b])=>a.localeCompare(b)).map(([label,child]) => {
    const nextPath=[...path,label]; const key=nextPath.join(' / ');
    if (!child.children.size) { const value=buttonClass==='library-side-category'?child.value.toLowerCase():child.value; return `<button type="button" class="${buttonClass}${depth?' nested':''}" data-depth="${depth}" data-value="${escapeHtml(value)}"><span>${escapeHtml(label)}</span><b>${child.count}</b></button>`; }
    const open = collapsedGenreFolders.has(key) ? '' : ' open';
    const parentValue=buttonClass==='library-side-category'?key.toLowerCase():key;
    const general=child.selfCount ? `<button type="button" class="${buttonClass} nested" data-depth="${depth+1}" data-value="${escapeHtml(buttonClass==='library-side-category'?child.value.toLowerCase():child.value)}"><span>General</span><b>${child.selfCount}</b></button>` : '';
    return `<details class="genre-folder-group" data-folder="${escapeHtml(key)}"${open}><summary><button type="button" class="${buttonClass} genre-folder-parent-filter" data-value="${escapeHtml(parentValue)}"><span>${escapeHtml(label)}</span><b>${child.count}</b></button><i aria-hidden="true">›</i></summary><div>${general}${render(child,nextPath,depth+1)}</div></details>`;
  }).join('');
  return render(root);
}

function bindGenreFolderState(scope) {
  scope.querySelectorAll('.genre-folder-parent-filter').forEach(button => button.addEventListener('click', event => { event.preventDefault(); event.stopPropagation(); }));
  scope.querySelectorAll('.genre-folder-group').forEach(folder => folder.addEventListener('toggle', () => {
    if (folder.open) collapsedGenreFolders.delete(folder.dataset.folder); else collapsedGenreFolders.add(folder.dataset.folder);
    localStorage.setItem('dj-collapsed-genre-folders',JSON.stringify([...collapsedGenreFolders]));
  }));
}

function genreEditorMarkup(current, suggested = '', compact = false) {
  const choices = [...new Set([current, suggested, ...GENRE_CATEGORIES].filter(Boolean))].sort();
  return `<form class="inline-genre-editor${compact ? ' compact' : ''}" hidden>
    <div><label>Genre<select class="inline-genre-select">${choices.map(name => `<option value="${escapeHtml(name)}"${name === current ? ' selected' : ''}>${escapeHtml(name)}</option>`).join('')}</select></label>
    <label>Or type a custom genre<input class="inline-genre-custom" maxlength="80" placeholder="Custom genre"></label></div>
    ${suggested && suggested !== current ? `<p class="genre-suggestion">Detected from metadata: <b>${escapeHtml(suggested)}</b> <button type="button" class="use-genre-suggestion">Use detected</button></p>` : ''}
    <p class="genre-folder-preview">Folder: ${escapeHtml(current.replace(' / ', '/'))}/</p>
    <div class="inline-genre-actions"><button type="submit">Save & move</button><button type="button" class="button secondary cancel-genre-edit">Cancel</button></div>
  </form>`;
}

function metadataEditorMarkup(track, position=1, total=1) {
  const current = track.genre_category || 'Other';
  const choices = [...new Set([current,...GENRE_CATEGORIES].filter(Boolean))].sort();
  const playlist = (track.playlists || [])[0] || 'Imported Singles';
  return `<form class="track-metadata-editor" hidden>
    <header><div><strong>Edit track metadata</strong><span>Updates the WAV, folder, Music Files, and linked Library entry.</span></div><div class="metadata-review-position"><span>${position} of ${total}</span><button type="button" class="button secondary close-metadata-editor" aria-label="Close metadata editor">×</button></div></header>
    <div class="metadata-fields"><label>Title<input name="title" maxlength="300" required value="${escapeHtml(track.title || '')}"></label><label>Artist<input name="artist" maxlength="300" value="${escapeHtml(track.artist || '')}"></label><label>Genre<select name="genre_category">${choices.map(name=>`<option value="${escapeHtml(name)}"${name===current?' selected':''}>${escapeHtml(name)}</option>`).join('')}</select></label><label>Detailed genre tags<input name="genre" maxlength="500" value="${escapeHtml(track.genre || '')}" placeholder="e.g. salsa, merengue"></label><label>Album / source playlist<input name="playlist_name" maxlength="180" required value="${escapeHtml(playlist)}"></label><label>Artwork image URL<input name="artwork_url" type="url" maxlength="1000" value="${escapeHtml(track.artwork_url || '')}" placeholder="Direct Spotify or YouTube cover image URL"></label><label class="metadata-rename"><input name="rename_file" type="checkbox"> Rename WAV to Artist - Title</label></div>
    <p class="metadata-message"></p><div class="metadata-actions"><div class="metadata-navigation"><button type="button" class="button secondary metadata-previous">← Previous</button><button type="button" class="button secondary metadata-next">Next →</button></div><div class="metadata-save-actions"><button type="submit" class="button secondary">Save</button><button type="submit" data-action="next">Save & next →</button></div></div>
  </form>`;
}

function detailedGenreSummary(rawGenres) {
  const tags=[...new Set(String(rawGenres||'').split(',').map(tag=>tag.trim()).filter(Boolean))];
  if(!tags.length)return {label:'No detailed genre',title:'No detailed genre metadata',empty:true};
  const visible=tags.slice(0,2);
  return {label:`${visible.join(' · ')}${tags.length>2?` +${tags.length-2}`:''}`,title:tags.join(', '),empty:false};
}

function bindGenreEditor(editor, trackIds, afterSave) {
  const select = editor.querySelector('.inline-genre-select');
  const custom = editor.querySelector('.inline-genre-custom');
  const preview = editor.querySelector('.genre-folder-preview');
  const value = () => custom.value.trim() || select.value;
  const sync = () => { preview.textContent = `Folder: ${value().replace(' / ', '/')}/`; };
  select.onchange = () => { custom.value = ''; sync(); };
  custom.oninput = sync;
  editor.querySelector('.use-genre-suggestion')?.addEventListener('click', event => { select.value = event.currentTarget.closest('.genre-suggestion').querySelector('b').textContent; custom.value = ''; sync(); });
  editor.querySelector('.cancel-genre-edit').onclick = () => { editor.hidden = true; };
  editor.onsubmit = async event => {
    event.preventDefault();
    const genre = value(); if (!genre || !trackIds().length) return;
    const save = editor.querySelector('[type="submit"]'); save.disabled = true; save.textContent = 'Moving…';
    try {
      const response = await fetch('/api/downloaded-library/genre', {method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_ids:trackIds(),genre_category:genre})});
      const payload = await response.json(); if (!response.ok) throw new Error(apiErrorMessage(payload, 'Could not change genre.'));
      notify(operationReceiptText(payload.receipt), payload.receipt?.failures?.length ? 'danger' : 'success', {timeout:9000});
      await afterSave(payload);
    } catch (error) { alert(error.message); save.disabled = false; save.textContent = 'Save & move'; }
  };
}


async function decodedAudio(url, cache, key) {
  if (!cache[key]) {
    const AudioEngine = window.AudioContext || window.webkitAudioContext;
    cache.context ||= new AudioEngine();
    await cache.context.resume();
    cache[key] = fetch(url).then(async response => {
      if (!response.ok) throw new Error('Audio unavailable');
      return cache.context.decodeAudioData(await response.arrayBuffer());
    });
  }
  return cache[key];
}


async function loadConfig() {
  const config = await fetch('/api/config').then(r => r.json());
  appConfig = config;
  ['preset', 'setting-preset'].forEach(id => {
    const select = $('#' + id); select.replaceChildren();
    config.presets.forEach(value => select.append(option(value, value === 'auto' ? 'Auto detect' : value)));
  });
  ['intro-bars', 'outro-bars'].forEach((id) => {
    const select = $('#' + id);
    select.replaceChildren();
    select.append(option('auto', 'Auto'));
    config.bar_counts.forEach(value => select.append(option(value, value === 0 ? 'None' : `${value} bars`)));
  });
  [['setting-intro', 'intro_bars'], ['setting-outro', 'outro_bars']].forEach(([id]) => {
    const select = $('#' + id); select.replaceChildren();
    config.bar_counts.forEach(value => select.append(option(value, value === 0 ? 'None' : `${value} bars`)));
  });
  applyEffectiveSettings(config.effective);
  refreshSearchableSelects();
  ['preset-intro', 'preset-outro'].forEach(id => {
    const select = $('#' + id); select.replaceChildren(...config.bar_counts.map(value => option(value, value === 0 ? 'None' : `${value} bars`)));
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
  $('#preset-message').textContent = preset ? `${preset.built_in ? 'Built-in' : 'Custom'} preset${preset.modified ? ' · customized' : ''}` : 'Creating a new preset';
  document.querySelectorAll('.preset-item').forEach(item => item.classList.toggle('selected', item.dataset.name === preset?.name));
}

async function loadPresets() {
  const payload = await fetch('/api/presets').then(response => response.json());
  presetLibrary = payload.presets || [];
  $('#preset-list').innerHTML = presetLibrary.map(preset => `<button class="preset-item" type="button" data-name="${escapeHtml(preset.name)}"><strong>${escapeHtml(preset.name)}</strong><span>${preset.intro_bars} intro · ${preset.outro_bars} outro · ${Math.round(preset.minimum_loop_quality)}% floor</span><small>${preset.use_stems ? 'Demucs' : 'Full mix'} · max ${preset.maximum_repetitions} copies${preset.modified ? ' · customized' : preset.built_in ? ' · built-in' : ' · custom'}</small></button>`).join('') || '<p class="empty">No presets available.</p>';
  document.querySelectorAll('.preset-item').forEach(item => item.onclick = () => editPreset(presetLibrary.find(preset => preset.name === item.dataset.name)));
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
    body.innerHTML = payload.operations.length ? payload.operations.map(item => `<tr><td>${escapeHtml(item.operation)}</td><td>${item.count}</td><td>${Number(item.average_ms).toFixed(1)} ms</td><td class="${item.p95_ms >= 250 ? 'diagnostic-warning' : ''}">${Number(item.p95_ms).toFixed(1)} ms</td><td>${Number(item.maximum_ms).toFixed(1)} ms</td><td class="${item.failures ? 'diagnostic-error' : ''}">${item.failures}</td></tr>`).join('') : '<tr><td colspan="6">Use the app, then refresh to see timings.</td></tr>';
    $('#performance-cache-stats').innerHTML = payload.cache.map(item => `<article><strong>${escapeHtml(item.name.replaceAll('_', ' '))}</strong><b>${item.hit_rate == null ? 'No data' : `${Number(item.hit_rate).toFixed(1)}% hit rate`}</b><small>${item.hits} hits · ${item.misses} misses</small></article>`).join('');
    $('#performance-slow-operations').innerHTML = payload.recent_slow_operations.length ? payload.recent_slow_operations.map(item => `<article><span>${escapeHtml(`${item.method} ${item.path}`)}</span><b>${Number(item.duration_ms).toFixed(1)} ms</b><small>${escapeHtml(new Date(item.timestamp).toLocaleTimeString())}</small></article>`).join('') : '<p>No slow operations in this sample.</p>';
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
  $('#preset').value = values.preset; $('#intro-bars').value = 'auto';
  $('#outro-bars').value = 'auto'; $('#use-stems').checked = values.use_stems;
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
  $('#workspace-default-summary').textContent = `${values.minimum_intro_loop_quality}%/${values.minimum_outro_loop_quality}% quality · max ${values.maximum_repetitions} copies · ${values.crossfade_ms} ms fade`;
  $('#setting-preset').value = values.preset; $('#setting-intro').value = values.intro_bars;
  $('#setting-outro').value = values.outro_bars; $('#setting-stems').checked = values.use_stems;
  $('#setting-auto-bars').checked = values.auto_bars;
  $('#setting-intro-quality').value = values.minimum_intro_loop_quality;
  $('#setting-outro-quality').value = values.minimum_outro_loop_quality;
  $('#setting-bits').value = values.pcm_bits; $('#setting-preview').value = values.preview_seconds;
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
  $('#settings-form').querySelectorAll('input[type="number"], input[data-numeric-setting]').forEach(input => {
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
const importIssuesFeature = createImportIssuesFeature({services: frontendServices, escapeHtml});
const {load: loadImportFailures} = importIssuesFeature;
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
  services: frontendServices, appConfig, downloadedUiState, downloadedSelection, downloadedRequestState,
  getLoadedAt: () => downloadedLoadedAt,
  setLoadedAt: value => { downloadedLoadedAt=value; },
  invalidateLibrary: () => { libraryLoadedAt=0; }, VIEW_CACHE_MS,
  escapeHtml, genreFolderTree, detailedGenreSummary,
  compactAudioMarkup, genreEditorMarkup, metadataEditorMarkup, option,
  syncControlUnlessEditing, refreshSearchableSelects, runBackgroundTask,
  loadLibrary: (...args) => loadLibrary(...args), renderTrackPagination, captureTextFilter,
  bindGenreEditor, startKeyAnalysis,
  showView, loadJobs, closeDownloadedInspector, clock, stopNativeAudio, bindCompactAudio, bindLazyAudio,
  compactAudioIsWithin, stopCompactAudio, collapsedGenreFolders, bindGenreFolderState,
});
const {loadDownloadedLibrary} = musicFilesFeature;
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
  services: frontendServices, getAppConfig: () => appConfig, libraryUiState, libraryRequestState,
  getLoadedAt: () => libraryLoadedAt, setLoadedAt: value => { libraryLoadedAt=value; },
  invalidateMusicFiles: () => { downloadedLoadedAt=0; }, VIEW_CACHE_MS,
  escapeHtml, genreFolderTree, bindGenreFolderState, option, refreshSearchableSelects,
  compactAudioMarkup, genreEditorMarkup, bindGenreEditor, bindCompactAudio,
  renderTrackPagination, clock, pct, loadJobs,
  loadDownloadedLibrary, loadReports: (...args) => loadReports(...args), showView,
  startKeyAnalysis,
  compactAudioIsWithin, stopCompactAudio, normalizedGenreCategory,
  ELECTRONIC_GENRE_CATEGORIES, LATIN_GENRE_CATEGORIES, libraryReprocessForm, reportDate,
  bindLazyAudio,
  syncControlUnlessEditing, captureTextFilter,
  loadAnalysis: (...args) => loadAnalysis(...args),
  jobAction: (...args) => jobAction(...args),
  jobElement: (...args) => jobElement(...args),
});
const {loadLibrary, renderLibraryIntelligence} = djLibraryFeature;
const reportingFeature = createReportingFeature({
  services: frontendServices, loadJobs, renderLibraryIntelligence, startKeyAnalysis,
});
const {loadAnalysis, loadReports} = reportingFeature;
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
  onAnalysisRefresh: jobs => loadAnalysis(jobs),
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
  services: frontendServices, option, escapeHtml, clock, decodedAudio, WaveSurfer,
  compatibility, harmonicCompatibility, camelotKey, formatLibraryKey,
  energyBand, songEnergy, LIBRARY_ROLE_INFO,
  libraryRoles, timingProfile, vocalProfile, bindCompactAudio, compactAudioMarkup,
  stopNativeAudio, stopCompactAudio,
});
const {loadSetBuilder} = setBuilderFeature;

function showView(id) {
  if (!compactAudioIsWithin(`#${id}`)) stopCompactAudio();
  document.querySelectorAll('audio').forEach(audio => {
    if (!audio.closest(`#${id}`) && !audio.paused) audio.pause();
  });
  document.querySelectorAll('.view').forEach(view => view.classList.toggle('active', view.id === id));
  document.querySelectorAll('.nav-button').forEach(button => button.classList.toggle('active', button.dataset.view === id));
  if (id === 'reports-view') loadReports();
  if (id === 'review-view') loadReviews();
  if (id === 'downloads-view' && Date.now() - downloadedLoadedAt > VIEW_CACHE_MS) loadDownloadedLibrary();
  if (id === 'library-view' && Date.now() - libraryLoadedAt > VIEW_CACHE_MS) loadLibrary();
  if (id === 'set-builder-view') loadSetBuilder();
  if (id === 'import-view') loadImportFailures();
  if (id === 'settings-view') { loadPresets(); loadLibraryHealth(); loadPerformanceDiagnostics(); loadStorageManager(); loadBackups(); }
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
document.querySelectorAll('[data-view]').forEach(control => control.addEventListener('click', () => showView(control.dataset.view)));
$('#refresh-performance-diagnostics')?.addEventListener('click', loadPerformanceDiagnostics);

// Native media elements do not coordinate playback by themselves. Keep the app
// DJ-friendly by allowing only one audition, source, or edit to play at a time.
document.addEventListener('play', event => {
  if (!(event.target instanceof HTMLMediaElement)) return;
  stopCompactAudio();
  stopNativeAudio(event.target);
}, true);

function describeFiles() {
  const count = stagedFiles.length;
  $('#file-count').textContent = count ? `${count} track${count === 1 ? '' : 's'} selected` : 'No tracks selected';
  const root = $('#staged-tracks'); root.hidden = !count;
  root.innerHTML = stagedFiles.map((file, index) => `<article><span class="staged-index">${index + 1}</span><div><strong>${escapeHtml(file.name)}</strong><small>${(file.size / 1024 / 1024).toFixed(1)} MB</small></div><button type="button" data-index="${index}" aria-label="Remove ${escapeHtml(file.name)}">×</button></article>`).join('');
  root.querySelectorAll('button').forEach(button => button.onclick = () => {
    stagedFiles.splice(Number(button.dataset.index), 1); describeFiles();
  });
}
function stageFiles(files) {
  const supported = new Set(['mp3','m4a','aac','ogg','opus','wav','flac','aif','aiff']);
  const rejected = []; let added = 0;
  [...files].forEach(file => {
    const extension = file.name.split('.').pop().toLowerCase();
    const identity = `${file.name.toLowerCase()}:${file.size}:${file.lastModified}`;
    if (!supported.has(extension)) { rejected.push(file.name); return; }
    if (stagedFiles.some(item => `${item.name.toLowerCase()}:${item.size}:${item.lastModified}` === identity)) return;
    stagedFiles.push(file); added++;
  });
  describeFiles();
  if (rejected.length) $('#upload-message').textContent = `Skipped unsupported files: ${rejected.join(', ')}`;
  else if (added) $('#upload-message').textContent = `${added} track${added === 1 ? '' : 's'} added to this batch.`;
}
fileInput.addEventListener('change', () => { stageFiles(fileInput.files); fileInput.value = ''; });
['dragenter', 'dragover'].forEach(event => dropZone.addEventListener(event, e => { e.preventDefault(); dropZone.classList.add('dragging'); }));
['dragleave', 'drop'].forEach(event => dropZone.addEventListener(event, e => { e.preventDefault(); dropZone.classList.remove('dragging'); }));
dropZone.addEventListener('drop', e => stageFiles(e.dataTransfer.files));

function setWorkspaceMode(mode) {
  workspaceMode = mode;
  $$('.workspace-action').forEach(button => {
    const active = button.dataset.mode === mode;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
  $$('.extension-settings').forEach(element => { element.hidden = mode === 'analyze' || mode === 'import'; });
  $('.analysis-submit').hidden = mode !== 'analyze';
  $('.workspace-import-settings').hidden = mode !== 'import';
  $('#review-candidates').checked = mode === 'review';
  $('#submit').textContent = mode === 'review' ? 'Generate candidates' : 'Create edit';
  $('#workspace-mode-label').textContent = mode === 'analyze' ? 'ANALYZE FOR LIBRARY' : mode === 'import' ? 'CONVERT AND ORGANIZE' : 'CREATE EXTENDED EDIT';
  $('#upload-message').textContent = mode === 'analyze'
    ? 'Analysis preserves the original audio and adds the track to Library.'
    : mode === 'import'
      ? 'Files will be converted to WAV, classified, and added to Music Files without analysis.'
    : mode === 'review'
      ? 'The job will pause after analysis so you can choose or build candidates.'
      : 'Automatic ranking will create the best available extended edit.';
}
$$('.workspace-action').forEach(button => button.onclick = () => setWorkspaceMode(button.dataset.mode));
$('#review-candidates').addEventListener('change', event => {
  $('#submit').textContent = event.target.checked ? 'Generate candidates' : 'Create edit';
  $('#upload-message').textContent = event.target.checked
    ? 'The job will pause after analysis so you can choose or build candidates.'
    : 'Automatic ranking will create the best available extended edit.';
});
$('#choose-downloads').onclick = () => showView('downloads-view');
setWorkspaceMode('analyze');

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!stagedFiles.length) { $('#upload-message').textContent = 'Choose at least one track.'; return; }
  if (workspaceMode === 'import') {
    await localAudioImportFeature.startWorkspace(stagedFiles, $('#workspace-import-playlist').value);
    return;
  }
  const data = new FormData();
  stagedFiles.forEach(file => data.append('files', file));
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
  $('#submit').disabled = true; $('#upload-message').textContent = 'Copying tracks to the local queue…';
  try {
    const response = await fetch('/api/jobs', { method: 'POST', body: data });
    const payload = await response.json();
    if (!response.ok) throw new Error(apiErrorMessage(payload, 'Upload failed'));
    $('#upload-message').textContent = `${payload.job_ids.length} track${payload.job_ids.length === 1 ? '' : 's'} added.`;
    form.reset(); stagedFiles = []; applyEffectiveSettings(appConfig.effective); describeFiles(); await loadJobs();
  } catch (error) { $('#upload-message').textContent = error.message; }
  finally { $('#submit').disabled = false; }
});
document.addEventListener('click', event => {
  document.querySelectorAll('.downloaded-actions[open],.library-row-actions[open]').forEach(menu => {
    if (!menu.contains(event.target)) menu.open=false;
  });
  const inspector=$('#downloaded-inspector');
  if (!inspector.hidden && !inspector.contains(event.target) && !event.target.closest('.inspect-downloaded')) closeDownloadedInspector();
});
document.addEventListener('keydown', event => {
  if(event.key!=='Escape'||!$('#downloads-view')?.classList.contains('active'))return;
  document.querySelectorAll('.downloaded-actions[open]').forEach(menu=>menu.open=false);
  closeDownloadedInspector({restoreFocus:true});
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
async function removeJob(id) { if (!await confirmAction('Remove this queue entry? Audio files will remain in output.', {title:'Remove queue entry', acceptLabel:'Remove', danger:true})) return; await processingWorkspaceApi.remove(id); await loadJobs(); }
$('#clear-queue').addEventListener('click', async () => {
  if (!await confirmAction('Clear queued and dismissed entries? A track currently processing will continue, and completed audio remains in Library.', {title:'Clear queue history', acceptLabel:'Clear', danger:true})) return;
  const button = $('#clear-queue'); button.disabled = true; button.textContent = 'Clearing…';
  try {
    await processingWorkspaceApi.clear();
    await Promise.all([loadJobs(), loadAnalysis()]);
  } catch (error) { alert(error.message); }
  finally { button.textContent = 'Clear queue'; }
});
async function moveJob(id, offset) {
  const jobs = annotateProcessingJobs(await processingWorkspaceApi.list());
  const queued = jobs.filter(job => job.status === 'queued').sort((a,b) => a.queue_index - b.queue_index);
  const index = queued.findIndex(job => job.id === id); const target = index + offset;
  if (index < 0 || target < 0 || target >= queued.length) return;
  [queued[index], queued[target]] = [queued[target], queued[index]];
  await processingWorkspaceApi.reorder(queued.map(job => job.id));
  await loadJobs();
}

async function hydrateCompletedJob(node, job) {
  let jobConfig = {}; try { jobConfig = JSON.parse(job.config_json || '{}'); } catch (_) { jobConfig = {}; }
  const hasExtendedAudio = !jobConfig.analysis_only && Boolean(job.extended_path);
  const [sourceWave, extendedWave, cues, override] = await Promise.all([
    fetch(`/api/jobs/${job.id}/waveform/wav`).then(r => r.ok ? r.json() : null),
    hasExtendedAudio ? fetch(`/api/jobs/${job.id}/waveform/extended`).then(r => r.ok ? r.json() : null) : Promise.resolve(null),
    fetch(`/api/jobs/${job.id}/cues`).then(r => r.json()),
    fetch(`/api/overrides/${encodeURIComponent(job.source_name)}`).then(r => r.json()),
  ]);
  if (!node.isConnected) return;
  const source = node.querySelector('.source-player audio');
  const extended = node.querySelector('.extended-player audio');
  const sourceSurface = sourceWave ? createWaveform(
    node.querySelector('.waveform-source'), node.querySelector('.timeline-source'),
    node.querySelector('.arrangement-source'), sourceWave, [], source,
  ) : null;
  const extendedSurface = extendedWave ? createWaveform(
    node.querySelector('.waveform-extended'), node.querySelector('.timeline-extended'),
    node.querySelector('.arrangement-extended'), extendedWave, cues.cues || [], extended,
  ) : null;
  let activeSurface = extendedSurface || sourceSurface;
  renderCues(node.querySelector('.cue-editor'), job.id, cues.cues || []);
  const form = node.querySelector('.override-editor');
  Object.entries(override).forEach(([key, value]) => { form.elements[key].value = value ?? ''; });
  form.addEventListener('submit', async event => {
    event.preventDefault(); const values = {};
    ['intro_before','outro_after','outro_before'].forEach(key => values[key] = form.elements[key].value ? Number(form.elements[key].value) : null);
    const response = await fetch(`/api/overrides/${encodeURIComponent(job.source_name)}`, {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(values)});
    form.querySelector('.override-message').textContent = response.ok ? 'Saved. Reprocess to apply these boundaries.' : (await response.json()).detail;
  });
  const pauseAll = except => [sourceSurface, extendedSurface].forEach(surface => { if (surface && surface !== except) surface.pause(); });
  const playSurface = surface => {
    if (!surface) return;
    pauseAll(surface); activeSurface = surface; surface.play();
  };
  sourceSurface?.on('interaction', () => { pauseAll(sourceSurface); activeSurface = sourceSurface; });
  extendedSurface?.on('interaction', () => { pauseAll(extendedSurface); activeSurface = extendedSurface; });
  node.querySelector('.play-source').onclick = () => playSurface(sourceSurface);
  node.querySelector('.play-extended').onclick = () => playSurface(extendedSurface);
  node.querySelector('.wave-play').onclick = () => activeSurface?.playPause();
  node.querySelector('.sync-audio').onclick = () => {
    const current = activeSurface?.getCurrentTime() || 0;
    [sourceSurface, extendedSurface].forEach(surface => surface?.setTime(Math.min(surface.getDuration(), current)));
  };
  node.querySelector('.wave-zoom').oninput = event => [sourceSurface, extendedSurface].forEach(surface => surface?.zoom(Number(event.target.value)));
  const time = node.querySelector('.wave-time');
  [sourceSurface, extendedSurface].forEach(surface => {
    surface?.on('timeupdate', current => {
      if (surface === activeSurface) time.textContent = `${clock(current)} / ${clock(surface.getDuration())}`;
    });
    surface?.on('play', () => { activeSurface = surface; node.querySelector('.wave-play').textContent = 'Ⅱ Pause'; });
    surface?.on('pause', () => { if (surface === activeSurface) node.querySelector('.wave-play').textContent = '▶ Play'; });
  });
}

function createWaveform(container, timeline, arrangement, wave, cues, media) {
  const regions = RegionsPlugin.create();
  const wavesurfer = WaveSurfer.create({
    container,
    media,
    peaks: [wave.peaks], duration: wave.duration,
    height: 104, waveColor: '#62695a', progressColor: '#d6ff44', cursorColor: '#ffb65c', cursorWidth: 2,
    barWidth: 2, barGap: 1, barRadius: 2, normalize: false, dragToSeek: true,
    autoCenter: true, autoScroll: true, minPxPerSec: 0,
    plugins: [
      regions,
      TimelinePlugin.create({ container: timeline, style:{ color:'#989991', fontSize:'10px' } }),
      HoverPlugin.create({ lineColor:'#ffb65c', labelBackground:'#202320', labelColor:'#d6ff44' }),
    ],
  });
  renderArrangementTimeline(arrangement, wave.timeline, wave.duration, wavesurfer);
  wavesurfer.on('ready', () => {
    cues.forEach(cue => regions.addRegion({
      start: cue.start,
      end: cue.end || Math.min(wave.duration, cue.start + .06),
      content: cue.kind === 'loop' ? cue.name : '',
      color: cue.kind === 'loop' ? 'rgba(214,255,68,.18)' : 'rgba(255,182,92,.24)',
      drag: false, resize: false,
    }));
  });
  return wavesurfer;
}


function renderArrangementTimeline(root, timeline, duration, wavesurfer) {
  const lanes = [
    ['behavior', 'Musical feel'],
    ['arrangement', 'Song section'],
    ['edits', 'Generated'],
  ];
  const colors = {
    'sparse/ambient':'#738c70', 'melodic/harmonic':'#8f78bd', 'rhythm-forward':'#4f9e91',
    'high-energy':'#c98545', 'dynamic/transition':'#b56576', 'vocal-forward':'#a66b8c',
    intro:'#718f72', verse:'#607d8b', buildup:'#b88445', drop:'#c45d43', breakdown:'#766da8',
    chorus:'#a85f73', closing:'#557f79', fade:'#59645f', 'Extended intro':'#b7d93d', 'Extended outro':'#8fb32f',
  };
  const markup = lanes.map(([key, label]) => {
    const items = (timeline?.[key] || []).filter(item => item.end > item.start).map(item => {
      const name = item.style || item.label || item.name || 'section';
      const left = 100 * item.start / duration; const width = 100 * (item.end - item.start) / duration;
      const detail = `${name} · ${clock(item.start)}–${clock(item.end)}${item.confidence == null ? '' : ` · ${Math.round(100*item.confidence)}%`}`;
      return `<button type="button" class="arrangement-segment" style="left:${left}%;width:${Math.max(width,.35)}%;background:${colors[name] || '#657064'}" data-time="${item.start}" title="${escapeHtml(detail)}"><span>${width >= 8 ? escapeHtml(name) : ''}</span></button>`;
    }).join('');
    return items ? `<div class="arrangement-row"><b>${label}</b><div>${items}</div></div>` : '';
  }).join('');
  root.innerHTML = markup || '<p>Section timeline appears after this track is reprocessed.</p>';
  root.querySelectorAll('.arrangement-segment').forEach(segment => segment.onclick = () => wavesurfer.setTime(Number(segment.dataset.time)));
}


function renderCues(root, jobId, cues) {
  const cueName = cue => cue.name === 'First Reliable Downbeat' ? 'Beat Grid Anchor' : cue.name;
  root.innerHTML = `<div class="cue-list">${cues.map((cue,index) => `<label class="cue-chip">${escapeHtml(cueName(cue))} <input data-index="${index}" type="number" min="0" step="0.01" value="${cue.start}"></label>`).join('')}</div><button class="button secondary save-cues">Save cue positions</button><span class="override-message"></span>`;
  root.querySelector('.save-cues').onclick = async () => {
    root.querySelectorAll('input').forEach(input => cues[Number(input.dataset.index)].start = Number(input.value));
    const response = await fetch(`/api/jobs/${jobId}/cues`, {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({cues})});
    root.querySelector('.override-message').textContent = response.ok ? 'Cue sheet and Rekordbox XML updated.' : 'Could not save cues.';
  };
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
  const selected = (value, current) => String(value) === String(current) ? ' selected' : '';
  const presets = appConfig.presets.map(value => `<option value="${value}"${selected(value, job.preset)}>${value === 'auto' ? 'Auto detect' : value}</option>`).join('');
  const bars = position => {
    const analysisOnly = Boolean(config.analysis_only);
    const current = analysisOnly ? Number(appConfig.effective[`${position}_bars`]) : Number(job[`${position}_bars`]);
    const automatic = analysisOnly || Boolean(config[`${position}_bars_auto`]);
    return `<option value="auto"${automatic ? ' selected' : ''}>Auto (${current} bars currently)</option>${appConfig.bar_counts.map(value => `<option value="${value}"${!automatic && current === Number(value) ? ' selected' : ''}>${value === 0 ? 'Preserve original' : `${value} bars`}</option>`).join('')}`;
  };
  const presetRepetitions = appConfig.preset_details?.[job.preset]?.maximum_repetitions;
  const inherited = key => config[key] ?? appConfig.effective[key];
  const stableSnapshot = ['minimum_intro_loop_quality','candidate_count','pcm_bits','preview_seconds'].every(key => key in config);
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
  services: frontendServices, downloadedUiState,
  setAppConfig: payload => { appConfig.effective=payload.effective;appConfig.overrides=payload.overrides; },
  applyEffectiveSettings, loadConfig, loadPresets, editPreset,
  getPresetLibrary: () => presetLibrary,
  loadJobs, loadAnalysis, loadDownloadedLibrary, loadLibrary,
  invalidateCatalogs: () => { downloadedLoadedAt=0;libraryLoadedAt=0; },
  loadPerformanceDiagnostics, escapeHtml, reportDate,
  libraryAvailabilityView,
});
const {loadLibraryHealth, loadLibraryStatus, loadRelocationState, loadBackups, loadStorageManager} = settingsFeature;
async function refresh() { const jobs = await loadJobs(); await loadAnalysis(jobs); }
settingsFeature.initialize(refresh);
