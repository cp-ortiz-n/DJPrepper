import WaveSurfer from '/vendor/wavesurfer/wavesurfer.esm.js';
import RegionsPlugin from '/vendor/wavesurfer/plugins/regions.esm.js';
import TimelinePlugin from '/vendor/wavesurfer/plugins/timeline.esm.js';
import HoverPlugin from '/vendor/wavesurfer/plugins/hover.esm.js';
import {AuthorizedImportQueue} from '/assets/import-queue.js?v=20260930-1';
import {$, $$, apiErrorMessage, captureTextFilter, clock, confirmAction, descriptorChipsMarkup, descriptorEditorMarkup, escapeHtml, fraction, inferDescriptorEditor, notify, openDescriptorEditorDialog, operationReceiptText, option, pct, renderTrackPagination, reportDate, saveDescriptorEditor, startKeyAnalysis, syncControlUnlessEditing} from './shared-components.js?v=20261005-7';
import {bindCompactAudio, bindLazyAudio, closeDownloadedInspector, compactAudioIsWithin, compactAudioMarkup, stopCompactAudio, stopNativeAudio} from './playback.js';
import {LIBRARY_ROLE_INFO, camelotKey, compatibility, createDjLibraryFeature, createLibraryUiState, effectivePreset, energyBand, formatLibraryKey, harmonicCompatibility, libraryKeyMode, libraryQuery, libraryRoles, normalizedKey, songEnergy, timingProfile, vocalProfile} from './dj-library.js?v=20261005-5';
import {createMusicFilesFeature, createMusicFilesUiState} from './music-files.js?v=20261005-15';
import {createRequestStateController} from './request-state-controller.js';
import {createReportingFeature} from './reporting.js?v=20261003-1';
import {createSetBuilderFeature} from './set-builder.js?v=20261005-4';
import {createSettingsFeature, libraryAvailabilityView} from './settings.js?v=20261003-1';

// Keep legacy call sites non-blocking and visually consistent while workflows migrate
// to structured inline messages and richer recovery actions.
window.alert = message => notify(message, 'danger');
let searchableSelectRefreshQueued = false;
let generatedSelectId = 0;
function refreshSearchableSelects() {
  document.querySelectorAll('select').forEach(select => {
    if (!select.id) select.id = `app-select-${++generatedSelectId}`;
    const id = select.id;
    let search = document.getElementById(`${id}-search`);
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
      search.id = `${id}-search`;
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
let workspacePollTimer = null;
let workspacePollInFlight = false;
let workspaceAnalysisRefreshAt = 0;
let jobsLoadPromise = null;
let queueFilter = 'active';
let appConfig = null;
let arrangementPreview = null;
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
const backgroundTasks = new Map();

$$('.import-method').forEach(method => method.addEventListener('toggle', () => {
  if (!method.open) return;
  $$('.import-method').forEach(other => { if (other !== method) other.open = false; });
}));

function stopBackgroundTask(key) {
  const task = backgroundTasks.get(key);
  if (!task) return;
  task.cancelled = true;
  clearTimeout(task.timer);
  task.controller?.abort();
  backgroundTasks.delete(key);
}

function runBackgroundTask({key, url, load=null, interval=1000, active=state => state.status === 'processing', update=()=>{}, complete=()=>{}, fail=()=>{}}) {
  stopBackgroundTask(key);
  const task = {cancelled:false,timer:null,controller:null};
  backgroundTasks.set(key, task);
  const tick = async () => {
    if (task.cancelled) return;
    task.controller = new AbortController();
    try {
      let state;
      if (load) state = await load(task.controller.signal);
      else {
        const response = await fetch(typeof url === 'function' ? url() : url, {cache:'no-store',signal:task.controller.signal});
        state = await response.json();
        if (!response.ok) throw new Error(state.detail || 'Background task status is unavailable.');
      }
      update(state);
      if (task.cancelled) return;
      if (active(state)) task.timer = setTimeout(tick, interval);
      else { backgroundTasks.delete(key); await complete(state); }
    } catch (error) {
      if (error.name === 'AbortError' || task.cancelled) return;
      backgroundTasks.delete(key);
      fail(error);
    }
  };
  tick();
  return () => stopBackgroundTask(key);
}
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
      const payload = await response.json(); if (!response.ok) throw new Error(payload.detail || 'Could not change genre.');
      notify(operationReceiptText(payload.receipt), payload.receipt?.failures?.length ? 'danger' : 'success', {timeout:9000});
      await afterSave(payload);
    } catch (error) { alert(error.message); save.disabled = false; save.textContent = 'Save & move'; }
  };
}

function stopArrangementPreview() {
  if (!arrangementPreview) return;
  arrangementPreview.nodes.forEach(node => { try { node.stop(); } catch (_) { /* already stopped */ } });
  clearTimeout(arrangementPreview.timer);
  cancelAnimationFrame(arrangementPreview.frame);
  if (arrangementPreview.button?.isConnected) arrangementPreview.button.textContent = arrangementPreview.label;
  arrangementPreview = null;
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

function schedulePreviewClip(context, buffer, offset, duration, when, fade = .015) {
  const safeDuration = Math.max(.02, Math.min(duration, buffer.duration - offset));
  const edge = Math.min(fade, safeDuration / 3);
  const node = context.createBufferSource();
  const gain = context.createGain();
  node.buffer = buffer; node.connect(gain).connect(context.destination);
  gain.gain.setValueAtTime(0, when);
  gain.gain.linearRampToValueAtTime(1, when + edge);
  gain.gain.setValueAtTime(1, when + safeDuration - edge);
  gain.gain.linearRampToValueAtTime(0, when + safeDuration);
  node.start(when, Math.max(0, offset), safeDuration);
  return {node, duration:safeDuration};
}

function insertionWaveContent(editor, copies) {
  const wave = editor._insertWaveData?.source;
  if (!wave?.peaks?.length) return `ADDED ×${copies}`;
  const start = Number(editor.querySelector('.custom-start').value);
  const end = Number(editor.querySelector('.custom-end').value);
  const first = Math.max(0, Math.floor(start / wave.duration * wave.peaks.length));
  const last = Math.min(wave.peaks.length, Math.ceil(end / wave.duration * wave.peaks.length));
  const selected = wave.peaks.slice(first, last);
  const points = selected.filter((_, index) => index % Math.max(1, Math.ceil(selected.length / 48)) === 0);
  const copyMarkup = points.map((peak, index) => {
    const height = Math.max(8, Number(peak) * 72);
    const left = (index + .5) * 100 / Math.max(points.length, 1);
    return `<i style="left:${left}%;height:${height}%"></i>`;
  }).join('');
  const element = document.createElement('span');
  element.className = 'inserted-wave-content';
  element.innerHTML = `<em>+ ×${copies}</em><span>${Array.from({length:copies}, (_, index) => `<b data-copy="${index + 1}">${copyMarkup}</b>`).join('')}</span>`;
  return element;
}

function updateInsertionVisualization(editor) {
  const region = editor._insertMarker;
  const duration = editor._insertWaveData?.extended?.duration;
  if (!region || !duration || editor._syncingInsert) return;
  const destination = Math.max(0, Math.min(Number(editor.querySelector('.insert-destination').value) || 0, duration));
  const sourceLength = Math.max(.08, Number(editor.querySelector('.custom-end').value) - Number(editor.querySelector('.custom-start').value));
  const copies = Number(editor.querySelector('.insert-copies').value) || 1;
  const sourceWave = editor._insertWaveData.source;
  const extendedWave = editor._insertWaveData.extended;
  const sourceFirst = Math.max(0, Math.floor(Number(editor.querySelector('.custom-start').value) / sourceWave.duration * sourceWave.peaks.length));
  const sourceLast = Math.min(sourceWave.peaks.length, Math.ceil(Number(editor.querySelector('.custom-end').value) / sourceWave.duration * sourceWave.peaks.length));
  const insertAt = Math.max(0, Math.min(extendedWave.peaks.length, Math.round(destination / duration * extendedWave.peaks.length)));
  const insertedPeaks = Array.from({length:copies}, () => sourceWave.peaks.slice(sourceFirst, sourceLast)).flat();
  const compositePeaks = [
    ...extendedWave.peaks.slice(0, insertAt),
    ...insertedPeaks,
    ...extendedWave.peaks.slice(insertAt),
  ];
  const compositeDuration = duration + sourceLength * copies;
  const applyRegion = () => region.setOptions({
    start:destination,
    end:destination + sourceLength * copies,
    content:insertionWaveContent(editor, copies),
  });
  applyRegion();
  editor._insertSurface?.load(
    '', [Float32Array.from(compositePeaks)], compositeDuration,
  ).then(() => {
    applyRegion();
    editor._insertSurface?.zoom(Number(editor.querySelector('.insert-zoom')?.value) || 0);
    if (Number(editor.querySelector('.insert-zoom')?.value) > 0) editor._insertSurface?.setScrollTime?.(destination);
    const previewTime = editor.querySelector('.insert-preview-time');
    if (previewTime && !arrangementPreview) previewTime.textContent = `00:00 / ${clock(compositeDuration)}`;
  }).catch(() => {
    editor.querySelector('.insert-message').textContent = 'Could not redraw the temporary edited waveform.';
  });
  if (Number(editor.querySelector('.insert-zoom')?.value) > 0) {
    editor._insertSurface?.setScrollTime?.(destination);
  }
  const added = editor.querySelector('.insert-added-time');
  if (added) added.textContent = `${clock(destination)} → ${clock(destination + sourceLength * copies)} · ${(sourceLength * copies).toFixed(1)}s added`;
  scheduleInsertionScore(editor);
}

function scheduleInsertionScore(editor) {
  if (!editor._insertJob || !editor.querySelector('.insert-score')) return;
  clearTimeout(editor._scoreTimer);
  const token = (editor._scoreToken || 0) + 1; editor._scoreToken = token;
  const root = editor.querySelector('.insert-score');
  root.className = 'insert-score score-loading';
  root.innerHTML = '<strong>Checking placement…</strong><span>Comparing bars, chords, energy, bass, rhythm, and vocals.</span>';
  editor._scoreTimer = setTimeout(async () => {
    const payload = {
      source_start:Number(editor.querySelector('.custom-start').value),
      source_end:Number(editor.querySelector('.custom-end').value),
      destination:Number(editor.querySelector('.insert-destination').value),
      copies:Number(editor.querySelector('.insert-copies').value),
    };
    try {
      const response = await fetch(`/api/jobs/${editor._insertJob.id}/transition-score`, {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload),
      });
      const result = await response.json();
      if (token !== editor._scoreToken) return;
      if (!response.ok) throw new Error(result.detail || 'Score unavailable');
      const metrics = [
        ['Grid',result.grid],['Harmony',result.harmony],['Energy',result.energy],
        ['Bass',result.bass],['Rhythm',result.rhythm],['Vocals',result.vocals],
      ].filter(([,value]) => value != null);
      const level = result.score >= 75 ? 'score-good' : result.score >= 60 ? 'score-caution' : 'score-risky';
      root.className = `insert-score ${level}`;
      root.innerHTML = `<div class="score-verdict"><b>${result.score}%</b><span><strong>${escapeHtml(result.verdict)}</strong><small>Custom transition confidence</small></span></div><div class="score-metrics">${metrics.map(([label,value])=>`<span><b>${value}%</b><small>${label}</small></span>`).join('')}</div><ul>${(result.warnings.length ? result.warnings : ['No major transition risks detected']).map(warning=>`<li>${escapeHtml(warning)}</li>`).join('')}</ul>`;
    } catch (error) {
      if (token !== editor._scoreToken) return;
      root.className = 'insert-score score-unavailable';
      root.innerHTML = `<strong>Preflight score unavailable</strong><span>${escapeHtml(error.message)}</span>`;
    }
  }, 300);
}

async function previewArrangementInsertion(editor, job, button) {
  stopArrangementPreview();
  const start = Number(editor.querySelector('.custom-start').value);
  const end = Number(editor.querySelector('.custom-end').value);
  const destination = Number(editor.querySelector('.insert-destination').value);
  const copies = Number(editor.querySelector('.insert-copies').value);
  if (![start,end,destination,copies].every(Number.isFinite) || end <= start) throw new Error('Choose a valid source region first.');
  const cache = editor._previewAudio ||= {};
  const [source, extended] = await Promise.all([
    decodedAudio(`/api/jobs/${job.id}/audio/wav`, cache, 'source'),
    decodedAudio(`/api/jobs/${job.id}/audio/extended`, cache, 'extended'),
  ]);
  if (destination > extended.duration) throw new Error('Choose a destination inside the current extended track.');
  const context = cache.context; const lead = Math.min(4, destination); const tail = 4; const fade = .015;
  const nodes = []; let when = context.currentTime + .04;
  if (lead > .02) {
    const clip = schedulePreviewClip(context, extended, destination - lead, lead, when, fade);
    nodes.push(clip.node); when += clip.duration - fade;
  }
  for (let copy = 0; copy < copies; copy += 1) {
    const clip = schedulePreviewClip(context, source, start, end - start, when, fade);
    nodes.push(clip.node); when += clip.duration - fade;
  }
  const remaining = Math.max(0, extended.duration - destination);
  if (remaining > .02) {
    const clip = schedulePreviewClip(context, extended, destination, Math.min(tail, remaining), when, fade);
    nodes.push(clip.node); when += clip.duration;
  }
  const previewStart = Math.max(0, destination - lead);
  const startedAt = context.currentTime + .04;
  const previewLength = when - startedAt;
  const surface = editor._insertSurface;
  const timeLabel = editor.querySelector('.insert-preview-time');
  editor._previewPlayhead ||= editor._insertRegions?.addRegion({
    start:previewStart, end:previewStart + .04,
    color:'rgba(202,255,52,.95)', drag:false, resize:false,
  });
  const followPlayhead = () => {
    if (!arrangementPreview || arrangementPreview.button !== button) return;
    const elapsed = Math.max(0, context.currentTime - startedAt);
    const position = Math.min(previewStart + elapsed, previewStart + previewLength);
    surface?.setTime(position);
    surface?.setScrollTime?.(position);
    editor._previewPlayhead?.setOptions({start:position,end:position + .04});
    if (timeLabel) timeLabel.textContent = `${clock(position)} / ${clock(surface?.getDuration() || 0)}`;
    arrangementPreview.frame = requestAnimationFrame(followPlayhead);
  };
  const label = button.textContent; button.textContent = '■ Stop placement preview';
  const timer = setTimeout(stopArrangementPreview, Math.max(100, (when - context.currentTime) * 1000));
  arrangementPreview = {nodes,timer,button,label,frame:requestAnimationFrame(followPlayhead)};
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

let currentImportFailures=[];
const importFailureKind=error=>{const value=String(error||'').toLowerCase();if(value.includes('age')||value.includes('sign in'))return ['Age-restricted source','Restricted'];if(value.includes('403')||value.includes('forbidden'))return ['Source blocked the download','Blocked'];if(value.includes('unavailable')||value.includes('removed'))return ['Source is unavailable','Unavailable'];if(value.includes('no reliable')||value.includes('no youtube'))return ['No reliable source match','No match'];return ['Download could not complete','Failed'];};
async function retryImportFailures(ids){
  if(!ids.length)return;const status=$('#import-retry-status');status.hidden=false;status.querySelector('strong').textContent=`Preparing ${ids.length} retr${ids.length===1?'y':'ies'}`;status.querySelector('span').textContent='0%';status.querySelector('progress').value=0;status.querySelector('p').textContent='Searching for a fresh source before downloading again.';
  $$('#import-failure-toolbar button,.retry-import-failure').forEach(button=>button.disabled=true);
  const response=await fetch('/api/imports/failures/retry',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({failure_ids:ids})});const payload=await response.json();
  if(!response.ok){status.querySelector('strong').textContent='Retry could not start';status.querySelector('p').textContent=payload.detail||'Try again later.';await loadImportFailures();return;}
  const poll=async()=>{try{const result=await fetch(`/api/imports/creative-commons/${payload.batch_id}`,{cache:'no-store'});const state=await result.json();if(!result.ok)throw new Error(result.status===404?'This retry was interrupted by an app restart. Your completed imports were kept; start Retry all again for the remaining tracks.':state.detail||'The retry status could not be loaded.');status.querySelector('strong').textContent=state.stage||'Retrying imports';status.querySelector('span').textContent=`${Math.round(Number(state.progress||0))}%`;status.querySelector('progress').value=Number(state.progress||0);const counts=state.counts||{};status.querySelector('p').textContent=`${counts.downloaded||0} imported · ${counts.already_downloaded||0} already present · ${counts.failed||0} still need attention`;if(state.status==='processing'){setTimeout(poll,1000);return;}await loadImportFailures();if(state.status==='complete'){status.querySelector('strong').textContent='Retry complete';}else{status.querySelector('strong').textContent='Retry stopped';status.querySelector('p').textContent=state.error||'The retry could not finish.';}}catch(error){status.querySelector('strong').textContent='Retry interrupted';status.querySelector('span').textContent='';status.querySelector('p').textContent=error.message||'Reload the import issues and try again.';await loadImportFailures();}};poll();
}
async function loadImportFailures() {
  const panel=$('#import-failures-panel'),root=$('#import-failures-list'),empty=$('#import-failures-empty'),counter=$('#import-failure-count'),toolbar=$('#import-failure-toolbar');
  if(!panel||!root)return;
  try{
    const response=await fetch('/api/imports/failures',{cache:'no-store'});const payload=await response.json();if(!response.ok)throw new Error(payload.detail||'Import issues could not be loaded.');
    currentImportFailures=payload.failures||[];counter.textContent=String(currentImportFailures.length);empty.hidden=Boolean(currentImportFailures.length);toolbar.hidden=!currentImportFailures.length;
    const render=()=>{const query=$('#import-failure-search').value.trim().toLowerCase(),selected=new Set($$('.failure-select:checked').map(input=>Number(input.value)));const visible=currentImportFailures.filter(item=>!query||`${item.title} ${item.artist} ${item.playlist_name} ${item.error}`.toLowerCase().includes(query));empty.hidden=Boolean(visible.length);empty.textContent=currentImportFailures.length?'No import issues match this search.':'No unresolved import failures.';
      root.innerHTML=visible.map(item=>{const spotifyId=String(item.spotify_uri||'').startsWith('spotify:track:')?String(item.spotify_uri).split(':').pop():'';const spotifyUrl=spotifyId?`https://open.spotify.com/track/${encodeURIComponent(spotifyId)}`:'';const source=item.youtube_url||spotifyUrl;const [summary,badge]=importFailureKind(item.error);const attempts=Number(item.attempts||1);return `<article class="import-failure-row" data-id="${item.id}"><input class="failure-select" type="checkbox" value="${item.id}" aria-label="Select ${escapeHtml(item.title||'track')}"${selected.has(Number(item.id))?' checked':''}><div><strong>${escapeHtml(item.title||'Unknown track')}</strong><span>${escapeHtml(item.artist||'Unknown artist')} · ${escapeHtml(item.playlist_name||'Imported playlist')}</span></div><div><div class="failure-summary"><b>${escapeHtml(summary)}</b><em>${escapeHtml(badge)}</em></div><small>${attempts} attempt${attempts===1?'':'s'} · ${escapeHtml(item.updated_at||'')}</small><details class="failure-error"><summary>Technical details</summary><p>${escapeHtml(item.error||'Download failed')}</p></details></div><div class="import-failure-actions"><button type="button" class="retry-import-failure">Retry</button>${source?`<a class="button secondary" href="${escapeHtml(source)}" target="_blank" rel="noopener">Open source</a>`:''}<button type="button" class="button secondary dismiss-import-failure">Dismiss</button></div></article>`;}).join('');
      const boxes=$$('.failure-select');const updateSelection=()=>{const checked=$$('.failure-select:checked');$('#retry-selected-imports').disabled=!checked.length;$('#retry-selected-imports').textContent=checked.length?`Retry selected (${checked.length})`:'Retry selected';$('#import-failure-select-all').checked=boxes.length>0&&boxes.every(box=>box.checked);$('#import-failure-select-all').indeterminate=boxes.some(box=>box.checked)&&!$('#import-failure-select-all').checked;};boxes.forEach(box=>box.onchange=updateSelection);updateSelection();
      root.querySelectorAll('.retry-import-failure').forEach(button=>button.onclick=()=>retryImportFailures([Number(button.closest('.import-failure-row').dataset.id)]));
      root.querySelectorAll('.dismiss-import-failure').forEach(button=>button.onclick=async()=>{const row=button.closest('.import-failure-row');button.disabled=true;const response=await fetch(`/api/imports/failures/${row.dataset.id}`,{method:'DELETE'});if(response.ok)await loadImportFailures();else button.disabled=false;});
    };
    $('#import-failure-search').oninput=render;$('#import-failure-select-all').onchange=event=>{$$('.failure-select').forEach(box=>box.checked=event.target.checked);root.querySelector('.failure-select')?.dispatchEvent(new Event('change'));};$('#retry-selected-imports').onclick=()=>retryImportFailures($$('.failure-select:checked').map(input=>Number(input.value)));$('#retry-all-imports').onclick=()=>retryImportFailures(currentImportFailures.map(item=>Number(item.id)));render();
  }catch(error){counter.textContent='!';toolbar.hidden=true;empty.hidden=false;empty.textContent=error.message;root.replaceChildren();}
}

const musicFilesFeature = createMusicFilesFeature({
  $, $$, appConfig, downloadedUiState, downloadedSelection, downloadedRequestState,
  getLoadedAt: () => downloadedLoadedAt,
  setLoadedAt: value => { downloadedLoadedAt=value; },
  invalidateLibrary: () => { libraryLoadedAt=0; }, VIEW_CACHE_MS,
  operationReceiptText, escapeHtml, genreFolderTree, detailedGenreSummary,
  compactAudioMarkup, genreEditorMarkup, metadataEditorMarkup, option,
  syncControlUnlessEditing, refreshSearchableSelects, runBackgroundTask,
  confirmAction, loadLibrary: (...args) => loadLibrary(...args), notify, renderTrackPagination, captureTextFilter,
  bindGenreEditor, startKeyAnalysis,
  showView, loadJobs, closeDownloadedInspector, clock, stopNativeAudio, bindCompactAudio, bindLazyAudio,
  compactAudioIsWithin, stopCompactAudio, collapsedGenreFolders, bindGenreFolderState,
  descriptorChipsMarkup, descriptorEditorMarkup, openDescriptorEditorDialog, saveDescriptorEditor, inferDescriptorEditor,
});
const {loadDownloadedLibrary} = musicFilesFeature;
const djLibraryFeature = createDjLibraryFeature({
  $, $$, getAppConfig: () => appConfig, libraryUiState, libraryRequestState,
  getLoadedAt: () => libraryLoadedAt, setLoadedAt: value => { libraryLoadedAt=value; },
  invalidateMusicFiles: () => { downloadedLoadedAt=0; }, VIEW_CACHE_MS,
  escapeHtml, genreFolderTree, bindGenreFolderState, option, refreshSearchableSelects,
  compactAudioMarkup, genreEditorMarkup, bindGenreEditor, bindCompactAudio,
  renderTrackPagination, confirmAction, notify, clock, pct, loadJobs,
  loadDownloadedLibrary, loadReports: (...args) => loadReports(...args), showView,
  startKeyAnalysis,
  compactAudioIsWithin, stopCompactAudio, normalizedGenreCategory,
  ELECTRONIC_GENRE_CATEGORIES, LATIN_GENRE_CATEGORIES, libraryReprocessForm, reportDate,
  bindLazyAudio,
  syncControlUnlessEditing, captureTextFilter, operationReceiptText,
  descriptorChipsMarkup, descriptorEditorMarkup, openDescriptorEditorDialog, saveDescriptorEditor, inferDescriptorEditor,
  loadAnalysis: (...args) => loadAnalysis(...args),
  jobAction: (...args) => jobAction(...args),
  jobElement: (...args) => jobElement(...args),
});
const {loadLibrary, renderLibraryIntelligence} = djLibraryFeature;
const reportingFeature = createReportingFeature({
  $, $$, loadJobs, renderLibraryIntelligence,
  startKeyAnalysis, notify,
});
const {loadAnalysis, loadReports} = reportingFeature;
const setBuilderFeature = createSetBuilderFeature({
  $, $$, option, escapeHtml, clock, confirmAction, decodedAudio, WaveSurfer,
  compatibility, harmonicCompatibility, camelotKey, formatLibraryKey,
  energyBand, songEnergy, LIBRARY_ROLE_INFO,
  libraryRoles, timingProfile, vocalProfile, bindCompactAudio, compactAudioMarkup,
  stopNativeAudio, stopCompactAudio, notify,
  descriptorEditorMarkup, saveDescriptorEditor, inferDescriptorEditor,
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
    const button = $('#workspace-import-submit'); button.disabled = true; button.textContent = 'Uploading…';
    const importData = new FormData();
    stagedFiles.forEach(file => importData.append('files', file, file.name));
    importData.append('playlist_name', $('#workspace-import-playlist').value.trim() || 'Local Playlist');
    try {
      const response = await fetch('/api/imports/local-audio', {method:'POST', body:importData});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'Could not start the import.');
      $('#upload-message').textContent = `Converting ${payload.track_count} tracks from ${payload.playlist_name}…`;
      pollWorkspaceLocalAudioImport(payload.batch_id);
    } catch (error) {
      button.disabled = false; button.textContent = 'Convert and organize';
      $('#upload-message').textContent = error.message;
    }
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
    if (!response.ok) throw new Error(payload.detail || 'Upload failed');
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

function pollAuthorizedImport(importId) {
  runBackgroundTask({key:'authorized-import',url:`/api/imports/${importId}`,update:state=>{const progress=$('#authorized-import-progress');progress.hidden=false;progress.querySelector('span').style.width=`${Math.max(2,Number(state.progress||0))}%`;progress.querySelector('small').textContent=`${state.stage} · ${Math.round(state.progress||0)}%`;},complete:async state=>{$('#authorized-import-submit').disabled=false;if(state.status==='complete'){const action=state.processed_with_extender?'imported and added to the DJ Library Studio queue':'converted to WAV without creating an extended edit';$('#authorized-import-message').innerHTML=`${escapeHtml(state.filename)} ${action}. <a href="/api/imports/${importId}/download">Download WAV</a>`;$('#authorized-import-form').reset();await loadJobs();}else $('#authorized-import-message').textContent=state.error||'The authorized import failed.';},fail:error=>{$('#authorized-import-submit').disabled=false;$('#authorized-import-message').textContent=error.message;}});
}
function sourceUrlType(value) {
  try {
    const host = new URL(value).hostname.toLowerCase();
    if (host === 'open.spotify.com' || host.endsWith('.spotify.com')) return 'spotify';
    if (host === 'youtu.be' || host === 'youtube.com' || host.endsWith('.youtube.com')) return 'youtube';
    if (host === 'soundcloud.com' || host.endsWith('.soundcloud.com')) return 'soundcloud';
  } catch (_) {}
  return 'unknown';
}
let sourceMatchTimer = null;
let currentSourceMetadata = null;
async function matchSpotifySource(url) {
  const result = $('#source-match-result');
  currentSourceMetadata = null;
  result.hidden = false;
  result.innerHTML = '<p>Finding Spotify metadata and ranking YouTube matches…</p>';
  try {
    const response = await fetch('/api/imports/source-match', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url})});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'The source could not be matched.');
    currentSourceMetadata = payload;
    if (!payload.youtube_url) {
      result.innerHTML = `<div class="source-match-copy"><span class="source-match-label">Spotify track</span><strong>${escapeHtml(payload.title)}</strong><p>${escapeHtml(payload.artist || 'Artist unavailable')}</p><small>No reliable YouTube match was selected.</small></div>`;
      return;
    }
    const warning = (payload.match_warnings || []).join(' · ');
    result.innerHTML = `${payload.thumbnail_url ? `<img src="${escapeHtml(payload.thumbnail_url)}" alt="" loading="lazy">` : '<span class="source-match-art">♫</span>'}<div class="source-match-copy"><span class="source-match-label">Spotify track</span><strong>${escapeHtml(payload.title)}</strong><p>${escapeHtml(payload.artist || 'Artist unavailable')}</p><small>Best YouTube match · ${payload.match_score || 0}% confidence</small><b>${escapeHtml(payload.youtube_title || '')}</b>${warning ? `<em>${escapeHtml(warning)}</em>` : ''}</div><button type="button" id="use-source-match" class="button secondary">Use match</button>`;
    $('#use-source-match').addEventListener('click', () => {
      $('#authorized-url').value = payload.youtube_url;
      $('#source-url-guidance').textContent = 'Matched from Spotify. Confirm the recording authorization, then import it as WAV.';
      $('#authorized-url').focus();
    });
  } catch (error) {
    result.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
  }
}
async function inspectSoundCloudSource(url) {
  const result=$('#source-match-result');
  currentSourceMetadata=null;
  result.hidden=false;
  result.innerHTML='<p>Reading SoundCloud track or mix metadata…</p>';
  try {
    const response=await fetch('/api/imports/source-match',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
    const payload=await response.json();
    if(!response.ok)throw new Error(payload.detail||'The SoundCloud source could not be inspected.');
    currentSourceMetadata=payload;
    result.innerHTML=`${payload.thumbnail_url?`<img src="${escapeHtml(payload.thumbnail_url)}" alt="" loading="lazy">`:'<span class="source-match-art">♫</span>'}<div class="source-match-copy"><span class="source-match-label">SoundCloud ${Number(payload.duration||0)>1200?'mix':'track'}</span><strong>${escapeHtml(payload.title||'Untitled')}</strong><p>${escapeHtml(payload.artist||'Uploader unavailable')}</p><small>${payload.duration?clock(payload.duration):'Duration unavailable'} · authorization required</small></div>`;
  } catch(error) {
    result.innerHTML=`<p>${escapeHtml(error.message)}</p>`;
  }
}
function authorizedSourceUrls(value=$('#authorized-url').value) {
  return [...new Set(String(value||'').split(/\r?\n/).map(url=>url.trim()).filter(Boolean))];
}
$('#authorized-url').addEventListener('input', event => {
  clearTimeout(sourceMatchTimer);
  const urls=authorizedSourceUrls(event.target.value);
  const type = urls.length===1?sourceUrlType(urls[0]):'bulk';
  const guidance = $('#source-url-guidance');
  if(urls.length>1){currentSourceMetadata=null;$('#source-match-result').hidden=true;const supported=urls.filter(url=>['youtube','soundcloud'].includes(sourceUrlType(url))).length;guidance.textContent=`${urls.length} unique URLs queued · ${supported} downloadable sources recognized.`;return;}
  if (type === 'spotify') {
    guidance.textContent = 'Spotify source detected. Looking up its metadata and searching for a matching YouTube recording…';
    sourceMatchTimer = setTimeout(() => matchSpotifySource(urls[0]), 500);
  }
  else if (type === 'youtube') guidance.textContent = 'YouTube source detected. The recording can be imported after you confirm its download authorization.';
  else if (type === 'soundcloud') {
    guidance.textContent = 'SoundCloud source detected. Reading its track or mix metadata…';
    sourceMatchTimer = setTimeout(() => inspectSoundCloudSource(urls[0]), 500);
  }
  else guidance.textContent = 'Paste a Spotify link or an authorized YouTube or SoundCloud recording.';
});
async function waitForAuthorizedImport(importId,url,onProgress){
  while(true){
    const response=await fetch(`/api/imports/${importId}`,{cache:'no-store'}),state=await response.json();
    if(!response.ok)throw new Error(state.detail||'Import status could not be loaded.');
    onProgress(Number(state.progress||0),state.stage||'Importing');
    if(state.status!=='processing')return {url,importId,...state};
    await new Promise(resolve=>setTimeout(resolve,900));
  }
}
const authorizedImportQueue = new AuthorizedImportQueue({
  select: $,
  escapeHtml,
  waitForImport: waitForAuthorizedImport,
  onComplete: async queue => {
    const completed=queue.items.filter(item=>item.status==='complete'),failed=queue.items.filter(item=>item.status!=='complete'),message=$('#authorized-import-message');
    message.innerHTML=`<strong>${completed.length} of ${queue.items.length} sources imported.</strong>${failed.length?`<span>${failed.length} failed or canceled. Use Retry in the queue when ready.</span>`:''}${completed.length===1?` <a href="/api/imports/${completed[0].importId}/download">Download WAV</a>`:''}`;
    $('#authorized-import-submit').disabled=false;
    if(!failed.length)$('#authorized-import-form').reset();
    await loadJobs();
  },
});
async function importAuthorizedSources(urls,basePayload){
  const metadata=urls.length===1?{title:currentSourceMetadata?.title||'',artist:currentSourceMetadata?.artist||'',spotify_uri:currentSourceMetadata?.spotify_uri||'',artwork_url:currentSourceMetadata?.thumbnail_url||''}:{title:'',artist:'',spotify_uri:'',artwork_url:''};
  await authorizedImportQueue.start(urls,basePayload,metadata);
}
$('#authorized-import-pause').onclick=()=>authorizedImportQueue.togglePause();
$('#authorized-import-retry').onclick=()=>authorizedImportQueue.retryFailed();
$('#authorized-import-form').addEventListener('submit', async event => {
  event.preventDefault();
  const urls=authorizedSourceUrls();
  if(!urls.length)return;
  if(urls.length>100){$('#authorized-import-message').textContent='Import at most 100 URLs in one batch.';return;}
  const unsupported=urls.filter(url=>!['youtube','soundcloud'].includes(sourceUrlType(url)));
  if (unsupported.length) {
    $('#authorized-import-message').textContent = `${unsupported.length} URL${unsupported.length===1?' is':'s are'} unsupported. Spotify supplies metadata only; bulk imports require direct YouTube or SoundCloud URLs.`;
    return;
  }
  stopBackgroundTask('authorized-import');
  const button = $('#authorized-import-submit'); button.disabled = true;
  $('#authorized-import-message').textContent = `Preparing ${urls.length} authorized source${urls.length===1?'':'s'}…`;
  await importAuthorizedSources(urls,{rights_basis:$('#rights-basis').value,confirmation:$('#rights-confirmation').checked,process_with_extender:$('#process-import-with-extender').checked});
});

let localAudioFiles = [];
const supportedLocalAudio = /\.(mp3|m4a|aac|flac|ogg|opus|wav|aiff?|aif)$/i;
function stageLocalAudio(files) {
  const known = new Set(localAudioFiles.map(file => `${file.name}|${file.size}|${file.lastModified}`));
  [...files].filter(file => supportedLocalAudio.test(file.name)).forEach(file => {
    const key = `${file.name}|${file.size}|${file.lastModified}`;
    if (!known.has(key)) { localAudioFiles.push(file); known.add(key); }
  });
  const root = $('#local-audio-staged');
  root.innerHTML = localAudioFiles.length
    ? `${localAudioFiles.slice(0,20).map(file => `<div><strong>${escapeHtml(file.name)}</strong><span>${(file.size/1024/1024).toFixed(1)} MB</span></div>`).join('')}${localAudioFiles.length > 20 ? `<span>+ ${localAudioFiles.length-20} more tracks</span>` : ''}`
    : '<span>No files selected.</span>';
  $('#local-audio-import-submit').disabled = !localAudioFiles.length;
  $('#local-audio-import-message').textContent = localAudioFiles.length ? `${localAudioFiles.length} track${localAudioFiles.length===1?'':'s'} ready to convert.` : '';
}
$('#local-audio-files').addEventListener('change', event => stageLocalAudio(event.target.files));
$('#local-audio-folder').addEventListener('change', event => {
  const files = [...event.target.files];
  const folder = files[0]?.webkitRelativePath?.split('/')[0];
  if (folder && $('#local-playlist-name').value === 'Local Playlist') $('#local-playlist-name').value = folder;
  stageLocalAudio(files);
});
function pollLocalAudioImport(batchId) {
  runBackgroundTask({key:'local-audio-import',url:`/api/imports/local-audio/${batchId}`,interval:900,update:state=>{const progress=$('#local-audio-import-progress');progress.hidden=false;progress.querySelector('span').style.width=`${Math.max(2,Number(state.progress||0))}%`;progress.querySelector('small').textContent=`${state.stage} · ${Math.round(state.progress||0)}%`;},complete:state=>{const button=$('#local-audio-import-submit');button.disabled=false;const result=$('#local-audio-import-result');result.hidden=false;if(state.status==='complete'){
    const counts = state.counts || {};
    const genres = {};
    (state.results || []).filter(item => item.status === 'imported').forEach(item => { const genre=item.genre_category||'Other'; genres[genre]=(genres[genre]||0)+1; });
    result.innerHTML = `<strong>${escapeHtml(state.playlist_name)} imported</strong><span>${counts.imported||0} converted · ${counts.duplicates||0} duplicates skipped · ${counts.failed||0} failed</span>${Object.keys(genres).length?`<span>${escapeHtml(Object.entries(genres).map(([genre,count])=>`${genre} (${count})`).join(' · '))}</span>`:''}<button type="button" class="button secondary view-local-imports">Open Music Files</button>`;
    result.querySelector('.view-local-imports').onclick = () => showView('downloads-view');
    localAudioFiles=[]; stageLocalAudio([]); $('#local-audio-files').value=''; $('#local-audio-folder').value='';
  } else result.innerHTML=`<strong>Import failed</strong><span>${escapeHtml(state.error||'The local playlist could not be imported.')}</span>`;},fail:error=>{$('#local-audio-import-submit').disabled=false;$('#local-audio-import-message').textContent=error.message;}});
}
function pollWorkspaceLocalAudioImport(batchId) {
  runBackgroundTask({key:'workspace-local-import',url:`/api/imports/local-audio/${batchId}`,interval:900,update:state=>{$('#upload-message').textContent=`${state.stage} · ${Math.round(state.progress||0)}%`;},complete:async state=>{const button=$('#workspace-import-submit');button.disabled=false;button.textContent='Convert and organize';if(state.status==='complete'){
    const counts = state.counts || {};
    $('#upload-message').textContent = `${counts.imported || 0} WAV${counts.imported === 1 ? '' : 's'} imported · ${counts.duplicates || 0} duplicates skipped · ${counts.failed || 0} failed. Open Music Files to review them.`;
    stagedFiles = []; describeFiles(); await loadDownloadedLibrary();
  }else $('#upload-message').textContent=state.error||'The local playlist import failed.';},fail:error=>{const button=$('#workspace-import-submit');button.disabled=false;button.textContent='Convert and organize';$('#upload-message').textContent=error.message;}});
}
$('#local-audio-import-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (!localAudioFiles.length) return;
  stopBackgroundTask('local-audio-import');
  const button=$('#local-audio-import-submit'); button.disabled=true; button.textContent='Uploading…';
  const data=new FormData(); localAudioFiles.forEach(file=>data.append('files',file,file.name)); data.append('playlist_name',$('#local-playlist-name').value.trim()||'Local Playlist');
  const response=await fetch('/api/imports/local-audio',{method:'POST',body:data}); const payload=await response.json(); button.textContent='Convert and organize';
  if(!response.ok){button.disabled=false;$('#local-audio-import-message').textContent=payload.detail||'Could not start the local import.';return;}
  $('#local-audio-import-message').textContent=`Converting ${payload.track_count} tracks from ${payload.playlist_name}…`;
  pollLocalAudioImport(payload.batch_id);
});

let spotifyMatchTimer = null;
const playlistPermissions = new Map();
let currentPlaylistMatches = [];
let currentPlaylistName = 'Imported Playlist';
function playlistTrackKey(track, index) {
  return track.spotify_uri || track.youtube_url || `${track.artist}|${track.title}|${index}`;
}
function updatePlaylistSelectionCount() {
  const selected = $$('#spotify-match-results .match-select:checked').length;
  $('#spotify-selected-count').textContent = `${selected} selected`;
  const boxes = $$('#spotify-match-results .match-select');
  $('#spotify-select-all').checked = boxes.length > 0 && selected === boxes.length;
  $('#spotify-select-all').indeterminate = selected > 0 && selected < boxes.length;
}
function renderSpotifyMatches(results) {
  currentPlaylistMatches = results;
  const root = $('#spotify-match-results');
  root.hidden = false;
  root.innerHTML = results.map((track, index) => {
    const key = playlistTrackKey(track, index);
    const permission = playlistPermissions.get(key) || 'unverified';
    const duration = track.youtube_duration ? clock(track.youtube_duration) : 'unknown length';
    const sourceDuration = track.duration_ms ? clock(track.duration_ms / 1000) : 'unknown source length';
    const match = track.youtube_url
      ? `<a href="${escapeHtml(track.youtube_url)}" target="_blank" rel="noreferrer">Open YouTube ↗</a><button type="button" class="button secondary use-youtube-match" data-url="${escapeHtml(track.youtube_url)}" data-key="${escapeHtml(key)}" ${permission === 'unverified' ? 'disabled' : ''}>Use for authorized import</button>`
      : '<span class="match-missing">No likely match found</span>';
    const sourceDetails = [track.genre_category, track.genre, track.tempo ? `${track.tempo} BPM` : ''].filter(Boolean).join(' · ');
    const quality = track.youtube_url ? `${track.match_score || 0}% match` : 'No reliable match';
    const warnings = (track.match_warnings || []).join(' · ');
    return `<article data-key="${escapeHtml(key)}"><label class="match-check"><input class="match-select" type="checkbox" aria-label="Select ${escapeHtml(track.title)}"></label><span class="match-number">${index + 1}</span><div class="match-copy"><strong>${escapeHtml(track.title)}</strong><small>${escapeHtml(track.artist)}${sourceDetails ? ` · ${escapeHtml(sourceDetails)}` : ''} · source ${sourceDuration}</small><p>${track.youtube_title ? escapeHtml(track.youtube_title) : 'No YouTube result'} · YouTube ${duration} · ${quality}</p>${warnings ? `<p class="match-warning">${escapeHtml(warnings)}</p>` : ''}<label class="match-permission-label">Permission<select class="match-permission"><option value="unverified" ${permission === 'unverified' ? 'selected' : ''}>Unverified</option><option value="own-upload" ${permission === 'own-upload' ? 'selected' : ''}>I own this recording</option><option value="creative-commons" ${permission === 'creative-commons' ? 'selected' : ''}>Creative Commons</option><option value="public-domain" ${permission === 'public-domain' ? 'selected' : ''}>Public domain</option><option value="permission" ${permission === 'permission' ? 'selected' : ''}>Direct permission</option></select></label></div><div class="match-actions">${match}</div></article>`;
  }).join('');
  $('#spotify-match-toolbar').hidden = false;
  root.querySelectorAll('.match-select').forEach(box => box.addEventListener('change', updatePlaylistSelectionCount));
  root.querySelectorAll('.match-permission').forEach(select => select.addEventListener('change', () => {
    const card = select.closest('article');
    playlistPermissions.set(card.dataset.key, select.value);
    const useButton = card.querySelector('.use-youtube-match');
    if (useButton) useButton.disabled = select.value === 'unverified';
  }));
  root.querySelectorAll('.use-youtube-match').forEach(button => button.addEventListener('click', () => {
    const permission = playlistPermissions.get(button.dataset.key) || 'unverified';
    if (permission === 'unverified') return;
    $('#authorized-url').value = button.dataset.url;
    $('#rights-basis').value = permission;
    $('#authorized-url').focus();
    $('#authorized-import-message').textContent = 'Match and permission copied above. Confirm your rights before importing it.';
    $('#authorized-import-form').scrollIntoView({behavior:'smooth', block:'center'});
  }));
  updatePlaylistSelectionCount();
}
$('#spotify-select-all').addEventListener('change', event => {
  $$('#spotify-match-results .match-select').forEach(box => { box.checked = event.target.checked; });
  updatePlaylistSelectionCount();
});
$('#spotify-apply-permission').addEventListener('click', () => {
  const permission = $('#spotify-bulk-permission').value;
  $$('#spotify-match-results article').forEach(card => {
    if (!card.querySelector('.match-select').checked) return;
    card.querySelector('.match-permission').value = permission;
    playlistPermissions.set(card.dataset.key, permission);
    const useButton = card.querySelector('.use-youtube-match');
    if (useButton) useButton.disabled = permission === 'unverified';
  });
  $('#spotify-playlist-message').textContent = `Permission updated for ${$$('#spotify-match-results .match-select:checked').length} selected tracks.`;
});
async function pollCreativeCommonsBatch(batchId) {
  const state = await fetch(`/api/imports/creative-commons/${batchId}`).then(response => response.json());
  const root = $('#creative-commons-result'); root.hidden = false;
  const counts = state.counts || {};
  root.innerHTML = `<strong>${escapeHtml(state.stage)}</strong><span>${Math.round(state.progress || 0)}% · ${counts.downloaded || 0} downloaded · ${counts.already_downloaded || 0} already present · ${counts.skipped_not_creative_commons || 0} not Creative Commons · ${counts.failed || 0} failed</span>`;
  if (state.status === 'processing') {
    setTimeout(() => pollCreativeCommonsBatch(batchId), 1200);
    return;
  }
  $('#download-creative-commons').disabled = false;
  if (state.status === 'complete') {
    const folders = Object.entries(state.genre_summary || {}).map(([genre,count]) => `${genre} (${count})`).join(' · ');
    root.innerHTML += `${folders ? `<span>${escapeHtml(state.playlist_name || currentPlaylistName)} folders: ${escapeHtml(folders)}</span>` : ''}<div><a class="button secondary" href="/api/imports/creative-commons/${batchId}/report">Download ${escapeHtml(state.playlist_name || currentPlaylistName)} report</a>${(counts.downloaded || 0) + (counts.already_downloaded || 0) > 0 ? `<a class="button" href="/api/imports/creative-commons/${batchId}/download">Download ${escapeHtml(state.playlist_name || currentPlaylistName)} WAV ZIP</a>` : ''}</div>`;
    await loadImportFailures();
  } else {
    root.innerHTML += `<p>${escapeHtml(state.error || 'Creative Commons import failed.')}</p>`;
  }
}
$('#download-creative-commons').addEventListener('click', async () => {
  const tracks = currentPlaylistMatches.filter(track => track.youtube_url).map(track => ({url:track.youtube_url, title:track.title, artist:track.artist, spotify_uri:track.spotify_uri || '', genre:track.genre || '', genre_category:track.genre_category || 'Other', artwork_url:track.artwork_url || ''}));
  if (!tracks.length) return;
  const button = $('#download-creative-commons'); button.disabled = true;
  $('#creative-commons-result').hidden = false;
  $('#creative-commons-result').textContent = `Checking Creative Commons licenses for ${tracks.length} matches…`;
  const response = await fetch('/api/imports/creative-commons', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({tracks, playlist_name:currentPlaylistName})});
  const payload = await response.json();
  if (!response.ok) { button.disabled = false; $('#creative-commons-result').textContent = payload.detail || 'Could not start verification.'; return; }
  pollCreativeCommonsBatch(payload.batch_id);
});
async function pollSpotifyMatches(matchId) {
  const response = await fetch(`/api/imports/playlist-matches/${matchId}`);
  const state = await response.json();
  const progress = $('#spotify-playlist-progress'); progress.hidden = false;
  progress.querySelector('span').style.width = `${Math.max(2, Number(state.progress || 0))}%`;
  progress.querySelector('small').textContent = `${state.stage} · ${Math.round(state.progress || 0)}%`;
  if (state.status === 'processing') {
    spotifyMatchTimer = setTimeout(() => pollSpotifyMatches(matchId), 1000);
    return;
  }
  if (state.status === 'complete') {
    currentPlaylistName = state.playlist_name || currentPlaylistName;
    $('#spotify-playlist-message').textContent = `${state.results.length} tracks matched. Verify titles and durations before using any result.`;
    renderSpotifyMatches(state.results);
  } else {
    $('#spotify-playlist-message').textContent = state.error || 'Playlist matching failed.';
  }
}
$('#playlist-csv-form').addEventListener('submit', async event => {
  event.preventDefault();
  clearTimeout(spotifyMatchTimer);
  const file = $('#playlist-csv-file').files[0];
  if (!file) return;
  const button = $('#playlist-csv-submit'); button.disabled = true;
  $('#spotify-match-results').hidden = true;
  $('#spotify-playlist-message').textContent = `Reading ${file.name}…`;
  const data = new FormData(); data.append('file', file);
  const response = await fetch('/api/imports/playlist-file/matches', {method:'POST', body:data});
  const payload = await response.json();
  if (!response.ok) { button.disabled = false; $('#spotify-playlist-message').textContent = payload.detail || 'Could not read that CSV.'; return; }
  currentPlaylistName = payload.playlist_name || file.name.replace(/\.csv$/i, '') || 'Imported Playlist';
  $('#spotify-playlist-message').textContent = `${payload.track_count} tracks loaded from ${currentPlaylistName}. Finding YouTube matches…`;
  await pollSpotifyMatches(payload.match_id);
  button.disabled = false;
});

function jobElement(job) {
  const node = template.content.firstElementChild.cloneNode(true);
  let detailsHydrated = false;
  node.dataset.status = job.status; node.dataset.jobId = job.id;
  node.dataset.renderSignature = jobRenderSignature(job);
  if (job.review_status === 'pending') node.classList.add('review-awaiting');
  if (job.review_status === 'rejected') node.classList.add('review-dismissed');
  node.querySelector('.track-title strong').textContent = job.source_name;
  node.querySelector('.meta').textContent = `${job.preset} · ${job.intro_bars} bar intro · ${job.outro_bars} bar outro${job.use_stems ? ' · stems' : ''} · generation ${job._generation || 1}${job._eta ? ` · ETA ${job._eta}` : ''}`;
  node.querySelector('.status').textContent = job.review_status === 'pending' ? 'awaiting review' : job.review_status === 'rejected' ? 'review dismissed' : job.status;
  node.querySelector('.progress-track span').style.width = `${job.progress}%`;
  node.querySelector('.stage').textContent = job.review_status === 'pending' ? 'Candidate review requested · choose options in Review' : job.review_status === 'rejected' ? 'Review dismissed · processed audio remains available in Library' : job.stage;
  if (job.status === 'processing' && Date.now() - new Date(job.created_at).getTime() > 300000) {
    node.querySelector('.stage').textContent = `${job.stage} · long analysis, still working`;
  }
  node.querySelector('.percent').textContent = `${Math.round(job.progress)}%`;
  node.querySelector('.job-error').textContent = job.error || '';
  node.querySelector('.cancel-job').addEventListener('click', () => jobAction(job.id, 'cancel'));
  const pauseButton = node.querySelector('.pause-job');
  pauseButton.textContent = job.pause_requested ? 'Resume' : 'Pause';
  pauseButton.addEventListener('click', () => jobAction(job.id, job.pause_requested ? 'resume' : 'pause'));
  const reprocessButton = node.querySelector('.reprocess-job');
  reprocessButton.textContent = job.review_status === 'rejected' ? 'Process automatically' : 'Reprocess';
  reprocessButton.addEventListener('click', () => jobAction(job.id, 'reprocess', job.review_status === 'rejected' ? {review_candidates:false} : null));
  node.querySelector('.remove-job').addEventListener('click', () => removeJob(job.id));
  node.querySelector('.details-job').addEventListener('click', async event => {
    const open = node.classList.toggle('details-open');
    event.currentTarget.textContent = open ? 'Hide details' : 'Show details';
    if (open && job.status === 'complete' && !detailsHydrated) {
      detailsHydrated = true;
      await hydrateCompletedJob(node, job);
    }
  });
  node.querySelector('.library-job').addEventListener('click', async () => {
    showView('library-view');
    await loadLibrary();
  });
  let jobConfig = {}; try { jobConfig = JSON.parse(job.config_json || '{}'); } catch (_) { jobConfig = {}; }
  const introLabel = jobConfig.intro_bars_auto ? 'auto intro' : `${job.intro_bars} bar intro`;
  const outroLabel = jobConfig.outro_bars_auto ? 'auto outro' : `${job.outro_bars} bar outro`;
  node.querySelector('.meta').textContent = jobConfig.analysis_only
    ? `analysis only${job.use_stems ? ' · stems' : ''}${job._eta ? ` · ETA ${job._eta}` : ''}`
    : `${job.preset} · ${introLabel} · ${outroLabel}${job.use_stems ? ' · stems' : ''} · generation ${job._generation || 1}${job._eta ? ` · ETA ${job._eta}` : ''}`;
  node.querySelector('.review-job').addEventListener('click', () => {
    if (job.review_status === 'pending') showView('review-view');
    else jobAction(job.id, 'reprocess', {review_candidates:true});
  });
  node.querySelector('.review-job').textContent = job.review_status === 'pending' ? 'Open review' : job.review_status === 'rejected' ? 'Reopen review' : 'Create review';
  node.querySelector('.move-up').addEventListener('click', () => moveJob(job.id, -1));
  node.querySelector('.move-down').addEventListener('click', () => moveJob(job.id, 1));
  if (job.status === 'complete' && job.review_status !== 'pending') {
    const downloads = node.querySelector('.downloads'); downloads.classList.add('visible');
    const players = node.querySelector('.players'); players.classList.add('visible');
    const sources = [
      ['.source-player', 'wav', job.wav_path],
      ['.extended-player', 'extended', job.extended_path],
      ['.intro-player', 'intro-preview', job.intro_preview_path],
      ['.outro-player', 'outro-preview', job.outro_preview_path],
    ];
    sources.forEach(([selector, kind, available]) => {
      const row = node.querySelector(selector);
      if (available) row.querySelector('audio').src = `/api/jobs/${job.id}/audio/${kind}`;
      else row.classList.add('unavailable');
    });
    node.querySelector('.wav-link').href = `/api/jobs/${job.id}/download/wav`;
    node.querySelector('.extended-link').href = `/api/jobs/${job.id}/download/extended`;
    node.querySelector('.cue-link').href = `/api/jobs/${job.id}/download/cue-sheet`;
    node.querySelector('.rekordbox-link').href = `/api/jobs/${job.id}/download/rekordbox`;
    if (!job.cue_sheet_path) node.querySelector('.cue-link').style.display = 'none';
    if (!job.rekordbox_path) node.querySelector('.rekordbox-link').style.display = 'none';
  }
  return node;
}

async function jobAction(id, action, body = null) {
  const options = { method:'POST' };
  if (body) { options.headers = {'Content-Type':'application/json'}; options.body = JSON.stringify(body); }
  const response = await fetch(`/api/jobs/${id}/${action}`, options);
  if (!response.ok) { alert((await response.json()).detail || `Could not ${action} job.`); return false; }
  await loadJobs();
  return true;
}
async function removeJob(id) { if (!await confirmAction('Remove this queue entry? Audio files will remain in output.', {title:'Remove queue entry', acceptLabel:'Remove', danger:true})) return; await fetch(`/api/jobs/${id}`, {method:'DELETE'}); await loadJobs(); }
$('#clear-queue').addEventListener('click', async () => {
  if (!await confirmAction('Clear queued and dismissed entries? A track currently processing will continue, and completed audio remains in Library.', {title:'Clear queue history', acceptLabel:'Clear', danger:true})) return;
  const button = $('#clear-queue'); button.disabled = true; button.textContent = 'Clearing…';
  try {
    const response = await fetch('/api/jobs/clear', {method:'POST'});
    if (!response.ok) throw new Error((await response.json()).detail || 'Could not clear the queue.');
    await Promise.all([loadJobs(), loadAnalysis()]);
  } catch (error) { alert(error.message); }
  finally { button.textContent = 'Clear queue'; }
});
async function moveJob(id, offset) {
  const jobs = await fetch('/api/jobs').then(r => r.json());
  const queued = jobs.filter(job => job.status === 'queued').sort((a,b) => a.queue_index - b.queue_index);
  const index = queued.findIndex(job => job.id === id); const target = index + offset;
  if (index < 0 || target < 0 || target >= queued.length) return;
  [queued[index], queued[target]] = [queued[target], queued[index]];
  await fetch('/api/jobs/reorder', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({job_ids:queued.map(job => job.id)})});
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

async function loadReviews() {
  const jobs = await fetch('/api/jobs').then(r => r.json());
  const generations = {};
  [...jobs].reverse().forEach(job => {
    const key = job.source_name.toLowerCase();
    generations[key] = (generations[key] || 0) + 1; job._generation = generations[key];
  });
  const reviewJobs = jobs.filter(job => {
    try { return job.status === 'complete' && job.review_status === 'pending' && JSON.parse(job.config_json || '{}').review_candidates; }
    catch (_) { return false; }
  });
  const root = $('#review-list');
  if (!reviewJobs.length) { root.innerHTML = '<div class="empty">No candidate reviews requested. Use “Create review” on a completed track or enable review before uploading.</div>'; return; }
  root.innerHTML = reviewJobs.map(job => `<article class="panel review-card" data-job-id="${job.id}"><div class="panel-head"><div><p class="eyebrow">GENERATION ${job._generation || 1}</p><h2>${escapeHtml(job.source_name)}</h2></div><div class="review-actions"><button class="button secondary regenerate-review">Regenerate auditions</button><button class="button secondary reject-review">Dismiss review</button></div></div><div class="review-players"><label>Source WAV<audio controls preload="metadata" src="/api/jobs/${job.id}/audio/wav"></audio></label><label>Selected extended edit<audio controls preload="metadata" src="/api/jobs/${job.id}/audio/extended"></audio></label></div><div class="candidate-studio"><p class="muted-copy">Loading candidate auditions…</p></div></article>`).join('');
  await Promise.all(reviewJobs.map(async job => {
    const card = root.querySelector(`[data-job-id="${job.id}"]`);
    const [data, feedback] = await Promise.all([
      fetch(`/api/jobs/${job.id}/candidates`).then(r => r.json()),
      fetch(`/api/jobs/${job.id}/feedback`).then(r => r.json()),
    ]);
    renderCandidates(card.querySelector('.candidate-studio'), job, data, feedback);
    card.querySelector('.regenerate-review').onclick = async () => {
      await jobAction(job.id, 'reprocess', {review_candidates:true});
      await loadReviews();
    };
    card.querySelector('.reject-review').onclick = async () => {
      if (!await confirmAction('Dismiss this candidate review? The processed track remains in Library.', {title:'Dismiss candidate review', acceptLabel:'Dismiss'})) return;
      const response = await fetch(`/api/jobs/${job.id}/review/reject`, {method:'POST'});
      if (response.ok) {
        await Promise.all([loadReviews(), loadJobs()]);
        showView('workspace-view');
      }
    };
  }));
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

function renderCandidates(root, job, data, feedback = []) {
  const selections = {};
  const customSelections = {};
  let arrangementInsertion = null;
  const sides = ['intro','outro'].map(position => {
    const accepted = feedback.find(item => item.position === position && item.accepted);
    if (accepted) selections[position] = accepted.candidate_rank;
    const cards = (data[position] || []).map(item => `<div class="candidate-card ${accepted?.candidate_rank===item.rank?'decision-accept':''}" data-rank="${item.rank}"><strong>Option ${item.rank} · ${clock(item.start)}–${clock(item.end)}</strong><p>Phrase ${pct(item.phrase)} · Loop ${pct(item.loop)} · Transition ${pct(item.transition)}</p><p>${escapeHtml(item.warnings.join(' · ') || 'All automatic checks passed')}</p><audio controls preload="none" src="/api/jobs/${job.id}/candidate/${position}/${item.rank}"></audio><div class="feedback-controls"><input class="tags" placeholder="tags"><input class="notes" placeholder="notes"><button class="candidate-choice ${accepted?.candidate_rank===item.rank?'decision-active':''}" data-choose>${accepted?.candidate_rank===item.rank?'Selected':'Accept option '+item.rank}</button></div></div>`).join('');
    const suggestion = (data[position] || [])[0] || {start:0,end:8};
    return `<section class="candidate-side" data-position="${position}"><div class="candidate-side-heading"><strong>${position} candidates</strong><span>${accepted ? `Option ${accepted.candidate_rank} selected` : 'Choose one option'}</span><div><button class="button secondary preserve-side">Preserve original</button><button class="button secondary open-custom">Build my own</button></div></div><div class="candidate-grid">${cards || '<p>No candidates generated.</p>'}</div><div class="custom-candidate" hidden><header><div class="custom-icon">✦</div><div><p class="eyebrow">CUSTOM EDITOR</p><strong>Build a custom ${position}</strong><small>Drag the highlighted waveform region or enter exact timestamps. Final rendering still applies boundary optimization and adaptive smoothing.</small></div><button class="button secondary discard-custom">Close editor</button></header><div class="custom-wave-shell"><div class="custom-waveform"></div><div class="custom-timeline"></div></div><div class="custom-fields"><label>Selection start<input class="custom-start" type="number" min="0" step="0.01" value="${Number(suggestion.start).toFixed(2)}"></label><label>Selection end<input class="custom-end" type="number" min="0.01" step="0.01" value="${Number(suggestion.end).toFixed(2)}"></label><label>Copies<select class="custom-copies"><option>1</option><option>2</option><option>3</option><option>4</option><option>6</option><option>8</option></select></label></div><div class="custom-stats"><p><b class="custom-duration">—</b><span>Selection</span></p><p><b class="custom-bars">—</b><span>Approx. bars</span></p><p><b class="custom-added">—</b><span>Audio added</span></p><p><b>${Number(job.bpm || 0).toFixed(1)}</b><span>Detected BPM</span></p></div><div class="custom-footer"><div class="custom-tools"><button class="button secondary snap-custom">⌁ Snap to bars</button><button class="button secondary play-custom">▶ Audition region</button></div><button class="button secondary use-custom">Use custom candidate →</button></div><p class="custom-message">Adjust the highlighted region, then audition it before selecting.</p></div></section>`;
  }).join('');
  root.innerHTML = `${sides}<div class="candidate-submit"><p>Select an automatic option, preserve the original, or build a custom candidate for each side.</p><button class="button secondary reprocess-candidates">Reprocess with selected candidates</button><span></span></div>`;
  root.querySelectorAll('.candidate-card audio').forEach(audio => audio.addEventListener('error', () => {
    audio.hidden = true;
    const message = document.createElement('p'); message.className = 'candidate-audio-error';
    message.textContent = 'Audition file is unavailable. Use “Regenerate auditions” above.';
    audio.after(message);
  }, {once:true}));
  root.querySelectorAll('.candidate-card').forEach(card => {
    const side = card.closest('.candidate-side');
    const position = side.dataset.position;
    const rank = Number(card.dataset.rank);
    card.querySelector('[data-choose]').onclick = async () => {
      const response = await fetch(`/api/jobs/${job.id}/feedback`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({position,candidate_rank:rank,accepted:true,tags:card.querySelector('.tags').value,notes:card.querySelector('.notes').value})});
      if (!response.ok) return;
      selections[position] = rank;
      delete customSelections[position];
      side.querySelectorAll('.candidate-card').forEach(optionCard => {
        const chosen = optionCard === card;
        optionCard.classList.toggle('decision-accept', chosen);
        const button = optionCard.querySelector('[data-choose]');
        button.classList.toggle('decision-active', chosen);
        button.textContent = chosen ? 'Selected' : `Accept option ${optionCard.dataset.rank}`;
      });
      side.querySelector('.candidate-side-heading span').textContent = `Option ${rank} selected`;
      updateSubmit();
    };
  });
  root.querySelectorAll('.candidate-side').forEach(side => {
    const position = side.dataset.position;
    const editor = side.querySelector('.custom-candidate');
    editor.querySelector('.custom-wave-shell').insertAdjacentHTML(
      'afterend',
      '<div class="custom-wave-controls"><div class="custom-wave-actions"><button class="button secondary play-full-custom" disabled>▶ Play full track</button></div><span class="custom-wave-time">00:00 / 00:00</span><label>Zoom <input class="custom-zoom" type="range" min="0" max="180" value="0"></label></div><div class="custom-arrangement"></div><div class="custom-legend"></div>',
    );
    const waveActions = editor.querySelector('.custom-wave-actions');
    waveActions.append(editor.querySelector('.snap-custom'), editor.querySelector('.play-custom'));
    editor.querySelector('.custom-tools').remove();
    editor.querySelector('.custom-bars').outerHTML = '<input class="custom-bars-input" aria-label="Approximate bars" type="number" min="0.25" max="64" step="0.25" value="1">';
    editor.querySelector('.custom-legend').insertAdjacentHTML('afterend', '<div class="insert-builder"><button class="button secondary open-insert">＋ Insert this section elsewhere</button><div class="insert-panel" hidden><div><p class="eyebrow">DESTINATION</p><strong>Place this source region in the extended arrangement</strong><small>Click the destination waveform or enter an exact output timestamp. The orange block is the material that will be added.</small></div><div class="insert-wave-shell"><div class="insert-waveform"></div><div class="insert-timeline"></div></div><div class="insert-preview-row"><button class="button secondary preview-insert">▶ Preview placement</button><span>Plays context before → selected region × copies → context after</span><output class="insert-preview-time">00:00 / 00:00</output><label>Zoom <input class="insert-zoom" type="range" min="0" max="180" value="0"></label><b class="insert-added-time">—</b></div><div class="insert-score score-loading"><strong>Checking placement…</strong><span>Comparing bars, chords, energy, bass, rhythm, and vocals.</span></div><div class="insert-controls"><label>Destination<input class="insert-destination" type="number" min="0" step="0.01" value="0"></label><label>Copies<select class="insert-copies"><option>1</option><option>2</option><option>3</option><option>4</option></select></label><label class="insert-also"><input type="checkbox"><span>Also use this region as the custom side extension</span></label><button class="button secondary snap-insert">Snap destination to bar</button><button class="button secondary use-insert">Use insertion</button></div><p class="insert-message"></p></div></div>');
    const sourceAudio = root.closest('.review-card').querySelector('.review-players audio');
    const updateMap = () => {
      const start = Number(editor.querySelector('.custom-start').value);
      const end = Number(editor.querySelector('.custom-end').value);
      const copies = Number(editor.querySelector('.custom-copies').value);
      const seconds = Math.max(0, end - start);
      const bar = 4 * 60 / Math.max(Number(job.bpm) || 120, 1);
      editor.querySelector('.custom-duration').textContent = `${seconds.toFixed(2)}s`;
      editor.querySelector('.custom-bars-input').value = `${(seconds / bar).toFixed(2)}`;
      editor.querySelector('.custom-added').textContent = `${(seconds * copies).toFixed(1)}s`;
      const region = editor._customRegion;
      if (region && !editor._syncingRegion) {
        editor._syncingInputs = true;
        region.setOptions({start, end});
        editor._syncingInputs = false;
      }
      updateInsertionVisualization(editor);
    };
    side.querySelector('.open-custom').onclick = () => {
      editor.hidden = false; side.classList.add('custom-open'); updateMap();
      initializeCustomWaveform(editor, job);
    };
    side.querySelector('.discard-custom').onclick = () => { editor.hidden = true; side.classList.remove('custom-open'); };
    side.querySelector('.preserve-side').onclick = () => {
      selections[position] = 0; delete customSelections[position];
      side.querySelector('.candidate-side-heading>span').textContent = 'Original preserved';
      side.querySelectorAll('.candidate-card').forEach(card => card.classList.remove('decision-accept'));
      updateSubmit();
    };
    editor.querySelectorAll('.custom-start,.custom-end,.custom-copies').forEach(input => input.oninput = updateMap);
    editor.querySelector('.custom-bars-input').oninput = event => {
      const bars = Number(event.target.value);
      if (!Number.isFinite(bars) || bars <= 0) return;
      const start = Number(editor.querySelector('.custom-start').value);
      const barSeconds = 4 * 60 / Math.max(Number(job.bpm) || 120, 1);
      editor.querySelector('.custom-end').value = (start + bars * barSeconds).toFixed(2);
      updateMap();
      editor.querySelector('.custom-message').textContent = `Selection resized to ${bars} bars on the detected 4/4 grid.`;
    };
    editor.querySelector('.snap-custom').onclick = () => {
      const beat = 60 / Math.max(Number(job.bpm) || 120, 1);
      const bar = beat * 4;
      const startInput = editor.querySelector('.custom-start');
      const endInput = editor.querySelector('.custom-end');
      const start = Math.max(0, Math.round(Number(startInput.value) / bar) * bar);
      const bars = Math.max(1, Math.round((Number(endInput.value) - Number(startInput.value)) / bar));
      startInput.value = start.toFixed(2); endInput.value = (start + bars * bar).toFixed(2);
      editor.querySelector('.custom-message').textContent = `Snapped to approximately ${bars} bar${bars === 1 ? '' : 's'} at ${Number(job.bpm || 120).toFixed(1)} BPM.`;
      updateMap();
    };
    editor.querySelector('.play-custom').onclick = () => {
      const start = Number(editor.querySelector('.custom-start').value);
      const end = Number(editor.querySelector('.custom-end').value);
      const surface = editor._customSurface;
      if (surface) {
        surface.setTime(start); surface.play();
        const stop = current => { if (current >= end) { surface.pause(); surface.un('timeupdate', stop); } };
        surface.on('timeupdate', stop);
      } else {
        sourceAudio.currentTime = start; sourceAudio.play();
        const stop = () => { if (sourceAudio.currentTime >= end) { sourceAudio.pause(); sourceAudio.removeEventListener('timeupdate', stop); } };
        sourceAudio.addEventListener('timeupdate', stop);
      }
    };
    editor.querySelector('.play-full-custom').onclick = event => {
      const surface = editor._customSurface;
      if (!surface) return;
      surface.playPause();
      event.currentTarget.textContent = surface.isPlaying() ? 'Ⅱ Pause full track' : '▶ Play full track';
    };
    const insertPanel = editor.querySelector('.insert-panel');
    editor.querySelector('.open-insert').onclick = event => {
      insertPanel.hidden = !insertPanel.hidden;
      event.currentTarget.textContent = insertPanel.hidden ? '＋ Insert this section elsewhere' : '− Hide destination editor';
      if (!insertPanel.hidden) initializeInsertionWaveform(editor, job);
    };
    editor.querySelector('.snap-insert').onclick = () => {
      const field = editor.querySelector('.insert-destination');
      const bar = 4 * 60 / Math.max(Number(job.bpm) || 120, 1);
      field.value = (Math.round(Number(field.value) / bar) * bar).toFixed(2);
      field.dispatchEvent(new Event('input'));
      editor.querySelector('.insert-message').textContent = 'Destination snapped to the nearest detected bar.';
    };
    editor.querySelector('.insert-destination').oninput = () => updateInsertionVisualization(editor);
    editor.querySelector('.insert-copies').oninput = () => updateInsertionVisualization(editor);
    editor.querySelector('.insert-zoom').oninput = event => {
      editor._insertSurface?.zoom(Number(event.target.value));
      updateInsertionVisualization(editor);
    };
    editor.querySelector('.preview-insert').onclick = async event => {
      if (arrangementPreview?.button === event.currentTarget) { stopArrangementPreview(); return; }
      const button = event.currentTarget;
      button.disabled = true; editor.querySelector('.insert-message').textContent = 'Preparing placement preview…';
      try {
        await previewArrangementInsertion(editor, job, button);
        editor.querySelector('.insert-message').textContent = 'Previewing the exact destination with the selected copy count.';
      } catch (error) {
        editor.querySelector('.insert-message').textContent = error.message || 'Could not prepare the placement preview.';
      } finally { button.disabled = false; }
    };
    editor.querySelector('.use-insert').onclick = () => {
      const start = Number(editor.querySelector('.custom-start').value);
      const end = Number(editor.querySelector('.custom-end').value);
      const destination = Number(editor.querySelector('.insert-destination').value);
      const copies = Number(editor.querySelector('.insert-copies').value);
      const extendedDuration = editor._insertWaveData?.extended?.duration;
      if (end <= start || destination < 0 || (extendedDuration && destination > extendedDuration)) {
        editor.querySelector('.insert-message').textContent = 'Choose a valid source region and destination.'; return;
      }
      arrangementInsertion = {start,end,destination,copies};
      if (editor.querySelector('.insert-also input').checked) {
        customSelections[position] = {start,end,copies:Number(editor.querySelector('.custom-copies').value)};
        delete selections[position];
      } else {
        selections[position] = 0;
        delete customSelections[position];
      }
      side.querySelector('.candidate-side-heading>span').textContent = `Insert ${clock(start)}–${clock(end)} at ${clock(destination)}`;
      editor.querySelector('.insert-message').textContent = 'Insertion selected. Reprocess to render it in the extended arrangement.';
      updateSubmit();
    };
    editor.querySelector('.use-custom').onclick = () => {
      const start = Number(editor.querySelector('.custom-start').value);
      const end = Number(editor.querySelector('.custom-end').value);
      const copies = Number(editor.querySelector('.custom-copies').value);
      if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start || start < 0 || (Number.isFinite(sourceAudio.duration) && end > sourceAudio.duration)) {
        editor.querySelector('.custom-message').textContent = 'Choose a valid start and end inside the source track.'; return;
      }
      customSelections[position] = {start,end,copies}; delete selections[position];
      side.querySelector('.candidate-side-heading>span').textContent = `Custom ${clock(start)}–${clock(end)} ×${copies}`;
      side.querySelectorAll('.candidate-card').forEach(card => card.classList.remove('decision-accept'));
      editor.querySelector('.custom-message').textContent = 'Custom candidate selected. Reprocess to render and audition it in full context.';
      updateSubmit();
    };
  });
  const needed = ['intro','outro'].filter(position => (data[position] || []).length);
  const submit = root.querySelector('.reprocess-candidates');
  const updateSubmit = () => { submit.disabled = needed.some(position => !(position in selections) && !customSelections[position]); };
  updateSubmit();
  submit.onclick = async () => {
    submit.disabled = true; submit.nextElementSibling.textContent = 'Added to the processing queue…';
    const body = {};
    if ('intro' in selections) body.intro_candidate = selections.intro;
    if ('outro' in selections) body.outro_candidate = selections.outro;
    for (const [position, custom] of Object.entries(customSelections)) {
      body[`custom_${position}_start`] = custom.start;
      body[`custom_${position}_end`] = custom.end;
      body[`custom_${position}_copies`] = custom.copies;
    }
    if (arrangementInsertion) {
      body.insert_source_start = arrangementInsertion.start;
      body.insert_source_end = arrangementInsertion.end;
      body.insert_destination = arrangementInsertion.destination;
      body.insert_copies = arrangementInsertion.copies;
    } else {
      // A fresh review decision must not inherit an insertion from its parent generation.
      body.clear_insertion = true;
    }
    body.review_candidates = true;
    const response = await fetch(`/api/jobs/${job.id}/reprocess`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if (!response.ok) { submit.disabled = false; submit.nextElementSibling.textContent = 'Could not queue this selection.'; return; }
    await loadJobs(); showView('workspace-view');
  };
}

async function initializeInsertionWaveform(editor, job) {
  if (editor._insertSurface) return;
  editor._insertJob = job;
  const [extendedResponse, sourceResponse] = await Promise.all([
    fetch(`/api/jobs/${job.id}/waveform/extended`),
    fetch(`/api/jobs/${job.id}/waveform/wav`),
  ]);
  if (!extendedResponse.ok || !sourceResponse.ok || !editor.isConnected) return;
  const wave = await extendedResponse.json();
  const sourceWave = await sourceResponse.json();
  editor._insertWaveData = {extended:wave, source:sourceWave};
  const regions = RegionsPlugin.create();
  editor._insertRegions = regions;
  const surface = WaveSurfer.create({
    container:editor.querySelector('.insert-waveform'),
    peaks:[wave.peaks], duration:wave.duration,
    height:90,waveColor:'#697061',progressColor:'#697061',cursorColor:'#ffb65c',cursorWidth:2,
    barWidth:2,barGap:1,barRadius:2,normalize:false,dragToSeek:true,
    autoCenter:true,autoScroll:true,minPxPerSec:0,
    plugins:[regions,TimelinePlugin.create({container:editor.querySelector('.insert-timeline'),style:{color:'#989991',fontSize:'9px'}})],
  });
  editor._insertSurface = surface;
  surface.once('ready', () => {
    editor._insertMarker = regions.addRegion({
      start:0, end:.08, color:'rgba(255,182,92,.24)', drag:true, resize:false,
      content:insertionWaveContent(editor, Number(editor.querySelector('.insert-copies').value)),
    });
    updateInsertionVisualization(editor);
  });
  surface.on('interaction', current => {
    editor.querySelector('.insert-destination').value = Number(current).toFixed(2);
    updateInsertionVisualization(editor);
  });
  regions.on('region-updated', region => {
    editor._syncingInsert = true;
    editor.querySelector('.insert-destination').value = region.start.toFixed(2);
    editor._syncingInsert = false;
  });
}

async function initializeCustomWaveform(editor, job) {
  if (editor._customSurface) return;
  editor.querySelector('.custom-waveform').textContent = 'Loading source waveform…';
  const response = await fetch(`/api/jobs/${job.id}/waveform/wav`);
  if (!response.ok || !editor.isConnected) {
    editor.querySelector('.custom-waveform').textContent = 'Waveform unavailable; exact timestamp controls still work.';
    return;
  }
  const wave = await response.json();
  const regions = RegionsPlugin.create();
  editor.querySelector('.custom-waveform').replaceChildren();
  const surface = WaveSurfer.create({
    container:editor.querySelector('.custom-waveform'),
    url:`/api/jobs/${job.id}/audio/wav`, peaks:[wave.peaks], duration:wave.duration,
    height:128, waveColor:'#697061', progressColor:'#b9d63c', cursorColor:'#ffb65c',
    cursorWidth:2, barWidth:2, barGap:1, barRadius:2, normalize:false, dragToSeek:true,
    autoCenter:true, autoScroll:true, minPxPerSec:0,
    plugins:[regions, TimelinePlugin.create({container:editor.querySelector('.custom-timeline'),style:{color:'#989991',fontSize:'10px'}})],
  });
  editor._customSurface = surface;
  renderArrangementTimeline(
    editor.querySelector('.custom-arrangement'), wave.timeline, wave.duration, surface,
  );
  renderCustomLegend(editor.querySelector('.custom-legend'), wave.timeline);
  editor.querySelector('.custom-zoom').oninput = event => surface.zoom(Number(event.target.value));
  const time = editor.querySelector('.custom-wave-time');
  surface.on('timeupdate', current => { time.textContent = `${clock(current)} / ${clock(wave.duration)}`; });
  surface.on('ready', () => {
    const start = Number(editor.querySelector('.custom-start').value);
    const end = Number(editor.querySelector('.custom-end').value);
    editor._customRegion = regions.addRegion({start,end,color:'rgba(214,255,68,.18)',drag:true,resize:true,minLength:.25});
    editor.querySelector('.play-full-custom').disabled = false;
  });
  surface.on('play', () => { editor.querySelector('.play-full-custom').textContent = 'Ⅱ Pause full track'; });
  surface.on('pause', () => { editor.querySelector('.play-full-custom').textContent = '▶ Play full track'; });
  regions.on('region-updated', region => {
    if (editor._syncingInputs) return;
    editor._syncingRegion = true;
    editor.querySelector('.custom-start').value = region.start.toFixed(2);
    editor.querySelector('.custom-end').value = region.end.toFixed(2);
    editor.querySelector('.custom-start').dispatchEvent(new Event('input'));
    editor._syncingRegion = false;
  });
}

function renderCustomLegend(root, timeline) {
  const colors = {
    'sparse/ambient':'#738c70', 'melodic/harmonic':'#8f78bd', 'rhythm-forward':'#4f9e91',
    'high-energy':'#c98545', 'dynamic/transition':'#b56576', 'vocal-forward':'#a66b8c',
    intro:'#718f72', verse:'#607d8b', buildup:'#b88445', drop:'#c45d43', breakdown:'#766da8',
    chorus:'#a85f73', closing:'#557f79', fade:'#59645f',
  };
  const labels = [...new Set([
    ...(timeline?.behavior || []).map(item => item.style),
    ...(timeline?.arrangement || []).map(item => item.label || item.name),
  ].filter(Boolean))];
  root.innerHTML = labels.map(label => `<span><i style="background:${colors[label] || '#657064'}"></i>${escapeHtml(label)}</span>`).join('');
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

function jobRenderSignature(job) {
  return JSON.stringify([job.status,job.progress,job.stage,job.error,job.pause_requested,job.queue_index,job.review_status,job.updated_at]);
}
function scheduleWorkspacePoll(active) {
  clearTimeout(workspacePollTimer); workspacePollTimer = null;
  if (!active) return;
  const delay = document.hidden ? 15000 : 2000;
  workspacePollTimer = setTimeout(async () => {
    if (workspacePollInFlight) return scheduleWorkspacePoll(true);
    workspacePollInFlight = true;
    try {
      const jobs = await loadJobs();
      const stillActive = jobs.some(job => ['queued','processing'].includes(job.status));
      if (!document.hidden && Date.now() >= workspaceAnalysisRefreshAt) {
        workspaceAnalysisRefreshAt = Date.now() + 15000;
        await loadAnalysis(jobs);
      }
      if (!stillActive) clearTimeout(workspacePollTimer);
    } finally { workspacePollInFlight = false; }
  }, delay);
}
document.addEventListener('visibilitychange', () => {
  if (workspacePollTimer) loadJobs();
});
async function loadJobs() {
  if (jobsLoadPromise) return jobsLoadPromise;
  jobsLoadPromise = loadJobsSnapshot().finally(() => { jobsLoadPromise = null; });
  return jobsLoadPromise;
}
async function loadJobsSnapshot() {
  const jobs = await fetch('/api/jobs', {cache:'no-store'}).then(r => r.json());
  const counts = {}; [...jobs].reverse().forEach(job => { const key=job.source_name.toLowerCase(); counts[key]=(counts[key]||0)+1; job._generation=counts[key]; });
  const completedDurations = jobs.filter(job => job.status==='complete').map(job => (new Date(job.updated_at)-new Date(job.created_at))/1000).filter(value => value>0);
  const average = completedDurations.length ? completedDurations.reduce((a,b)=>a+b,0)/completedDurations.length : 120;
  let queuePosition=0; [...jobs].reverse().forEach(job => { if(job.status==='queued'){ queuePosition++; job._eta=`~${Math.round(queuePosition*average/60)} min`; } });
  const priority = {processing:0, queued:1, review:2, failed:3, canceled:4};
  const newestByTrack = new Map();
  jobs.forEach(job => {
    const key = job.source_name.toLowerCase();
    if (!newestByTrack.has(key) || job.id > newestByTrack.get(key)) newestByTrack.set(key, job.id);
  });
  const categories = {
    active: jobs.filter(job => ['queued','processing'].includes(job.status)),
    attention: jobs.filter(job => job.review_status === 'pending' || job.review_status === 'rejected' || ['failed','canceled'].includes(job.status)),
    history: jobs.filter(job => job.status === 'complete' && !['pending','rejected'].includes(job.review_status) && newestByTrack.get(job.source_name.toLowerCase()) === job.id),
  };
  Object.entries(categories).forEach(([name,items]) => {
    const count = $(`#queue-${name}-count`); if (count) count.textContent = items.length;
  });
  const filteredJobs = categories[queueFilter].sort((a,b) => {
    const aState = a.review_status === 'pending' ? 'review' : a.status;
    const bState = b.review_status === 'pending' ? 'review' : b.status;
    const statusOrder = (priority[aState] ?? 9) - (priority[bState] ?? 9);
    if (statusOrder) return statusOrder;
    if (a.status === 'queued') return (a.queue_index ?? 9999) - (b.queue_index ?? 9999);
    return b.id - a.id;
  });
  const visibleJobs = queueFilter === 'history' ? filteredJobs.slice(0, 20) : filteredJobs;
  const processingCount=jobs.filter(job=>job.status==='processing').length;
  const queuedCount=jobs.filter(job=>job.status==='queued').length;
  $('#queue-count').textContent = queueFilter === 'active'
    ? `${processingCount} analyzing · ${queuedCount} queued`
    : queueFilter === 'history' && filteredJobs.length > visibleJobs.length
    ? `${visibleJobs.length} newest of ${filteredJobs.length}`
    : `${visibleJobs.length} track${visibleJobs.length === 1 ? '' : 's'}`;
  $('#clear-queue').disabled = !jobs.some(job => !job.is_active);
  const emptyMessages = {active:'No tracks are currently queued or processing.',attention:'Nothing needs your attention.',history:'No completed processing history yet.'};
  if (visibleJobs.length) {
    const existing=new Map([...jobsRoot.querySelectorAll('.job-card[data-job-id]')].map(node=>[Number(node.dataset.jobId),node]));
    const nodes=visibleJobs.map(job=>{const current=existing.get(Number(job.id));return current?.dataset.renderSignature===jobRenderSignature(job)?current:jobElement(job);});
    jobsRoot.replaceChildren(...nodes);
  } else jobsRoot.replaceChildren(Object.assign(document.createElement('div'), { className:'empty', textContent:emptyMessages[queueFilter] }));
  const active = jobs.some(job => ['queued', 'processing'].includes(job.status));
  scheduleWorkspacePoll(active);
  return jobs;
}

$$('[data-queue-filter]').forEach(button => button.addEventListener('click', () => {
  queueFilter = button.dataset.queueFilter;
  $$('[data-queue-filter]').forEach(item => item.classList.toggle('active', item === button));
  loadJobs();
}));

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
  $, apiErrorMessage, operationReceiptText, downloadedUiState,
  setAppConfig: payload => { appConfig.effective=payload.effective;appConfig.overrides=payload.overrides; },
  applyEffectiveSettings, loadConfig, loadPresets, editPreset,
  getPresetLibrary: () => presetLibrary,
  loadJobs, loadAnalysis, loadDownloadedLibrary, loadLibrary,
  invalidateCatalogs: () => { downloadedLoadedAt=0;libraryLoadedAt=0; },
  loadPerformanceDiagnostics, escapeHtml, confirmAction, reportDate,
  libraryAvailabilityView,
});
const {loadLibraryHealth, loadLibraryStatus, loadRelocationState, loadBackups, loadStorageManager} = settingsFeature;
async function refresh() { const jobs = await loadJobs(); await loadAnalysis(jobs); }
settingsFeature.initialize(refresh);
