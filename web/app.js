import WaveSurfer from '/vendor/wavesurfer/wavesurfer.esm.js';
import RegionsPlugin from '/vendor/wavesurfer/plugins/regions.esm.js';
import TimelinePlugin from '/vendor/wavesurfer/plugins/timeline.esm.js';
import HoverPlugin from '/vendor/wavesurfer/plugins/hover.esm.js';

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function notify(message, tone = 'info', options = {}) {
  const region = $('#app-toast-region');
  if (!region || !message) return;
  const toast = document.createElement('article');
  toast.className = 'app-toast';
  toast.dataset.tone = tone;
  toast.setAttribute('role', tone === 'danger' ? 'alert' : 'status');
  const text = document.createElement('span');
  text.textContent = String(message);
  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'toast-close';
  close.setAttribute('aria-label', 'Dismiss notification');
  close.textContent = '×';
  close.addEventListener('click', () => toast.remove());
  toast.append(text, close);
  region.append(toast);
  requestAnimationFrame(() => toast.classList.add('visible'));
  const timeout = Number(options.timeout ?? (tone === 'danger' ? 7000 : 4200));
  if (timeout > 0) setTimeout(() => { toast.classList.remove('visible'); setTimeout(() => toast.remove(), 180); }, timeout);
}

function confirmAction(message, options = {}) {
  const dialog = $('#app-confirm-dialog');
  if (!dialog?.showModal) return Promise.resolve(window.confirm(message));
  $('#app-confirm-title').textContent = options.title || 'Confirm action';
  $('#app-confirm-message').textContent = message;
  const accept = $('#app-confirm-accept');
  accept.textContent = options.acceptLabel || 'Continue';
  accept.dataset.tone = options.danger ? 'danger' : 'success';
  return new Promise(resolve => {
    const finish = () => resolve(dialog.returnValue === 'confirm');
    dialog.addEventListener('close', finish, {once:true});
    dialog.showModal();
  });
}

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
            if (select.id === 'set-genre') setGenreSelectionOrder = [];
          } else {
            if (any) any.selected = false;
            option.selected = !option.selected;
            if (select.id === 'set-genre' && option.selected && !setGenreSelectionOrder.includes(option.value)) setGenreSelectionOrder.push(option.value);
            if (select.id === 'set-genre' && !option.selected) setGenreSelectionOrder = setGenreSelectionOrder.filter(value => value !== option.value);
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
let reportSongs = [];
let reportJobs = [];
let reportFeedback = [];
let reportKeyVerificationStats = {items:[], total:0, detector_accuracy:{}};
let reportDetailBodies = new Map();
let reportPage = 1;
let reportPageSize = 50;
let arrangementPreview = null;
let stagedFiles = [];
let workspaceMode = 'analyze';
let setBuilderLibrary = [];
let currentSetPlan = [];
let setRequiredIds = new Set();
let setExcludedIds = new Set();
let setLockedIds = new Set();
let setBuilderBound = false;
let setGenreSelectionOrder = [];
let setGenerationNonce = 0;
let setProposals = [];
let activeSetProposal = '';
let setPlanHistory = [];
let setPlanFuture = [];
let transitionPreviewAudio = [];
let transitionPreviewFrame = 0;
let transitionPreviewTimer = 0;
let transitionPreviewPlayheadFrame = 0;
let transitionPreviewState = null;
const compactAudioEngine = new Audio();
compactAudioEngine.preload = 'none';
let compactAudioOwner = null;
let setCompactMode = localStorage.getItem('set-builder-compact') === 'true';
let setTransitionSettings = {};
let transitionEditorSurfaces = [];
const transitionWaveCache = new Map();
const downloadedUiState = {search:'', genre:'all', detailedGenre:'all', playlist:'all', analysis:'all', artwork:'all', quality:'all', sort:'newest', page:1, pageSize:Number(localStorage.getItem('music-files-page-size') || 50)};
const downloadedSelection = new Map();
let downloadedLoadSequence = 0;
let downloadedSearchTimer = null;
let downloadedRequestController = null;
let downloadedLoadedAt = 0;
let libraryLoadedAt = 0;
let librarySearchTimer = null;
const libraryUiState = {search:'',role:'all',category:'all',detailedGenre:'all',preset:'all',sort:'newest',result:'all',quality:'all',bpmMin:'',bpmMax:'',key:'all',energy:'all',vocals:'all',timing:'all',page:1,pageSize:Number(localStorage.getItem('dj-library-page-size') || 50)};
let libraryLoadSequence = 0;
let libraryRequestController = null;
let pendingMetadataReview = null;
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

function bindLazyAudio(scope = document) {
  scope.querySelectorAll('audio[data-src]').forEach(audio => {
    if (audio.dataset.lazyBound === 'true') return;
    audio.dataset.lazyBound = 'true';
    const activate = () => {
      if (audio.getAttribute('src')) return;
      audio.src = audio.dataset.src;
      audio.removeAttribute('data-src');
      audio.load();
    };
    audio.addEventListener('pointerdown', activate, {once:true});
    audio.addEventListener('focus', activate, {once:true});
    audio.addEventListener('keydown', activate, {once:true});
  });
}

function compactAudioMarkup(src, duration=0, seekable=false) {
  return `<div class="compact-audio${seekable?' seekable':''}" data-src="${escapeHtml(src)}" data-duration="${Number(duration)||0}"><button type="button" class="compact-audio-play" aria-label="Play track">▶</button><span class="compact-audio-time">0:00 / ${clock(duration)}</span>${seekable?'<input class="compact-audio-seek" type="range" min="0" max="1000" value="0" aria-label="Seek through track">':''}<button type="button" class="compact-audio-volume" aria-label="Mute track">🔊</button></div>`;
}

function renderCompactAudio(player=compactAudioOwner) {
  if (!player?.isConnected) return;
  const duration=Number.isFinite(compactAudioEngine.duration)?compactAudioEngine.duration:Number(player.dataset.duration||0);
  const time=player.querySelector('.compact-audio-time');const seek=player.querySelector('.compact-audio-seek');
  time.textContent=`${clock(compactAudioEngine.currentTime||0)} / ${clock(duration)}`;
  if(seek&&!seek.matches(':active'))seek.value=duration?String(Math.round((compactAudioEngine.currentTime||0)/duration*1000)):'0';
}

function stopCompactAudio() {
  compactAudioEngine.pause();compactAudioEngine.currentTime=0;
  if(compactAudioOwner?.isConnected){const play=compactAudioOwner.querySelector('.compact-audio-play');if(play){play.textContent='▶';play.setAttribute('aria-label','Play track');}renderCompactAudio(compactAudioOwner);}
  compactAudioOwner=null;
}

function stopNativeAudio(except = null, scope = document) {
  scope.querySelectorAll('audio,video').forEach(media => {
    if (media !== except && !media.paused) media.pause();
  });
}

function closeDownloadedInspector({restoreFocus=false} = {}) {
  const inspector=$('#downloaded-inspector');
  if (!inspector || inspector.hidden) return;
  stopNativeAudio(null, inspector);
  inspector.hidden=true;
  if (restoreFocus) document.querySelector(`.downloaded-card[data-id="${inspector.dataset.returnId}"]`)?.focus();
}

function bindCompactAudio(scope = document) {
  scope.querySelectorAll('.compact-audio').forEach(player => {
    if (player.dataset.bound === 'true') return;
    player.dataset.bound = 'true';
    const play=player.querySelector('.compact-audio-play');const volume=player.querySelector('.compact-audio-volume');const seek=player.querySelector('.compact-audio-seek');
    const activate=()=>{if(compactAudioOwner===player)return;if(compactAudioOwner?.isConnected){const oldPlay=compactAudioOwner.querySelector('.compact-audio-play');if(oldPlay){oldPlay.textContent='▶';oldPlay.setAttribute('aria-label','Play track');}}compactAudioEngine.pause();compactAudioOwner=player;compactAudioEngine.src=player.dataset.src;compactAudioEngine.load();};
    play.onclick=async event=>{event.stopPropagation();const wasOwner=compactAudioOwner===player;activate();if(!wasOwner||compactAudioEngine.paused){stopNativeAudio();try{await compactAudioEngine.play();}catch(_){play.textContent='▶';}}else compactAudioEngine.pause();};
    volume.onclick=event=>{event.stopPropagation();activate();compactAudioEngine.muted=!compactAudioEngine.muted;volume.textContent=compactAudioEngine.muted?'🔇':'🔊';volume.setAttribute('aria-label',compactAudioEngine.muted?'Unmute track':'Mute track');};
    if(seek){seek.onpointerdown=event=>event.stopPropagation();seek.onclick=event=>event.stopPropagation();seek.oninput=event=>{event.stopPropagation();activate();const duration=Number.isFinite(compactAudioEngine.duration)?compactAudioEngine.duration:Number(player.dataset.duration||0);if(duration)compactAudioEngine.currentTime=Number(seek.value)/1000*duration;renderCompactAudio(player);};}
  });
}

compactAudioEngine.addEventListener('play',()=>{const play=compactAudioOwner?.querySelector('.compact-audio-play');if(play){play.textContent='❚❚';play.setAttribute('aria-label','Pause track');}});
compactAudioEngine.addEventListener('pause',()=>{const play=compactAudioOwner?.querySelector('.compact-audio-play');if(play){play.textContent='▶';play.setAttribute('aria-label','Play track');}});
compactAudioEngine.addEventListener('ended',()=>{compactAudioEngine.currentTime=0;renderCompactAudio();});
compactAudioEngine.addEventListener('loadedmetadata',()=>renderCompactAudio());
compactAudioEngine.addEventListener('timeupdate',()=>renderCompactAudio());

function renderTrackPagination(container, page, totalPages, totalItems, onPage) {
  container.hidden = totalPages <= 1;
  if (container.hidden) { container.replaceChildren(); return; }
  const candidates = [...new Set([1,page-2,page-1,page,page+1,page+2,totalPages].filter(value => value >= 1 && value <= totalPages))].sort((a,b) => a-b);
  let previous = 0;
  const pages = candidates.map(value => { const gap = previous && value - previous > 1 ? '<span class="page-gap">…</span>' : ''; previous = value; return `${gap}<button type="button" class="page-number${value === page ? ' active' : ''}" data-page="${value}"${value === page ? ' aria-current="page"' : ''}>${value}</button>`; }).join('');
  container.innerHTML = `<button type="button" class="page-previous"${page <= 1 ? ' disabled' : ''}>← Previous</button><span class="page-numbers">${pages}</span><span class="page-summary">Page ${page} of ${totalPages} · ${totalItems} tracks</span><button type="button" class="page-next"${page >= totalPages ? ' disabled' : ''}>Next →</button>`;
  container.querySelector('.page-previous').onclick = () => onPage(page - 1);
  container.querySelector('.page-next').onclick = () => onPage(page + 1);
  container.querySelectorAll('.page-number').forEach(button => button.onclick = () => onPage(Number(button.dataset.page)));
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

function option(value, label = value) {
  const node = document.createElement('option');
  node.value = value; node.textContent = label; return node;
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
  $('#batch-intro-search').value = values.intro_search_seconds;
  $('#batch-outro-search').value = values.outro_search_seconds;
  $('#batch-vocal-coverage').value = values.maximum_vocal_coverage_percent;
  $('#batch-vocal-risk').value = values.maximum_vocal_boundary_risk_percent;
  $('#batch-buildup-risk').value = values.maximum_buildup_risk_percent;
  $('#batch-bass-risk').value = values.maximum_bass_reset_risk_percent;
  $('#batch-stem-reliability').value = values.minimum_stem_reliability_percent;
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
  $('#setting-intro-search').value = values.intro_search_seconds;
  $('#setting-outro-search').value = values.outro_search_seconds;
  $('#setting-vocal-coverage').value = values.maximum_vocal_coverage_percent;
  $('#setting-vocal-risk').value = values.maximum_vocal_boundary_risk_percent;
  $('#setting-buildup-risk').value = values.maximum_buildup_risk_percent;
  $('#setting-bass-risk').value = values.maximum_bass_reset_risk_percent;
  $('#setting-stem-reliability').value = values.minimum_stem_reliability_percent;
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

function showView(id) {
  if (compactAudioOwner && !compactAudioOwner.closest(`#${id}`)) stopCompactAudio();
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
  if (id === 'settings-view') { loadPresets(); loadPerformanceDiagnostics(); loadStorageManager(); loadBackups(); }
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
let authorizedImportQueue=null;
function renderAuthorizedImportQueue(){
  const queue=authorizedImportQueue;if(!queue)return;
  const panel=$('#authorized-import-queue'),list=$('#authorized-import-queue-list'),progress=$('#authorized-import-progress');panel.hidden=false;progress.hidden=false;
  const terminal=queue.items.filter(item=>['complete','failed','canceled'].includes(item.status)),percent=queue.items.reduce((sum,item)=>sum+Number(item.progress||0),0)/Math.max(1,queue.items.length);
  progress.querySelector('span').style.width=`${Math.max(2,percent)}%`;progress.querySelector('small').textContent=`${terminal.length} of ${queue.items.length} finished · ${queue.paused?'Queue paused':queue.active+' active'} · ${Math.round(percent)}%`;
  $('#authorized-import-queue-summary').textContent=`${queue.items.filter(item=>item.status==='waiting').length} waiting · ${queue.active} active`;
  $('#authorized-import-pause').textContent=queue.paused?'Resume queue':'Pause queue';
  $('#authorized-import-retry').disabled=!queue.items.some(item=>['failed','canceled'].includes(item.status));
  list.innerHTML=queue.items.map((item,index)=>`<article class="authorized-import-queue-item" data-index="${index}" data-status="${item.status}"><div><strong>${escapeHtml(item.url)}</strong><small>${escapeHtml(item.stage||item.status)}${item.error?` · ${escapeHtml(item.error)}`:''}</small></div><div class="authorized-import-queue-actions">${item.status==='waiting'?`<button type="button" data-action="up" aria-label="Move up" ${index===0?'disabled':''}>↑</button><button type="button" data-action="down" aria-label="Move down" ${index===queue.items.length-1?'disabled':''}>↓</button>`:''}${['waiting','processing'].includes(item.status)?'<button type="button" data-action="cancel">Cancel</button>':''}${['failed','canceled'].includes(item.status)?'<button type="button" data-action="retry">Retry</button>':''}</div></article>`).join('');
  list.querySelectorAll('button').forEach(button=>button.onclick=async()=>{const index=Number(button.closest('article').dataset.index),item=queue.items[index],action=button.dataset.action;if(action==='up'&&index>0)[queue.items[index-1],queue.items[index]]=[item,queue.items[index-1]];if(action==='down'&&index<queue.items.length-1)[queue.items[index+1],queue.items[index]]=[item,queue.items[index+1]];if(action==='cancel'){if(item.importId)await fetch(`/api/imports/${item.importId}/cancel`,{method:'POST'});else{item.status='canceled';item.stage='Canceled before download';item.progress=100;}}if(action==='retry'){Object.assign(item,{status:'waiting',stage:'Waiting to retry',progress:0,error:'',importId:null});}renderAuthorizedImportQueue();queue.schedule();});
}
async function importAuthorizedSources(urls,basePayload){
  const metadata=urls.length===1?{title:currentSourceMetadata?.title||'',artist:currentSourceMetadata?.artist||'',spotify_uri:currentSourceMetadata?.spotify_uri||'',artwork_url:currentSourceMetadata?.thumbnail_url||''}:{title:'',artist:'',spotify_uri:'',artwork_url:''};
  const queue={items:urls.map(url=>({url,status:'waiting',stage:'Waiting',progress:0,error:'',importId:null})),active:0,paused:false,finished:false,schedule:null};authorizedImportQueue=queue;
  const done=new Promise(resolve=>queue.resolve=resolve);
  const run=async item=>{queue.active++;item.status='processing';item.stage='Preparing';item.progress=1;renderAuthorizedImportQueue();try{const response=await fetch('/api/imports/authorized',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...basePayload,url:item.url,...metadata})}),payload=await response.json();if(!response.ok)throw new Error(payload.detail||'Could not start import.');item.importId=payload.import_id;const result=await waitForAuthorizedImport(payload.import_id,item.url,(value,stage)=>{item.progress=value;item.stage=stage;renderAuthorizedImportQueue();});Object.assign(item,{...result,status:result.status,progress:100,stage:result.status==='complete'?'Complete':result.status==='canceled'?'Canceled':'Failed',error:result.error||''});}catch(error){Object.assign(item,{status:'failed',stage:'Failed',progress:100,error:error.message});}finally{queue.active--;renderAuthorizedImportQueue();queue.schedule();}};
  queue.schedule=()=>{if(queue.finished)return;while(!queue.paused&&queue.active<2){const next=queue.items.find(item=>item.status==='waiting');if(!next)break;run(next);}const pending=queue.items.some(item=>['waiting','processing'].includes(item.status));if(!pending&&queue.active===0){queue.finished=true;queue.resolve();}};
  renderAuthorizedImportQueue();queue.schedule();await done;
  const completed=queue.items.filter(item=>item.status==='complete'),failed=queue.items.filter(item=>item.status!=='complete'),message=$('#authorized-import-message');message.innerHTML=`<strong>${completed.length} of ${queue.items.length} sources imported.</strong>${failed.length?`<span>${failed.length} failed or canceled. Use Retry in the queue when ready.</span>`:''}${completed.length===1?` <a href="/api/imports/${completed[0].importId}/download">Download WAV</a>`:''}`;$('#authorized-import-submit').disabled=false;if(!failed.length)$('#authorized-import-form').reset();await loadJobs();
}
$('#authorized-import-pause').onclick=()=>{if(!authorizedImportQueue)return;authorizedImportQueue.paused=!authorizedImportQueue.paused;renderAuthorizedImportQueue();authorizedImportQueue.schedule();};
$('#authorized-import-retry').onclick=()=>{if(!authorizedImportQueue)return;authorizedImportQueue.finished=false;authorizedImportQueue.items.filter(item=>['failed','canceled'].includes(item.status)).forEach(item=>Object.assign(item,{status:'waiting',stage:'Waiting to retry',progress:0,error:'',importId:null}));renderAuthorizedImportQueue();authorizedImportQueue.schedule();};
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
  if (!response.ok) alert((await response.json()).detail || `Could not ${action} job.`);
  await loadJobs();
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
  const [sourceWave, extendedWave, cues, override] = await Promise.all([
    fetch(`/api/jobs/${job.id}/waveform/wav`).then(r => r.ok ? r.json() : null),
    fetch(`/api/jobs/${job.id}/waveform/extended`).then(r => r.ok ? r.json() : null),
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

async function loadDownloadedLibrary() {
  const sequence = ++downloadedLoadSequence;
  downloadedRequestController?.abort();
  downloadedRequestController = new AbortController();
  const view = $('#downloads-view');
  view.classList.add('view-refreshing');
  const parameters = new URLSearchParams({paged:'true',page:String(downloadedUiState.page),page_size:String(downloadedUiState.pageSize),search:downloadedUiState.search,genre:downloadedUiState.genre,detailed_genre:downloadedUiState.detailedGenre,playlist:downloadedUiState.playlist,analysis:downloadedUiState.analysis,artwork:downloadedUiState.artwork,quality:downloadedUiState.quality,sort:downloadedUiState.sort});
  let payload;
  try {
    const response = await fetch(`/api/downloaded-library?${parameters}`, {cache:'no-store',signal:downloadedRequestController.signal});
    if (!response.ok) throw new Error('Music Files could not be loaded.');
    payload = await response.json();
  } catch (error) {
    if (error.name === 'AbortError') return;
    throw error;
  } finally {
    if (sequence === downloadedLoadSequence) view.classList.remove('view-refreshing');
  }
  if (sequence !== downloadedLoadSequence) return;
  downloadedLoadedAt = Date.now();
  const tracks = payload.tracks || [];
  const paginationData = payload.pagination || {page:1,page_size:50,filtered_total:tracks.length,catalog_total:tracks.length,total_pages:1};
  const analyzableTotal = Number(paginationData.analyzable_total || 0);
  downloadedUiState.page = paginationData.page;
  const root = $('#downloaded-list');
  if (compactAudioOwner?.closest('#downloaded-list')) stopCompactAudio();
  const summary = $('#downloaded-summary');
  const genreEntries = Object.entries(payload.genres || {});
  const detailedGenreEntries = Object.entries(payload.detailed_genres || {}).sort(([a],[b])=>a.localeCompare(b));
  const detailedGenresByCategory = payload.detailed_genres_by_category || {};
  const playlistEntries = Object.entries(payload.playlists || {});
  const reviewStates = payload.review_states || {};
  const needsGenreCount = Number(reviewStates.needs_attention||0);
  summary.innerHTML = `<div class="downloaded-sidebar-head"><div><p class="eyebrow">MUSIC FILES</p><h2>Browse collection</h2><span>${paginationData.catalog_total} downloaded track${paginationData.catalog_total===1?'':'s'}</span></div><button type="button" class="downloaded-sidebar-toggle" aria-label="Collapse Music Files crates" title="Collapse Music Files crates">‹</button></div>
    <nav class="downloaded-folder-nav" aria-label="Music file folders">
      <div class="folder-heading"><span>Collection</span></div>
      <button type="button" class="filter-downloaded-genre" data-value="all"><span>All downloads</span><b>${paginationData.catalog_total}</b></button>
      <details class="genre-folder-group needs-genre-group" data-folder="Needs genre review"${collapsedGenreFolders.has('Needs genre review')?'':' open'}><summary><span>Needs attention</span><b>${needsGenreCount}</b><i aria-hidden="true">›</i></summary><div>
        <button type="button" class="filter-downloaded-analysis needs-genre nested" data-value="attention"><span>Review all</span><b>${needsGenreCount}</b></button>
        <p class="attention-group-label">Missing information</p>
        <button type="button" class="filter-downloaded-analysis needs-genre nested" data-value="missing_title"><span>Title</span><b>${reviewStates.missing_title||0}</b></button>
        <button type="button" class="filter-downloaded-analysis needs-genre nested" data-value="missing_artist"><span>Artist</span><b>${reviewStates.missing_artist||0}</b></button>
        <button type="button" class="filter-downloaded-analysis needs-genre nested" data-value="missing_genre"><span>Genre tags</span><b>${reviewStates.missing_genre||0}</b></button>
        <button type="button" class="filter-downloaded-analysis needs-genre nested" data-value="missing_artwork"><span>Artwork</span><b>${reviewStates.missing_artwork||0}</b></button>
        <p class="attention-group-label">Classification issues</p>
        <button type="button" class="filter-downloaded-analysis needs-genre nested" data-value="unmapped_genre"><span>Unrecognized genre</span><b>${reviewStates.unmapped_genre||0}</b></button>
        <button type="button" class="filter-downloaded-analysis needs-genre nested" data-value="broad_genre"><span>Needs a specific genre</span><b>${reviewStates.broad_genre||0}</b></button>
      </div></details>
      <div class="folder-heading genre-heading"><span>Genre folders</span><button type="button" class="collapse-genre-folders">Collapse all</button></div>
      ${genreFolderTree(genreEntries,'filter-downloaded-genre') || '<p>No genre folders yet.</p>'}
      <details class="downloaded-detailed-genres"${downloadedUiState.detailedGenre!=='all'?' open':''}><summary><span>Detailed genres</span><b>${detailedGenreEntries.length}</b><i aria-hidden="true">›</i></summary><div>
        <input class="detailed-genre-search" type="search" placeholder="Find a genre…" aria-label="Search detailed genres">
        <button type="button" class="filter-detailed-genre${downloadedUiState.detailedGenre==='all'?' active':''}" data-value="all"><span>All detailed genres</span></button>
        <div class="detailed-genre-list">${detailedGenreEntries.map(([name,count])=>`<button type="button" class="filter-detailed-genre${downloadedUiState.detailedGenre===name?' active':''}" data-value="${escapeHtml(name)}" data-search="${escapeHtml(name.toLowerCase())}"><span>${escapeHtml(name)}</span><b>${count}</b></button>`).join('')}</div>
        <p class="detailed-genre-empty" hidden>No detailed genres match.</p>
      </div></details>
    </nav>
    <details class="downloaded-playlist-nav"><summary>Source playlists <b>${playlistEntries.length}</b></summary><div>${playlistEntries.map(([playlist,count]) => `<button type="button" class="filter-downloaded-playlist" data-value="${escapeHtml(playlist)}"><span>${escapeHtml(playlist)}</span><b>${count}</b></button>`).join('') || '<p>No playlists yet.</p>'}</div></details>
    <details class="downloaded-tools"><summary><span>Music file tools</span><i aria-hidden="true">›</i></summary><div>
      <section class="music-tool-row"><div><strong>Reconcile files</strong><p>Check new or modified source records against the catalog.</p></div><button type="button" class="sidebar-reconcile">Run</button></section>
      <section class="music-tool-row"><div><strong>Rescan genres</strong><p>Re-read saved tags and reorganize WAV folders.</p></div><button type="button" class="sidebar-rescan">Run</button></section>
      <section class="music-tool-row"><div><strong>Sync artwork</strong><p>Find and embed cover art for existing tracks.</p></div><button type="button" class="sidebar-artwork">Run</button></section>
    </div></details>`;
  const downloadsLayout = document.querySelector('.downloads-layout');
  const downloadsSidebarToggle = summary.querySelector('.downloaded-sidebar-toggle');
  const setDownloadsSidebarCollapsed = collapsed => {
    downloadsLayout.classList.toggle('sidebar-collapsed', collapsed);
    downloadsSidebarToggle.textContent = collapsed ? '›' : '‹';
    downloadsSidebarToggle.setAttribute('aria-label', collapsed ? 'Expand Music Files crates' : 'Collapse Music Files crates');
    downloadsSidebarToggle.title = downloadsSidebarToggle.getAttribute('aria-label');
    localStorage.setItem('dj-music-files-crates-collapsed', String(collapsed));
  };
  setDownloadsSidebarCollapsed(localStorage.getItem('dj-music-files-crates-collapsed') === 'true');
  downloadsSidebarToggle.onclick = () => setDownloadsSidebarCollapsed(!downloadsLayout.classList.contains('sidebar-collapsed'));
  bindGenreFolderState(summary);
  summary.querySelector('.collapse-genre-folders').onclick = () => {
    summary.querySelectorAll('.downloaded-folder-nav>.genre-folder-group:not(.needs-genre-group)').forEach(folder => { folder.open=false; });
  };
  if (!tracks.length) {
    root.innerHTML = paginationData.catalog_total ? '<div class="empty">No tracks match the current filters.</div>' : '<div class="empty">No downloaded tracks yet. Complete an import to add the WAV here automatically.</div>';
  } else {
    root.innerHTML = tracks.map(track => {
      const state = track.analysis_status || 'not_analyzed';
      const label = {not_analyzed:'Ready to analyze',queued:'Queued',processing:'Analyzing',complete:'Analyzed',failed:'Analysis failed',canceled:'Analysis canceled'}[state] || state;
      const genre = track.genre_category || 'Other';
      const artwork = track.artwork_available ? `<img src="/api/downloaded-library/tracks/${track.id}/artwork?thumbnail=true" alt="" loading="lazy" decoding="async">` : '♫';
      const detailed = detailedGenreSummary(track.genre);
      const identity = `${track.recording_code || 'OTH-PENDING'}-${track.version_code || 'ORG'}`;
      return `<article class="panel downloaded-card" data-id="${track.id}" data-available="${track.available ? 'true' : 'false'}" data-analysis-status="${escapeHtml(state)}" data-title="${escapeHtml(String(track.title || '').toLowerCase())}" data-artist="${escapeHtml(String(track.artist || '').toLowerCase())}" data-genre="${escapeHtml(genre)}" data-needs-genre="${track.needs_genre ? 'true' : 'false'}" data-playlists="${escapeHtml((track.playlists || []).join('|'))}" data-imported="${escapeHtml(track.imported_at || '')}"><label class="downloaded-check"><input type="checkbox" value="${track.id}" aria-label="Select ${escapeHtml(track.title || track.filename)}"${downloadedSelection.has(Number(track.id)) ? ' checked' : ''}><span></span></label><div class="downloaded-row-icon">${artwork}</div><div class="downloaded-copy"><h3>${escapeHtml(track.title || track.filename)}</h3><p>${escapeHtml(track.artist || 'Unknown artist')}</p><small class="track-identity" title="Permanent recording identity">${escapeHtml(identity)}</small></div><div class="downloaded-genre-cell"><button type="button" class="downloaded-genre edit-downloaded-genre" title="Change primary genre">${escapeHtml(genre)}</button><button type="button" class="downloaded-detailed-genre${detailed.empty?' empty':''}" title="${escapeHtml(detailed.title)}"${detailed.empty?' disabled':''}>${escapeHtml(detailed.label)}</button></div><span class="downloaded-analysis-status" data-status="${escapeHtml(state)}">${escapeHtml(label)}</span>${compactAudioMarkup(`/api/downloaded-library/tracks/${track.id}/audio`,track.duration_seconds)}<details class="downloaded-actions"><summary aria-label="Track actions">•••</summary><div><button type="button" class="inspect-downloaded">Quick view</button><button type="button" class="edit-track-metadata">Edit metadata</button>${state === 'complete' ? '<button type="button" class="view-downloaded-library">View in DJ Library</button>' : ''}${track.available ? `<a href="/api/downloaded-library/tracks/${track.id}/download">Download WAV</a>` : '<span>File unavailable</span>'}<button type="button" class="edit-downloaded-genre">Change genre</button><button type="button" class="remove-downloaded danger-text">Remove from catalog</button></div></details>${genreEditorMarkup(genre, track.suggested_genre)}${metadataEditorMarkup(track)}</article>`;
    }).join('');
  }
  const genreSelect = $('#downloaded-genre'); const detailedGenreSelect=$('#downloaded-detailed-genre-filter'); const playlistSelect = $('#downloaded-playlist');
  const genreNames = [...new Set(genreEntries.flatMap(([name])=>{
    const parts=String(name).split(' / ');
    return parts.map((_,index)=>parts.slice(0,index+1).join(' / '));
  }))];
  const playlistNames = playlistEntries.map(([name]) => name);
  if (String(downloadedUiState.genre).startsWith('__')) downloadedUiState.genre = 'all';
  if (downloadedUiState.genre !== 'all' && !genreNames.includes(downloadedUiState.genre)) genreNames.push(downloadedUiState.genre);
  if (downloadedUiState.playlist !== 'all' && !playlistNames.includes(downloadedUiState.playlist)) playlistNames.push(downloadedUiState.playlist);
  genreSelect.replaceChildren(option('all','All parent genres'),...genreNames.sort().map(name=>option(name,name)));
  const availableDetailedGenres=downloadedUiState.genre==='all'
    ? detailedGenreEntries
    : Object.entries(Object.entries(detailedGenresByCategory).reduce((counts,[category,tags])=>{
        if(category===downloadedUiState.genre||category.startsWith(`${downloadedUiState.genre} / `))Object.entries(tags).forEach(([tag,count])=>{counts[tag]=(counts[tag]||0)+Number(count);});
        return counts;
      },{})).sort(([a],[b])=>a.localeCompare(b));
  detailedGenreSelect.replaceChildren(option('all',downloadedUiState.genre==='all'?'All detailed genres':'Any detailed genre'),...availableDetailedGenres.map(([name,count])=>option(name,`${name} (${count})`)));
  playlistSelect.replaceChildren(option('all','All playlists'), ...playlistNames.sort().map(name => option(name,name)));
  const cards = [...root.querySelectorAll('.downloaded-card')];
  const pagination = $('#downloaded-pagination');
  const paginationTop = $('#downloaded-pagination-top');
  const pageSizeSelect = $('#downloaded-page-size');
  let pageSize = downloadedUiState.pageSize;
  pageSizeSelect.value = String(pageSize);
  let currentPage = paginationData.page;
  const search = $('#downloaded-search'); const analysisSelect = $('#downloaded-analysis'); const artworkSelect = $('#downloaded-artwork'); const qualitySelect=$('#downloaded-quality'); const sort = $('#downloaded-sort');
  search.value = downloadedUiState.search;
  genreSelect.value = [...genreSelect.options].some(item => item.value === downloadedUiState.genre) ? downloadedUiState.genre : 'all';
  detailedGenreSelect.value=[...detailedGenreSelect.options].some(item=>item.value===downloadedUiState.detailedGenre)?downloadedUiState.detailedGenre:'all';
  playlistSelect.value = [...playlistSelect.options].some(item => item.value === downloadedUiState.playlist) ? downloadedUiState.playlist : 'all';
  analysisSelect.value = downloadedUiState.analysis;
  artworkSelect.value = downloadedUiState.artwork;
  qualitySelect.value = downloadedUiState.quality;
  sort.value = downloadedUiState.sort;
  const selectAll = $('#downloaded-select-all'); const clearSelection = $('#downloaded-clear-selection'); const analyzeSelected = $('#downloaded-analyze-selected'); const keyAnalyzeSelected=$('#downloaded-key-analyze-selected'); const analyzeMatching = $('#downloaded-analyze-matching'); const reanalyzeSelected = $('#downloaded-reanalyze-selected'); const reanalyzeMatching = $('#downloaded-reanalyze-matching'); const downloadSelected = $('#downloaded-download-selected'); const removeSelected = $('#downloaded-remove-selected'); const changeGenre = $('#downloaded-change-genre'); const retagSelected = $('#downloaded-retag-selected');
  const rescanGenres = $('#downloaded-rescan-genres');
  const reconcileFiles = $('#downloaded-reconcile-files');
  const retagAll = $('#downloaded-retag-all');
  const syncArtwork = $('#downloaded-sync-artwork');
  const progressPanel = $('#downloaded-maintenance-progress');
  const progressDismiss = $('#downloaded-progress-dismiss');
  progressDismiss.onclick = () => { progressPanel.hidden = true; };
  const renderMaintenanceProgress = (title, batch, detail) => {
    const percent = batch.total ? Math.round(Number(batch.processed || 0) / Number(batch.total) * 100) : 100;
    progressPanel.hidden = false;
    $('#downloaded-progress-title').textContent = title;
    $('#downloaded-progress-percent').textContent = `${percent}%`;
    $('#downloaded-progress-bar').value = percent;
    $('#downloaded-progress-detail').textContent = detail;
    progressPanel.classList.toggle('complete', batch.status === 'complete');
    progressPanel.classList.toggle('failed', batch.status === 'failed');
  };
  const renderProgressError = (title, error) => {
    renderMaintenanceProgress(title, {total:1,processed:1,status:'failed'}, error.message || String(error));
  };
  const integrityRoot=$('#downloaded-integrity'); const integrityButton=$('#downloaded-integrity-scan'); const integrityStatus=$('#downloaded-integrity-status'); const integrityResults=$('#downloaded-integrity-results');
  const integrityGroups={missing_files:['Missing WAV files','remove-missing','Remove catalog entries'],uncataloged_files:['Uncataloged WAV files','catalog-uncataloged','Add to catalog'],duplicate_records:['Possible duplicate records',null,null],stale_sidecars:['Stale metadata records','delete-stale-sidecars','Delete stale records'],broken_analysis_links:['Broken analysis links',null,null],tag_mismatches:['WAV tags differ from catalog','retag-mismatches','Rewrite tags from catalog'],unreadable_tags:['Unreadable WAV metadata',null,null]};
  const runIntegrityRepair=async(action,items,label)=>{
    if(!items.length||!await confirmAction(`${label} for ${items.length} item${items.length===1?'':'s'}? Only this listed issue group will be changed.`, {title:'Apply integrity repair', acceptLabel:label}))return;
    const response=await fetch('/api/downloaded-library/integrity-repair',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,item_ids:items.map(item=>item.id)})}); const payload=await response.json();
    if(!response.ok){integrityStatus.textContent=payload.detail||'The repair could not be completed.';return;}
    integrityStatus.textContent=`Repair complete · ${payload.updated||0} item${payload.updated===1?'':'s'} updated. Run the scan again to verify.`; await loadDownloadedLibrary(); integrityRoot.open=true;
  };
  const duplicateFindingMarkup=item=>{
    const ids=item.track_ids||[],paths=item.paths||[],identities=item.identities||[];
    return `<li class="duplicate-review-item"><div><strong>${escapeHtml(item.artist||'Unknown artist')} — ${escapeHtml(item.title||'Unknown title')}</strong><span>${escapeHtml(item.reason||'Possible duplicate')}</span></div><div class="duplicate-versions">${ids.map((id,index)=>`<label><input type="radio" name="duplicate-survivor-${ids.join('-')}" value="${id}"${index===0?' checked':''}><b>${escapeHtml(identities[index]||`Track ${id}`)}</b><small>${escapeHtml(paths[index]||'')}</small></label>`).join('')}</div><div class="duplicate-review-actions"><button type="button" class="button secondary merge-duplicate" data-ids="${ids.join(',')}">Merge as duplicate</button><button type="button" class="button secondary keep-duplicate-separate" data-id="${ids[1]||''}">Keep as separate recording</button></div></li>`;
  };
  const renderIntegrityResults=batch=>{
    const findings=batch.findings||{}; const groups=Object.entries(integrityGroups).filter(([key])=>(findings[key]||[]).length);
    integrityStatus.textContent=groups.length?`${groups.reduce((sum,[key])=>sum+(findings[key]||[]).length,0)} findings across ${groups.length} categories. Review each group before applying a repair.`:'No catalog, file, path, or WAV-tag integrity issues were found.';
    integrityResults.innerHTML=groups.map(([key,[label,action,actionLabel]])=>{const items=findings[key]||[];const rows=key==='duplicate_records'?items.slice(0,25).map(duplicateFindingMarkup).join(''):items.slice(0,25).map(item=>`<li><strong>${escapeHtml(item.title||'Unknown item')}</strong><span>${escapeHtml((item.fields||[]).join(', ')||item.error||item.status||'')}</span><small>${escapeHtml(item.path||'')}</small></li>`).join('');return `<details class="integrity-group" data-key="${key}"><summary><span>${escapeHtml(label)}</span><b>${items.length}</b></summary><ul>${rows}</ul>${items.length>25?`<p>+ ${items.length-25} more findings</p>`:''}${action?`<button type="button" class="button secondary integrity-repair">${escapeHtml(actionLabel)}</button>`:key==='duplicate_records'?'<p>Select the file to retain in the catalog. Merging keeps the other WAV on disk.</p>':'<p>Review manually; no automatic repair is applied for this group.</p>'}</details>`;}).join('');
    integrityResults.querySelectorAll('.integrity-repair').forEach(button=>{const group=button.closest('.integrity-group');const [label,action,actionLabel]=integrityGroups[group.dataset.key];button.onclick=()=>runIntegrityRepair(action,findings[group.dataset.key]||[],actionLabel||label);});
    integrityResults.querySelectorAll('.merge-duplicate').forEach(button=>button.onclick=async()=>{const ids=button.dataset.ids.split(',').map(Number);const survivor=Number(button.closest('li').querySelector('input:checked')?.value||ids[0]);const duplicate=ids.find(id=>id!==survivor);if(!duplicate||!await confirmAction('Merge these catalog records? Analysis, playlists, feedback, and verified keys will follow the selected recording. The other WAV will remain on disk.', {title:'Merge duplicate records', acceptLabel:'Merge records'}))return;button.disabled=true;const response=await fetch('/api/downloaded-library/merge-duplicate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({survivor_id:survivor,duplicate_id:duplicate})});const result=await response.json();if(!response.ok){button.disabled=false;alert(result.detail||'Could not merge the duplicate.');return;}await loadDownloadedLibrary();integrityButton.click();});
    integrityResults.querySelectorAll('.keep-duplicate-separate').forEach(button=>button.onclick=async()=>{const id=Number(button.dataset.id);if(!id)return;button.disabled=true;const response=await fetch(`/api/downloaded-library/tracks/${id}/keep-separate`,{method:'POST'});const result=await response.json();if(!response.ok){button.disabled=false;alert(result.detail||'Could not separate the recording.');return;}await loadDownloadedLibrary();integrityButton.click();});
  };
  const watchIntegrityScan=batchId=>runBackgroundTask({key:'integrity-scan',url:`/api/downloaded-library/integrity-scan/${batchId}`,interval:700,update:batch=>{integrityRoot.open=true;integrityButton.disabled=true;integrityButton.textContent='Scanning…';integrityStatus.textContent=`${batch.stage} · ${Math.round(batch.progress||0)}%`;},complete:batch=>{integrityButton.disabled=false;integrityButton.textContent='Scan collection';renderIntegrityResults(batch);},fail:error=>{integrityButton.disabled=false;integrityButton.textContent='Scan collection';integrityStatus.textContent=error.message;}});
  integrityButton.onclick=async()=>{integrityButton.disabled=true;integrityButton.textContent='Starting…';integrityResults.replaceChildren();integrityStatus.textContent='Indexing catalog and music folders…';const response=await fetch('/api/downloaded-library/integrity-scan',{method:'POST'});const batch=await response.json();if(!response.ok){integrityButton.disabled=false;integrityButton.textContent='Scan collection';integrityStatus.textContent=batch.detail||'Could not start integrity scan.';return;}watchIntegrityScan(batch.batch_id);};
  summary.querySelector('.sidebar-rescan').onclick = () => rescanGenres.click();
  summary.querySelector('.sidebar-reconcile').onclick = () => reconcileFiles.click();
  summary.querySelector('.sidebar-artwork').onclick = () => syncArtwork.click();
  const watchGenreRescan = batchId => runBackgroundTask({
    key:'genre-rescan', url:`/api/downloaded-library/rescan-genres/${batchId}`, interval:500,
    update:batch => {
      renderMaintenanceProgress(batch.status === 'complete' ? 'Genre rescan complete' : 'Rescanning genre folders',batch,`${batch.processed} of ${batch.total} checked · ${batch.updated} reorganized · ${batch.unchanged} already correct · ${batch.unresolved} need attention${batch.failed ? ` · ${batch.failed} failed` : ''}`);
      $('#downloaded-rescan-message').textContent = batch.status === 'complete' ? 'Genre folders and catalog paths are synchronized.' : '';
    },
    complete:async () => { rescanGenres.disabled=false; rescanGenres.textContent='Rescan genres'; retagAll.disabled=false; await loadDownloadedLibrary(); },
    fail:error => { renderProgressError('Genre rescan stopped',error); rescanGenres.disabled=false; retagAll.disabled=false; },
  });
  rescanGenres.onclick = async () => {
    if (!paginationData.catalog_total) return;
    if (!await confirmAction(`Rescan ${paginationData.catalog_total} downloaded track${paginationData.catalog_total === 1 ? '' : 's'} and move WAVs into their detected genre folders? Tracks without detailed genre metadata will stay where they are.`, {title:'Rescan genre metadata', acceptLabel:'Start rescan'})) return;
    rescanGenres.disabled = true; retagAll.disabled = true; rescanGenres.textContent = 'Rescanning…';
    renderMaintenanceProgress('Rescanning genre folders', {total:paginationData.catalog_total,processed:0,status:'processing'}, `0 of ${paginationData.catalog_total} checked · preparing library scan`);
    $('#downloaded-rescan-message').textContent = '';
    try {
      const response = await fetch('/api/downloaded-library/rescan-genres', {method:'POST'});
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Genre rescan failed.');
      watchGenreRescan(result.batch_id);
    } catch (error) { renderProgressError('Genre rescan could not start', error); rescanGenres.disabled=false; retagAll.disabled=false; rescanGenres.textContent='Rescan genres'; }
  };
  const watchReconcile = batchId => runBackgroundTask({
    key:'catalog-reconcile',url:`/api/downloaded-library/reconcile-files/${batchId}`,interval:500,
    update:batch=>renderMaintenanceProgress(batch.status==='complete'?'File reconciliation complete':'Reconciling changed files',batch,`${batch.processed} of ${batch.total} checked · ${batch.updated} updated · ${batch.skipped} unchanged${batch.failed?` · ${batch.failed} unavailable/invalid`:''}`),
    complete:async()=>{reconcileFiles.disabled=false;reconcileFiles.textContent='Reconcile files';await loadDownloadedLibrary();},
    fail:error=>{renderProgressError('File reconciliation stopped',error);reconcileFiles.disabled=false;reconcileFiles.textContent='Reconcile files';},
  });
  reconcileFiles.onclick=async()=>{
    reconcileFiles.disabled=true;reconcileFiles.textContent='Starting…';renderMaintenanceProgress('Reconciling changed files',{total:0,processed:0,status:'processing'},'Indexing source records…');
    try{const response=await fetch('/api/downloaded-library/reconcile-files',{method:'POST'});const batch=await response.json();if(!response.ok)throw new Error(batch.detail||'Could not start file reconciliation.');reconcileFiles.textContent='Reconciling…';watchReconcile(batch.batch_id);}catch(error){renderProgressError('File reconciliation could not start',error);reconcileFiles.disabled=false;reconcileFiles.textContent='Reconcile files';}
  };
  const renderTagFailures = (batch, reportType='wav-tags') => {
    const details = $('#downloaded-retag-errors');
    const errors = batch.errors || [];
    if (!errors.length) {
      if (details.dataset.reportType !== reportType) return;
      details.hidden = true; details.open = false; details.querySelector('ul').replaceChildren(); return;
    }
    details.dataset.reportType = reportType;
    details.hidden = false;
    details.querySelector('summary').textContent = `Review ${errors.length} file${errors.length === 1 ? '' : 's'} that could not be updated`;
    details.querySelector('ul').innerHTML = errors.map(item => `<li><strong>${escapeHtml(item.filename || `Track ${item.id}`)}</strong><span>${escapeHtml(item.error || 'Unknown metadata error')}</span><small>${escapeHtml(item.path || '')}</small></li>`).join('');
    const removeFailed = $('#downloaded-remove-failed');
    const missing = errors.filter(item => String(item.error || '').toLowerCase().includes('missing') || String(item.error || '').includes('No such file'));
    removeFailed.hidden = !missing.length;
    removeFailed.onclick = async () => {
      if (!missing.length || !await confirmAction(`Remove ${missing.length} missing file entr${missing.length === 1 ? 'y' : 'ies'} from the catalog? This does not delete any files.`, {title:'Remove missing entries', acceptLabel:'Remove entries', danger:true})) return;
      const response = await fetch('/api/downloaded-library/tracks', {method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_ids:missing.map(item => item.id)})});
      if (!response.ok) { alert((await response.json()).detail || 'Could not remove missing entries.'); return; }
      await loadDownloadedLibrary();
    };
  };
  const watchTagBatch = batchId => runBackgroundTask({
    key:'wav-tag-sync', url:`/api/downloaded-library/retag-all/${batchId}`,
    update:batch => { renderTagFailures(batch); renderMaintenanceProgress(batch.status === 'complete' ? 'WAV tag sync complete' : 'Synchronizing WAV tags',batch,`${batch.processed} of ${batch.total} checked · ${batch.tagged} updated · ${batch.skipped || 0} already correct${batch.failed ? ` · ${batch.failed} unavailable/failed` : ''}`); $('#downloaded-rescan-message').textContent=''; },
    complete:() => { retagAll.disabled=false; retagAll.textContent='Sync all WAV tags'; rescanGenres.disabled=false; },
    fail:error => { renderProgressError('WAV tag sync stopped',error); retagAll.disabled=false; rescanGenres.disabled=false; retagAll.textContent='Sync all WAV tags'; },
  });
  retagAll.onclick = async () => {
    if (!paginationData.catalog_total || !await confirmAction(`Synchronize title, artist, genre, and playlist tags across all ${paginationData.catalog_total} catalog tracks? This runs in the background and may take several minutes.`, {title:'Synchronize WAV tags', acceptLabel:'Start sync'})) return;
    retagAll.disabled = true; rescanGenres.disabled = true; retagAll.textContent = 'Starting…';
    renderMaintenanceProgress('Synchronizing WAV tags', {total:paginationData.catalog_total,processed:0,status:'processing'}, `0 of ${paginationData.catalog_total} checked · preparing metadata sync`);
    try {
      const response = await fetch('/api/downloaded-library/retag-all', {method:'POST'});
      const batch = await response.json();
      if (!response.ok) throw new Error(batch.detail || 'Could not start WAV metadata synchronization.');
      retagAll.textContent = 'Syncing all…';
      watchTagBatch(batch.batch_id);
    } catch (error) { renderProgressError('WAV tag sync could not start', error); retagAll.disabled = false; rescanGenres.disabled=false; retagAll.textContent = 'Sync all WAV tags'; }
  };
  const watchArtworkBatch = batchId => runBackgroundTask({
    key:'artwork-sync', url:`/api/downloaded-library/artwork-sync/${batchId}`, interval:700,
    update:batch => renderMaintenanceProgress(batch.status === 'complete' ? 'Artwork sync complete' : 'Finding and embedding artwork',batch,`${batch.processed} of ${batch.total} checked · ${batch.updated} updated · ${batch.skipped} already ready${batch.resolved ? ` · ${batch.resolved} resolved later` : ''}${batch.failed ? ` · ${batch.failed} need attention` : ''}`),
    complete:async batch => {
      syncArtwork.disabled=false; syncArtwork.textContent='Sync artwork'; rescanGenres.disabled=false; retagAll.disabled=false;
      await loadDownloadedLibrary();
      renderTagFailures(batch,'artwork');
    },
    fail:error => { renderProgressError('Artwork sync stopped',error); syncArtwork.disabled=false; syncArtwork.textContent='Sync artwork'; rescanGenres.disabled=false; retagAll.disabled=false; },
  });
  syncArtwork.onclick = async () => {
    const selectedTracks=[...downloadedSelection.values()];
    const selectedIds=selectedTracks.filter(track=>!track.artwork_available).map(track=>Number(track.id));
    if(selectedTracks.length&&!selectedIds.length){alert('Every selected track already has artwork.');return;}
    const targetCount=selectedIds.length||Number(paginationData.filtered_total||0);
    if (!targetCount || !await confirmAction(selectedIds.length?`Find and embed artwork for ${selectedIds.length} selected track${selectedIds.length===1?'':'s'} that need it?`:`Find and embed artwork for tracks that still need it? Existing artwork will be skipped.`, {title:'Synchronize artwork', acceptLabel:'Start sync'})) return;
    syncArtwork.disabled=true; rescanGenres.disabled=true; retagAll.disabled=true; syncArtwork.textContent='Starting…';
    renderMaintenanceProgress('Finding and embedding artwork',{total:paginationData.catalog_total,processed:0,status:'processing'},`0 of ${paginationData.catalog_total} checked · preparing artwork sync`);
    try {
      const response=await fetch('/api/downloaded-library/artwork-sync',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_ids:selectedIds})});
      const batch=await response.json();
      if(!response.ok) throw new Error(batch.detail || 'Could not start artwork synchronization.');
      syncArtwork.textContent='Syncing artwork…';
      watchArtworkBatch(batch.batch_id);
    } catch(error) { renderProgressError('Artwork sync could not start',error); syncArtwork.disabled=false; syncArtwork.textContent='Sync artwork'; rescanGenres.disabled=false; retagAll.disabled=false; }
  };
  fetch('/api/downloaded-library/rescan-genres-latest', {cache:'no-store'}).then(response => response.json()).then(batch => {
    if (batch.status !== 'processing') return;
    rescanGenres.disabled=true; retagAll.disabled=true; rescanGenres.textContent='Rescanning…';
    watchGenreRescan(batch.batch_id);
  }).catch(() => {});
  fetch('/api/downloaded-library/retag-all-latest', {cache:'no-store'}).then(response => response.json()).then(batch => {
    if (batch.status === 'none') return;
    renderTagFailures(batch,'wav-tags');
    if (batch.status === 'processing') {
      retagAll.disabled = true; retagAll.textContent = 'Syncing all…';
      watchTagBatch(batch.batch_id);
    } else if (batch.failed) {
      $('#downloaded-rescan-message').textContent = `Previous WAV metadata sync · ${batch.tagged} updated · ${batch.skipped || 0} already correct · ${batch.failed} unavailable/failed`;
    }
  }).catch(() => {});
  fetch('/api/downloaded-library/artwork-sync-latest', {cache:'no-store'}).then(response => response.json()).then(batch => {
    if (batch.status === 'none') return;
    renderTagFailures(batch,'artwork');
    if (batch.status === 'processing') {
      syncArtwork.disabled=true; rescanGenres.disabled=true; retagAll.disabled=true; syncArtwork.textContent='Syncing artwork…';
      watchArtworkBatch(batch.batch_id);
    }
  }).catch(() => {});
  const refreshSelection = () => {
    const selected = [...downloadedSelection.values()];
    const downloadable = selected.filter(track => track.available);
    const missingArtwork = selected.filter(track => !track.artwork_available);
    const analyzable = downloadable.filter(track => !['queued','processing','complete'].includes(track.analysis_status));
    $('#downloaded-selection-count').textContent = `${selected.length} selected${selected.length ? ` · ${missingArtwork.length} need artwork` : ''}`;
    downloadSelected.disabled = !downloadable.length;
    analyzeSelected.disabled = !analyzable.length;
    keyAnalyzeSelected.disabled = !downloadable.length;
    reanalyzeSelected.disabled = !downloadable.length;
    removeSelected.disabled = !selected.length;
    changeGenre.disabled = !selected.length;
    retagSelected.disabled = !downloadable.length;
    if(syncArtwork.dataset.busy!=='true') syncArtwork.textContent=selected.length ? `Sync artwork${missingArtwork.length ? ` (${missingArtwork.length})` : ''}` : 'Sync artwork';
    document.querySelector('.downloaded-selection').classList.toggle('has-selection', selected.length > 0);
    cards.forEach(card => { const selected=card.querySelector('.downloaded-check input').checked; card.classList.toggle('is-selected',selected); card.setAttribute('aria-selected',String(selected)); });
    selectAll.checked = cards.length > 0 && cards.every(card => card.querySelector('input').checked);
    selectAll.indeterminate = cards.some(card => card.querySelector('input').checked) && !selectAll.checked;
  };
  const reloadCollectionViews = async () => {
    const previousScroll = window.scrollY;
    await Promise.all([loadDownloadedLibrary(), loadLibrary()]);
    requestAnimationFrame(() => window.scrollTo({top:previousScroll,behavior:'instant'}));
  };
  const matchesCurrentDownloadedFilters = track => {
    const query=downloadedUiState.search.trim().toLowerCase();
    const haystack=`${track.title||''} ${track.artist||''} ${track.genre||''} ${track.genre_category||''} ${(track.playlists||[]).join(' ')}`.toLowerCase();
    if(query&&!haystack.includes(query))return false;
    if(downloadedUiState.playlist!=='all'&&!(track.playlists||[]).includes(downloadedUiState.playlist))return false;
    const category=String(track.genre_category||'Other'),filter=downloadedUiState.genre;
    if(filter!=='all'&&category!==filter&&!category.startsWith(`${filter} / `))return false;
    if(downloadedUiState.detailedGenre!=='all'){
      const tags=String(track.genre||'').split(',').map(tag=>tag.trim().toLowerCase());
      if(!tags.includes(downloadedUiState.detailedGenre.toLowerCase()))return false;
    }
    if(downloadedUiState.quality!=='all'){
      const quality=String(track.audio_quality_label||'unanalyzed');
      if(downloadedUiState.quality==='below-target'?!['review','poor'].includes(quality):quality!==downloadedUiState.quality)return false;
    }
    const title=String(track.title||'').trim().toLowerCase(),artist=String(track.artist||'').trim().toLowerCase(),genre=String(track.genre||'').trim();
    const reviewFlags={missing_title:!title||['unknown title','untitled'].includes(title),missing_artist:!artist||['unknown artist','unknown','unavailable'].includes(artist),missing_genre:!genre,missing_artwork:!track.artwork_available,unmapped_genre:Boolean(genre)&&category==='Other',broad_genre:category.endsWith(' / General')||category.endsWith(' / Other')};
    const analysis=downloadedUiState.analysis,status=String(track.analysis_status||'not_analyzed');
    if(analysis==='attention'&&!Object.values(reviewFlags).some(Boolean))return false;
    if(Object.hasOwn(reviewFlags,analysis)&&!reviewFlags[analysis])return false;
    if(analysis==='needs'&&!['not_analyzed','failed','canceled'].includes(status))return false;
    if(analysis==='complete'&&status!=='complete')return false;
    if(analysis==='active'&&!['queued','processing'].includes(status))return false;
    if(analysis==='failed'&&!['failed','canceled'].includes(status))return false;
    return true;
  };
  const adjustSidebarCount = (selector,delta) => { const counter=summary.querySelector(`${selector} b`);if(counter)counter.textContent=String(Math.max(0,Number(counter.textContent||0)+delta)); };
  const adjustTrackFacets = (before,after) => {
    const beforeGenre=String(before.genre_category||'Other'),afterGenre=String(after.genre_category||'Other');
    summary.querySelectorAll('.filter-downloaded-genre[data-value]').forEach(button=>{const value=button.dataset.value;if(value==='all')return;const had=beforeGenre===value||beforeGenre.startsWith(`${value} / `),has=afterGenre===value||afterGenre.startsWith(`${value} / `);if(had!==has){const counter=button.querySelector('b');if(counter)counter.textContent=String(Math.max(0,Number(counter.textContent||0)+(has?1:-1)));}});
    const reviewFlags=track=>{const title=String(track.title||'').trim().toLowerCase(),artist=String(track.artist||'').trim().toLowerCase(),genre=String(track.genre||'').trim(),category=String(track.genre_category||'Other');return {missing_title:!title||['unknown title','untitled'].includes(title),missing_artist:!artist||['unknown artist','unknown','unavailable'].includes(artist),missing_genre:!genre,missing_artwork:!track.artwork_available,unmapped_genre:Boolean(genre)&&category==='Other',broad_genre:category.endsWith(' / General')||category.endsWith(' / Other')};};
    const oldReview=reviewFlags(before),newReview=reviewFlags(after);Object.keys(oldReview).forEach(value=>{if(oldReview[value]!==newReview[value])adjustSidebarCount(`.filter-downloaded-analysis[data-value="${value}"]`,newReview[value]?1:-1);});
    const needsBefore=Object.values(oldReview).some(Boolean),needsAfter=Object.values(newReview).some(Boolean);if(needsBefore!==needsAfter)adjustSidebarCount('.needs-genre-group>summary',needsAfter?1:-1);
    const oldPlaylists=new Set(before.playlists||[]),newPlaylists=new Set(after.playlists||[]);new Set([...oldPlaylists,...newPlaylists]).forEach(name=>{const button=[...summary.querySelectorAll('.filter-downloaded-playlist')].find(item=>item.dataset.value===name);if(button&&oldPlaylists.has(name)!==newPlaylists.has(name)){const counter=button.querySelector('b');counter.textContent=String(Math.max(0,Number(counter.textContent||0)+(newPlaylists.has(name)?1:-1)));}});
  };
  const applyTrackPatch = async (card,patch) => {
    const track=tracks.find(item=>Number(item.id)===Number(card.dataset.id));if(!track)return false;
    const before={...track,playlists:[...(track.playlists||[])]};
    Object.assign(track,patch);if(patch.playlist_name)track.playlists=[patch.playlist_name];
    if(!matchesCurrentDownloadedFilters(track)){await loadDownloadedLibrary();libraryLoadedAt=0;return false;}
    adjustTrackFacets(before,track);
    card.dataset.title=String(track.title||track.filename||'').toLowerCase();card.dataset.artist=String(track.artist||'').toLowerCase();card.dataset.genre=track.genre_category||'Other';card.dataset.playlists=(track.playlists||[]).join('|');
    card.querySelector('.downloaded-copy h3').textContent=track.title||track.filename;card.querySelector('.downloaded-copy p').textContent=track.artist||'Unknown artist';card.querySelectorAll('.downloaded-genre').forEach(button=>button.textContent=track.genre_category||'Other');const detailed=detailedGenreSummary(track.genre);const detailedButton=card.querySelector('.downloaded-detailed-genre');detailedButton.textContent=detailed.label;detailedButton.title=detailed.title;detailedButton.disabled=detailed.empty;detailedButton.classList.toggle('empty',detailed.empty);card.setAttribute('aria-label',`${track.title||track.filename} by ${track.artist||'Unknown artist'}`);
    const metadataEditor=card.querySelector('.track-metadata-editor');if(metadataEditor){metadataEditor.elements.title.value=track.title||'';metadataEditor.elements.artist.value=track.artist||'';metadataEditor.elements.genre_category.value=track.genre_category||'Other';metadataEditor.elements.genre.value=track.genre||'';metadataEditor.elements.playlist_name.value=(track.playlists||[])[0]||'Imported Singles';metadataEditor.elements.artwork_url.value=track.artwork_url||'';}
    const genreEditor=card.querySelector('.inline-genre-editor');if(genreEditor){const genreSelect=genreEditor.querySelector('.inline-genre-select');if(![...genreSelect.options].some(option=>option.value===track.genre_category))genreSelect.add(option(track.genre_category,track.genre_category));genreSelect.value=track.genre_category||'Other';genreEditor.querySelector('.inline-genre-custom').value='';genreEditor.querySelector('.genre-folder-preview').textContent=`Folder: ${String(track.genre_category||'Other').replace(' / ','/')}/`;}
    if(track.artwork_available){card.querySelector('.downloaded-row-icon').innerHTML=`<img src="/api/downloaded-library/tracks/${track.id}/artwork?thumbnail=true&v=${Date.now()}" alt="" loading="lazy" decoding="async">`;}
    if(downloadedSelection.has(Number(track.id)))downloadedSelection.set(Number(track.id),track);
    libraryLoadedAt=0;refreshSelection();return true;
  };
  const requestPage = (page = 1) => { downloadedUiState.page = page; loadDownloadedLibrary(); };
  const syncFilters = () => { downloadedUiState.search=search.value.trim();downloadedUiState.genre=genreSelect.value;downloadedUiState.detailedGenre=detailedGenreSelect.value;downloadedUiState.playlist=playlistSelect.value; downloadedUiState.analysis=analysisSelect.value; downloadedUiState.artwork=artworkSelect.value; downloadedUiState.quality=qualitySelect.value; downloadedUiState.sort=sort.value; requestPage(1); };
  clearTimeout(downloadedSearchTimer);
  search.oninput = () => { clearTimeout(downloadedSearchTimer); downloadedSearchTimer=setTimeout(syncFilters,220); };
  genreSelect.onchange = () => {downloadedUiState.detailedGenre='all';detailedGenreSelect.value='all';syncFilters();}; detailedGenreSelect.onchange=syncFilters; playlistSelect.onchange = syncFilters; analysisSelect.onchange = syncFilters; artworkSelect.onchange = syncFilters; qualitySelect.onchange=syncFilters; sort.onchange = syncFilters;
  $('#downloaded-reset-filters').onclick=()=>{Object.assign(downloadedUiState,{search:'',genre:'all',detailedGenre:'all',playlist:'all',analysis:'all',artwork:'all',quality:'all',sort:'newest',page:1});loadDownloadedLibrary();};
  pageSizeSelect.onchange = () => { pageSize=Number(pageSizeSelect.value); downloadedUiState.pageSize=pageSize; localStorage.setItem('music-files-page-size',String(pageSize)); requestPage(1); };
  cards.forEach((card,index) => card.querySelector('input').onchange = event => { const track=tracks[index]; if (event.currentTarget.checked) downloadedSelection.set(Number(track.id),track); else downloadedSelection.delete(Number(track.id)); refreshSelection(); });
  cards.forEach(card => card.onclick = event => {
    if (!downloadedSelection.size) return;
    if (event.target.closest('input,label,a,button,audio,details,summary,select,form')) return;
    const checkbox = card.querySelector('.downloaded-check input');
    checkbox.checked = !checkbox.checked;
    checkbox.dispatchEvent(new Event('change'));
  });
  cards.forEach((card,index) => {
    card.tabIndex=0; card.setAttribute('role','option'); card.setAttribute('aria-label',`${tracks[index].title||tracks[index].filename} by ${tracks[index].artist||'Unknown artist'}`);
    card.onkeydown=event=>{
      if(event.target!==card)return;
      if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();const next=index+(event.key==='ArrowDown'?1:-1);cards[next]?.focus({preventScroll:true});cards[next]?.scrollIntoView({behavior:'smooth',block:'nearest'});}
      else if(event.key==='Enter'||event.key===' '){event.preventDefault();const checkbox=card.querySelector('.downloaded-check input');checkbox.checked=!checkbox.checked;checkbox.dispatchEvent(new Event('change'));}
      else if(event.key==='Escape'){card.querySelectorAll('.inline-genre-editor,.track-metadata-editor').forEach(editor=>editor.hidden=true);card.querySelectorAll('details[open]').forEach(details=>details.open=false);$('#downloaded-inspector').hidden=true;}
    };
  });
  selectAll.onchange = () => { cards.forEach((card,index) => { const checkbox=card.querySelector('input'); checkbox.checked=selectAll.checked; if (selectAll.checked) downloadedSelection.set(Number(tracks[index].id),tracks[index]); else downloadedSelection.delete(Number(tracks[index].id)); }); refreshSelection(); };
  clearSelection.onclick=()=>{downloadedSelection.clear();cards.forEach(card=>{card.querySelector('.downloaded-check input').checked=false;});refreshSelection();};
  const changePage = page => { downloadedUiState.page=page; loadDownloadedLibrary(); document.querySelector('.downloaded-toolbar').scrollIntoView({behavior:'smooth',block:'start'}); };
  renderTrackPagination(pagination,currentPage,paginationData.total_pages,paginationData.filtered_total,changePage);
  renderTrackPagination(paginationTop,currentPage,paginationData.total_pages,paginationData.filtered_total,changePage);
  summary.querySelectorAll('.filter-downloaded-genre').forEach(button => button.classList.toggle('active',button.dataset.value===genreSelect.value));
  summary.querySelectorAll('.filter-downloaded-playlist').forEach(button => button.classList.toggle('active',button.dataset.value===playlistSelect.value));
  const resultTotal=paginationData.filtered_total===paginationData.catalog_total?`${paginationData.catalog_total} tracks`:`${paginationData.filtered_total} of ${paginationData.catalog_total} tracks`;
  $('#downloaded-filter-count').textContent=`${resultTotal}${paginationData.total_pages>1?` · Page ${currentPage} of ${paginationData.total_pages}`:''}`;
  const reviewMatching=$('#downloaded-review-matching');
  const reviewFilterActive=['attention','missing_title','missing_artist','missing_genre','missing_artwork','unmapped_genre','broad_genre'].includes(downloadedUiState.analysis);
  reviewMatching.hidden=!reviewFilterActive||!paginationData.filtered_total;
  reviewMatching.textContent=`Review metadata (${paginationData.filtered_total})`;
  analyzeMatching.disabled=!analyzableTotal;
  analyzeMatching.textContent=analyzableTotal?`Analyze ${analyzableTotal} new track${analyzableTotal===1?'':'s'}`:'All matching analyzed';
  reanalyzeMatching.disabled=!paginationData.filtered_total;
  reanalyzeMatching.textContent=paginationData.filtered_total?`Reanalyze ${paginationData.filtered_total} track${paginationData.filtered_total===1?'':'s'}`:'No tracks to reanalyze';
  refreshSelection();
  changeGenre.onclick = () => {
    const selected = [...downloadedSelection.values()];
    if (!selected.length) return;
    let editor = document.querySelector('#downloaded-bulk-genre-editor');
    if (!editor) { document.querySelector('.downloaded-toolbar').insertAdjacentHTML('beforeend', `<div id="downloaded-bulk-genre-editor">${genreEditorMarkup(selected[0].genre_category || 'Other', '', true)}</div>`); editor = document.querySelector('#downloaded-bulk-genre-editor .inline-genre-editor'); bindGenreEditor(editor, () => [...downloadedSelection.keys()], reloadCollectionViews); }
    editor.hidden = false; editor.querySelector('select').focus();
  };
  retagSelected.onclick = async () => {
    const trackIds = [...downloadedSelection.values()].filter(track => track.available).map(track => Number(track.id));
    if (!trackIds.length || !await confirmAction(`Write title, artist, genre, and playlist metadata into ${trackIds.length} selected WAV${trackIds.length === 1 ? '' : 's'}?`, {title:'Write WAV metadata', acceptLabel:'Write tags'})) return;
    retagSelected.disabled = true; retagSelected.textContent = 'Syncing tags…';
    try {
      const response = await fetch('/api/downloaded-library/retag', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_ids:trackIds})});
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Could not update WAV metadata.');
      alert(`${result.tagged.length} updated · ${(result.skipped || []).length} already correct${result.failed.length ? ` · ${result.failed.length} failed` : ''}.`);
    } catch (error) { alert(error.message); }
    finally { retagSelected.textContent = 'Sync WAV tags'; refreshSelection(); }
  };
  downloadSelected.onclick = async () => {
    const trackIds = [...downloadedSelection.values()].filter(track => track.available).map(track => Number(track.id));
    downloadSelected.disabled = true; downloadSelected.textContent = 'Preparing ZIP…';
    try {
      const response = await fetch('/api/downloaded-library/download', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_ids:trackIds})});
      if (!response.ok) throw new Error((await response.json()).detail || 'Could not prepare the download.');
      const url = URL.createObjectURL(await response.blob()); const link = document.createElement('a'); link.href = url; link.download = 'Selected Downloaded Tracks - WAVs.zip'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { alert(error.message); }
    finally { downloadSelected.textContent = 'Download WAVs'; refreshSelection(); }
  };
  analyzeSelected.onclick = async () => {
    const trackIds = [...downloadedSelection.values()].filter(track => track.available && !['queued','processing','complete'].includes(track.analysis_status)).map(track => Number(track.id));
    if (!trackIds.length) return;
    analyzeSelected.disabled = true; analyzeSelected.textContent = 'Adding to queue…';
    try {
      const response = await fetch('/api/downloaded-library/analyze', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_ids:trackIds})});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'Could not queue analysis.');
      showView('workspace-view'); await loadJobs();
    } catch (error) { alert(error.message); analyzeSelected.textContent = 'Analyze'; refreshSelection(); }
  };
  keyAnalyzeSelected.onclick=()=>{const ids=[...downloadedSelection.values()].filter(track=>track.available).map(track=>Number(track.id));startKeyAnalysis(ids,keyAnalyzeSelected,async()=>{downloadedLoadedAt=0;libraryLoadedAt=0;await loadDownloadedLibrary();});};
  analyzeMatching.onclick = async () => {
    if (!analyzableTotal || !await confirmAction(`Add all ${analyzableTotal} matching track${analyzableTotal===1?'':'s'} that still need analysis to the processing queue? Analysis will run with safe automatic concurrency.`, {title:'Analyze matching tracks', acceptLabel:'Add to queue'})) return;
    analyzeMatching.disabled=true; analyzeMatching.textContent='Adding all to queue…';
    try {
      const response=await fetch('/api/downloaded-library/analyze-matching',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({search:downloadedUiState.search,genre:downloadedUiState.genre,detailed_genre:downloadedUiState.detailedGenre,playlist:downloadedUiState.playlist,analysis:downloadedUiState.analysis,quality:downloadedUiState.quality,sort:downloadedUiState.sort})});
      const result=await response.json();
      if(!response.ok)throw new Error(result.detail||'Could not queue matching tracks.');
      downloadedSelection.clear();
      showView('workspace-view'); await loadJobs();
    } catch(error) { alert(error.message); analyzeMatching.disabled=false; analyzeMatching.textContent=`Analyze all matching (${analyzableTotal})`; }
  };
  const queueReanalysis = async (url, body, button, count) => {
    const estimatedMinutes = Math.max(1, Math.ceil(count * 11 / 2 / 60));
    if (!count || !await confirmAction(`Reanalyze ${count} track${count===1?'':'s'} without changing the audio files? Estimated analysis time is about ${estimatedMinutes} minute${estimatedMinutes===1?'':'s'}. Existing artwork, genres, metadata, cues, and verified keys will be preserved.`, {title:'Reanalyze matching tracks', acceptLabel:'Reanalyze'})) return;
    const original = button.textContent; button.disabled = true; button.textContent = 'Adding to queue…';
    try {
      const response = await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); const result=await response.json();
      if(!response.ok)throw new Error(result.detail||'Could not queue reanalysis.');
      downloadedSelection.clear(); showView('workspace-view'); await loadJobs();
      if(result.skipped?.length)alert(`${result.job_ids.length} queued · ${result.skipped.length} already active and skipped.`);
    } catch(error) { alert(error.message); button.disabled=false; }
    finally { button.textContent=original; }
  };
  reanalyzeSelected.onclick=()=>{const ids=[...downloadedSelection.values()].filter(track=>track.available).map(track=>Number(track.id));queueReanalysis('/api/downloaded-library/reanalyze',{track_ids:ids},reanalyzeSelected,ids.length);};
  reanalyzeMatching.onclick=()=>queueReanalysis('/api/downloaded-library/reanalyze-matching',{search:downloadedUiState.search,genre:downloadedUiState.genre,detailed_genre:downloadedUiState.detailedGenre,playlist:downloadedUiState.playlist,analysis:downloadedUiState.analysis,quality:downloadedUiState.quality,sort:downloadedUiState.sort},reanalyzeMatching,paginationData.filtered_total);
  removeSelected.onclick = async () => {
    const trackIds = [...downloadedSelection.keys()];
    if (!trackIds.length || !await confirmAction(`Remove ${trackIds.length} selected track${trackIds.length === 1 ? '' : 's'} from the catalog? WAV files that still exist will remain on disk.`, {title:'Remove catalog entries', acceptLabel:'Remove', danger:true})) return;
    removeSelected.disabled = true; removeSelected.textContent = 'Removing…';
    try {
      const response = await fetch('/api/downloaded-library/tracks', {method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_ids:trackIds})});
      if (!response.ok) throw new Error((await response.json()).detail || 'Could not remove the selected tracks.');
      trackIds.forEach(id => downloadedSelection.delete(Number(id)));
      await loadDownloadedLibrary();
    } catch (error) { alert(error.message); removeSelected.textContent = 'Remove'; refreshSelection(); }
  };
  root.querySelectorAll('.remove-downloaded').forEach(button => button.onclick = async () => {
    const card = button.closest('.downloaded-card');
    if (!await confirmAction('Remove this track from the master catalog? The WAV file will remain on disk.', {title:'Remove track', acceptLabel:'Remove', danger:true})) return;
    await fetch(`/api/downloaded-library/tracks/${card.dataset.id}`, {method:'DELETE'}); await reloadCollectionViews();
  });
  root.querySelectorAll('.view-downloaded-library').forEach(button => button.onclick = () => showView('library-view'));
  root.querySelectorAll('.edit-downloaded-genre').forEach(button => button.onclick = () => { const card=button.closest('.downloaded-card'); const editor=card.querySelector('.inline-genre-editor'); const opening=editor.hidden; root.querySelectorAll('.inline-genre-editor,.track-metadata-editor').forEach(item=>item.hidden=true); editor.hidden=!opening; button.closest('details')?.removeAttribute('open'); if (!editor.hidden) editor.querySelector('select').focus(); });
  root.querySelectorAll('.downloaded-detailed-genre:not(:disabled)').forEach(button=>button.onclick=()=>{downloadedUiState.genre='all';downloadedUiState.detailedGenre=String(button.title).split(',')[0].trim();requestPage(1);document.querySelector('.downloaded-toolbar').scrollIntoView({behavior:'smooth'});});
  root.querySelectorAll('.downloaded-card').forEach(card => bindGenreEditor(card.querySelector('.inline-genre-editor'), () => [Number(card.dataset.id)], async payload => {await applyTrackPatch(card,{genre_category:payload.genre_category});card.querySelector('.inline-genre-editor').hidden=true;}));
  const metadataCards=[...root.querySelectorAll('.downloaded-card')];
  const openMetadataAt=index=>{
    if(index<0||index>=metadataCards.length)return;
    metadataCards.forEach(card=>{card.querySelector('.track-metadata-editor').hidden=true;});
    const card=metadataCards[index]; const editor=card.querySelector('.track-metadata-editor'); editor.hidden=false;
    card.scrollIntoView({behavior:'smooth',block:'center'}); editor.elements.title.focus();
  };
  reviewMatching.onclick=()=>openMetadataAt(0);
  root.querySelectorAll('.edit-track-metadata').forEach(button => button.onclick = () => {
    const card=button.closest('.downloaded-card'); const editor=card.querySelector('.track-metadata-editor');
    const opening=editor.hidden; root.querySelectorAll('.inline-genre-editor,.track-metadata-editor').forEach(item=>item.hidden=true); button.closest('details').open=false; editor.hidden=!opening;
    if(!editor.hidden) editor.elements.title.focus();
  });
  root.querySelectorAll('.track-metadata-editor').forEach((editor,index) => {
    editor.querySelector('.metadata-review-position span').textContent=`${(paginationData.page-1)*paginationData.page_size+index+1} of ${paginationData.filtered_total}`;
    editor.querySelectorAll('.close-metadata-editor').forEach(button => button.onclick=()=>{editor.hidden=true;editor.closest('.downloaded-card').focus();});
    editor.querySelector('.metadata-previous').disabled=index===0;
    editor.querySelector('.metadata-next').disabled=index===metadataCards.length-1;
    editor.querySelector('.metadata-previous').onclick=()=>openMetadataAt(index-1);
    editor.querySelector('.metadata-next').onclick=()=>openMetadataAt(index+1);
    editor.onkeydown=event=>{if(event.key==='Escape'){event.preventDefault();editor.hidden=true;editor.closest('.downloaded-card').focus();}else if(event.altKey&&event.key==='ArrowRight'){event.preventDefault();openMetadataAt(index+1);}else if(event.altKey&&event.key==='ArrowLeft'){event.preventDefault();openMetadataAt(index-1);}else if((event.ctrlKey||event.metaKey)&&event.key==='Enter'){event.preventDefault();editor.requestSubmit(event.shiftKey?editor.querySelector('[data-action="next"]'):editor.querySelector('[type="submit"]'));}};
    editor.onsubmit=async event=>{
      event.preventDefault(); const card=editor.closest('.downloaded-card'); const save=event.submitter||editor.querySelector('[type="submit"]'); const message=editor.querySelector('.metadata-message'); const advance=save.dataset.action==='next';
      save.disabled=true; save.textContent='Saving…'; message.textContent='Writing WAV tags, artwork, and synchronizing the catalog…';
      const body=Object.fromEntries(new FormData(editor).entries()); body.rename_file=editor.elements.rename_file.checked;
      try {
        const response=await fetch(`/api/downloaded-library/tracks/${card.dataset.id}/metadata`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const payload=await response.json(); if(!response.ok) throw new Error(payload.detail||'Could not update metadata.');
        downloadedSelection.delete(Number(card.dataset.id));const nextCard=metadataCards[index+1]||null;
        if(advance)pendingMetadataReview={id:nextCard?Number(nextCard.dataset.id):null};
        const stayed=await applyTrackPatch(card,{...payload,playlists:[payload.playlist_name]});
        if(stayed){editor.hidden=true;if(advance&&nextCard?.isConnected){pendingMetadataReview=null;openMetadataAt(index+1);}else if(advance){await loadDownloadedLibrary();}else card.focus();}
      } catch(error) { message.textContent=error.message; save.disabled=false; save.textContent=advance?'Save & next →':'Save'; }
    };
  });
  root.querySelectorAll('.inspect-downloaded').forEach(button => button.onclick = () => {
    const card = button.closest('.downloaded-card');
    button.closest('details').open = false;
    const track = tracks.find(item => Number(item.id) === Number(card.dataset.id));
    const inspector = $('#downloaded-inspector');
    inspector.hidden = false; inspector.dataset.returnId=card.dataset.id;
    const preview = track.available ? `<audio controls preload="metadata" src="/api/downloaded-library/tracks/${track.id}/audio"></audio>` : '<div class="inspector-unavailable">The catalog entry remains available, but its WAV file is missing from disk.</div>';
    const identity=`${track.recording_code || 'OTH-PENDING'}-${track.version_code || 'ORG'}`;
    inspector.innerHTML = `<div class="inspector-head"><div><p class="eyebrow">QUICK VIEW · ${escapeHtml(identity)}</p><h2>${escapeHtml(track.title || track.filename)}</h2><span>${escapeHtml(track.artist || 'Unknown artist')}</span></div><button type="button" class="close-inspector" aria-label="Close inspector">×</button></div>${preview}<div class="inspector-metrics"><button type="button" class="inspector-genre-trigger" title="Change genre"><b>${escapeHtml(track.genre_category || 'Other')}</b><span>Genre</span></button><p><b>${clock(track.duration_seconds)}</b><span>Length</span></p><p><b>${escapeHtml((track.analysis_status || 'not_analyzed').replaceAll('_',' '))}</b><span>Analysis</span></p></div>${genreEditorMarkup(track.genre_category || 'Other', track.suggested_genre || '', true)}<section class="inspector-family" hidden><div class="inspector-family-heading"><div><b>Recording family</b><span>Originals, remixes, edits, and alternate versions</span></div><div class="inspector-family-heading-actions"><button type="button" class="button secondary inspector-family-toggle">Link as version of…</button><button type="button" class="button secondary inspector-family-close" aria-label="Close recording family">×</button></div></div><div class="inspector-family-content"><p>Loading related versions…</p></div><form class="inspector-family-link" hidden><label>Target track ID<input name="target" placeholder="HOU-002386-ORG"></label><label>Relationship<select name="relationship"><option value="RMX">Remix</option><option value="EXT">Extended mix</option><option value="RADIO">Radio edit</option><option value="LIVE">Live version</option><option value="INST">Instrumental</option><option value="ACAP">Acapella</option><option value="REM">Remaster</option><option value="ORG">Original / alternate original</option></select></label><button type="submit">Link version</button><small>Choose a suggestion below or enter the visible genre-based track ID.</small></form><div class="inspector-family-suggestions"></div></section><details class="inspector-metadata"><summary>File & source details</summary><dl><dt>Recording ID</dt><dd>${escapeHtml(identity)}</dd><dt>Identity basis</dt><dd>${escapeHtml(track.identity_reason || 'Catalog assignment')}</dd><dt>Detailed tags</dt><dd>${escapeHtml(track.genre || 'No metadata')}</dd><dt>Source playlist</dt><dd>${escapeHtml((track.playlists || []).join(', ') || 'Imported Singles')}</dd><dt>Filename</dt><dd>${escapeHtml(track.filename || '')}</dd><dt>Absolute path</dt><dd class="inspector-path">${escapeHtml(track.absolute_path || 'Path unavailable')}</dd></dl></details><div class="inspector-actions">${track.completed_library_job_id ? '<button type="button" class="button secondary inspector-library">View in DJ Library</button>' : ''}<button type="button" class="button secondary inspector-edit-metadata">Edit metadata</button><button type="button" class="button secondary inspector-edit-genre">Change genre only</button><button type="button" class="button secondary inspector-manage-family">Recording family</button>${track.available ? `<button type="button" class="button secondary inspector-copy-path">Copy path</button><button type="button" class="button secondary inspector-reveal">Reveal in Finder</button><a class="button secondary" href="/api/downloaded-library/tracks/${track.id}/download">Download WAV</a>` : ''}</div>`;
    inspector.querySelector('.close-inspector').onclick = () => closeDownloadedInspector({restoreFocus:true});
    inspector.querySelector('.inspector-edit-metadata').onclick = () => { const editor=card.querySelector('.track-metadata-editor'); closeDownloadedInspector(); editor.hidden=false; card.scrollIntoView({behavior:'smooth',block:'center'}); editor.elements.title.focus(); };
    const inspectorGenreEditor=inspector.querySelector('.inline-genre-editor');
    const openInspectorGenre=()=>{inspectorGenreEditor.hidden=false;refreshSearchableSelects();(inspectorGenreEditor.querySelector('.select-search-input')||inspectorGenreEditor.querySelector('.inline-genre-custom')).focus();};
    inspector.querySelector('.inspector-genre-trigger').onclick=openInspectorGenre;
    inspector.querySelector('.inspector-edit-genre').onclick=openInspectorGenre;
    bindGenreEditor(inspectorGenreEditor,()=>[Number(track.id)],async payload=>{await applyTrackPatch(card,{genre_category:payload.genre_category});inspectorGenreEditor.hidden=true;inspector.querySelector('.inspector-genre-trigger b').textContent=payload.genre_category;});
    inspector.querySelector('.inspector-library')?.addEventListener('click', () => { closeDownloadedInspector(); showView('library-view'); });
    inspector.querySelector('.inspector-copy-path')?.addEventListener('click', async event => {try{await navigator.clipboard.writeText(track.absolute_path||'');event.currentTarget.textContent='Path copied';}catch(_){event.currentTarget.textContent='Copy failed';}});
    inspector.querySelector('.inspector-reveal')?.addEventListener('click', async event => {const response=await fetch(`/api/downloaded-library/tracks/${track.id}/reveal`,{method:'POST'}),payload=await response.json();event.currentTarget.textContent=response.ok?'Revealed in Finder':payload.detail||'Could not reveal';});
    inspector.querySelector('.inspector-analyze-key')?.addEventListener('click',async event=>{const action=event.currentTarget,status=inspector.querySelector('.key-analysis-result');action.disabled=true;action.textContent='Analyzing key…';status.textContent='Comparing tonal estimates; all other analysis remains unchanged.';try{const response=await fetch(`/api/downloaded-library/tracks/${track.id}/analyze-key`,{method:'POST'}),payload=await response.json();if(!response.ok)throw new Error(payload.detail||'Key analysis failed.');track.detected_key=payload.detected_key;track.key_confidence=payload.key_confidence;track.key_analyzed_at=payload.key_analyzed_at;inspector.querySelector('.inspector-key-value').textContent=payload.detected_key||'Unknown';inspector.querySelector('.inspector-key-value').nextElementSibling.textContent=`Key · ${Math.round(Number(payload.key_confidence||0))}%`;status.textContent=`Complete · ${payload.detected_key} is the current estimate.`;action.textContent='Analyze key again';}catch(error){status.textContent=error.message;action.textContent='Try key analysis again';}finally{action.disabled=false;}});
    const familyForm=inspector.querySelector('.inspector-family-link'),familyContent=inspector.querySelector('.inspector-family-content'),familySuggestions=inspector.querySelector('.inspector-family-suggestions');
    const familySection=inspector.querySelector('.inspector-family');
    familySection.classList.add('is-collapsed');
    let familyLoaded=false;
    inspector.querySelector('.inspector-manage-family').onclick=()=>{familySection.hidden=false;familySection.classList.remove('is-collapsed');if(!familyLoaded){familyLoaded=true;loadFamily();}familySection.scrollIntoView({behavior:'smooth',block:'nearest'});};
    inspector.querySelector('.inspector-family-close').onclick=()=>{familySection.hidden=true;familySection.classList.add('is-collapsed');familyForm.hidden=true;inspector.querySelector('.inspector-family-toggle').textContent='Link as version of…';};
    inspector.querySelector('.inspector-family-toggle').onclick=event=>{
      if(familyForm.hidden){
        familyForm.hidden=false;
        event.currentTarget.textContent='Close version tools';
      }else{
        familyForm.hidden=true;
        event.currentTarget.textContent='Link as version of…';
      }
      if(!familyForm.hidden)familyForm.elements.target.focus();
    };
    const loadFamily=async()=>{const response=await fetch(`/api/downloaded-library/tracks/${track.id}/family`),payload=await response.json();if(!response.ok){familyContent.innerHTML=`<p>${escapeHtml(payload.detail||'Related versions could not be loaded.')}</p>`;return;}familyContent.innerHTML=payload.family.map(member=>`<article><div><b>${escapeHtml(member.title||member.filename)}</b><span>${escapeHtml(member.artist||'Unknown artist')} · ${escapeHtml(member.recording_code)}-${escapeHtml(member.version_code||'ORG')}</span></div>${Number(member.id)===Number(track.id)?'<em>Current</em>':`<button type="button" data-family-target="${member.id}">View</button>`}</article>`).join('');if(payload.family.length>1)familyContent.insertAdjacentHTML('beforeend','<button type="button" class="button secondary inspector-family-unlink">Unlink current track</button>');familySuggestions.innerHTML=payload.suggestions.length?`<b>Suggested families</b>${payload.suggestions.map(item=>`<button type="button" data-suggestion-id="${escapeHtml(item.track.recording_code)}-${escapeHtml(item.track.version_code||'ORG')}"><span>${escapeHtml(item.track.title||item.track.filename)} · ${escapeHtml(item.track.artist||'Unknown artist')}</span><small>${item.score}% · ${escapeHtml(item.reasons.join(', '))}</small></button>`).join('')}`:'<small>No strong automatic suggestions. Enter a target track ID to link manually.</small>';familySuggestions.querySelectorAll('[data-suggestion-id]').forEach(option=>option.onclick=()=>{familyForm.hidden=false;familyForm.elements.target.value=option.dataset.suggestionId;familyForm.elements.relationship.focus();});familyContent.querySelector('.inspector-family-unlink')?.addEventListener('click',async()=>{if(!await confirmAction('Unlink this version into its own recording family? You can link it again later.', {title:'Unlink recording version', acceptLabel:'Unlink'}))return;const result=await fetch(`/api/downloaded-library/tracks/${track.id}/unlink-version`,{method:'POST'});if(result.ok){await loadDownloadedLibrary();closeDownloadedInspector();}});};
    familyForm.onsubmit=async event=>{event.preventDefault();const target=familyForm.elements.target.value.trim();if(!target){familyForm.querySelector('small').textContent='Enter a valid track ID.';return;}const response=await fetch(`/api/downloaded-library/tracks/${track.id}/link-version`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target_identity:target,relationship:familyForm.elements.relationship.value})}),payload=await response.json();if(!response.ok){familyForm.querySelector('small').textContent=payload.detail||'Could not link this version.';return;}await loadDownloadedLibrary();closeDownloadedInspector();};
  });
  summary.querySelectorAll('.filter-downloaded-genre').forEach(button => button.onclick = () => { downloadedUiState.genre=button.dataset.value;downloadedUiState.detailedGenre='all'; requestPage(1); document.querySelector('.downloaded-toolbar').scrollIntoView({behavior:'smooth'}); });
  summary.querySelectorAll('.filter-detailed-genre').forEach(button => button.onclick = () => { downloadedUiState.genre='all';downloadedUiState.detailedGenre=button.dataset.value; requestPage(1); document.querySelector('.downloaded-toolbar').scrollIntoView({behavior:'smooth'}); });
  const detailedGenreSearch=summary.querySelector('.detailed-genre-search');
  if(detailedGenreSearch)detailedGenreSearch.oninput=()=>{const query=detailedGenreSearch.value.trim().toLowerCase();let visible=0;summary.querySelectorAll('.detailed-genre-list .filter-detailed-genre').forEach(button=>{const matches=!query||button.dataset.search.includes(query);button.hidden=!matches;visible+=Number(matches);});summary.querySelector('.detailed-genre-empty').hidden=visible!==0;};
  summary.querySelectorAll('.filter-downloaded-analysis').forEach(button => button.onclick = () => { downloadedUiState.analysis=button.dataset.value; requestPage(1); document.querySelector('.downloaded-toolbar').scrollIntoView({behavior:'smooth'}); });
  summary.querySelectorAll('.filter-downloaded-playlist').forEach(button => button.onclick = () => { downloadedUiState.playlist=button.dataset.value; requestPage(1); document.querySelector('.downloaded-toolbar').scrollIntoView({behavior:'smooth'}); });
  root.querySelectorAll('.downloaded-actions').forEach(menu=>menu.addEventListener('toggle',()=>{if(!menu.open)return;root.querySelectorAll('.downloaded-actions[open]').forEach(other=>{if(other!==menu)other.open=false;});}));
  bindLazyAudio(root);
  bindCompactAudio(root);
  if(pendingMetadataReview){const requested=root.querySelector(`.downloaded-card[data-id="${pendingMetadataReview.id}"]`)||metadataCards[0];pendingMetadataReview=null;requested?.querySelector('.edit-track-metadata')?.click();}
}

function libraryRoles(song) {
  if (Array.isArray(song._roles) && song._roles.length) return song._roles;
  const style = String(song.detected_style || '').toLowerCase();
  const timing = String(song.timing || '').toLowerCase();
  const bpm = Number(song.bpm || 0);
  const roles = new Set();
  if (style.includes('ambient') || style.includes('sparse')) roles.add('ambient');
  if (style.includes('melodic') || style.includes('harmonic') || Number(song.key_confidence || 0) >= .65) roles.add('melodic');
  if (style.includes('vocal-safe') || Math.max(song.intro?.instrumentalness || 0, song.outro?.instrumentalness || 0) >= .72) roles.add('vocal-safe');
  if (timing.includes('live') || timing.includes('variable') || Number(song.tempo_drift || 0) >= .08) roles.add('live timing');
  if (style.includes('peak') || style.includes('high-energy') || (bpm >= 122 && !roles.has('ambient'))) roles.add('peak-time');
  if (style.includes('slow') || style.includes('subtle') || bpm && bpm < 120 || roles.has('ambient')) roles.add('warm-up');
  if (style.includes('closing') || Number(song.dj_readiness?.outro_mixable_bars || 0) >= 8 || song.outro?.section === 'closing') roles.add('closing');
  if (!roles.size) roles.add(bpm >= 122 ? 'peak-time' : 'warm-up');
  return [...roles];
}

const LIBRARY_ROLE_INFO = {
  'warm-up':['Warm-up','Lower-pressure selections that build the room without spending peak energy too early.'],
  'peak-time':['Peak-time','High-impact tracks suited to the busiest, most energetic part of a set.'],
  closing:['Closing','Tracks with an ending, mood, or mix-out shape that can resolve a set.'],
  'vocal-safe':['Vocal-safe','More instrumental space, useful for layering without clashing with another vocal.'],
  melodic:['Melodic','Clear tonal or harmonic identity; key compatibility matters more when mixing these.'],
  ambient:['Ambient','Sparse or atmospheric material useful for openings, resets, and transitions.'],
  'live timing':['Live timing','Tempo may drift; ride the pitch or mix shorter instead of trusting a rigid beat grid.'],
};

const CAMELOT_KEYS = {
  'A minor':'8A','E minor':'9A','B minor':'10A','F# minor':'11A','C# minor':'12A','G# minor':'1A','D# minor':'2A','A# minor':'3A','F minor':'4A','C minor':'5A','G minor':'6A','D minor':'7A',
  'C major':'8B','G major':'9B','D major':'10B','A major':'11B','E major':'12B','B major':'1B','F# major':'2B','C# major':'3B','G# major':'4B','D# major':'5B','A# major':'6B','F major':'7B',
};

function normalizedKey(value) {
  return String(value || '').replace(/^Db /,'C# ').replace(/^Eb /,'D# ').replace(/^Gb /,'F# ').replace(/^Ab /,'G# ').replace(/^Bb /,'A# ');
}

function camelotKey(value) { return CAMELOT_KEYS[normalizedKey(value)] || '—'; }
function libraryKeyMode() { return localStorage.getItem('audioextender-key-view') || 'both'; }
function formatLibraryKey(value, mode=libraryKeyMode()) {
  const standard = value || 'Unknown key'; const camelot = camelotKey(value);
  if (mode === 'standard') return standard;
  if (mode === 'camelot') return camelot === '—' ? 'Unknown Camelot' : camelot;
  return camelot === '—' ? standard : `${standard} · ${camelot}`;
}

function songEnergy(song) {
  if (Number.isFinite(Number(song._energy))) return Number(song._energy);
  const values = (song.section_profiles || []).map(section => Number(String(section.reason || '').match(/energy\s+([\d.]+)/i)?.[1])).filter(Number.isFinite);
  if (values.length) return values.reduce((sum,value) => sum + value, 0) / values.length;
  const style = String(song.detected_style || '').toLowerCase();
  return style.includes('high-energy') || style.includes('peak') ? .8 : style.includes('ambient') || style.includes('sparse') ? .25 : .5;
}
function energyBand(value) { return value >= .67 ? 'high' : value < .4 ? 'low' : 'medium'; }
function vocalProfile(song) {
  if (song._vocals) return song._vocals;
  const instrumental = Math.max(Number(song.intro?.instrumentalness || 0), Number(song.outro?.instrumentalness || 0));
  return instrumental >= .72 ? 'vocal-safe' : instrumental < .45 ? 'vocal-forward' : 'mixed';
}
function timingProfile(song) {
  if (song._timing) return song._timing;
  const timing = String(song.timing || '').toLowerCase();
  return timing.includes('live') || timing.includes('variable') || Number(song.tempo_drift || 0) >= .08 ? 'variable' : 'steady';
}
function effectivePreset(song, job) {
  const analyzed = String(song.preset || '');
  const resolved = analyzed.includes('→') ? analyzed.split('→').at(-1).trim() : analyzed.trim();
  return String(resolved || job?.preset || 'default').toLowerCase();
}

function harmonicCompatibility(left, right) {
  const notes = {C:0,'C#':1,Db:1,D:2,'D#':3,Eb:3,E:4,F:5,'F#':6,Gb:6,G:7,'G#':8,Ab:8,A:9,'A#':10,Bb:10,B:11};
  const parse = value => { const match = String(value || '').match(/^([A-G](?:#|b)?)\s+(major|minor)/i); return match ? {pitch:notes[match[1]], mode:match[2].toLowerCase()} : null; };
  const a = parse(left); const b = parse(right);
  if (!a || !b) return {score:10,label:'key unknown'};
  const distance = Math.min((a.pitch-b.pitch+12)%12,(b.pitch-a.pitch+12)%12);
  if (a.pitch === b.pitch && a.mode === b.mode) return {score:40,label:'same key'};
  if (a.mode !== b.mode && ((a.mode === 'minor' && (a.pitch+3)%12 === b.pitch) || (b.mode === 'minor' && (b.pitch+3)%12 === a.pitch))) return {score:36,label:'relative key'};
  if (distance === 5 && a.mode === b.mode) return {score:30,label:'neighboring key'};
  if (a.pitch === b.pitch) return {score:24,label:'parallel key'};
  return {score:0,label:'distant key'};
}

function compatibility(left, right) {
  const bpmA = Number(left.bpm || 0); const bpmB = Number(right.bpm || 0);
  const ratios = [bpmB, bpmB / 2, bpmB * 2].filter(Boolean);
  const difference = bpmA ? Math.min(...ratios.map(value => Math.abs(value - bpmA) / bpmA)) : 1;
  const tempoScore = Math.max(0, 45 * (1 - difference / .08));
  const key = harmonicCompatibility(left.key, right.key);
  const keyScore = key.score * .875;
  const energyScore = Math.max(0, 10 * (1 - Math.abs(songEnergy(left) - songEnergy(right)) / .55));
  const sharedRoles = libraryRoles(left).filter(role => libraryRoles(right).includes(role));
  const roleScore = Math.min(10, sharedRoles.length * 5);
  return {score:Math.round(tempoScore + keyScore + energyScore + roleScore), difference, key:key.label, components:{tempo:Math.round(tempoScore),key:Math.round(keyScore),energy:Math.round(energyScore),role:Math.round(roleScore)}, sharedRoles};
}

const SET_STORAGE_KEY = 'dj-library-studio-sets-v1';
function setTrackId(track) { return String(track.source_name || '').toLowerCase(); }
function selectedSetGenres() { return [...$('#set-genre').selectedOptions].map(option=>option.value).filter(value=>value&&value!=='all'); }
function selectedSetDetailedGenres() { return [...$('#set-detailed-genres').selectedOptions].map(option=>option.value).filter(value=>value&&value!=='all'); }
function selectedExcludedSetGenres() { return [...$('#set-excluded-genres').selectedOptions].map(option=>option.value).filter(Boolean); }
function renderExcludedSetGenres() { const selected=selectedExcludedSetGenres();const chips=$('#set-excluded-genre-chips');chips.replaceChildren(...selected.map(genre=>{const chip=document.createElement('button');chip.type='button';chip.textContent=`${genre} ×`;chip.onclick=()=>{const option=[...$('#set-excluded-genres').options].find(item=>item.value===genre);if(option)option.selected=false;$('#set-excluded-genres').dispatchEvent(new Event('change',{bubbles:true}));};return chip;})); }
function trackMatchesSetGenre(track, genre) { return track._genre===genre || track._genre.startsWith(`${genre} / `); }
function setTrackDetailedGenres(track){return String(track._detailedGenre||'').split(',').map(value=>value.trim()).filter(Boolean);}
function trackMatchesSetDetailedGenre(track, genre) { return setTrackDetailedGenres(track).some(value=>value.toLowerCase()===String(genre||'').toLowerCase()); }
function renderSetDetailedGenres(){const selected=selectedSetDetailedGenres(),chips=$('#set-detailed-genre-chips');chips.replaceChildren(...selected.map(genre=>{const chip=document.createElement('button');chip.type='button';chip.textContent=`${genre} ×`;chip.onclick=()=>{const option=[...$('#set-detailed-genres').options].find(item=>item.value===genre);if(option)option.selected=false;$('#set-detailed-genres').dispatchEvent(new Event('change',{bubbles:true}));};return chip;}));}
function populateSetDetailedGenres(restore=[]){const parents=selectedSetGenres();const select=$('#set-detailed-genres');const current=restore.length?restore:selectedSetDetailedGenres();const choices=[...new Set(setBuilderLibrary.filter(track=>!parents.length||parents.some(parent=>trackMatchesSetGenre(track,parent))).flatMap(setTrackDetailedGenres))].sort((a,b)=>a.localeCompare(b));select.replaceChildren(option('all','Any detailed genre'),...choices.map(value=>option(value,value)));[...select.options].forEach(item=>{item.selected=current.length?current.includes(item.value):item.value==='all';});if(!select.selectedOptions.length)select.querySelector('option[value="all"]').selected=true;renderSetDetailedGenres();}
function renderSetGenreMix() {
  const genres=selectedSetGenres(); const chips=$('#set-genre-chips'); const weights=$('#set-genre-weights');
  const existing=new Map([...weights.querySelectorAll('input')].map(input=>[input.dataset.genre,input.value]));
  const countChanged=Number(weights.dataset.count||0)!==genres.length;weights.dataset.count=String(genres.length);
  chips.replaceChildren(); weights.replaceChildren(); weights.hidden=!genres.length;
  genres.forEach(genre=>{
    const chip=document.createElement('button');chip.type='button';chip.textContent=`${genre} ×`;chip.onclick=()=>{const option=[...$('#set-genre').options].find(item=>item.value===genre);if(option)option.selected=false;setGenreSelectionOrder=setGenreSelectionOrder.filter(value=>value!==genre);if(!selectedSetGenres().length)$('#set-genre').querySelector('option[value="all"]').selected=true;$('#set-genre').dispatchEvent(new Event('change',{bubbles:true}));};chips.append(chip);
    const row=document.createElement('label');const input=document.createElement('input');input.type='number';input.min='0';input.max='100';input.step='5';input.value=!countChanged&&existing.has(genre)?existing.get(genre):String(Math.round(100/genres.length));input.dataset.genre=genre;row.append(document.createTextNode(genre),input);const suffix=document.createElement('span');suffix.textContent='%';row.append(suffix);weights.append(row);
  });
}
function setBrief() {
  const genres=selectedSetGenres();const genreWeights=Object.fromEntries([...$('#set-genre-weights').querySelectorAll('input')].map(input=>[input.dataset.genre,Math.max(0,Number(input.value||0))]));
  return {name:$('#set-name').value.trim() || 'New DJ Set',length:Number($('#set-length').value),genres,detailedGenres:selectedSetDetailedGenres(),excludedGenres:selectedExcludedSetGenres(),genreWeights,genreFlow:$('#set-genre-flow').value,vibe:$('#set-vibe').value,curve:$('#set-curve').value,bpmMin:Number($('#set-bpm-min').value || 0),bpmMax:Number($('#set-bpm-max').value || Infinity),keyStrictness:$('#set-key-strictness').value,vocals:$('#set-vocals').value,timing:$('#set-timing').value,edits:$('#set-edits').value,minimumHealth:Number($('#set-minimum-health').value || 65)};
}
function targetSetEnergy(index, count, brief) {
  const progress = count <= 1 ? 0 : index / (count - 1);
  const base = {balanced:.5,'dance-party':.7,'warm-up':.32,'peak-time':.78,melodic:.52,'vocal-safe':.48,ambient:.24,closing:.55}[brief.vibe] ?? .5;
  if (brief.curve === 'rise') return Math.min(.92, base - .12 + progress * .45);
  if (brief.curve === 'peak-release') return progress < .72 ? Math.min(.92, base - .12 + progress * .62) : Math.max(.35, .92 - (progress - .72) * 1.45);
  if (brief.curve === 'waves') return Math.max(.2, Math.min(.92, base + Math.sin(progress * Math.PI * 4 - Math.PI / 2) * .22 + progress * .12));
  return base;
}
const SET_PROPOSAL_STRATEGIES = [
  {id:'safe',label:'Safe Flow',summary:'Smooth, dependable transitions',detail:'Prioritizes tempo, harmony, vocal space, and consistent mixability.'},
  {id:'energy',label:'Energy Journey',summary:'The strongest planned arc',detail:'Follows the requested rise, waves, or peak-and-release shape most closely.'},
  {id:'adventurous',label:'Adventurous Mix',summary:'More variety and surprise',detail:'Explores broader genres, roles, and harmonic color while respecting your health floor.'},
];
function setCandidateScore(track, previous, index, count, brief, strategy='balanced', usedByOtherProposals=new Set()) {
  const energyFit = Math.max(0, 45 * (1 - Math.abs(songEnergy(track) - targetSetEnergy(index, count, brief)) / .7));
  const roles = libraryRoles(track);
  const vibeFit = brief.vibe === 'balanced' || roles.includes(brief.vibe) || (brief.vibe==='dance-party'&&songEnergy(track)>=.58) ? 15 : 0;
  const transition = previous ? compatibility(previous, track) : null;
  let transitionScore = transition ? transition.score * .7 : 25;
  if (brief.keyStrictness === 'strict' && transition && transition.components.key < 20) transitionScore -= 35;
  if (brief.keyStrictness === 'adventurous' && transition) transitionScore = transition.components.tempo * .65 + transition.components.energy * 1.2;
  const editFit = brief.edits === 'either' ? 0 : (brief.edits === 'extended') === track._hasExtended ? 6 : -3;
  const matchingGenres=(brief.genres||[]).filter(genre=>trackMatchesSetGenre(track,genre));
  const totalWeight=Math.max(1,Object.values(brief.genreWeights||{}).reduce((sum,value)=>sum+value,0));
  let genreFit=matchingGenres.length?18*Math.max(...matchingGenres.map(genre=>(brief.genreWeights[genre]||0)/totalWeight)):0;
  if (brief.genres?.length>1 && brief.genreFlow!=='blend') {
    const order=setGenreSelectionOrder.filter(genre=>brief.genres.includes(genre)).concat(brief.genres.filter(genre=>!setGenreSelectionOrder.includes(genre)));
    const progress=(index+.5)/Math.max(1,count);let target=order[Math.min(order.length-1,Math.floor(progress*order.length))];
    if(brief.genreFlow==='chapters'){let cursor=0;for(const genre of order){cursor+=(brief.genreWeights[genre]||0)/totalWeight;if(progress<=cursor){target=genre;break;}}}
    if(trackMatchesSetGenre(track,target))genreFit+=22;
  }
  let strategyFit=0;
  if(strategy==='safe') strategyFit=(transition?.score||65)*.48+(setVocalProfile(track)==='vocal-forward'&&previous&&setVocalProfile(previous)==='vocal-forward'?-28:8)-Math.abs(songEnergy(track)-(previous?songEnergy(previous):songEnergy(track)))*18;
  if(strategy==='energy') strategyFit=energyFit*.8-Math.abs(songEnergy(track)-targetSetEnergy(index,count,brief))*34+(previous?Math.min(12,Math.abs(songEnergy(track)-songEnergy(previous))*14):0)-(usedByOtherProposals.has(setTrackId(track))?8:0);
  if(strategy==='adventurous') { const genreChange=previous&&track._genre!==previous._genre?18:0;const roleChange=previous?libraryRoles(track).filter(role=>!libraryRoles(previous).includes(role)).length*6:8;const harmonicColor=transition&&transition.components.key<31&&transition.components.key>=20?10:0;strategyFit=genreChange+roleChange+harmonicColor-(usedByOtherProposals.has(setTrackId(track))?18:0); }
  return energyFit + vibeFit + transitionScore + editFit + genreFit + strategyFit;
}
function setVocalProfile(track) {
  return track.intro || track.outro || track.stem_reliability != null ? vocalProfile(track) : 'mixed';
}
function eligibleSetTracks(brief) {
  return setBuilderLibrary.filter(track => {
    const bpm = Number(track.bpm || 0); const id = setTrackId(track);
    return !setExcludedIds.has(id)
      && (!brief.genres.length || brief.genres.some(genre=>trackMatchesSetGenre(track,genre)))
      && (!(brief.detailedGenres||[]).length || brief.detailedGenres.some(genre=>trackMatchesSetDetailedGenre(track,genre)))
      && !(brief.excludedGenres||[]).some(genre=>trackMatchesSetGenre(track,genre))
      && (!brief.bpmMin || bpm >= brief.bpmMin)
      && (!Number.isFinite(brief.bpmMax) || !brief.bpmMax || bpm <= brief.bpmMax)
      && (brief.vocals === 'all' || setVocalProfile(track) === brief.vocals)
      && (brief.timing === 'all' || timingProfile(track) === brief.timing);
  });
}
async function generateSetPlan() {
  const brief = setBrief(); const pool = eligibleSetTracks(brief);
  if (pool.length < 2) { $('#set-builder-message').textContent = 'Not enough analyzed tracks match this brief. Relax a filter and try again.'; return; }
  const averageSeconds = pool.reduce((sum,track) => sum + Math.max(90, Number(track.duration_seconds || 210) - 30), 0) / pool.length;
  const count = Math.max(2, Math.min(pool.length, Math.ceil(brief.length * 60 / averageSeconds)));
  const required = pool.filter(track => setRequiredIds.has(setTrackId(track)));
  const previousPlan = currentSetPlan;
  const generatedTrackIds=new Set();
  const buildVariation = (strategy) => {
    const remaining = new Map(pool.map(track => [setTrackId(track), track])); const nextPlan = []; let failed = false;
    setGenerationNonce += 1;
    Array.from({length:count}, (_, index) => {
      if (failed) return;
      const locked = previousPlan[index];
      if (locked && setLockedIds.has(setTrackId(locked)) && remaining.has(setTrackId(locked))) { remaining.delete(setTrackId(locked)); nextPlan.push(locked); return; }
      const requiredIndex = required.length ? Math.round(index * (required.length + 1) / count) - 1 : -1;
      const forced = required[requiredIndex];
      if (forced && remaining.has(setTrackId(forced))) { remaining.delete(setTrackId(forced)); nextPlan.push(forced); return; }
      const previous = nextPlan[index - 1] || null;
      const ranked = [...remaining.values()].map(track=>{const wasSamePosition=Boolean(previousPlan[index])&&setTrackId(previousPlan[index])===setTrackId(track),wasInPrevious=previousPlan.some(item=>setTrackId(item)===setTrackId(track));return {track,score:setCandidateScore(track,previous,index,count,brief,strategy,generatedTrackIds)-(wasSamePosition?12:wasInPrevious?3:0)};}).sort((a,b)=>b.score-a.score);
      if (!ranked.length) { failed = true; return; }
      const competitive=ranked.filter(item=>item.score>=ranked[0].score-18).slice(0,18);
      const weights=competitive.map(item=>Math.exp((item.score-competitive.at(-1).score)/5));const total=weights.reduce((sum,value)=>sum+value,0);let pick=(Math.abs(Math.sin(setGenerationNonce*9283+index*3343))*total),choice=competitive[0]?.track;for(let option=0;option<competitive.length;option+=1){pick-=weights[option];if(pick<=0){choice=competitive[option].track;break;}}
      if (choice) { remaining.delete(setTrackId(choice)); nextPlan.push(choice); }
    });
    required.forEach(track => { if (!nextPlan.some(item => setTrackId(item) === setTrackId(track))) nextPlan.push(track); });
    return failed ? [] : nextPlan;
  };
  const proposals=[];
  for(const strategy of SET_PROPOSAL_STRATEGIES){let bestPlan=[],bestHealth={score:-1,transitions:[],vocalClashes:0},attempts=0;for(;attempts<24;attempts+=1){const candidate=buildVariation(strategy.id);if(candidate.length<count)continue;const repaired=improveSetOrder(candidate,brief);const health=setHealth(repaired);const overlap=repaired.filter(track=>generatedTrackIds.has(setTrackId(track))).length/Math.max(1,repaired.length);const distinctBonus=strategy.id==='adventurous'?(1-overlap)*12:0;const rank=health.score+distinctBonus;if(rank>(bestHealth.rank??-1)){bestPlan=repaired;bestHealth={...health,rank};}if(health.score>=brief.minimumHealth&&attempts>=5){attempts+=1;break;}}const accepted=bestPlan.length>=count&&bestHealth.score>=brief.minimumHealth;if(accepted)bestPlan.forEach(track=>generatedTrackIds.add(setTrackId(track)));proposals.push({...strategy,accepted,attempts,health:bestHealth,snapshot:{tracks:bestPlan.map(setTrackId),locked:[...setLockedIds],transitions:{}}});}
  const accepted=proposals.filter(proposal=>proposal.accepted);if(!accepted.length){const best=proposals.sort((a,b)=>b.health.score-a.health.score)[0];const issues=setHealthIssues(best.health,brief.minimumHealth);$('#set-builder-message').textContent=`No direction was applied. The best search reached ${best.health.score}/100, below your ${brief.minimumHealth} target. ${issues.slice(0,2).join(' · ')||'Relax a constraint or lower the health floor.'}`;return;}
  if(currentSetPlan.length)pushSetHistory();setProposals=proposals;const preferred=proposals.find(proposal=>proposal.id==='safe'&&proposal.accepted)||accepted.sort((a,b)=>b.health.score-a.health.score)[0];activeSetProposal=preferred.id;restoreSetSnapshot(preferred.snapshot,false);$('#set-builder-message').textContent=`Built ${accepted.length} distinct direction${accepted.length===1?'':'s'}. Optimizing transition techniques for ${preferred.label}…`;await autoOptimizeSetTransitions();preferred.snapshot=setPlanSnapshot();preferred.health=setHealth();renderSetPlan();$('#set-builder-message').textContent=`${accepted.length} distinct direction${accepted.length===1?'':'s'} ready · ${preferred.label} applied at ${preferred.health.score}/100. Switch directions below to compare.`;
}
function setPlanSnapshot() { return {tracks:currentSetPlan.map(setTrackId),locked:[...setLockedIds],transitions:JSON.parse(JSON.stringify(setTransitionSettings))}; }
function restoreSetSnapshot(snapshot,render=true) { const byId=new Map(setBuilderLibrary.map(track=>[setTrackId(track),track]));currentSetPlan=(snapshot?.tracks||[]).map(id=>byId.get(id)).filter(Boolean);setLockedIds=new Set(snapshot?.locked||[]);setTransitionSettings=snapshot?.transitions||{};if(render)renderSetPlan(); }
async function selectSetProposal(id){const next=setProposals.find(proposal=>proposal.id===id&&proposal.accepted);if(!next||id===activeSetProposal)return;const current=setProposals.find(proposal=>proposal.id===activeSetProposal);if(current){current.snapshot=setPlanSnapshot();current.health=setHealth();}stopTransitionPreview();pushSetHistory();activeSetProposal=id;restoreSetSnapshot(next.snapshot,false);if(!Object.keys(setTransitionSettings).length){$('#set-builder-message').textContent=`Optimizing transitions for ${next.label}…`;await autoOptimizeSetTransitions();next.snapshot=setPlanSnapshot();next.health=setHealth();}renderSetPlan();$('#set-builder-message').textContent=`${next.label} applied · ${setHealth().score}/100 health. Your edits to the other directions are saved.`;}
function renderSetProposals(){const root=$('#set-proposals');if(!root)return;root.innerHTML=setProposals.map(proposal=>{const active=proposal.id===activeSetProposal;const score=Math.max(0,proposal.health?.score??0);return `<button type="button" class="set-proposal${active?' active':''}${proposal.accepted?'':' unavailable'}" role="radio" aria-checked="${active}" data-proposal="${proposal.id}" ${proposal.accepted?'':'disabled'}><span><b>${proposal.label}</b><em>${proposal.accepted?`${score}/100 health`:`Below target · ${score}/100`}</em></span><strong>${proposal.summary}</strong><small>${proposal.detail}</small></button>`;}).join('');root.querySelectorAll('[data-proposal]').forEach(button=>{button.onclick=()=>selectSetProposal(button.dataset.proposal);button.onkeydown=event=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;event.preventDefault();const available=[...root.querySelectorAll('[data-proposal]:not(:disabled)')];const offset=['ArrowRight','ArrowDown'].includes(event.key)?1:-1;const next=available[(available.indexOf(button)+offset+available.length)%available.length];next?.focus();next?.click();};});}
function pushSetHistory() { if(!currentSetPlan.length)return;setPlanHistory.push(setPlanSnapshot());if(setPlanHistory.length>60)setPlanHistory.shift();setPlanFuture=[];updateSetHistoryButtons(); }
function updateSetHistoryButtons() { const undo=$('#set-undo'),redo=$('#set-redo');if(undo)undo.disabled=!setPlanHistory.length;if(redo)redo.disabled=!setPlanFuture.length; }
function undoSetEdit() { if(!setPlanHistory.length)return;setPlanFuture.push(setPlanSnapshot());restoreSetSnapshot(setPlanHistory.pop());updateSetHistoryButtons(); }
function redoSetEdit() { if(!setPlanFuture.length)return;setPlanHistory.push(setPlanSnapshot());restoreSetSnapshot(setPlanFuture.pop());updateSetHistoryButtons(); }
function setTransitionOverlap(left,right) { const duration=Number(left?.duration_seconds||0);const tail=Number.isFinite(Number(left?.mix_out))&&Number(left.mix_out)>0&&duration>Number(left.mix_out)?duration-Number(left.mix_out):0;const lead=Number(right?.mix_in||0);const bpm=Math.max(60,Number(left?.bpm||right?.bpm||120));const bars=Math.min(Number(left?.outro?.mixable_bars||left?.dj_readiness?.outro_mixable_bars||0),Number(right?.intro?.mixable_bars||right?.dj_readiness?.intro_mixable_bars||0));const musical=bars>0?bars*4*60/bpm:0;return Math.max(8,Math.min(90,Math.max(tail,lead,musical,30))); }
function setRuntime(plan=currentSetPlan) { return plan.reduce((sum,track,index) => sum + Number(track.duration_seconds || 210) - (index ? setTransitionOverlap(plan[index-1],track) : 0), 0); }
function setHealth(plan=currentSetPlan) { if(plan.length<2)return {score:100,transitions:[],vocalClashes:0};const transitions=plan.slice(1).map((track,index)=>({...compatibility(plan[index],track),from:index,to:index+1}));const average=transitions.reduce((sum,item)=>sum+item.score,0)/transitions.length;const vocalClashes=plan.slice(1).filter((track,index)=>setVocalProfile(plan[index])==='vocal-forward'&&setVocalProfile(track)==='vocal-forward').length;const score=Math.max(0,Math.min(100,Math.round(average-vocalClashes*3)));return {score,transitions,vocalClashes}; }
function setOrderFitness(plan,brief) { const health=setHealth(plan);const energyPenalty=plan.reduce((sum,track,index)=>sum+Math.abs(songEnergy(track)-targetSetEnergy(index,plan.length,brief)),0)*3;return health.score*5-energyPenalty; }
function improveSetOrder(plan,brief) { const improved=[...plan];const fixed=new Set(improved.map((track,index)=>setLockedIds.has(setTrackId(track))?index:null).filter(index=>index!=null));let current=setOrderFitness(improved,brief);for(let pass=0;pass<5;pass+=1){let best=current,bestSwap=null;for(let left=0;left<improved.length-1;left+=1){if(fixed.has(left))continue;for(let right=left+1;right<improved.length;right+=1){if(fixed.has(right))continue;[improved[left],improved[right]]=[improved[right],improved[left]];const score=setOrderFitness(improved,brief);[improved[left],improved[right]]=[improved[right],improved[left]];if(score>best+.01){best=score;bestSwap=[left,right];}}}if(!bestSwap)break;[improved[bestSwap[0]],improved[bestSwap[1]]]=[improved[bestSwap[1]],improved[bestSwap[0]]];current=best;}return improved; }
function setHealthIssues(health, threshold) { const issues=[];health.transitions.filter(item=>item.score<threshold).sort((a,b)=>a.score-b.score).slice(0,4).forEach(item=>{const weakest=Object.entries(item.components).sort((a,b)=>a[1]-b[1])[0]?.[0]||'compatibility';issues.push(`${item.from+1}→${item.to+1} ${item.score}% (${weakest}${item.key==='distant key'?', distant keys':''})`);});if(health.vocalClashes)issues.push(`${health.vocalClashes} vocal clash${health.vocalClashes===1?'':'es'}`);return issues; }
function transitionSettingKey(left,right) { return `${setTrackId(left)}→${setTrackId(right)}`; }
function transitionSettings(index) { const left=currentSetPlan[index-1],right=currentSetPlan[index];const key=transitionSettingKey(left,right);const bars=Number($('#set-transition-bars')?.value||16);const bpm=Math.max(60,Number(left?.bpm||120));const overlap=bars*4*60/bpm;return setTransitionSettings[key]||{mixOut:Math.max(0,Number(left?.mix_out||Number(left?.duration_seconds||210)-overlap)),mixIn:Math.max(0,Number(right?.mix_in||0)),bars,curve:'smooth',technique:'crossfade',tempoSync:true,notes:''}; }
function saveTransitionSettings(index,values) { const key=transitionSettingKey(currentSetPlan[index-1],currentSetPlan[index]);setTransitionSettings[key]={...transitionSettings(index),...values}; }
function stopTransitionPreview(nextPreviewLabel='▶ Preview mix') { if(transitionPreviewFrame)cancelAnimationFrame(transitionPreviewFrame);if(transitionPreviewPlayheadFrame)cancelAnimationFrame(transitionPreviewPlayheadFrame);if(transitionPreviewTimer)clearTimeout(transitionPreviewTimer);transitionPreviewFrame=0;transitionPreviewPlayheadFrame=0;transitionPreviewTimer=0;const previewEditor=transitionPreviewState?.button.closest('.transition-editor');if(previewEditor)updateTransitionFadePlayhead(previewEditor,0,transitionPreviewState.settings.curve,false,transitionPreviewState.settings.technique||'crossfade');transitionPreviewState?.audioGraph?.context?.close?.().catch(()=>{});transitionPreviewAudio.forEach(audio=>{audio.pause();audio.removeAttribute('src');});transitionPreviewAudio=[];transitionPreviewState=null;$$('.set-audition').forEach(button=>{button.disabled=false;button.textContent='Mix transition';button.style.removeProperty('--mix-progress');button.classList.remove('playing','paused');});$$('.preview-transition').forEach(button=>{button.disabled=false;button.textContent=nextPreviewLabel;button.style.removeProperty('--mix-progress');button.classList.remove('playing','paused');}); }
function audioMetadata(audio) { return audio.readyState>=1?Promise.resolve():new Promise((resolve,reject)=>{audio.addEventListener('loadedmetadata',resolve,{once:true});audio.addEventListener('error',()=>reject(new Error('Transition audio unavailable')),{once:true});audio.load();}); }
function createTransitionAudioGraph(outgoing,incoming,technique){const AudioContextClass=window.AudioContext||window.webkitAudioContext;if(!AudioContextClass||technique==='crossfade'||technique==='vocal-duck'||technique==='drop-swap')return null;try{const context=new AudioContextClass(),outSource=context.createMediaElementSource(outgoing),inSource=context.createMediaElementSource(incoming),outFilter=context.createBiquadFilter(),inFilter=context.createBiquadFilter(),outEq=context.createBiquadFilter(),inEq=context.createBiquadFilter(),outGain=context.createGain(),inGain=context.createGain();outFilter.type='lowpass';outFilter.frequency.value=20000;inFilter.type='highpass';inFilter.frequency.value=20;outEq.type='lowshelf';outEq.frequency.value=180;inEq.type='lowshelf';inEq.frequency.value=180;outSource.connect(outFilter).connect(outEq).connect(outGain).connect(context.destination);inSource.connect(inFilter).connect(inEq).connect(inGain).connect(context.destination);const graph={context,outFilter,inFilter,outEq,inEq,outGain,inGain};if(technique==='echo-out'){const delay=context.createDelay(1),feedback=context.createGain(),echoGain=context.createGain();delay.delayTime.value=.32;feedback.gain.value=.28;echoGain.gain.value=0;outEq.connect(delay);delay.connect(feedback).connect(delay);delay.connect(echoGain).connect(context.destination);Object.assign(graph,{delay,feedback,echoGain});}return graph;}catch(_){return null;}}
async function auditionTransition(index,button) {
  if(transitionPreviewState?.button===button){toggleTransitionPreview();return;}
  stopTransitionPreview();const previous=currentSetPlan[index-1],next=currentSetPlan[index];if(!previous?._job?.id||!next?._job?.id)return;
  stopCompactAudio();document.querySelectorAll('audio').forEach(audio=>audio.pause());const settings=transitionSettings(index);const bars=Number(settings.bars||16);const outgoingBpm=Math.max(60,Number(previous.bpm||120));const incomingBpm=Math.max(60,Number(next.bpm||outgoingBpm));const overlap=bars*4*60/outgoingBpm;const lead=Math.min(6,overlap*.25);
  const outgoing=new Audio(`/api/jobs/${previous._job.id}/audio/wav`);const incoming=new Audio(`/api/jobs/${next._job.id}/audio/wav`);outgoing.preload='auto';incoming.preload='auto';incoming.volume=0;incoming.playbackRate=settings.tempoSync?Math.max(.92,Math.min(1.08,outgoingBpm/incomingBpm)):1;transitionPreviewAudio=[outgoing,incoming];button.disabled=true;button.textContent=`Preparing ${bars}-bar mix…`;
  try{await Promise.all([audioMetadata(outgoing),audioMetadata(incoming)]);const outgoingStart=Math.max(0,Number(settings.mixOut||0)-lead);outgoing.currentTime=Math.min(outgoingStart,Math.max(0,outgoing.duration-1));incoming.currentTime=Math.min(Math.max(0,Number(settings.mixIn||0)),Math.max(0,incoming.duration-1));const audioGraph=createTransitionAudioGraph(outgoing,incoming,settings.technique||'crossfade');transitionPreviewState={button,outgoing,incoming,settings,bars,overlap,lead,outgoingBpm,audioGraph,phase:'lead',remaining:lead,progress:0,paused:false};button.disabled=false;button.classList.add('playing');await audioGraph?.context?.resume?.();await outgoing.play();followTransitionPreviewPlayheads();runTransitionPreviewPhase();}catch(error){stopTransitionPreview();button.textContent='Audio unavailable';setTimeout(()=>{button.textContent=button.classList.contains('preview-transition')?'▶ Preview mix':'Mix transition';},1600);}
}
function followTransitionPreviewPlayheads(){if(transitionPreviewPlayheadFrame)cancelAnimationFrame(transitionPreviewPlayheadFrame);const tick=()=>{const state=transitionPreviewState;if(!state||state.paused)return;const editor=state.button.closest('.transition-editor');if(editor){const outgoingInput=editor.querySelector('.transition-mix-out'),incomingInput=editor.querySelector('.transition-mix-in');[[outgoingInput,state.outgoing],[incomingInput,state.incoming]].forEach(([input,audio])=>{const surface=input?._transitionSurface;if(!surface)return;const localTime=Math.max(0,Math.min(60,Number(audio.currentTime||0)-Number(input._transitionWindowStart||0)));surface.setTime(localTime);});const fadeProgress=state.phase==='lead'?0:state.phase==='tail'?1:state.progress;updateTransitionFadePlayhead(editor,fadeProgress,state.settings.curve,true,state.settings.technique||'crossfade');}transitionPreviewPlayheadFrame=requestAnimationFrame(tick);};transitionPreviewPlayheadFrame=requestAnimationFrame(tick);}
function applyTransitionFade(state,progress){const {outgoing,incoming,settings,audioGraph}=state,technique=settings.technique||'crossfade';let {outgoing:outLevel,incoming:inLevel}=transitionFadeLevels(settings.curve,progress,technique);if(technique==='echo-out'&&audioGraph?.echoGain){audioGraph.echoGain.gain.setTargetAtTime(Math.max(0,(progress-.45)*1.35),audioGraph.context.currentTime,.03);}else if(technique==='bass-swap'&&audioGraph){const swap=Math.max(0,Math.min(1,(progress-.4)/.2));audioGraph.outEq.gain.setTargetAtTime(-20*swap,audioGraph.context.currentTime,.03);audioGraph.inEq.gain.setTargetAtTime(-20*(1-swap),audioGraph.context.currentTime,.03);}else if(technique==='filter-blend'&&audioGraph){audioGraph.outFilter.frequency.setTargetAtTime(20000*Math.pow(.025,progress),audioGraph.context.currentTime,.03);audioGraph.inFilter.frequency.setTargetAtTime(20*Math.pow(75,1-progress),audioGraph.context.currentTime,.03);}else if(technique==='loop-assist'&&progress>.05&&progress<.72){const beat=60/Math.max(60,Number(state.outgoingBpm||120)),loopEnd=Number(settings.mixOut||0),loopStart=Math.max(0,loopEnd-beat*8);state.loopRepeats??=0;if(outgoing.currentTime>=loopEnd-.045&&state.loopRepeats<2&&!state.loopPending){state.loopPending=true;const gain=audioGraph?.outGain?.gain,now=audioGraph?.context?.currentTime||0;if(gain){gain.cancelScheduledValues(now);gain.setValueAtTime(gain.value,now);gain.linearRampToValueAtTime(0,now+.035);}setTimeout(()=>{if(transitionPreviewState!==state)return;outgoing.currentTime=loopStart;state.loopRepeats+=1;state.loopPending=false;if(gain){const resumeAt=audioGraph.context.currentTime;gain.cancelScheduledValues(resumeAt);gain.setValueAtTime(0,resumeAt);gain.linearRampToValueAtTime(1,resumeAt+.045);}},38);}}outgoing.volume=Math.max(0,Math.min(1,outLevel));incoming.volume=Math.max(0,Math.min(1,inLevel));}
function runTransitionPreviewPhase(){const state=transitionPreviewState;if(!state||state.paused)return;const {button,outgoing,incoming}=state;button.classList.add('playing');button.classList.remove('paused');if(state.phase==='lead'){button.textContent=`❚❚ Outgoing · mix in ${Math.ceil(state.remaining)}s`;state.started=performance.now();transitionPreviewTimer=setTimeout(async()=>{if(!transitionPreviewState||state.paused)return;state.phase='mix';state.progress=0;try{await incoming.play();runTransitionPreviewPhase();}catch(_){stopTransitionPreview();}},state.remaining*1000);return;}button.textContent=`❚❚ Mixing ${state.bars} bars…`;state.started=performance.now()-state.progress*state.overlap*1000;const fade=now=>{if(!transitionPreviewState||state.paused)return;state.progress=Math.max(0,Math.min(1,(now-state.started)/(state.overlap*1000)));applyTransitionFade(state,state.progress);button.style.setProperty('--mix-progress',`${Math.round(state.progress*100)}%`);if(state.progress<1)transitionPreviewFrame=requestAnimationFrame(fade);else stopTransitionPreview();};transitionPreviewFrame=requestAnimationFrame(fade);}
function toggleTransitionPreview(){const state=transitionPreviewState;if(!state)return;if(!state.paused){state.paused=true;if(transitionPreviewTimer)clearTimeout(transitionPreviewTimer);if(transitionPreviewFrame)cancelAnimationFrame(transitionPreviewFrame);if(transitionPreviewPlayheadFrame)cancelAnimationFrame(transitionPreviewPlayheadFrame);transitionPreviewTimer=0;transitionPreviewFrame=0;transitionPreviewPlayheadFrame=0;if(state.phase!=='mix')state.remaining=Math.max(0,(state.remaining*1000-(performance.now()-state.started))/1000);state.outgoing.pause();state.incoming.pause();state.audioGraph?.context?.suspend?.();state.button.classList.remove('playing');state.button.classList.add('paused');state.button.textContent='▶ Resume mix';return;}state.paused=false;state.audioGraph?.context?.resume?.();state.button.classList.remove('paused');if(state.phase==='lead')state.outgoing.play().catch(stopTransitionPreview);else if(state.phase==='mix')Promise.all([state.outgoing.play(),state.incoming.play()]).catch(stopTransitionPreview);else state.incoming.play().catch(stopTransitionPreview);followTransitionPreviewPlayheads();runTransitionPreviewPhase();}
async function initializeTransitionWave(container,track,input,color) { container.textContent='Loading waveform…';try{const wave=await transitionWaveData(track);if(!wave)throw new Error();container.replaceChildren();const windowSeconds=60,halfWindow=windowSeconds/2,sourcePeaks=Array.from(wave.peaks||[]),peaksPerSecond=sourcePeaks.length/Math.max(1,wave.duration),windowPeakCount=Math.max(240,Math.round(peaksPerSecond*windowSeconds));const surface=WaveSurfer.create({container,height:58,waveColor:'#77806f',progressColor:color,cursorColor:'#f2f3ed',cursorWidth:2,barWidth:2,barGap:1,barRadius:2,normalize:true,dragToSeek:true,minPxPerSec:0});transitionEditorSurfaces.push(surface);input._transitionSurface=surface;const renderWindow=position=>{const center=Math.max(0,Math.min(wave.duration,Number(position)||0)),windowStart=center-halfWindow,windowPeaks=Array.from({length:windowPeakCount},(_,index)=>{const absoluteTime=windowStart+(index/windowPeakCount)*windowSeconds;if(absoluteTime<0||absoluteTime>=wave.duration)return 0;const sourceIndex=Math.min(sourcePeaks.length-1,Math.max(0,Math.floor(absoluteTime*peaksPerSecond)));return sourcePeaks[sourceIndex]||0;});input._transitionWindowStart=windowStart;surface.load('',[Float32Array.from(windowPeaks)],windowSeconds).then(()=>surface.setTime(halfWindow)).catch(()=>{});};input._renderTransitionWindow=renderWindow;surface.on('interaction',seconds=>{input._recordTransitionUndo?.();const actual=Math.max(0,Math.min(wave.duration,input._transitionWindowStart+Number(seconds)));input.value=actual.toFixed(1);input.dispatchEvent(new Event('input',{bubbles:true}));});renderWindow(input.value);}catch(_){container.textContent='Waveform unavailable · use the timing slider below.';} }
function transitionFadeLevels(curve,progress,technique='crossfade'){let outgoing=1-progress,incoming=progress;if(curve==='quick-cut'){outgoing=progress<.55?1:Math.max(0,1-(progress-.55)/.2);incoming=progress<.45?0:Math.min(1,(progress-.45)/.2);}else if(curve==='long-blend'){outgoing=Math.cos(progress*Math.PI/2)*.9;incoming=Math.sin(progress*Math.PI/2)*.9;}else if(curve==='smooth'){outgoing=Math.cos(progress*Math.PI/2);incoming=Math.sin(progress*Math.PI/2);}if(technique==='vocal-duck'){const duck=1-.32*Math.sin(progress*Math.PI)**2;outgoing*=duck;incoming*=duck;}else if(technique==='drop-swap'){outgoing=progress<.5?1:0;incoming=progress<.5?0:1;}else if(technique==='echo-out')outgoing*=progress<.55?1:Math.max(0,1-(progress-.55)/.3);return {outgoing,incoming};}
function renderTransitionFadeCurve(panel,curve,bars,technique='crossfade'){const outgoing=panel.querySelector('.fade-out-path'),incoming=panel.querySelector('.fade-in-path'),label=panel.querySelector('.fade-curve-length');if(!outgoing||!incoming)return;const points=48,path=key=>Array.from({length:points+1},(_,index)=>{const progress=index/points,x=progress*100,y=22-transitionFadeLevels(curve,progress,technique)[key]*20;return `${index?'L':'M'}${x.toFixed(2)} ${y.toFixed(2)}`;}).join(' ');outgoing.setAttribute('d',path('outgoing'));incoming.setAttribute('d',path('incoming'));label.textContent=`${bars} bars`;updateTransitionFadePlayhead(panel,0,curve,false,technique);}
function updateTransitionFadePlayhead(panel,progress,curve,isActive=true,technique='crossfade'){const cursor=panel?.querySelector('.fade-live-line'),outgoing=panel?.querySelector('.fade-live-out'),incoming=panel?.querySelector('.fade-live-in'),status=panel?.querySelector('.fade-live-status');if(!cursor||!outgoing||!incoming)return;const value=Math.max(0,Math.min(1,Number(progress)||0)),x=value*100,levels=transitionFadeLevels(curve,value,technique);cursor.setAttribute('x1',x);cursor.setAttribute('x2',x);outgoing.setAttribute('cx',x);outgoing.setAttribute('cy',22-levels.outgoing*20);incoming.setAttribute('cx',x);incoming.setAttribute('cy',22-levels.incoming*20);cursor.closest('svg')?.classList.toggle('is-live',isActive);if(status)status.textContent=isActive?`${Math.round(value*100)}% through fade`:'Preview to follow the fade';}
function transitionWaveEnergy(wave,time,windowSeconds=8){const peaks=Array.from(wave?.peaks||[]);if(!peaks.length||!wave?.duration)return .5;const start=Math.max(0,Math.floor((time-windowSeconds/2)/wave.duration*peaks.length)),end=Math.min(peaks.length,Math.ceil((time+windowSeconds/2)/wave.duration*peaks.length));const values=peaks.slice(start,Math.max(start+1,end)).map(value=>Math.abs(Number(value)||0));return values.reduce((sum,value)=>sum+value,0)/Math.max(1,values.length);}
function transitionWaveData(track){const id=track?._job?.id;if(!id)return Promise.resolve(null);if(!transitionWaveCache.has(id))transitionWaveCache.set(id,fetch(`/api/jobs/${id}/waveform/wav`).then(response=>response.ok?response.json():null).catch(()=>null));return transitionWaveCache.get(id);}
function transitionCueCandidates(track,side='in') {
  const duration=Math.max(1,Number(track?.duration_seconds||210));
  const bpm=Math.max(60,Number(track?.bpm||120));
  const bar=4*60/bpm,phrase=bar*8;
  const points=[];
  const add=(time,label,reason,score)=>{const value=Math.max(0,Math.min(duration,Math.round(Number(time||0)/bar)*bar));if(!Number.isFinite(value))return;points.push({time:value,label,reason,score});};
  if(side==='in'){
    add(0,'Track start','Opening downbeat',100);
    add(Number(track?.mix_in||0),'Primary mix in','Existing analyzed cue',105);
    add(phrase,'First clean phrase','Eight bars after the opening',96);
    add(phrase*2,'Second phrase','Sixteen bars after the opening',90);
  } else {
    add(Number(track?.mix_out??duration-phrase),'Primary mix out','Existing analyzed cue',105);
    add(duration-phrase*2,'Earlier exit','Sixteen bars before the ending',90);
    add(duration-phrase,'Final clean phrase','Eight bars before the ending',96);
    add(duration,'Track end','End of the recording',100);
  }
  (track?.arrangement_sections||[]).forEach(section=>{
    const label=String(section.label||'section').toLowerCase(),confidence=Number(section.confidence||.5);
    if(side==='in'){
      if(section.start<=duration*.8&&/drop|chorus|groove|main|verse/.test(label))add(section.start,`${label.includes('drop')?'Drop':'Groove'} entry`,`${section.label} begins`,80+confidence*12);
      if(section.end<=duration*.8&&/intro|break|build/.test(label))add(section.end,`After ${section.label}`,`Clean boundary after ${section.label}`,76+confidence*12);
    } else {
      if(section.start>=duration*.25&&/break|outro|build/.test(label))add(section.start,`${section.label} begins`,`Exit at the start of ${section.label}`,82+confidence*12);
      if(section.end>=duration*.25&&/drop|chorus|groove|main|verse/.test(label))add(section.end,`After ${section.label}`,`Exit after ${section.label}`,74+confidence*12);
    }
  });
  (track?.section_profiles||[]).forEach(section=>{
    const name=String(section.name||section.style||'section'),style=String(section.style||'').toLowerCase(),confidence=Number(section.confidence||.5);
    if(side==='in'&&section.start<=duration*.8&&/instrument|sparse|groove|steady|break/.test(style))add(section.start,`${name} entry`,`Low-conflict section · ${section.style}`,72+confidence*10);
    if(side==='out'&&section.start>=duration*.25&&/closing|break|sparse|transition/.test(style))add(section.start,`${name} exit`,`Transition-safe section · ${section.style}`,76+confidence*10);
  });
  const deduped=new Map();points.forEach(point=>{const key=Math.round(point.time*2)/2,existing=deduped.get(key);if(!existing||point.score>existing.score)deduped.set(key,point);});
  const ranked=[...deduped.values()].sort((a,b)=>b.score-a.score),chosen=[];
  ranked.forEach(point=>{const repeated=chosen.filter(item=>item.label===point.label).length>=2,tooClose=chosen.some(item=>Math.abs(item.time-point.time)<phrase/2);if(chosen.length<8&&(!repeated||point.score>=100)&&(!tooClose||point.score>=96))chosen.push(point);});
  return chosen.sort((a,b)=>a.time-b.time);
}
async function optimizeTransitionCandidates(left,right){const [leftWave,rightWave]=await Promise.all([transitionWaveData(left),transitionWaveData(right)]);const bpmA=Math.max(60,Number(left.bpm||120)),bpmB=Math.max(60,Number(right.bpm||bpmA)),durationA=Math.max(1,Number(left.duration_seconds||leftWave?.duration||210)),durationB=Math.max(1,Number(right.duration_seconds||rightWave?.duration||210)),tempoDifference=Math.min(Math.abs(bpmA-bpmB)/bpmA,Math.abs(bpmA-bpmB*2)/bpmA,Math.abs(bpmA-bpmB/2)/bpmA),harmonic=harmonicCompatibility(left.key,right.key),energyDifference=Math.abs(songEnergy(left)-songEnergy(right)),vocalCollision=setVocalProfile(left)==='vocal-forward'&&setVocalProfile(right)==='vocal-forward',outroInstrumental=Math.max(Number(left.outro?.instrumentalness||0),Number(left.intro?.instrumentalness||0)),variableTiming=timingProfile(left)==='variable'||timingProfile(right)==='variable',genre=`${left._genre||''} ${right._genre||''}`.toLowerCase(),danceGenre=/house|techno|electronic|reggaeton|salsa|bachata|dance/.test(genre),techniques=['crossfade','bass-swap','filter-blend','vocal-duck','echo-out','drop-swap','loop-assist'],curves=['smooth','linear','quick-cut','long-blend'],outCues=transitionCueCandidates(left,'out'),inCues=transitionCueCandidates(right,'in'),candidates=[];for(const bars of [8,16,32]){const overlap=bars*4*60/bpmA,eligibleOut=outCues.filter(cue=>cue.time>=overlap&&cue.time<durationA),eligibleIn=inCues.filter(cue=>cue.time+overlap<=durationB);for(const outCue of (eligibleOut.length?eligibleOut:outCues.slice(-1)))for(const inCue of (eligibleIn.length?eligibleIn:inCues.slice(0,1))){const mixOut=Math.max(overlap,Math.min(durationA-1,outCue.time)),mixIn=Math.max(0,Math.min(durationB-1,inCue.time)),outEnergy=transitionWaveEnergy(leftWave,mixOut),inEnergy=transitionWaveEnergy(rightWave,mixIn),loudnessScore=15*Math.max(0,1-Math.abs(outEnergy-inEnergy)/Math.max(.05,outEnergy,inEnergy));for(const technique of techniques)for(const curve of curves){let phraseScore=20*Math.min(1,Math.min(Number(left.beat_grid_confidence??.75),Number(right.beat_grid_confidence??.75))+.2)+5*Math.min(1,(Number(outCue.score||0)+Number(inCue.score||0))/210);const availableBars=Math.min(Number(left.outro?.mixable_bars||left.dj_readiness?.outro_mixable_bars||32),Number(right.intro?.mixable_bars||right.dj_readiness?.intro_mixable_bars||32));if(bars>availableBars)phraseScore-=Math.min(10,(bars-availableBars)/2);const tempoScore=25*Math.max(0,1-tempoDifference/.12),keyScore=15*(harmonic.score/40),energyScore=10*Math.max(0,1-energyDifference/.65),timingScore=variableTiming?3:5;let vocalScore=vocalCollision?(technique==='vocal-duck'?10:technique==='echo-out'||technique==='drop-swap'?8:3):10,techniqueBonus=0;if(technique==='bass-swap'&&danceGenre)techniqueBonus+=5;if(technique==='filter-blend'&&!variableTiming)techniqueBonus+=4;if(technique==='echo-out'&&tempoDifference>.05)techniqueBonus+=5;if(technique==='drop-swap'){techniqueBonus-=16;if(tempoDifference>.1&&energyDifference>.4&&Number(left.beat_grid_confidence||0)>.85&&Number(right.beat_grid_confidence||0)>.85)techniqueBonus+=8;}if(technique==='loop-assist'){techniqueBonus-=22;if(variableTiming&&outroInstrumental>=.85&&Number(left.beat_grid_confidence||0)>.9)techniqueBonus+=6;if(vocalCollision)techniqueBonus-=6;}if(technique==='crossfade'&&tempoDifference<.025&&!vocalCollision)techniqueBonus+=3;if(curve==='quick-cut'&&(technique==='drop-swap'||tempoDifference>.07))techniqueBonus+=3;if(curve==='smooth'&&(technique==='crossfade'||technique==='bass-swap'||technique==='filter-blend'))techniqueBonus+=2;const rawScore=phraseScore+tempoScore+keyScore+loudnessScore+vocalScore+energyScore+timingScore+techniqueBonus,score=Math.max(0,Math.min(100,Math.round(rawScore/1.15)));candidates.push({score,mixOut,mixIn,outCueLabel:outCue.label,inCueLabel:inCue.label,bars,curve,technique,tempoSync:tempoDifference>.008,components:{phrase:Math.round(phraseScore),tempo:Math.round(tempoScore),key:Math.round(keyScore),loudness:Math.round(loudnessScore),vocals:Math.round(vocalScore),energy:Math.round(energyScore),timing:Math.round(timingScore)},reason:`${outCue.label} → ${inCue.label} · ${harmonic.label} · ${Math.round(loudnessScore)}/15 loudness · ${vocalCollision?'vocal protection':'clear vocals'}`});}}}return candidates.sort((a,b)=>b.score-a.score).filter((candidate,index,list)=>list.findIndex(item=>item.technique===candidate.technique)===index).slice(0,3);}
async function runBounded(tasks,limit=3){let cursor=0;const worker=async()=>{while(cursor<tasks.length){const task=tasks[cursor++];await task();}};await Promise.all(Array.from({length:Math.min(limit,tasks.length)},worker));}
async function autoOptimizeSetTransitions(){const pending=[];for(let index=1;index<currentSetPlan.length;index+=1){const key=transitionSettingKey(currentSetPlan[index-1],currentSetPlan[index]),existing=setTransitionSettings[key];if(existing&&(!existing.optimized||Number(existing.optimizedVersion||0)>=4))continue;pending.push(async()=>{const candidates=await optimizeTransitionCandidates(currentSetPlan[index-1],currentSetPlan[index]);if(candidates[0])setTransitionSettings[key]={...transitionSettings(index),...candidates[0],optimized:true,optimizedVersion:4};});}await runBounded(pending,3);return pending.length;}
function openTransitionEditor(index,card) { document.querySelectorAll('.transition-editor').forEach(editor=>editor.remove());transitionEditorSurfaces.forEach(surface=>surface.destroy());transitionEditorSurfaces=[];const left=currentSetPlan[index-1],right=currentSetPlan[index],settings=transitionSettings(index);const panel=document.createElement('section');panel.className='transition-editor';const leftDuration=Math.max(1,Number(left.duration_seconds||210)),rightDuration=Math.max(1,Number(right.duration_seconds||210));panel.innerHTML=`<header><div><strong>Transition ${index} → ${index+1}</strong><span>${escapeHtml(left.source_name.replace(/\.[^.]+$/,''))} into ${escapeHtml(right.source_name.replace(/\.[^.]+$/,''))}</span></div><div class="transition-header-actions"><button type="button" class="optimize-transition">✦ Find best</button><button type="button" class="undo-transition-timing" disabled>↶ Undo timing</button><button type="button" class="close-transition-editor">×</button></div></header><div class="transition-wave-stack"><span class="transition-point-label">Mix starts here · matched 60-second view</span><span class="transition-point-line" aria-hidden="true"></span><div class="transition-wave-row"><label>Outgoing mix-out <b class="mix-out-label">${clock(settings.mixOut)}</b></label><div class="transition-wave outgoing-wave"></div><input class="transition-mix-out" type="range" min="0" max="${leftDuration}" step="0.1" value="${settings.mixOut}"><div class="transition-cue-options outgoing-cues" aria-label="Alternative outgoing cue points"></div></div><div class="transition-wave-row"><label>Incoming mix-in <b class="mix-in-label">${clock(settings.mixIn)}</b></label><div class="transition-wave incoming-wave"></div><input class="transition-mix-in" type="range" min="0" max="${rightDuration}" step="0.1" value="${settings.mixIn}"><div class="transition-cue-options incoming-cues" aria-label="Alternative incoming cue points"></div></div></div><div class="transition-fade-visual"><div><span>Fade shape</span><b class="fade-curve-length">${settings.bars} bars</b></div><svg viewBox="0 0 100 24" preserveAspectRatio="none" aria-label="Transition fade curve"><path class="fade-grid" d="M0 12 H100 M50 1 V23"></path><path class="fade-out-path"></path><path class="fade-in-path"></path><line class="fade-live-line" x1="0" x2="0" y1="1" y2="23"></line><circle class="fade-live-out" cx="0" cy="2" r="1.6"></circle><circle class="fade-live-in" cx="0" cy="22" r="1.6"></circle></svg><div class="fade-legend"><span class="fade-out-key">Outgoing</span><span class="fade-in-key">Incoming</span><small class="fade-live-status">Preview to follow the fade</small></div></div><div class="transition-optimizer-results" hidden></div><div class="transition-editor-controls"><label>Length<select class="transition-bars"><option value="8">8 bars</option><option value="16">16 bars</option><option value="32">32 bars</option></select></label><label>Fade curve<select class="transition-curve"><option value="smooth">Smooth equal-power</option><option value="linear">Linear</option><option value="quick-cut">Quick cut</option><option value="long-blend">Long blend</option></select></label><label>Technique<select class="transition-technique"><option value="crossfade">Classic crossfade</option><option value="bass-swap">Bass swap</option><option value="filter-blend">Filter blend</option><option value="vocal-duck">Vocal duck</option><option value="echo-out">Echo out</option><option value="drop-swap">Drop swap</option><option value="loop-assist">Loop-assisted blend</option></select></label><label class="transition-tempo"><input type="checkbox" class="transition-tempo-sync"> Tempo match</label><label class="transition-notes">Transition notes<input class="transition-note" type="text" maxlength="300" placeholder="Loop 8 bars, swap bass on phrase…" value="${escapeHtml(settings.notes||'')}"></label><button type="button" class="preview-transition">▶ Preview mix</button></div>`;card.append(panel);const mixOut=panel.querySelector('.transition-mix-out'),mixIn=panel.querySelector('.transition-mix-in'),bars=panel.querySelector('.transition-bars'),curve=panel.querySelector('.transition-curve'),technique=panel.querySelector('.transition-technique'),sync=panel.querySelector('.transition-tempo-sync'),notes=panel.querySelector('.transition-note'),undo=panel.querySelector('.undo-transition-timing'),optimizer=panel.querySelector('.optimize-transition'),optimizerResults=panel.querySelector('.transition-optimizer-results');bars.value=String(settings.bars);curve.value=settings.curve;technique.value=settings.technique||'crossfade';sync.checked=settings.tempoSync;const withCurrentCue=(cues,time)=>cues.some(cue=>Math.abs(cue.time-Number(time))<.25)?cues:[...cues,{time:Number(time),label:'Current selection',reason:'Current optimized or manually selected cue',score:110}].sort((a,b)=>a.time-b.time);const cueBindings=[[panel.querySelector('.outgoing-cues'),withCurrentCue(transitionCueCandidates(left,'out'),settings.mixOut),mixOut],[panel.querySelector('.incoming-cues'),withCurrentCue(transitionCueCandidates(right,'in'),settings.mixIn),mixIn]];const refreshCueButtons=()=>cueBindings.forEach(([root,cues,input])=>root.querySelectorAll('button').forEach(button=>button.classList.toggle('active',Math.abs(Number(button.dataset.time)-Number(input.value))<.25)));cueBindings.forEach(([root,cues,input])=>{root.innerHTML=cues.map(cue=>`<button type="button" data-time="${cue.time.toFixed(2)}" title="${escapeHtml(cue.reason)}"><b>${escapeHtml(cue.label)}</b><span>${clock(cue.time)}</span></button>`).join('');root.querySelectorAll('button').forEach(button=>button.onclick=()=>{recordTimingUndo();input.value=button.dataset.time;input.dispatchEvent(new Event('input',{bubbles:true}));refreshCueButtons();});});const persist=()=>saveTransitionSettings(index,{mixOut:Number(mixOut.value),mixIn:Number(mixIn.value),bars:Number(bars.value),curve:curve.value,technique:technique.value,tempoSync:sync.checked,notes:notes.value,optimized:false});const restartPreview=()=>{if(transitionPreviewState?.button.closest('.transition-editor')===panel)stopTransitionPreview('↻ Preview updated mix');};const timingHistory=[];const timingSnapshot=()=>({mixOut:Number(mixOut.value),mixIn:Number(mixIn.value)});const recordTimingUndo=()=>{const snapshot=timingSnapshot(),last=timingHistory.at(-1);if(last&&last.mixOut===snapshot.mixOut&&last.mixIn===snapshot.mixIn)return;timingHistory.push(snapshot);undo.disabled=false;};mixOut._recordTransitionUndo=recordTimingUndo;mixIn._recordTransitionUndo=recordTimingUndo;const syncWave=input=>input._renderTransitionWindow?.(Number(input.value));const refreshTiming=()=>{panel.querySelector('.mix-out-label').textContent=clock(Number(mixOut.value));panel.querySelector('.mix-in-label').textContent=clock(Number(mixIn.value));syncWave(mixOut);syncWave(mixIn);restartPreview();persist();};mixOut.oninput=()=>{panel.querySelector('.mix-out-label').textContent=clock(Number(mixOut.value));syncWave(mixOut);restartPreview();persist();refreshCueButtons();};mixIn.oninput=()=>{panel.querySelector('.mix-in-label').textContent=clock(Number(mixIn.value));syncWave(mixIn);restartPreview();persist();refreshCueButtons();};undo.onclick=()=>{const previous=timingHistory.pop();if(!previous)return;mixOut.value=previous.mixOut;mixIn.value=previous.mixIn;refreshTiming();undo.disabled=!timingHistory.length;};panel.querySelectorAll('input,select,button,.transition-wave').forEach(control=>control.addEventListener('pointerdown',event=>event.stopPropagation()));panel.querySelectorAll('input[type="range"]').forEach(control=>{control.addEventListener('pointerdown',()=>{recordTimingUndo();card.draggable=false;});control.addEventListener('keydown',event=>{if(event.key.startsWith('Arrow')||event.key==='Home'||event.key==='End')recordTimingUndo();});control.addEventListener('pointerup',()=>{card.draggable=!card.classList.contains('locked');});control.addEventListener('pointercancel',()=>{card.draggable=!card.classList.contains('locked');});});[bars,curve,technique,sync].forEach(control=>control.addEventListener('change',()=>{restartPreview();persist();}));notes.addEventListener('change',persist);[bars,curve,technique].forEach(control=>control.addEventListener('change',()=>renderTransitionFadeCurve(panel,curve.value,Number(bars.value),technique.value)));renderTransitionFadeCurve(panel,curve.value,Number(bars.value),technique.value);refreshCueButtons();optimizer.onclick=async()=>{optimizer.disabled=true;optimizer.textContent='Scoring…';optimizerResults.hidden=false;optimizerResults.innerHTML='<p>Comparing timing, phrasing, harmony, loudness, vocals, energy, and technique…</p>';try{const candidates=await optimizeTransitionCandidates(left,right);optimizerResults.innerHTML=candidates.map((candidate,candidateIndex)=>`<article class="${candidateIndex?'':'recommended'}" data-candidate="${candidateIndex}"><div><b>${candidateIndex?'Alternative '+(candidateIndex+1):'Recommended'} · ${candidate.score}/100</b><strong>${escapeHtml(candidate.technique.replaceAll('-',' '))} · ${candidate.bars} bars · ${escapeHtml(candidate.curve.replaceAll('-',' '))}</strong><span>${clock(candidate.mixOut)} → ${clock(candidate.mixIn)} · ${escapeHtml(candidate.reason)}</span><small>Phrase ${candidate.components.phrase}/25 · tempo ${candidate.components.tempo}/25 · key ${candidate.components.key}/15 · loudness ${candidate.components.loudness}/15 · vocals ${candidate.components.vocals}/10</small></div><button type="button">Apply</button></article>`).join('');optimizerResults.querySelectorAll('[data-candidate]').forEach(row=>row.querySelector('button').onclick=()=>{const candidate=candidates[Number(row.dataset.candidate)];recordTimingUndo();mixOut.value=candidate.mixOut;mixIn.value=candidate.mixIn;bars.value=String(candidate.bars);curve.value=candidate.curve;technique.value=candidate.technique;sync.checked=candidate.tempoSync;refreshTiming();renderTransitionFadeCurve(panel,curve.value,Number(bars.value),technique.value);optimizerResults.querySelectorAll('article').forEach(item=>item.classList.toggle('applied',item===row));});}catch(error){optimizerResults.innerHTML=`<p>Could not score this transition: ${escapeHtml(error.message)}</p>`;}finally{optimizer.disabled=false;optimizer.textContent='✦ Find best';}};panel.querySelector('.close-transition-editor').onclick=()=>{stopTransitionPreview();transitionEditorSurfaces.forEach(surface=>surface.destroy());transitionEditorSurfaces=[];panel.remove();};panel.querySelector('.preview-transition').onclick=event=>{persist();auditionTransition(index,event.currentTarget);};initializeTransitionWave(panel.querySelector('.outgoing-wave'),left,mixOut,'#ffb45c');initializeTransitionWave(panel.querySelector('.incoming-wave'),right,mixIn,'#d6ff44');panel.scrollIntoView({behavior:'smooth',block:'nearest'}); }
function setSvgCurve(selector, values, color) {
  const svg = $(selector); if (!values.length) { svg.replaceChildren(); return; }
  const low = Math.min(...values); const high = Math.max(...values); const range = Math.max(.001, high-low);
  const points = values.map((value,index) => `${index * 600 / Math.max(1,values.length-1)},${80-(value-low)/range*65}`).join(' ');
  svg.innerHTML = `<polyline points="${points}" fill="none" stroke="${color}" stroke-width="3" vector-effect="non-scaling-stroke"/><line x1="0" y1="80" x2="600" y2="80" stroke="#30332f"/>`;
}
function renderSetRules() {
  const byId = new Map(setBuilderLibrary.map(track => [setTrackId(track), track]));
  const ruleTotal = setRequiredIds.size + setExcludedIds.size;
  $('#set-rule-count').textContent = `${ruleTotal} rule${ruleTotal === 1 ? '' : 's'}`;
  $('#set-rule-chips').innerHTML = [...setRequiredIds].map(id => `<button type="button" class="required-chip" data-rule="required" data-id="${escapeHtml(id)}">Required · ${escapeHtml(byId.get(id)?.source_name || id)} ×</button>`).concat([...setExcludedIds].map(id => `<button type="button" class="excluded-chip" data-rule="excluded" data-id="${escapeHtml(id)}">Excluded · ${escapeHtml(byId.get(id)?.source_name || id)} ×</button>`)).join('');
  $('#set-rule-chips').querySelectorAll('button').forEach(button => button.onclick = () => { (button.dataset.rule === 'required' ? setRequiredIds : setExcludedIds).delete(button.dataset.id); renderSetRules(); });
}
function transitionExplanation(previous, track) {
  if (!previous) return {score:null,text:'Opening track · establishes the starting mood'};
  const match = compatibility(previous,track); const tempo = match.difference <= .02 ? 'tempo locked' : `${(match.difference*100).toFixed(1)}% tempo move`;
  return {score:match.score,text:`${tempo} · ${match.key} · energy ${match.components.energy}/10`};
}
function renderSetPlan() {
  const result = $('#set-result'); result.hidden = !currentSetPlan.length; if (!currentSetPlan.length) return;
  transitionEditorSurfaces.forEach(surface=>surface.destroy());transitionEditorSurfaces=[];
  result.classList.toggle('compact-planning',setCompactMode);$('#set-compact').textContent=setCompactMode?'Comfortable view':'Compact view';updateSetHistoryButtons();
  const activeProposal=setProposals.find(proposal=>proposal.id===activeSetProposal);if(activeProposal){activeProposal.snapshot=setPlanSnapshot();activeProposal.health=setHealth();}
  renderSetProposals();
  const brief = setBrief(); const runtime = setRuntime();
  $('#set-result-name').textContent = brief.name;
  const genreSummary=(brief.detailedGenres||[]).length?brief.detailedGenres.join(' + '):brief.genres.length?brief.genres.join(' + '):'open genre mix';
  $('#set-result-summary').textContent = `${currentSetPlan.length} tracks · approximately ${Math.round(runtime/60)} minutes · ${genreSummary} · ${brief.genreFlow.replace('-', ' ')} · ${brief.curve.replace('-', ' ')}`;
  const exportStatus=$('#set-export-status');exportStatus.className='set-export-status';exportStatus.innerHTML='<span>Rekordbox paths will be checked before export.</span>';
  const health=setHealth();const healthThreshold=brief.minimumHealth;const healthAccepted=health.score>=healthThreshold;const weak=health.transitions.filter(item=>item.score<healthThreshold).sort((a,b)=>a.score-b.score);const healthDetail=weak.length?weak.slice(0,8).map(item=>`<button type="button" data-transition="${item.to}"><b>${item.from+1} → ${item.to+1}</b><span>${item.score}% · ${escapeHtml(item.key)} · tempo ${item.components.tempo}/45</span></button>`).join(''):healthAccepted?`<p>Health target met. No transitions fall below ${healthThreshold}.</p>`:`<p>${health.vocalClashes} vocal-forward pairing${health.vocalClashes===1?' is':'s are'} lowering the overall health below ${healthThreshold}. Regenerate or replace those tracks.</p>`;$('#set-health').className=`set-health ${healthAccepted?'good':health.score>=healthThreshold-10?'fair':'weak'}`;$('#set-health').innerHTML=`<summary><strong>${health.score}</strong><span>Set health</span><small>${healthAccepted?'target met':'below target · regenerate required'} · target ${healthThreshold} · ${weak.length} transition${weak.length===1?'':'s'} below target · ${health.vocalClashes} vocal clash${health.vocalClashes===1?'':'es'}</small></summary><div>${healthDetail}</div>`;$('#set-health').querySelectorAll('[data-transition]').forEach(button=>button.onclick=()=>document.querySelector(`.set-track-card[data-index="${button.dataset.transition}"]`)?.scrollIntoView({behavior:'smooth',block:'center'}));
  ['#save-set','#export-set-csv','#export-set-m3u'].forEach(selector=>{const button=$(selector);button.disabled=!healthAccepted;button.title=healthAccepted?'':`Set health must reach ${healthThreshold} before saving or exporting.`;});
  $('#set-track-list').innerHTML = currentSetPlan.map((track,index) => {
    const transition = transitionExplanation(currentSetPlan[index-1],track); const id = setTrackId(track); const locked = setLockedIds.has(id);
    const preview=track._job?.id?compactAudioMarkup(`/api/jobs/${track._job.id}/audio/wav`,track.duration_seconds,true):'';
    return `<article class="set-track-card${locked?' locked':''}" draggable="${locked?'false':'true'}" data-index="${index}"><span class="set-position">${index+1}</span><div class="set-track-title"><strong>${escapeHtml(track.source_name.replace(/\.[^.]+$/,''))}</strong><span>${track.artist ? `${escapeHtml(track.artist)} · ` : ''}${escapeHtml(track._genre)} · ${libraryRoles(track).map(role => LIBRARY_ROLE_INFO[role]?.[0] || role).join(', ')}</span>${preview}</div><div class="set-track-meta"><strong>${Number(track.bpm||0).toFixed(1)} BPM · ${escapeHtml(formatLibraryKey(track.key))}</strong><span>${energyBand(songEnergy(track))} energy · ${setVocalProfile(track)} · ${timingProfile(track)}</span><span>${track._hasExtended?'Extended edit available':'Original analyzed track'}</span></div><div class="set-transition ${transition.score != null && transition.score < healthThreshold?'warning':'good'}"><b>${transition.score == null?'OPEN':`${transition.score}% match`}</b><span><i>Why:</i> ${escapeHtml(transition.text)}</span>${index?'<button type="button" class="set-audition">Mix transition</button><button type="button" class="edit-transition">Edit mix</button>':''}</div><div class="set-row-actions"><button type="button" class="set-move-up" ${index===0?'disabled':''}>↑ Earlier</button><button type="button" class="set-move-down" ${index===currentSetPlan.length-1?'disabled':''}>↓ Later</button><button type="button" class="set-lock">${locked?'Unlock':'Lock'}</button><button type="button" class="set-remove">Remove</button><button type="button" class="set-add-after">Add after</button><button type="button" class="set-alternative">Find alternative</button></div></article>`;
  }).join('');
  bindSetRows();
  bindCompactAudio($('#set-track-list'));
  setSvgCurve('#set-energy-curve',currentSetPlan.map(songEnergy),'#d6ff44');
  setSvgCurve('#set-bpm-curve',currentSetPlan.map(track => Number(track.bpm||0)),'#ffb45c');
  const warnings = [];
  currentSetPlan.slice(1).forEach((track,index) => { const match=compatibility(currentSetPlan[index],track); if(match.score<healthThreshold) { const weakest=Object.entries(match.components).sort((a,b)=>a[1]-b[1])[0]?.[0]||'compatibility';warnings.push(`Transition ${index+1} → ${index+2}: ${match.score}% is below the ${healthThreshold}% target; weakest area is ${weakest}${match.key==='distant key'?' with distant keys':''}.`); } if(setVocalProfile(currentSetPlan[index])==='vocal-forward'&&setVocalProfile(track)==='vocal-forward') warnings.push(`Transition ${index+1} → ${index+2}: both tracks are vocal-forward; avoid overlapping verses.`); });
  $('#set-warnings').innerHTML = warnings.length ? warnings.map(text=>`<p>${escapeHtml(text)}</p>`).join('') : `<p class="set-ready">Set health target ${healthThreshold} met with no transition warnings. Listen through the plan before performing it live.</p>`;
}
function moveSetTrack(from,to) { if(to<0||to>=currentSetPlan.length||from===to) return;pushSetHistory(); const [track]=currentSetPlan.splice(from,1); currentSetPlan.splice(to,0,track); renderSetPlan(); }
function bindSetRows() {
  let dragging = null;
  $$('.set-track-card').forEach(card => {
    const index=Number(card.dataset.index);
    card.querySelector('.set-move-up').onclick=()=>moveSetTrack(index,index-1); card.querySelector('.set-move-down').onclick=()=>moveSetTrack(index,index+1);
    card.querySelector('.set-lock').onclick=()=>{pushSetHistory();const id=setTrackId(currentSetPlan[index]); setLockedIds.has(id)?setLockedIds.delete(id):setLockedIds.add(id);renderSetPlan();};
    card.querySelector('.set-remove').onclick=()=>{pushSetHistory();setLockedIds.delete(setTrackId(currentSetPlan[index]));currentSetPlan.splice(index,1);renderSetPlan();};
    card.querySelector('.set-add-after').onclick=()=>addSetTrack(index+1,card);
    card.querySelector('.set-alternative').onclick=()=>replaceSetTrack(index);
    card.querySelector('.set-audition')?.addEventListener('click',event=>auditionTransition(index,event.currentTarget));
    card.querySelector('.edit-transition')?.addEventListener('click',()=>openTransitionEditor(index,card));
    card.ondragstart=event=>{if(event.target.closest('input,select,button,audio,.transition-editor,.set-compact-audio')){event.preventDefault();return;}dragging=index;card.classList.add('dragging');}; card.ondragend=()=>card.classList.remove('dragging'); card.ondragover=event=>event.preventDefault(); card.ondrop=event=>{event.preventDefault();moveSetTrack(dragging,index);};
  });
}
function addSetTrack(insertIndex=currentSetPlan.length, anchor=null) {
  document.querySelectorAll('.set-add-track-panel').forEach(item=>item.remove());
  const used=new Set(currentSetPlan.map(setTrackId));const brief=setBrief();const previous=currentSetPlan[insertIndex-1];const next=currentSetPlan[insertIndex];
  const available=setBuilderLibrary.filter(track=>!used.has(setTrackId(track))).map(track=>({track,score:setCandidateScore(track,previous,insertIndex,currentSetPlan.length+1,brief)+(next?compatibility(track,next).score*.3:0)})).sort((a,b)=>b.score-a.score);
  const panel=document.createElement('section');panel.className='set-alternative-panel set-add-track-panel';const genres=[...new Set(available.map(choice=>choice.track._genre).filter(Boolean))].sort((a,b)=>a.localeCompare(b));
  panel.innerHTML=`<header><div><strong>${insertIndex>=currentSetPlan.length?'Add a track to the end':`Add a track at position ${insertIndex+1}`}</strong><span>Search any unused song in your DJ Library.</span></div><button type="button" class="close-alternatives" aria-label="Close track browser">×</button></header><div class="set-alternative-tools"><label><span>Song, artist, or genre</span><input class="alternative-search" type="search" placeholder="Search your library…" autocomplete="off"></label><label><span>Genre</span><select class="alternative-genre"><option value="">All genres</option>${genres.map(genre=>`<option value="${escapeHtml(genre)}">${escapeHtml(genre)}</option>`).join('')}</select></label></div><div class="set-alternative-status" aria-live="polite"></div><div class="set-alternative-list"></div>`;
  const list=panel.querySelector('.set-alternative-list');const status=panel.querySelector('.set-alternative-status');
  const renderChoices=()=>{const query=panel.querySelector('.alternative-search').value.trim().toLowerCase();const genre=panel.querySelector('.alternative-genre').value;const matches=available.filter(({track})=>{const haystack=`${track.source_name||''} ${track.artist||''} ${track._genre||''}`.toLowerCase();return (!query||haystack.includes(query))&&(!genre||track._genre===genre);});const choices=matches.slice(0,query||genre?30:5);status.textContent=`${matches.length} available track${matches.length===1?'':'s'} · showing ${choices.length}${query||genre?'':' best fits'}`;list.innerHTML=choices.length?choices.map((choice,choiceIndex)=>{const track=choice.track;const preview=track._job?.id?compactAudioMarkup(`/api/jobs/${track._job.id}/audio/wav`,track.duration_seconds,true):'';return `<article data-choice="${choiceIndex}"><div><strong>${escapeHtml(track.source_name.replace(/\.[^.]+$/,''))}</strong><span>${track.artist?`${escapeHtml(track.artist)} · `:''}${escapeHtml(track._genre)} · ${Number(track.bpm||0).toFixed(1)} BPM · ${escapeHtml(formatLibraryKey(track.key))} · ${Math.round(choice.score)} fit</span></div>${preview}<button type="button" class="use-alternative">Add to set</button></article>`;}).join(''):'<p class="empty">No unused tracks match that search.</p>';list.querySelectorAll('.use-alternative').forEach(button=>button.onclick=()=>{const choice=choices[Number(button.closest('article').dataset.choice)];if(!choice)return;pushSetHistory();currentSetPlan.splice(Math.min(insertIndex,currentSetPlan.length),0,choice.track);renderSetPlan();});bindCompactAudio(list);};
  (anchor||$('#set-add-track-panel-host')).append(panel);panel.querySelector('.close-alternatives').onclick=()=>panel.remove();panel.querySelector('.alternative-search').oninput=renderChoices;panel.querySelector('.alternative-genre').onchange=renderChoices;renderChoices();panel.scrollIntoView({behavior:'smooth',block:'nearest'});panel.querySelector('.alternative-search').focus();
}
function replaceSetTrack(index) {
  const used=new Set(currentSetPlan.map(setTrackId)); const brief=setBrief(); const previous=currentSetPlan[index-1]; const next=currentSetPlan[index+1];
  const rankTrack=track=>({track,score:setCandidateScore(track,previous,index,currentSetPlan.length,brief)+(next?compatibility(track,next).score*.3:0)});
  const available=setBuilderLibrary.filter(track=>!used.has(setTrackId(track))).map(rankTrack).sort((a,b)=>b.score-a.score);
  const recommendedIds=new Set(eligibleSetTracks(brief).filter(track=>!used.has(setTrackId(track))).map(setTrackId));
  const card=$(`.set-track-card[data-index="${index}"]`);if(!card)return;card.querySelector('.set-alternative-panel')?.remove();
  const panel=document.createElement('section');panel.className='set-alternative-panel';
  const genres=[...new Set(available.map(choice=>choice.track._genre).filter(Boolean))].sort((a,b)=>a.localeCompare(b));
  panel.innerHTML=`<header><div><strong>Replace this track</strong><span>Start with recommended matches or search your entire DJ Library.</span></div><button type="button" class="close-alternatives" aria-label="Close alternatives">×</button></header><div class="set-alternative-tools"><label><span>Song, artist, or genre</span><input class="alternative-search" type="search" placeholder="Search your library…" autocomplete="off"></label><label><span>Genre</span><select class="alternative-genre"><option value="">All genres</option>${genres.map(genre=>`<option value="${escapeHtml(genre)}">${escapeHtml(genre)}</option>`).join('')}</select></label></div><div class="set-alternative-status" aria-live="polite"></div><div class="set-alternative-list"></div>`;
  const list=panel.querySelector('.set-alternative-list');const status=panel.querySelector('.set-alternative-status');
  const renderChoices=()=>{const query=panel.querySelector('.alternative-search').value.trim().toLowerCase();const genre=panel.querySelector('.alternative-genre').value;const searching=Boolean(query||genre);const matches=available.filter(choice=>{const track=choice.track;const haystack=`${track.source_name||''} ${track.artist||''} ${track._genre||''}`.toLowerCase();return (!query||haystack.includes(query))&&(!genre||track._genre===genre);});const choices=(searching?matches:matches.filter(choice=>recommendedIds.has(setTrackId(choice.track)))).slice(0,searching?30:5);status.textContent=searching?`${matches.length} matching unused track${matches.length===1?'':'s'} · showing ${choices.length}`:`${choices.length} recommended replacement${choices.length===1?'':'s'} · search to choose any track`;list.innerHTML=choices.length?choices.map((choice,choiceIndex)=>{const track=choice.track;const preview=track._job?.id?compactAudioMarkup(`/api/jobs/${track._job.id}/audio/wav`,track.duration_seconds,true):'';return `<article data-choice="${choiceIndex}"><div><strong>${escapeHtml(track.source_name.replace(/\.[^.]+$/,''))}</strong><span>${track.artist?`${escapeHtml(track.artist)} · `:''}${escapeHtml(track._genre)} · ${Number(track.bpm||0).toFixed(1)} BPM · ${escapeHtml(formatLibraryKey(track.key))} · ${Math.round(choice.score)} fit</span></div>${preview}<button type="button" class="use-alternative">Use this track</button></article>`;}).join(''):'<p class="empty">No unused tracks match that search.</p>';list.querySelectorAll('.use-alternative').forEach(button=>button.onclick=()=>{const choice=choices[Number(button.closest('article').dataset.choice)];if(!choice)return;pushSetHistory();setLockedIds.delete(setTrackId(currentSetPlan[index]));currentSetPlan[index]=choice.track;renderSetPlan();});bindCompactAudio(list);};
  card.append(panel);panel.querySelector('.close-alternatives').onclick=()=>panel.remove();panel.querySelector('.alternative-search').oninput=renderChoices;panel.querySelector('.alternative-genre').onchange=renderChoices;renderChoices();panel.scrollIntoView({behavior:'smooth',block:'nearest'});panel.querySelector('.alternative-search').focus();
}
function savedSets() { try{return JSON.parse(localStorage.getItem(SET_STORAGE_KEY)||'[]');}catch(_){return [];} }
function storeSavedSets(sets) { localStorage.setItem(SET_STORAGE_KEY,JSON.stringify(sets)); renderSavedSets(); }
function renderSavedSets() { const select=$('#saved-set-select'); const current=select.value; const sets=savedSets(); select.replaceChildren(option('','Choose a saved set'),...sets.map(set=>option(set.id,`${set.name} · ${set.tracks.length} tracks`))); select.value=sets.some(set=>set.id===current)?current:''; }
async function saveCurrentSet() { if(!currentSetPlan.length)return;const button=$('#save-set'); const sets=savedSets(); const id=$('#saved-set-select').value||String(Date.now()); const record={id,name:setBrief().name,brief:setBrief(),tracks:currentSetPlan.map(setTrackId),trackDetails:currentSetPlan.map(track=>({id:setTrackId(track),source_name:track.source_name,artist:track.artist||'',genre:track._genre,bpm:Number(track.bpm||0),key:track.key||''})),transitions:JSON.parse(JSON.stringify(setTransitionSettings)),locked:[...setLockedIds],required:[...setRequiredIds],excluded:[...setExcludedIds],updatedAt:new Date().toISOString()}; const existing=sets.findIndex(set=>set.id===id); existing>=0?sets.splice(existing,1,record):sets.unshift(record); storeSavedSets(sets); $('#saved-set-select').value=id;button.disabled=true;button.textContent='Saving…';const entries=setM3uEntries();try{const response=await fetch('/api/set-builder/save-playlist',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:record.name,tracks:entries.map(({track,path})=>({path,title:`${track.artist?`${track.artist} - `:''}${track.source_name.replace(/\.[^.]+$/,'')}`,duration_seconds:Number(track.duration_seconds||0)}))})});if(!response.ok){const error=await response.json().catch(()=>({}));throw new Error(error.detail?.message||error.detail||'Playlist file could not be saved.');}const result=await response.json();$('#set-builder-message').textContent=`Set saved · playlist written to ${result.path}`;}catch(error){$('#set-builder-message').textContent=`Set saved in the app, but the playlist file needs attention: ${error.message||error}`;}finally{button.disabled=false;button.textContent='Save set';} }
function recoveryScore(candidate,detail,previous) { const wanted=String(detail?.source_name||detail?.id||'').toLowerCase().replace(/\.[^.]+$/,'');const words=wanted.split(/\W+/).filter(word=>word.length>2);const haystack=`${candidate.source_name} ${candidate.artist||''}`.toLowerCase();const titleScore=words.length?words.filter(word=>haystack.includes(word)).length/words.length*45:0;const genreScore=detail?.genre&&trackMatchesSetGenre(candidate,detail.genre)?25:0;const bpmScore=detail?.bpm?Math.max(0,20-Math.abs(Number(candidate.bpm||0)-Number(detail.bpm))):0;return titleScore+genreScore+bpmScore+(previous?compatibility(previous,candidate).score*.15:0); }
async function loadSavedSet(record) {
  if(!record)return;const byId=new Map(setBuilderLibrary.map(track=>[setTrackId(track),track]));const brief=record.brief||{};
  Object.entries(brief).forEach(([key,value])=>{if(['genres','detailedGenres','excludedGenres','genreWeights'].includes(key))return;const element=$(`#set-${key.replace(/[A-Z]/g,letter=>`-${letter.toLowerCase()}`)}`);if(element&&value!==Infinity&&!Array.isArray(value))element.value=value;});
  const savedGenres=brief.genres||(brief.genre&&brief.genre!=='all'?[brief.genre]:[]);[...$('#set-genre').options].forEach(option=>{option.selected=savedGenres.length?savedGenres.includes(option.value):option.value==='all';});populateSetDetailedGenres(brief.detailedGenres||[]);[...$('#set-excluded-genres').options].forEach(option=>{option.selected=(brief.excludedGenres||[]).includes(option.value);});setGenreSelectionOrder=[...savedGenres];renderSetGenreMix();renderSetDetailedGenres();renderExcludedSetGenres();Object.entries(brief.genreWeights||{}).forEach(([genre,value])=>{const input=[...$('#set-genre-weights').querySelectorAll('input')].find(item=>item.dataset.genre===genre);if(input)input.value=value;});$('#set-genre').dispatchEvent(new Event('change',{bubbles:true}));$('#set-detailed-genres').dispatchEvent(new Event('change',{bubbles:true}));$('#set-excluded-genres').dispatchEvent(new Event('change',{bubbles:true}));
  const details=new Map((record.trackDetails||[]).map(item=>[item.id,item]));const used=new Set();const recoveredPlan=[];let recovered=0;
  (record.tracks||[]).forEach(id=>{let track=byId.get(id);if(!track){track=setBuilderLibrary.filter(candidate=>!used.has(setTrackId(candidate))).map(candidate=>({candidate,score:recoveryScore(candidate,details.get(id)||{id},recoveredPlan.at(-1))})).sort((a,b)=>b.score-a.score)[0]?.candidate;if(track)recovered+=1;}if(track){used.add(setTrackId(track));recoveredPlan.push(track);}});
  currentSetPlan=recoveredPlan;setLockedIds=new Set(record.locked||[]);setRequiredIds=new Set(record.required||[]);setExcludedIds=new Set(record.excluded||[]);setTransitionSettings=record.transitions||{};setProposals=[];activeSetProposal='';setPlanHistory=[];setPlanFuture=[];renderSetRules();const optimized=await autoOptimizeSetTransitions();renderSetPlan();$('#set-builder-message').textContent=(recovered?`Loaded set and recovered ${recovered} unavailable track${recovered===1?'':'s'} with the closest Library matches.`:'Saved set loaded with every track available.')+(optimized?` Optimized ${optimized} transition${optimized===1?'':'s'} that previously used defaults.`:'');
}
function downloadSetText(filename,text,type='text/plain') { const url=URL.createObjectURL(new Blob([text],{type}));const link=document.createElement('a');link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000); }
function safeSetFilename() { return (setBrief().name||'DJ Set').replace(/[^\w .-]+/g,'').trim()||'DJ Set'; }
function exportSetCsv() { const rows=[['Position','Track','BPM','Key','Camelot','Energy','Genre','Roles','Transition Match','Mix In','Mix Out','Transition Bars','Fade Curve','Technique','Tempo Sync','Transition Notes']];currentSetPlan.forEach((track,index)=>{const match=index?compatibility(currentSetPlan[index-1],track):null;const settings=index?transitionSettings(index):{};rows.push([index+1,track.source_name,Number(track.bpm||0).toFixed(1),track.key||'',camelotKey(track.key),energyBand(songEnergy(track)),track._genre,libraryRoles(track).join('; '),match?.score??'',index?settings.mixIn:(track.mix_in??''),index?settings.mixOut:(track.mix_out??''),settings.bars||'',settings.curve||'',settings.technique||'',index?(settings.tempoSync?'yes':'no'):'',settings.notes||'']);});downloadSetText(`${safeSetFilename()}.csv`,rows.map(row=>row.map(value=>`"${String(value).replaceAll('"','""')}"`).join(',')).join('\n'),'text/csv'); }
function setM3uEntries() { const preference=setBrief().edits;return currentSetPlan.map(track=>{const extended=track._hasExtended?track._job?.extended_path:'';const original=track._libraryPath||track._job?.library_path||track.file_path||track.wav_path||track._job?.wav_path||track.output_path;return {track,path:preference==='original'?original:(extended||original)};}); }
function downloadSetM3uEntries(entries) { const lines=['#EXTM3U',...entries.flatMap(({track,path})=>[`#EXTINF:${Math.round(track.duration_seconds||0)},${track.artist?`${track.artist} - `:''}${track.source_name.replace(/\.[^.]+$/,'')}`,path])];downloadSetText(`${safeSetFilename()}.m3u8`,lines.join('\r\n'),'audio/x-mpegurl;charset=utf-8'); }
async function exportSetM3u() { const button=$('#export-set-m3u');const status=$('#set-export-status');const entries=setM3uEntries();button.disabled=true;button.textContent='Checking paths…';status.className='set-export-status checking';status.innerHTML=`<span>Checking ${entries.length} tracks on disk…</span>`;try{const response=await fetch('/api/set-builder/export-preflight',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({paths:entries.map(entry=>entry.path||'')})});if(!response.ok)throw new Error(await response.text());const result=await response.json();const validEntries=entries.filter((entry,index)=>result.items[index]?.exists);if(result.ready){status.className='set-export-status ready';status.innerHTML=`<strong>Ready for Rekordbox: ${result.valid}/${result.total} tracks</strong><span>All audio files were found. Downloading the playlist now.</span>`;downloadSetM3uEntries(validEntries);}else{const missing=entries.filter((entry,index)=>!result.items[index]?.exists);status.className='set-export-status warning';status.innerHTML=`<strong>${result.missing} of ${result.total} tracks need attention</strong><span>The playlist was not downloaded because these files are unavailable:</span><ul>${missing.map(({track,path})=>`<li><b>${escapeHtml(track.source_name.replace(/\.[^.]+$/,''))}</b><small>${escapeHtml(path||'No file path')}</small></li>`).join('')}</ul>${validEntries.length?'<button type="button" class="button secondary export-valid-only">Export valid tracks only</button>':''}`;status.querySelector('.export-valid-only')?.addEventListener('click',()=>downloadSetM3uEntries(validEntries));}}catch(error){status.className='set-export-status warning';status.innerHTML=`<strong>Could not validate the playlist</strong><span>${escapeHtml(error.message||String(error))}</span>`;}finally{button.disabled=false;button.textContent='Export M3U8';} }
async function loadSetBuilder() {
  const catalog=await fetch('/api/set-builder/catalog',{cache:'no-store'}).then(response=>{if(!response.ok)throw new Error('Set Builder catalog could not be loaded.');return response.json();});
  setBuilderLibrary=(catalog.tracks||[]).map(item=>{const song=item.analysis||{};const job=item.job||{};const hasExtended=Boolean(job.extended_path)&&!JSON.parse(job.config_json||'{}').analysis_only;const preferred=$('#set-edits').value;const libraryPath=job.library_path||song.file_path||song.wav_path||job.wav_path;return {...song,_job:job,_genre:item.genre||song.detected_style||'Other',_detailedGenre:item.detailed_genre||'',_hasExtended:hasExtended,_libraryPath:libraryPath,_selectedPath:preferred==='original'?libraryPath:(hasExtended?job.extended_path:libraryPath)};});
  const names=setBuilderLibrary.slice().sort((a,b)=>a.source_name.localeCompare(b.source_name)); const trackOptions=names.map(track=>option(setTrackId(track),track.source_name.replace(/\.[^.]+$/,''))); $('#set-required').replaceChildren(option('','Choose a track'),...trackOptions.map(item=>item.cloneNode(true)));$('#set-excluded').replaceChildren(option('','Choose a track'),...trackOptions);
  const leafGenres=[...new Set(setBuilderLibrary.map(track=>track._genre))].sort();const genre=$('#set-genre');const excluded=$('#set-excluded-genres');const current=selectedSetGenres();const currentDetailed=selectedSetDetailedGenres();const currentExcluded=selectedExcludedSetGenres();const choices=new Map();leafGenres.forEach(name=>{const parts=name.split(' / ');for(let index=1;index<parts.length;index+=1){const parent=parts.slice(0,index).join(' / ');choices.set(parent,`All ${parent}`);}choices.set(name,name);});const sortedChoices=[...choices].sort((a,b)=>a[0].localeCompare(b[0]));genre.replaceChildren(option('all','Any parent genre'),...sortedChoices.map(([value,label])=>option(value,label)));excluded.replaceChildren(...sortedChoices.map(([value,label])=>option(value,label)));[...genre.options].forEach(item=>{item.selected=current.length?current.includes(item.value):item.value==='all';});populateSetDetailedGenres(currentDetailed);[...excluded.options].forEach(item=>{item.selected=currentExcluded.includes(item.value);});if(current.length)setGenreSelectionOrder=setGenreSelectionOrder.filter(value=>current.includes(value)).concat(current.filter(value=>!setGenreSelectionOrder.includes(value)));
  bindSetBuilder();renderSetGenreMix();renderSetDetailedGenres();renderExcludedSetGenres();renderSavedSets();renderSetRules();if(currentSetPlan.length)renderSetPlan();
}
function bindSetBuilder() {
  if(setBuilderBound)return;setBuilderBound=true;
  $('#set-builder-form').onsubmit=event=>{event.preventDefault();const button=$('#set-generate');button.disabled=true;button.textContent='Building and optimizing…';$('#set-builder-message').textContent='Ranking compatible tracks and shaping the energy journey…';requestAnimationFrame(()=>setTimeout(async()=>{try{await generateSetPlan();}finally{button.disabled=false;button.textContent='Generate set plan';}},0));};
  $('#add-required-track').onclick=()=>{const id=$('#set-required').value;if(id){setRequiredIds.add(id);setExcludedIds.delete(id);renderSetRules();}};
  $('#add-excluded-track').onclick=()=>{const id=$('#set-excluded').value;if(id){setExcludedIds.add(id);setRequiredIds.delete(id);renderSetRules();}};
  $('#set-genre').addEventListener('change',()=>{renderSetGenreMix();populateSetDetailedGenres();});
  $('#set-detailed-genres').addEventListener('change',renderSetDetailedGenres);
  $('#set-excluded-genres').addEventListener('change',renderExcludedSetGenres);
  $('#reset-set-brief').onclick=()=>{$('#set-builder-form').reset();[...$('#set-genre').options].forEach(option=>{option.selected=option.value==='all';});populateSetDetailedGenres();[...$('#set-excluded-genres').options].forEach(option=>{option.selected=false;});setGenreSelectionOrder=[];renderSetGenreMix();renderSetDetailedGenres();renderExcludedSetGenres();setRequiredIds.clear();setExcludedIds.clear();setLockedIds.clear();setProposals=[];activeSetProposal='';renderSetRules();renderSetProposals();$('#set-builder-message').textContent='Set brief reset.';};
  $('#set-undo').onclick=undoSetEdit;$('#set-redo').onclick=redoSetEdit;$('#set-compact').onclick=()=>{setCompactMode=!setCompactMode;localStorage.setItem('set-builder-compact',String(setCompactMode));renderSetPlan();};$('#add-set-track').onclick=()=>addSetTrack();$('#save-set').onclick=saveCurrentSet;$('#export-set-csv').onclick=exportSetCsv;$('#export-set-m3u').onclick=exportSetM3u;
  document.addEventListener('keydown',event=>{if(!$('#set-builder-view').classList.contains('active')||!(event.metaKey||event.ctrlKey)||event.key.toLowerCase()!=='z')return;event.preventDefault();event.shiftKey?redoSetEdit():undoSetEdit();});
  $('#load-set').onclick=()=>loadSavedSet(savedSets().find(set=>set.id===$('#saved-set-select').value));
  $('#duplicate-set').onclick=()=>{const record=savedSets().find(set=>set.id===$('#saved-set-select').value);if(!record)return;const copy={...record,id:String(Date.now()),name:`${record.name} Copy`,brief:{...record.brief,name:`${record.name} Copy`}};storeSavedSets([copy,...savedSets()]);$('#saved-set-select').value=copy.id;loadSavedSet(copy);};
  $('#delete-set').onclick=async()=>{const id=$('#saved-set-select').value;if(!id||!await confirmAction('Delete this saved set plan? Audio and Library tracks will not be removed.', {title:'Delete saved set', acceptLabel:'Delete', danger:true}))return;storeSavedSets(savedSets().filter(set=>set.id!==id));};
}

function renderLibraryIntelligence(songs, latestByName) {
  const roleNames = ['warm-up','peak-time','closing','vocal-safe','melodic','ambient','live timing'];
  const groups = Object.fromEntries(roleNames.map(role => [role, []]));
  songs.forEach(song => libraryRoles(song).forEach(role => groups[role].push(song)));
  $('#role-groups').innerHTML = roleNames.map(role => {
    const [label,description] = LIBRARY_ROLE_INFO[role];
    return `<details class="role-card"><summary><strong>${groups[role].length}</strong><span>${label}</span><small>${escapeHtml(description)}</small></summary><div>${groups[role].length ? groups[role].map(song => `<button type="button" data-job-id="${latestByName.get(song.source_name.toLowerCase())?.id || ''}">${escapeHtml(song.source_name.replace(/\.[^.]+$/, ''))}<span>${Number(song.bpm || 0).toFixed(1)} BPM · ${escapeHtml(formatLibraryKey(song.key))}</span></button>`).join('') : '<p>No matching tracks yet.</p>'}<button type="button" class="role-filter" data-role="${role}">Filter DJ Library to ${label}</button></div></details>`;
  }).join('');
  $('#role-groups').querySelectorAll('[data-job-id]').forEach(button => button.onclick = () => document.querySelector(`.library-card[data-job-id="${button.dataset.jobId}"]`)?.scrollIntoView({behavior:'smooth',block:'start'}));
  $('#role-groups').querySelectorAll('.role-filter').forEach(button => button.onclick = () => { $('#library-role').value = button.dataset.role; $('#library-role').dispatchEvent(new Event('change')); document.querySelector('.library-toolbar')?.scrollIntoView({behavior:'smooth',block:'start'}); });
  const select = $('#compatibility-source'); const previous = select.value;
  select.replaceChildren(option('', 'Choose a track'), ...songs.sort((a,b) => a.source_name.localeCompare(b.source_name)).map(song => option(song.source_name, song.source_name.replace(/\.[^.]+$/, ''))));
  if (songs.some(song => song.source_name === previous)) select.value = previous;
  const show = () => {
    const source = songs.find(song => song.source_name === select.value);
    if (!source) { $('#compatible-tracks').innerHTML = '<p>Select a track to see BPM and key-compatible suggestions.</p>'; return; }
    const matches = songs.filter(song => song !== source).map(song => ({song,...compatibility(source,song)})).filter(match => match.score >= 40).sort((a,b) => b.score-a.score).slice(0,8);
    $('#compatible-tracks').innerHTML = matches.length ? `<div class="compatibility-title"><div><strong>Mix suggestions for ${escapeHtml(source.source_name)}</strong><span>${Number(source.bpm || 0).toFixed(1)} BPM · ${escapeHtml(formatLibraryKey(source.key))}</span></div><p><b>How the score works:</b> tempo 45% · harmonic key 35% · energy 10% · shared role 10%. Treat it as a shortlist, then listen before mixing.</p></div>${matches.map(match => `<button type="button" data-job-id="${latestByName.get(match.song.source_name.toLowerCase())?.id || ''}"><strong>${escapeHtml(match.song.source_name.replace(/\.[^.]+$/, ''))}</strong><span>${match.score}% match · ${Number(match.song.bpm || 0).toFixed(1)} BPM · ${escapeHtml(formatLibraryKey(match.song.key))}</span><small>${match.difference <= .02 ? 'tempo locked' : `${(match.difference*100).toFixed(1)}% tempo move`} · ${match.key}</small><em>Tempo ${match.components.tempo}/45 · Key ${match.components.key}/35 · Energy ${match.components.energy}/10 · Role ${match.components.role}/10</em></button>`).join('')}` : '<p>No strong matches are available yet. Try another source track or relax the Library filters.</p>';
    $('#compatible-tracks').querySelectorAll('button').forEach(button => button.onclick = () => document.querySelector(`.library-card[data-job-id="${button.dataset.jobId}"]`)?.scrollIntoView({behavior:'smooth',block:'start'}));
  };
  select.onchange = show; show();
}

async function loadLibrary() {
  const view = $('#library-view');
  view.classList.add('view-refreshing');
  let catalog;
  const sequence = ++libraryLoadSequence;
  libraryRequestController?.abort();
  libraryRequestController = new AbortController();
  try {
    const parameters = new URLSearchParams({page:String(libraryUiState.page),page_size:String(libraryUiState.pageSize),search:libraryUiState.search,role:libraryUiState.role,category:libraryUiState.category,detailed_genre:libraryUiState.detailedGenre,preset:libraryUiState.preset,sort:libraryUiState.sort,result:libraryUiState.result,quality:libraryUiState.quality,key:libraryUiState.key,energy:libraryUiState.energy,vocals:libraryUiState.vocals,timing:libraryUiState.timing});
    if(libraryUiState.bpmMin)parameters.set('bpm_min',libraryUiState.bpmMin);
    if(libraryUiState.bpmMax)parameters.set('bpm_max',libraryUiState.bpmMax);
    const response = await fetch(`/api/library/catalog?${parameters}`, {cache:'no-store',signal:libraryRequestController.signal});
    if (!response.ok) throw new Error('DJ Library could not be loaded.');
    catalog = await response.json();
    if(sequence!==libraryLoadSequence)return;
    libraryUiState.page=Number(catalog.page||1);
    libraryLoadedAt = Date.now();
  } catch(error) {
    if(error.name==='AbortError')return;
    $('#library-list').innerHTML=`<div class="empty danger-text">${escapeHtml(error.message||'DJ Library could not be loaded.')} <button type="button" class="button secondary library-retry">Retry</button></div>`;
    $('#library-list .library-retry')?.addEventListener('click',loadLibrary);
    return;
  } finally {
    if(sequence===libraryLoadSequence)view.classList.remove('view-refreshing');
  }
  const allJobs = (catalog.tracks || []).map(track => track.job);
  const report = {songs:Object.fromEntries((catalog.tracks || []).map((track,index) => [index, track.analysis || {}]))};
  const downloadedTracks = (catalog.tracks || []).map(track => track.downloaded).filter(Boolean);
  const downloaded = {tracks:downloadedTracks, genres:catalog.facets?.categories || {}};
  const downloadedByJob = new Map((downloaded.tracks || []).filter(track => track.completed_library_job_id).map(track => [Number(track.completed_library_job_id), track]));
  $('#library-genre-options').replaceChildren(...[...new Set([...Object.keys(downloaded.genres || {}),...ELECTRONIC_GENRE_CATEGORIES,...LATIN_GENRE_CATEGORIES])].sort().map(name => option(name, name)));
  const jobs = allJobs.filter(job => job.status === 'complete');
  const analysisByTrack = new Map(Object.values(report.songs || {}).map(song => [String(song.source_name || '').toLowerCase(), song]));
  const grouped = new Map();
  [...jobs].reverse().forEach(job => {
    const key = job.source_name.toLowerCase();
    const versions = grouped.get(key) || [];
    job._generation = Number(job.generation_count || versions.length + 1); versions.push(job); grouped.set(key, versions);
  });
  const latestByName = new Map([...grouped.entries()].map(([name, versions]) => [name, versions.at(-1)]));
  const intelligenceSongs=(catalog.intelligence||[]).map(item=>item.analysis).filter(song=>song?.source_name);
  const intelligenceJobs=new Map((catalog.intelligence||[]).map(item=>[String(item.source_name||'').toLowerCase(),{id:item.job_id}]));
  renderLibraryIntelligence(intelligenceSongs, intelligenceJobs);
  const root = $('#library-list');
  if (compactAudioOwner?.closest('#library-list')) stopCompactAudio();
  if (!catalog.total) {
    root.innerHTML = '<div class="empty">No completed tracks yet.</div>';
    $('#library-select-all').checked = false;
    $('#library-select-all').disabled = true;
    $('#library-selection-count').textContent = '0 selected';
    $('#library-download-selected').disabled = true;
    return;
  }
  $('#library-select-all').disabled = false;
  const cards = [...grouped.values()].reverse().map(versions => {
    const latest = versions.at(-1); const config = JSON.parse(latest.config_json || '{}');
    const analysisOnly = Boolean(config.analysis_only);
    const versioned = String(latest.extended_path || '').includes('/versions/');
    const reviewPending = latest.review_status === 'pending';
    const choice = config.manual_candidate_selection ? `Manual choices: intro ${config.intro_candidate ?? '—'} · outro ${config.outro_candidate ?? '—'}` : 'Automatic ranking';
    const generationCount = Number(latest.generation_count || versions.length);
    return `<article class="panel library-card" data-job-id="${latest.id}"><div class="library-head"><div><p class="eyebrow">LATEST · GENERATION ${latest._generation}${analysisOnly?' · ANALYZED':''}</p><h2>${escapeHtml(latest.source_name)}</h2><span>${escapeHtml(analysisOnly ? 'DJ analysis complete · original preserved' : choice)}</span></div><div class="library-head-actions"><button class="button secondary library-reprocess">${analysisOnly?'Extend track':'Configure reprocess'}</button>${analysisOnly?'':`<button class="button secondary library-review">${reviewPending?'Open review':'Create review'}</button>`}<button class="button secondary open-latest">Show full details</button></div></div>${libraryReprocessForm(latest, config)}<div class="library-metrics"><p><b>${latest.bpm ? Number(latest.bpm).toFixed(1) : '—'}</b><span>BPM</span></p><p><b class="library-key-value">—</b><span>Key</span></p><p><b>${analysisOnly?'Not extended':latest.intro_quality == null ? 'Preserved' : pct(latest.intro_quality)}</b><span>Intro</span></p><p><b>${analysisOnly?'Not extended':latest.outro_quality == null ? 'Preserved' : pct(latest.outro_quality)}</b><span>Outro</span></p><p><b>${reportDate(latest.updated_at)}</b><span>Processed</span></p></div><div class="library-player"><span>${analysisOnly?'Original analyzed track':'Newest extended edit'}</span><audio controls preload="none" data-src="/api/jobs/${latest.id}/audio/${analysisOnly?'wav':'extended'}"></audio></div><div class="library-downloads"><a class="button secondary" href="/api/jobs/${latest.id}/download/wav">Source WAV</a>${!analysisOnly && versioned ? `<a class="button secondary" href="/api/jobs/${latest.id}/download/extended">Download newest extended WAV</a>` : analysisOnly ? '<span>Choose Extend track whenever you want to create an edit.</span>' : '<span>Reprocess once to create an immutable downloadable generation.</span>'}</div><div class="library-detail-host"></div><details class="version-history" data-loaded="false"><summary>${generationCount} generation${generationCount===1?'':'s'} · view version history</summary><ul><li class="muted-copy">Open to load version history.</li></ul></details></article>`;
  });
  root.innerHTML = cards.join('') || '<div class="empty">No tracks match these filters.</div>';
  root.querySelectorAll('.library-card').forEach(card => {
    const latest = jobs.find(job => String(job.id) === card.dataset.jobId);
    const analysis = analysisByTrack.get(latest.source_name.toLowerCase()) || {};
    let latestConfig = {}; try { latestConfig = JSON.parse(latest.config_json || '{}'); } catch (_) { latestConfig = {}; }
    const analysisOnly = Boolean(latestConfig.analysis_only);
    const reviewPending = latest.review_status === 'pending';
    const downloadedTrack = downloadedByJob.get(Number(latest.id));
    const category = normalizedGenreCategory(downloadedTrack?.genre_category || analysis.detected_style || 'Unclassified');
    card.dataset.downloadedId = downloadedTrack?.id || '';
    card.dataset.title = latest.source_name.toLowerCase();
    card.dataset.sourceName = latest.source_name;
    card.dataset.category = String(category).toLowerCase();
    const roles = libraryRoles(analysis);
    const energy = songEnergy(analysis);
    const resolvedPreset = effectivePreset(analysis, latest);
    card.dataset.preset = resolvedPreset;
    card.dataset.requestedPreset = String(latest.preset || 'default').toLowerCase();
    card.dataset.roles = roles.join('|');
    card.dataset.key = normalizedKey(analysis.key || '');
    card.dataset.camelot = camelotKey(analysis.key);
    card.dataset.bpm = Number(analysis.bpm || latest.bpm || 0);
    card.dataset.energy = energyBand(energy);
    card.dataset.energyValue = energy;
    card.dataset.vocals = vocalProfile(analysis);
    card.dataset.timing = timingProfile(analysis);
    card.dataset.updated = Date.parse(latest.updated_at || 0);
    card.dataset.result = latest.review_status === 'pending' ? 'review' : ((latest.intro_quality != null || latest.outro_quality != null) ? 'extended' : 'preserved');
    card.dataset.quality = downloadedTrack?.audio_quality_label || 'unanalyzed';
    const description = card.querySelector('.library-head>div>span');
    const presetLabel = card.dataset.requestedPreset === 'auto' ? `auto → ${resolvedPreset}` : resolvedPreset;
    description.textContent = `${category}${downloadedTrack ? ' · library genre' : ' · detected category'} · ${presetLabel} · ${description.textContent}`;
    const keyValue = card.querySelector('.library-key-value');
    keyValue.dataset.standard = analysis.key || '';
    keyValue.textContent = formatLibraryKey(analysis.key);
    card.querySelector('.library-head-actions').insertAdjacentHTML('beforeend', '<button class="button secondary remove-library-track">Remove from library</button>');
    if (downloadedTrack) {
      card.querySelector('.library-head-actions').insertAdjacentHTML('afterbegin', '<button class="button secondary edit-library-genre">Edit genre</button>');
      card.querySelector('.library-head').insertAdjacentHTML('afterend', genreEditorMarkup(downloadedTrack.genre_category || 'Other', downloadedTrack.suggested_genre || '', true));
    }
    const resultLabel = latest.review_status === 'pending' ? 'Awaiting review' : (analysisOnly ? 'Analyzed only' : ((latest.intro_quality != null || latest.outro_quality != null) ? 'Extended' : 'Preserved'));
    const sourceStem = latest.source_name.replace(/\.[^.]+$/,'');
    const sourceParts = sourceStem.split(' - ');
    const trackTitle = downloadedTrack?.title || (sourceParts.length > 1 ? sourceParts.slice(1).join(' - ') : sourceStem);
    const trackArtist = downloadedTrack?.artist || (sourceParts.length > 1 ? sourceParts[0] : 'Unknown artist');
    const trackArtwork = downloadedTrack?.artwork_available
      ? `<img src="/api/downloaded-library/tracks/${downloadedTrack.id}/artwork?thumbnail=true" alt="" loading="lazy" decoding="async">`
      : '♫';
    card.dataset.artist = String(trackArtist).toLowerCase();
    const body = document.createElement('div'); body.className = 'library-card-body'; body.hidden = true;
    [...card.children].forEach(child => body.append(child));
    card.append(body);
    const identity=downloadedTrack?.recording_code?`${downloadedTrack.recording_code}-${downloadedTrack.version_code||'ORG'}`:'';
    const qualityScore=downloadedTrack?.audio_quality_score;
    const qualityTarget=downloadedTrack?.audio_quality?.target_status;
    const qualitySuffix=qualityTarget==='meets_target'?' · Target met':qualityTarget==='below_target'?' · Below target':qualityTarget==='unverified'?' · Unverified':'';
    const qualityText=qualityScore==null?'Quality pending':`Quality ${Math.round(Number(qualityScore))}${qualitySuffix}`;
    card.insertAdjacentHTML('afterbegin', `<div class="library-compact-row" role="button" tabindex="0" aria-expanded="false" aria-label="Show DJ details for ${escapeHtml(trackTitle)}"><label class="library-track-select"><input type="checkbox" value="${card.dataset.jobId}" aria-label="Select ${escapeHtml(trackTitle)}"><span></span></label><div class="library-row-icon">${trackArtwork}</div><div class="library-row-title"><h3>${escapeHtml(trackTitle)}</h3><span class="library-row-artist">${escapeHtml(trackArtist)}</span><small>${escapeHtml(category)}${identity?` · ${escapeHtml(identity)}`:''}</small></div><div class="library-row-metric"><b>${Number(analysis.bpm || latest.bpm || 0).toFixed(1)}</b><span>BPM</span></div><div class="library-row-metric"><b>${escapeHtml(formatLibraryKey(analysis.key))}</b><span>Key / Camelot</span></div><div class="library-row-metric"><b>${escapeHtml(energyBand(energy))}</b><span>Energy</span></div><div class="library-row-role">${roles.slice(0,2).map(role => `<span>${escapeHtml(LIBRARY_ROLE_INFO[role]?.[0] || role)}</span>`).join('')}</div><span class="library-result" data-result="${card.dataset.result}">${resultLabel}<small>${escapeHtml(qualityText)}</small></span>${compactAudioMarkup(`/api/jobs/${latest.id}/audio/${analysisOnly?'wav':'extended'}`,latest.duration_seconds||analysis.duration_seconds||0)}<details class="library-row-actions"><summary aria-label="Library track actions">•••</summary><div><button type="button" class="compact-remove danger-text">Remove from Library</button></div></details></div>`);
  });
  bindLazyAudio(root);
  bindCompactAudio(root);
  root.querySelectorAll('.version-history').forEach(history => history.addEventListener('toggle', async () => {
    if (!history.open || history.dataset.loaded === 'true') return;
    history.dataset.loaded = 'loading';
    const list = history.querySelector('ul');
    list.innerHTML = '<li class="muted-copy">Loading version history…</li>';
    try {
      const card = history.closest('.library-card');
      const payload = await fetch(`/api/library/jobs/${card.dataset.jobId}/details`).then(async response => {
        if (!response.ok) throw new Error((await response.json()).detail || 'Could not load version history.');
        return response.json();
      });
      const versions = payload.versions || [];
      list.innerHTML = versions.map((job,index) => {
        const generation = versions.length - index;
        const stored = String(job.extended_path || '').includes('/versions/');
        let config = {}; try { config = JSON.parse(job.config_json || '{}'); } catch (_) { config = {}; }
        const summary = config.analysis_only ? 'analysis only' : `${job.intro_quality == null ? 'intro preserved' : `${Math.round(job.intro_quality)}% intro`} · ${job.outro_quality == null ? 'outro preserved' : `${Math.round(job.outro_quality)}% outro`}`;
        return `<li><div><strong>Generation ${generation}${index===0?' · latest':''}</strong><span>${reportDate(job.updated_at)} · ${summary}</span></div>${stored ? `<a class="button secondary" href="/api/jobs/${job.id}/download/extended">Download</a>` : '<small>Original source</small>'}</li>`;
      }).join('') || '<li class="muted-copy">No version history is available.</li>';
      history.dataset.loaded = 'true';
    } catch (error) {
      list.innerHTML = `<li class="danger-text">${escapeHtml(error.message)}</li>`;
      history.dataset.loaded = 'false';
    }
  }));
  const libraryCards = [...root.querySelectorAll('.library-card')];
  const roleCounts = catalog.facets?.roles || {}; const categoryCounts = catalog.facets?.categories || {};
  $('#library-sidebar').innerHTML = `<div class="library-sidebar-head"><div><p class="eyebrow">DJ CRATES</p><h2>Browse Library</h2><span>${catalog.total} analyzed track${catalog.total===1?'':'s'}</span></div><button type="button" class="library-sidebar-toggle" aria-label="Collapse DJ crates" title="Collapse DJ crates">‹</button></div><nav><button type="button" class="library-side-all active"><span>All tracks</span><b>${catalog.total}</b></button><div class="folder-heading"><span>Set roles</span></div>${Object.entries(roleCounts).sort().map(([role,count])=>`<button type="button" class="library-side-role" data-value="${escapeHtml(role)}"><span>${escapeHtml(LIBRARY_ROLE_INFO[role]?.[0]||role)}</span><b>${count}</b></button>`).join('')}<div class="folder-heading"><span>Genres</span></div>${genreFolderTree(Object.entries(categoryCounts),'library-side-category')}</nav>`;
  const libraryLayout = document.querySelector('.library-layout');
  const sidebarToggle = $('#library-sidebar').querySelector('.library-sidebar-toggle');
  const setSidebarCollapsed = collapsed => { libraryLayout.classList.toggle('sidebar-collapsed', collapsed); sidebarToggle.textContent = collapsed ? '›' : '‹'; sidebarToggle.setAttribute('aria-label', collapsed ? 'Expand DJ crates' : 'Collapse DJ crates'); sidebarToggle.title = sidebarToggle.getAttribute('aria-label'); localStorage.setItem('dj-library-crates-collapsed', String(collapsed)); };
  setSidebarCollapsed(localStorage.getItem('dj-library-crates-collapsed') === 'true');
  sidebarToggle.onclick = () => setSidebarCollapsed(!libraryLayout.classList.contains('sidebar-collapsed'));
  bindGenreFolderState($('#library-sidebar'));
  bindLibraryFilters(catalog);
  bindLibrarySelection();
  root.querySelectorAll('.library-compact-row').forEach(row => {
    const toggle = () => { const body=row.closest('.library-card').querySelector('.library-card-body'); body.hidden=!body.hidden; row.setAttribute('aria-expanded', String(!body.hidden)); };
    row.onclick = event => {
      if (event.target.closest('input,label,a,button,audio,details,summary,select,form')) return;
      const selected = root.querySelectorAll('.library-track-select input:checked');
      if (selected.length) {
        const checkbox = row.querySelector('.library-track-select input');
        checkbox.checked = !checkbox.checked;
        checkbox.dispatchEvent(new Event('change'));
        return;
      }
      toggle();
    };
    row.onkeydown = event => { if ((event.key === 'Enter' || event.key === ' ') && event.target === row) { event.preventDefault(); toggle(); } };
  });
  const cardAction = (button, selector) => { const card=button.closest('.library-card'); card.querySelector('.library-card-body').hidden=false; card.querySelector(selector)?.click(); button.closest('details').open=false; };
  root.querySelectorAll('.compact-remove').forEach(button => button.onclick = () => cardAction(button,'.remove-library-track'));
  $('#library-sidebar').querySelector('.library-side-all').onclick = () => { libraryUiState.role='all'; libraryUiState.category='all'; libraryUiState.detailedGenre='all'; libraryUiState.page=1; loadLibrary(); };
  $('#library-sidebar').querySelectorAll('.library-side-role').forEach(button => button.onclick=()=>{ libraryUiState.role=button.dataset.value; libraryUiState.page=1; loadLibrary(); });
  $('#library-sidebar').querySelectorAll('.library-side-category').forEach(button => button.onclick=()=>{ libraryUiState.category=button.dataset.value; libraryUiState.detailedGenre='all'; libraryUiState.page=1; loadLibrary(); });
  root.querySelectorAll('.library-reprocess').forEach(button => button.onclick = () => {
    const form = button.closest('.library-card').querySelector('.library-reprocess-form');
    form.hidden = !form.hidden;
    button.textContent = form.hidden ? 'Configure reprocess' : 'Close configuration';
    if (!form.hidden) form.querySelector('select').focus();
  });
  root.querySelectorAll('.edit-library-genre').forEach(button => button.onclick = () => {
    const card = button.closest('.library-card');
    const editor = card.querySelector('.inline-genre-editor'); editor.hidden = !editor.hidden;
    if (!editor.hidden) editor.querySelector('select').focus();
  });
  root.querySelectorAll('.library-card[data-downloaded-id]:not([data-downloaded-id=""])').forEach(card => bindGenreEditor(card.querySelector('.inline-genre-editor'), () => [Number(card.dataset.downloadedId)], async payload => {card.querySelector('.library-row-title small').textContent=payload.genre_category;card.querySelector('.inline-genre-editor').hidden=true;downloadedLoadedAt=0;}));
  root.querySelectorAll('.close-reprocess').forEach(button => button.onclick = () => {
    const card = button.closest('.library-card');
    card.querySelector('.library-reprocess-form').hidden = true;
    card.querySelector('.library-reprocess').textContent = 'Configure reprocess';
  });
  root.querySelectorAll('.library-reprocess-form').forEach(reprocessForm => {
    const submit = async review => {
      const card = reprocessForm.closest('.library-card');
      const latest = jobs.find(job => String(job.id) === card.dataset.jobId);
      let latestConfig = {}; try { latestConfig = JSON.parse(latest.config_json || '{}'); } catch (_) { latestConfig = {}; }
      const introAuto = reprocessForm.elements.intro_bars.value === 'auto';
      const outroAuto = reprocessForm.elements.outro_bars.value === 'auto';
      const body = {
        preset:reprocessForm.elements.preset.value,
        intro_bars:introAuto ? Number(latestConfig.analysis_only ? appConfig.effective.intro_bars : latest.intro_bars) : Number(reprocessForm.elements.intro_bars.value),
        outro_bars:outroAuto ? Number(latestConfig.analysis_only ? appConfig.effective.outro_bars : latest.outro_bars) : Number(reprocessForm.elements.outro_bars.value),
        intro_bars_auto:introAuto, outro_bars_auto:outroAuto,
        use_stems:reprocessForm.elements.use_stems.value === 'true',
        auto_bars:reprocessForm.elements.auto_bars.checked,
        minimum_intro_loop_quality:Number(reprocessForm.elements.minimum_intro_loop_quality.value),
        minimum_outro_loop_quality:Number(reprocessForm.elements.minimum_outro_loop_quality.value),
        maximum_repetitions:Number(reprocessForm.elements.maximum_repetitions.value),
        crossfade_ms:Number(reprocessForm.elements.crossfade_ms.value),
        candidate_count:Number(reprocessForm.elements.candidate_count.value),
        intro_search_seconds:Number(reprocessForm.elements.intro_search_seconds.value),
        outro_search_seconds:Number(reprocessForm.elements.outro_search_seconds.value),
        maximum_vocal_coverage_percent:Number(reprocessForm.elements.maximum_vocal_coverage_percent.value),
        maximum_vocal_boundary_risk_percent:Number(reprocessForm.elements.maximum_vocal_boundary_risk_percent.value),
        maximum_buildup_risk_percent:Number(reprocessForm.elements.maximum_buildup_risk_percent.value),
        maximum_bass_reset_risk_percent:Number(reprocessForm.elements.maximum_bass_reset_risk_percent.value),
        minimum_stem_reliability_percent:Number(reprocessForm.elements.minimum_stem_reliability_percent.value),
        pcm_bits:Number(reprocessForm.elements.pcm_bits.value),
        preview_seconds:Number(reprocessForm.elements.preview_seconds.value),
        export_cues:reprocessForm.elements.export_cues.value === 'true',
        review_candidates:review,
      };
      reprocessForm.querySelectorAll('button').forEach(item => item.disabled = true);
      reprocessForm.querySelector('.reprocess-message').textContent = review ? 'Queuing review…' : 'Queuing new generation…';
      await jobAction(latest.id, 'reprocess', body);
      showView('workspace-view');
    };
    reprocessForm.addEventListener('submit', event => { event.preventDefault(); submit(false); });
    reprocessForm.querySelector('.reprocess-review').onclick = () => submit(true);
  });
  root.querySelectorAll('.library-review').forEach(button => button.onclick = async () => {
    const card = button.closest('.library-card');
    const latest = jobs.find(job => String(job.id) === card.dataset.jobId);
    if (latest.review_status === 'pending') { showView('review-view'); return; }
    await jobAction(latest.id, 'reprocess', {review_candidates:true});
    showView('workspace-view');
  });
  root.querySelectorAll('.open-latest').forEach(button => button.onclick = async () => {
    const card = button.closest('.library-card');
    const host = card.querySelector('.library-detail-host');
    if (host.childElementCount) {
      host.replaceChildren(); button.textContent = 'Show full details'; return;
    }
    const latest = jobs.find(job => String(job.id) === card.dataset.jobId);
    const detail = jobElement(latest); detail.classList.add('library-embedded');
    host.append(detail); detail.querySelector('.details-job').click();
    button.textContent = 'Hide full details';
  });
  root.querySelectorAll('.remove-library-track').forEach(button => button.onclick = async () => {
    const card = button.closest('.library-card');
    const latest = jobs.find(job => String(job.id) === card.dataset.jobId);
    if (!await confirmAction(`Remove ${latest.source_name} and all of its generations from the Library? Exported audio files will remain in the output folder.`, {title:'Remove Library track', acceptLabel:'Remove', danger:true})) return;
    button.disabled = true; button.textContent = 'Removing…';
    const response = await fetch(`/api/library/${encodeURIComponent(latest.source_name)}`, {method:'DELETE'});
    if (!response.ok) { alert((await response.json()).detail || 'Could not remove the track.'); button.disabled = false; button.textContent = 'Remove from library'; return; }
    await Promise.all([loadLibrary(), loadAnalysis(), loadReports()]);
  });
}

function bindLibraryFilters(catalog) {
  const controls={search:$('#library-search'),role:$('#library-role'),category:$('#library-category'),detailedGenre:$('#library-detailed-genre'),preset:$('#library-preset'),sort:$('#library-sort'),result:$('#library-result'),quality:$('#library-quality'),bpmMin:$('#library-bpm-min'),bpmMax:$('#library-bpm-max'),key:$('#library-key'),energy:$('#library-energy'),vocals:$('#library-vocals'),timing:$('#library-timing')};
  const fill=(select,values,label)=>{const current=libraryUiState[select===controls.category?'category':select===controls.preset?'preset':'key'];select.replaceChildren(option('all',label),...[...new Set(values.filter(Boolean))].sort().map(value=>option(value,value==='unclassified'?'Unclassified':value)));select.value=[...select.options].some(item=>item.value===current)?current:'all';};
  controls.role.replaceChildren(option('all','All roles'),...Object.keys(LIBRARY_ROLE_INFO).map(value=>option(value,LIBRARY_ROLE_INFO[value][0]))); controls.role.value=libraryUiState.role;
  const categories=Object.keys(catalog.facets?.categories||{}).flatMap(name=>{const parts=name.split(' / ');return parts.map((_,index)=>parts.slice(0,index+1).join(' / ').toLowerCase());});
  fill(controls.category,categories,'All parent genres');
  const detailedByCategory=catalog.facets?.detailed_genres_by_category||{};
  const detailedCounts=libraryUiState.category==='all'?(catalog.facets?.detailed_genres||{}):Object.entries(detailedByCategory).reduce((counts,[category,genres])=>{const selected=libraryUiState.category.toLowerCase();if(category.toLowerCase()===selected||category.toLowerCase().startsWith(`${selected} / `))Object.entries(genres).forEach(([genre,count])=>{counts[genre]=(counts[genre]||0)+Number(count);});return counts;},{});
  controls.detailedGenre.replaceChildren(option('all',libraryUiState.category==='all'?'All detailed genres':'Any detailed genre'),...Object.entries(detailedCounts).sort(([a],[b])=>a.localeCompare(b)).map(([genre,count])=>option(genre,`${genre} (${count})`)));
  controls.detailedGenre.value=[...controls.detailedGenre.options].some(item=>item.value===libraryUiState.detailedGenre)?libraryUiState.detailedGenre:'all';
  if(controls.detailedGenre.value==='all')libraryUiState.detailedGenre='all';
  fill(controls.preset,catalog.facets?.presets||[],'All effective presets'); fill(controls.key,catalog.facets?.keys||[],'All keys');
  Object.entries(controls).forEach(([name,control])=>{if(name==='category'||name==='preset'||name==='key'||name==='role')return; control.value=libraryUiState[name]??control.value;});
  $('#library-page-size').value=String(libraryUiState.pageSize); $('#library-key-display').value=libraryKeyMode();
  const request=(page=1)=>{libraryUiState.page=page;loadLibrary();};
  controls.search.oninput=()=>{clearTimeout(librarySearchTimer);librarySearchTimer=setTimeout(()=>{libraryUiState.search=controls.search.value.trim();request(1);},240);};
  Object.entries(controls).filter(([name])=>!['search','category'].includes(name)).forEach(([name,control])=>control.onchange=()=>{libraryUiState[name]=control.value;request(1);});
  controls.category.onchange=()=>{libraryUiState.category=controls.category.value;libraryUiState.detailedGenre='all';request(1);};
  [controls.bpmMin,controls.bpmMax].forEach(input=>input.oninput=()=>{clearTimeout(librarySearchTimer);librarySearchTimer=setTimeout(()=>{libraryUiState.bpmMin=controls.bpmMin.value;libraryUiState.bpmMax=controls.bpmMax.value;request(1);},240);});
  $('#library-page-size').onchange=event=>{libraryUiState.pageSize=Number(event.target.value);localStorage.setItem('dj-library-page-size',String(libraryUiState.pageSize));request(1);};
  $('#library-key-display').onchange=event=>{localStorage.setItem('audioextender-key-view',event.target.value);document.querySelectorAll('.library-key-value').forEach(node=>node.textContent=formatLibraryKey(node.dataset.standard,event.target.value));};
  const resetLibraryFilters=()=>{Object.assign(libraryUiState,{search:'',role:'all',category:'all',detailedGenre:'all',preset:'all',sort:'newest',result:'all',quality:'all',bpmMin:'',bpmMax:'',key:'all',energy:'all',vocals:'all',timing:'all',page:1});loadLibrary();};
  $('#library-reset-filters').onclick=resetLibraryFilters;
  $('#library-reset-filters-top').onclick=resetLibraryFilters;
  const changePage=page=>{libraryUiState.page=page;loadLibrary();document.querySelector('.library-toolbar').scrollIntoView({behavior:'smooth',block:'start'});};
  renderTrackPagination($('#library-pagination'),catalog.page,catalog.total_pages,catalog.filtered_total,changePage);
  renderTrackPagination($('#library-pagination-top'),catalog.page,catalog.total_pages,catalog.filtered_total,changePage);
  $('#library-filter-count').textContent=`${catalog.filtered_total} of ${catalog.total} tracks${catalog.total_pages>1?` · page ${catalog.page}/${catalog.total_pages}`:''}`;
  const active=[libraryUiState.search,libraryUiState.role!=='all',libraryUiState.category!=='all',libraryUiState.detailedGenre!=='all',libraryUiState.preset!=='all',libraryUiState.result!=='all',libraryUiState.quality!=='all',libraryUiState.bpmMin,libraryUiState.bpmMax,libraryUiState.key!=='all',libraryUiState.energy!=='all',libraryUiState.vocals!=='all',libraryUiState.timing!=='all'].filter(Boolean).length;
  $('#library-active-filter-count').textContent=active?`${active} active`:'';
  $('#library-filter-chips').innerHTML=[libraryUiState.role!=='all'&&`Role: ${LIBRARY_ROLE_INFO[libraryUiState.role]?.[0]||libraryUiState.role}`,libraryUiState.category!=='all'&&`Parent: ${libraryUiState.category}`,libraryUiState.detailedGenre!=='all'&&`Detailed: ${libraryUiState.detailedGenre}`,libraryUiState.preset!=='all'&&`Preset: ${libraryUiState.preset}`,libraryUiState.quality!=='all'&&`Quality: ${controls.quality.options[controls.quality.selectedIndex]?.text||libraryUiState.quality}`,libraryUiState.key!=='all'&&`Key: ${formatLibraryKey(libraryUiState.key)}`].filter(Boolean).map(label=>`<span>${escapeHtml(label)}</span>`).join('');
  const sidebar=$('#library-sidebar');sidebar.querySelector('.library-side-all')?.classList.toggle('active',libraryUiState.role==='all'&&libraryUiState.category==='all');sidebar.querySelectorAll('.library-side-role').forEach(button=>button.classList.toggle('active',libraryUiState.role===button.dataset.value));sidebar.querySelectorAll('.library-side-category').forEach(button=>button.classList.toggle('active',libraryUiState.category===button.dataset.value));
}

function bindLibrarySelection() {
  const boxes = [...document.querySelectorAll('.library-track-select input:not(:disabled)')];
  const typeBoxes = [...document.querySelectorAll('.library-export-options input')];
  const all = $('#library-select-all');
  const button = $('#library-download-selected');
  const count = $('#library-selection-count');
  const genreInput = $('#library-genre-value');
  const genreButton = $('#library-change-genre');
  const removeButton = $('#library-remove-selected');
  const reanalyzeButton = $('#library-reanalyze-selected');
  const keyAnalyzeButton = $('#library-key-analyze-selected');
  const refreshSelection = () => {
    const selected = boxes.filter(box => box.checked).length;
    const fileTypes = typeBoxes.filter(box => box.checked).length;
    count.textContent = `${selected} selected`;
    button.disabled = selected === 0 || fileTypes === 0;
    const catalogSelected = boxes.filter(box => box.checked && box.closest('.library-card').dataset.downloadedId).length;
    genreButton.disabled = selected === 0 || catalogSelected !== selected || !genreInput.value.trim();
    removeButton.disabled = selected === 0;
    reanalyzeButton.disabled = selected === 0 || catalogSelected !== selected;
    keyAnalyzeButton.disabled = selected === 0 || catalogSelected !== selected;
    document.querySelector('.library-selection').classList.toggle('has-selection', selected > 0);
    boxes.forEach(box => box.closest('.library-card').classList.toggle('is-selected', box.checked));
    all.checked = boxes.length > 0 && selected === boxes.length;
    all.indeterminate = selected > 0 && selected < boxes.length;
  };
  all.onchange = () => {
    boxes.filter(box => !box.closest('.library-card').hidden).forEach(box => { box.checked = all.checked; });
    refreshSelection();
  };
  boxes.forEach(box => box.onchange = refreshSelection);
  typeBoxes.forEach(box => box.onchange = refreshSelection);
  genreInput.oninput = refreshSelection;
  genreButton.onclick = async () => {
    const selectedCards = boxes.filter(box => box.checked).map(box => box.closest('.library-card'));
    const trackIds = selectedCards.map(card => Number(card.dataset.downloadedId)).filter(Boolean);
    const genre = genreInput.value.trim();
    if (!trackIds.length || trackIds.length !== selectedCards.length || !genre) return;
    if (!await confirmAction(`Move ${trackIds.length} selected track${trackIds.length === 1 ? '' : 's'} to the ${genre} genre folder?`, {title:'Change track genre', acceptLabel:'Move tracks'})) return;
    genreButton.disabled = true; genreButton.textContent = 'Moving…';
    try {
      const response = await fetch('/api/downloaded-library/genre', {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({track_ids:trackIds, genre_category:genre})});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'Could not change genre.');
      genreInput.value = '';
      await Promise.all([loadLibrary(), loadDownloadedLibrary()]);
    } catch (error) { alert(error.message); }
    finally { genreButton.textContent = 'Change genre'; }
  };
  removeButton.onclick = async () => {
    const selectedCards = boxes.filter(box => box.checked).map(box => box.closest('.library-card'));
    if (!selectedCards.length || !await confirmAction(`Remove ${selectedCards.length} selected track${selectedCards.length === 1 ? '' : 's'} and all of their generations from the Library? Exported audio files will remain in the output folder.`, {title:'Remove selected tracks', acceptLabel:'Remove', danger:true})) return;
    removeButton.disabled = true; removeButton.textContent = 'Removing…';
    try {
      for (const card of selectedCards) {
        const response = await fetch(`/api/library/${encodeURIComponent(card.dataset.sourceName)}`, {method:'DELETE'});
        if (!response.ok) throw new Error((await response.json()).detail || `Could not remove ${card.dataset.sourceName}.`);
      }
      await Promise.all([loadLibrary(), loadAnalysis(), loadReports()]);
    } catch (error) { alert(error.message); removeButton.textContent = 'Remove from library'; refreshSelection(); }
  };
  reanalyzeButton.onclick = async () => {
    const selectedCards = boxes.filter(box => box.checked).map(box => box.closest('.library-card'));
    const trackIds = selectedCards.map(card => Number(card.dataset.downloadedId)).filter(Boolean);
    if (!trackIds.length || trackIds.length !== selectedCards.length || !await confirmAction(`Reanalyze ${trackIds.length} selected track${trackIds.length===1?'':'s'}? Audio files, metadata, artwork, and verified keys will be preserved.`, {title:'Reanalyze selected tracks', acceptLabel:'Reanalyze'})) return;
    reanalyzeButton.disabled=true; reanalyzeButton.textContent='Adding to queue…';
    try { const response=await fetch('/api/downloaded-library/reanalyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_ids:trackIds})});const result=await response.json();if(!response.ok)throw new Error(result.detail||'Could not queue reanalysis.');showView('workspace-view');await loadJobs(); }
    catch(error){alert(error.message);reanalyzeButton.textContent='Reanalyze';refreshSelection();}
  };
  keyAnalyzeButton.onclick=()=>{const cards=boxes.filter(box=>box.checked).map(box=>box.closest('.library-card'));const ids=cards.map(card=>Number(card.dataset.downloadedId)).filter(Boolean);startKeyAnalysis(ids,keyAnalyzeButton,async()=>{libraryLoadedAt=0;await Promise.all([loadLibrary(),loadReports()]);});};
  button.onclick = async () => {
    const jobIds = boxes.filter(box => box.checked).map(box => Number(box.value));
    const fileTypes = typeBoxes.filter(box => box.checked).map(box => box.value);
    button.disabled = true; button.textContent = 'Preparing download…';
    try {
      const response = await fetch('/api/library/download', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({job_ids:jobIds, file_types:fileTypes})});
      if (!response.ok) throw new Error((await response.json()).detail || 'Could not prepare download.');
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a'); link.href = url; link.download = 'DJ Library Studio Selected Tracks.zip'; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { alert(error.message); }
    finally { button.textContent = 'Download selected'; refreshSelection(); }
  };
  refreshSelection();
}

async function loadAnalysis(jobs = null) {
  const availableJobs = jobs || await fetch('/api/jobs', {cache:'no-store'}).then(r => r.json());
  const songs = availableJobs.filter(job => job.status === 'complete').slice(0, 4);
  const root = $('#analysis'); root.className = 'analysis-list';
  if (!songs.length) {
    root.className = 'analysis-empty';
    root.innerHTML = '<span class="disc">◉</span><p>Completed tracks will appear here with their BPM, key, and candidate scores.</p>';
    return;
  }
  root.replaceChildren(...songs.map(song => {
    const item = document.createElement('div'); item.className = 'analysis-item';
    const intro = song.intro_quality != null ? `${Math.round(song.intro_quality)}% intro` : 'intro preserved';
    const outro = song.outro_quality != null ? `${Math.round(song.outro_quality)}% outro` : 'outro preserved';
    item.innerHTML = `<strong></strong><p>${Number(song.bpm || 0).toFixed(1)} BPM · <span class="score">${intro}</span> · ${outro}</p>`;
    item.querySelector('strong').textContent = song.source_name; return item;
  }));
}

function pct(value) { return value == null ? '—' : `${Math.round(value)}%`; }
function candidateLabel(candidate) { return candidate ? `${candidate.extension_bars} bars · ${pct(candidate.loop_quality)}` : 'Preserved'; }
function escapeHtml(value) { const node = document.createElement('span'); node.textContent = String(value ?? ''); return node.innerHTML; }
function apiErrorMessage(payload, fallback = 'The request could not be completed.') {
  const detail = payload?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(item => {
    const field = Array.isArray(item?.loc) ? item.loc.filter(value => value !== 'body').join(' → ') : '';
    return `${field ? `${field}: ` : ''}${item?.msg || 'Invalid value'}`;
  }).join(' · ');
  if (detail && typeof detail === 'object') return detail.message || JSON.stringify(detail);
  return fallback;
}
function fraction(value) { return value == null ? '—' : `${Math.round(100 * value)}%`; }
function reportDate(value) { if (!value) return 'Not processed yet'; return new Date(value).toLocaleString([], {dateStyle:'medium', timeStyle:'short'}); }
function reportJob(song) { return reportJobs.find(item => item.source_name.toLowerCase() === song.source_name.toLowerCase() && item.status === 'complete'); }
function reportHasEdit(song) { return Boolean(song.intro || song.outro || reportJob(song)?.extended_available); }

function reportHealth(song) {
  const grid = Number(song.beat_grid_confidence || 0);
  const key = Number(song.key_confidence || 0);
  const candidateRisks = [song.intro, song.outro].flatMap(candidate => candidate ? [candidate.buildup_risk, candidate.bass_reset_risk, candidate.resolution_risk, candidate.vocal_boundary_risk] : []).map(Number).filter(Number.isFinite);
  const hasEdit = reportHasEdit(song);
  const risk = hasEdit ? Math.max(Number(song.tempo_drift || 0), ...candidateRisks, 0) : 0;
  const introBars = Number(song.dj_readiness?.intro_mixable_bars || 0);
  const outroBars = Number(song.dj_readiness?.outro_mixable_bars || 0);
  const flags = {
    grid: !song.bpm || grid < .6,
    key: !song.key || key < .5,
    risk: hasEdit && (risk > .45 || Number(song.tempo_drift || 0) > .08),
    slow: Number(song.processing_seconds || 0) > 90,
  };
  const attention = Object.values(flags).some(Boolean);
  const downbeat = Number.isFinite(Number(song.downbeat_continuity)) ? Number(song.downbeat_continuity) : grid;
  const timingStability = Math.max(0, Math.min(1, 1 - (Number(song.tempo_drift || 0) / .12)));
  const analysisConfidence = Math.max(0, Math.min(1, grid * .35 + key * .30 + downbeat * .20 + timingStability * .15));
  const candidateScores = [song.intro, song.outro].filter(Boolean).map(candidate => {
    const values = [candidate.loop_quality, candidate.transition_quality, candidate.phrase_suitability].map(Number).filter(Number.isFinite).map(value => value > 1 ? value / 100 : value);
    return values.length ? values.reduce((total, value) => total + value, 0) / values.length : 0;
  });
  const naturalMixability = (Math.min(introBars, 16) + Math.min(outroBars, 16)) / 32;
  const editMixability = candidateScores.length ? candidateScores.reduce((total, value) => total + value, 0) / candidateScores.length : 0;
  const mixability = Math.max(naturalMixability, editMixability);
  const labels = [flags.grid && 'Low beat grid', flags.key && 'Low key confidence', flags.risk && 'High risk', flags.slow && 'Slow analysis'].filter(Boolean);
  return {flags, attention, analysisConfidence, risk, mixability, labels, healthy: !attention && analysisConfidence >= .65, mixReady: mixability >= .65, hasEdit};
}

function reportTrackType(song) {
  if (song.intro && song.outro) return 'Intro + outro edit';
  if (song.intro) return 'Intro edit';
  if (song.outro) return 'Outro edit';
  if (reportHasEdit(song)) return 'Generated edit';
  return 'Original analyzed';
}

function reportFeedbackPanel(song) {
  const entries = reportFeedback.filter(item => item.source_name.toLowerCase() === song.source_name.toLowerCase());
  const history = entries.slice(0, 4).map(item => `<li><strong>${item.accepted ? 'Works' : 'Needs work'} · ${escapeHtml(item.position)}</strong><span>${escapeHtml(item.tags || 'no tags')} · ${reportDate(item.created_at)}</span>${item.notes ? `<p>${escapeHtml(item.notes)}</p>` : ''}</li>`).join('');
  return `<section class="report-feedback"><div><h3>Listening feedback</h3><p>Teach future ranking what worked or sounded wrong.</p></div><form data-source="${escapeHtml(song.source_name)}"><select name="position" aria-label="Feedback area"><option value="overall">Overall edit</option><option value="intro">Intro</option><option value="outro">Outro</option></select><select name="accepted" aria-label="Feedback decision"><option value="true">Works well</option><option value="false">Needs work</option></select><input name="tags" placeholder="Tags: smooth, chopped, vocal…"><textarea name="notes" placeholder="What did you hear? Be specific about the transition or musical flow."></textarea><button type="submit">Save feedback</button><span class="feedback-message"></span></form>${history ? `<details class="feedback-history-wrap"><summary>${entries.length} saved listening decision${entries.length === 1 ? '' : 's'}</summary><ul class="feedback-history">${history}</ul></details>` : '<p class="no-feedback">No listening feedback saved for this track yet.</p>'}</section>`;
}

function reportKeyReviewPanel(song) {
  const keys = ['C major','C# major','D major','D# major','E major','F major','F# major','G major','G# major','A major','A# major','B major','C minor','C# minor','D minor','D# minor','E minor','F minor','F# minor','G minor','G# minor','A minor','A# minor','B minor'];
  const selected = song.key_verification?.verified_key || song.key || '';
  const candidates = (song.key_candidates || []).map(candidate => `<button type="button" class="key-candidate-choice" data-key="${escapeHtml(candidate.key)}">${escapeHtml(candidate.key)} · ${Math.round(Number(candidate.confidence || 0))}%</button>`).join('');
  const trackId=reportJob(song)?.downloaded_track_id;
  return `<section class="key-review-panel"><div><h3>Verify musical key</h3><p>${song.key_verified ? `Manually verified · analyzer originally selected ${escapeHtml(song.detected_key || '—')}` : 'Confirm or correct the analysis. Verified keys are protected from future reanalysis.'}</p></div>${trackId?`<button type="button" class="button secondary report-analyze-key" data-track-id="${trackId}">Analyze key only</button>`:''}<form data-source="${escapeHtml(song.source_name)}" data-detected="${escapeHtml(song.detected_key || song.key || '')}"><div class="key-review-candidates">${candidates}</div><select name="verified_key" aria-label="Verified musical key">${keys.map(key => `<option value="${key}" ${key===selected?'selected':''}>${key}</option>`).join('')}</select><input name="notes" value="${escapeHtml(song.key_verification?.notes || '')}" placeholder="Optional verification notes"><button type="submit">${song.key_verified ? 'Update verified key' : 'Verify key'}</button>${song.key_verified ? '<button type="button" class="secondary clear-key-verification">Remove verification</button>' : ''}<span class="key-review-message"></span></form></section>`;
}

function bindReportFeedback() {
  document.querySelectorAll('.report-analyze-key:not([data-bound])').forEach(button=>{button.dataset.bound='true';button.onclick=()=>startKeyAnalysis([Number(button.dataset.trackId)],button,loadReports);});
  document.querySelectorAll('.report-feedback form:not([data-bound])').forEach(form => {
    form.dataset.bound = 'true';
    form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('button'); const message = form.querySelector('.feedback-message');
    button.disabled = true; message.textContent = 'Saving…';
    const response = await fetch('/api/report-feedback', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({source_name:form.dataset.source, position:form.elements.position.value, accepted:form.elements.accepted.value === 'true', tags:form.elements.tags.value, notes:form.elements.notes.value})});
    button.disabled = false;
    if (!response.ok) { message.textContent = (await response.json()).detail || 'Could not save feedback.'; return; }
    message.textContent = 'Feedback saved'; await loadReports();
    });
  });
  document.querySelectorAll('.key-review-panel form:not([data-bound])').forEach(form => {
    form.dataset.bound = 'true';
    form.querySelectorAll('.key-candidate-choice').forEach(button => button.onclick = () => { form.elements.verified_key.value = button.dataset.key; });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const message = form.querySelector('.key-review-message'); message.textContent = 'Saving…';
      const song = reportSongs.find(item => item.source_name === form.dataset.source);
      const response = await fetch(`/api/key-verifications/${encodeURIComponent(form.dataset.source)}`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({source_name:form.dataset.source, verified_key:form.elements.verified_key.value, detected_key:form.dataset.detected, candidates:song?.key_candidates || [], notes:form.elements.notes.value})});
      if (!response.ok) { message.textContent = (await response.json()).detail || 'Could not verify key.'; return; }
      message.textContent = 'Key verified'; await loadReports();
    });
    const clear = form.querySelector('.clear-key-verification');
    if (clear) clear.onclick = async () => { clear.disabled = true; await fetch(`/api/key-verifications/${encodeURIComponent(form.dataset.source)}`, {method:'DELETE'}); await loadReports(); };
  });
}

function renderReports() {
  reportDetailBodies = new Map();
  const query = $('#report-search').value.trim().toLowerCase();
  const filter = $('#report-filter').value;
  const issue = $('#report-issue').value;
  let songs = reportSongs.filter(song => {
    const matches = [song.source_name, song.detected_style, song.preset, song.key].some(value => String(value || '').toLowerCase().includes(query));
    const extended = reportHasEdit(song);
    const health = reportHealth(song);
    const keyDisagreement = new Set((song.key_candidates || []).map(candidate => candidate.key)).size > 1;
    const issueMatches = issue === 'all' || (issue === 'attention' && health.attention) || (issue === 'low-grid' && health.flags.grid) || (issue === 'low-key' && health.flags.key) || (issue === 'key-missing' && !song.key) || (issue === 'key-disagreement' && keyDisagreement && !song.key_verified) || (issue === 'key-verified' && song.key_verified) || (issue === 'key-review' && !song.key_verified && (health.flags.key || keyDisagreement)) || (issue === 'high-risk' && health.flags.risk) || (issue === 'slow' && health.flags.slow) || (issue === 'healthy' && health.healthy) || (issue === 'mix-ready' && health.mixReady);
    return matches && issueMatches && (filter === 'all' || (filter === 'extended' ? extended : !extended));
  });
  const sort = $('#report-sort').value;
  if (sort === 'name') songs.sort((a,b) => a.source_name.localeCompare(b.source_name));
  if (sort === 'recent') songs.sort((a,b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')));
  if (sort === 'bpm') songs.sort((a,b) => Number(b.bpm || 0) - Number(a.bpm || 0));
  if (sort === 'quality') songs.sort((a,b) => Math.max(b.intro?.loop_quality || 0,b.outro?.loop_quality || 0)-Math.max(a.intro?.loop_quality || 0,a.outro?.loop_quality || 0));
  const filteredTotal = songs.length;
  const totalPages = Math.max(1, Math.ceil(filteredTotal / reportPageSize));
  reportPage = Math.min(Math.max(1, reportPage), totalPages);
  const pageStart = (reportPage - 1) * reportPageSize;
  const pageSongs = songs.slice(pageStart, pageStart + reportPageSize);
  const cards = pageSongs.map((song, pageIndex) => {
    const reportIndex = pageStart + pageIndex;
    const intro = song.intro; const outro = song.outro;
    const side = (name, value, reason, fallback) => `<div class="candidate-detail"><h3>${name}</h3>${value ? `<div class="metric-grid"><p><b>${clock(value.source_start)}–${clock(value.source_end)}</b><span>Source material</span></p><p><b>${clock(value.output_start)}–${clock(value.output_end)}</b><span>Extended placement</span></p><p><b>${value.unit_bars} / ${value.extension_bars}</b><span>Unique / added bars</span></p><p><b>${value.copies}</b><span>Copies</span></p></div><p>Phrase <b>${pct(value.phrase_suitability)}</b> · Loop <b>${pct(value.loop_quality)}</b> · Transition <b>${pct(value.transition_quality)}</b> · Instrumental <b>${fraction(value.instrumentalness)}</b></p><p>Section <b>${escapeHtml(value.section)}</b> (${fraction(value.section_confidence)}) · arrangement fit ${fraction(value.arrangement_fit)} · energy ${escapeHtml(value.energy)}</p><p>Regional behavior <b>${escapeHtml(value.regional_style || 'unknown')}</b> · opening/ending match ${fraction(value.regional_compatibility)} · regional boundary risk ${fraction(value.regional_boundary_risk)}</p><p>Context ${fraction(value.context_match)} · chord return ${fraction(value.chord_return)} · local grid ${fraction(value.local_grid)} · boundary grid ${fraction(value.boundary_grid)}</p><p>Risks: buildup ${fraction(value.buildup_risk)} · bass reset ${fraction(value.bass_reset_risk)} · harmonic resolution ${fraction(value.resolution_risk)} · vocal boundary ${fraction(value.vocal_boundary_risk)}</p><p>Built with <b>${escapeHtml(value.construction)}</b> · ${escapeHtml(value.splice_mode)} splice${fallback ? ` · fallback: ${escapeHtml(fallback)}` : ''}</p>` : `<p>Original ${name.toLowerCase()} preserved.</p><p>${escapeHtml(reason || 'No extension was necessary.')}</p>`}</div>`;
    const job = reportJob(song);
    const listening = job ? `<div class="report-audio"><span>Listen</span>${job.wav_available ? `<audio controls preload="none" src="/api/jobs/${job.id}/audio/wav"></audio>` : ''}${job.extended_available ? `<audio controls preload="none" src="/api/jobs/${job.id}/audio/extended"></audio>` : ''}</div>` : '';
    const preview = job && (job.extended_available || job.wav_available) ? `<audio class="report-row-audio" controls preload="none" aria-label="Preview ${escapeHtml(song.source_name)}" src="/api/jobs/${job.id}/audio/${job.extended_available ? 'extended' : 'wav'}"></audio>` : `<span class="report-no-preview">${job ? 'Audio file unavailable' : 'Analysis record only'}</span>`;
    const health = reportHealth(song);
    const trackType = reportTrackType(song);
    const healthBadge = health.attention ? `<span class="report-health-badge attention">${health.labels.length} issue${health.labels.length === 1 ? '' : 's'}</span>` : '<span class="report-health-badge ready">Healthy analysis</span>';
    const warningBadges = `${song.key_verified ? '<span class="report-health-badge ready">Key verified</span>' : ''}${health.labels.slice(0, 2).map(label => `<span class="report-issue-badge">${escapeHtml(label)}</span>`).join('')}`;
    const cues = (song.cues || []).map(cue => `<span class="cue-chip">${escapeHtml(cue.name)} · ${clock(cue.start)}</span>`).join('') || '<span class="muted-copy">No exported cues</span>';
    const keyCandidates = (song.key_candidates || []).length > 1 ? `<div class="key-candidate-list"><b>Key candidates</b>${song.key_candidates.map(candidate => `<span class="${candidate.selected ? 'selected' : ''}">${escapeHtml(candidate.key)} · ${Math.round(Number(candidate.confidence || 0))}%${candidate.selected ? ' selected' : ''}</span>`).join('')}</div>` : '';
    const sectionProfiles = (song.section_profiles || []).map(profile => `<article><span>${escapeHtml(profile.name)} · ${clock(profile.start)}–${clock(profile.end)}</span><strong>${escapeHtml(profile.style)}</strong><b>${fraction(profile.confidence)} confidence</b><small>${escapeHtml(profile.reason)}</small></article>`).join('') || '<p class="muted-copy">Reprocess this track to add section-aware classification.</p>';
    const body = `${listening}<section class="analysis-overview"><h3>Track analysis</h3><div class="metric-grid"><p><b>${song.beats ?? '—'} / ${song.bars ?? '—'}</b><span>Beats / bars</span></p><p><b>${fraction(song.beat_grid_confidence)}</b><span>Beat-grid confidence</span></p><p><b>${fraction(song.key_confidence)}</b><span>Key confidence</span></p><p><b>${fraction(song.tempo_drift)}</b><span>Tempo drift</span></p><p><b>${fraction(song.downbeat_continuity)}</b><span>Downbeat continuity</span></p><p><b>${clock(song.duration_seconds)}</b><span>Output duration</span></p><p><b>${clock(song.processing_seconds)}</b><span>Processing time</span></p><p><b>${song.stem_reliability == null ? 'Not used' : fraction(song.stem_reliability)}</b><span>Stem reliability</span></p></div><p><b>Groove:</b> ${escapeHtml(song.groove || '—')} · <b>timing:</b> ${escapeHtml(song.timing || '—')}</p><p><b>Whole-track classification:</b> ${escapeHtml(song.detected_style || '—')} · ${escapeHtml(song.preset_reason || 'No classifier explanation')}</p><div class="section-profile-grid">${sectionProfiles}</div><p><b>Existing DJ room:</b> intro ${song.dj_readiness?.intro_mixable_bars ?? 0} bars · outro ${song.dj_readiness?.outro_mixable_bars ?? 0} bars · <b>cues:</b> mix in ${clock(song.mix_in)} · mix out ${clock(song.mix_out)}</p><p><b>Analysis cache:</b> track ${song.cache?.track_analysis ? 'hit' : 'fresh'} · vocals ${song.cache?.vocal_analysis ? 'hit' : 'fresh'}</p><div class="cue-list">${cues}</div></section><div class="report-detail">${side('Intro', intro, song.intro_disabled_reason, song.intro_fallback)}${side('Outro', outro, song.outro_disabled_reason, song.outro_fallback)}</div>${reportFeedbackPanel(song)}`;
    const keyReview = reportKeyReviewPanel(song);
    const enrichedBody = body.replace('<p><b>Groove:</b>', `${keyCandidates}<p><b>Groove:</b>`).replace('</section><div class="report-detail">', `</section>${keyReview}<div class="report-detail">`);
    reportDetailBodies.set(String(reportIndex), enrichedBody);
    return `<details class="report-card ${health.attention ? 'has-attention' : 'is-ready'}" data-report-index="${reportIndex}"><summary><div class="report-name"><strong>${escapeHtml(song.source_name)}</strong><small>${escapeHtml(song.detected_style || 'Unclassified')} · ${escapeHtml(song.preset || 'default')} · ${reportDate(song.updated_at)}</small><span class="report-row-issues"><span class="report-type-badge ${health.hasEdit ? 'edited' : ''}">${trackType}</span>${healthBadge}${warningBadges}</span></div><div class="report-pair"><div class="report-metric"><strong>${Number(song.bpm || 0).toFixed(1)}</strong><small>BPM</small></div><div class="report-metric"><strong>${escapeHtml(song.key || '—')}</strong><small>Key</small></div></div><div class="report-meter"><span><b>Analysis confidence</b><strong>${fraction(health.analysisConfidence)}</strong></span><i><em style="width:${Math.round(health.analysisConfidence * 100)}%"></em></i></div><div class="report-meter"><span><b>DJ mixability</b><strong>${fraction(health.mixability)}</strong></span><i><em style="width:${Math.round(health.mixability * 100)}%"></em></i></div><div class="report-preview">${preview}</div><span class="report-expand" aria-hidden="true">⌄</span></summary><div class="report-body" hidden></div></details>`;
  });
  $('#report-cards').innerHTML = cards.length ? cards.join('') : '<div class="empty">No tracks match this view.</div>';
  const first = filteredTotal ? pageStart + 1 : 0;
  const last = Math.min(pageStart + reportPageSize, filteredTotal);
  $('#report-result-count').textContent = `Showing ${first}–${last} of ${filteredTotal} matching tracks · ${reportSongs.length} analyzed total`;
  const changePage = page => { reportPage = Math.min(Math.max(1, page), totalPages); renderReports(); $('#diagnostics-heading').scrollIntoView({behavior:'smooth',block:'start'}); };
  renderTrackPagination($('#report-pagination-top'), reportPage, totalPages, filteredTotal, changePage);
  renderTrackPagination($('#report-pagination'), reportPage, totalPages, filteredTotal, changePage);
  document.querySelectorAll('.report-card').forEach(card => card.addEventListener('toggle', () => {
    if (!card.open) return;
    document.querySelectorAll('.report-card[open]').forEach(other => { if (other !== card) other.open = false; });
    const body = card.querySelector('.report-body');
    if (!body.dataset.hydrated) { body.innerHTML = reportDetailBodies.get(card.dataset.reportIndex) || ''; body.dataset.hydrated = 'true'; bindReportFeedback(); }
    body.hidden = false;
  }));
  document.querySelectorAll('.report-row-audio').forEach(audio => ['click','pointerdown','keydown'].forEach(name => audio.addEventListener(name, event => event.stopPropagation())));
}

function clock(seconds) { if (seconds == null) return '—'; const total = Math.max(0, Math.round(seconds)); return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`; }

async function loadReports() {
  const [report, analytics, jobs, feedback, keyStats] = await Promise.all([fetch('/api/report').then(r => r.json()), fetch('/api/analytics').then(r => r.json()), fetch('/api/report-audio-index').then(r => r.json()), fetch('/api/report-feedback').then(r => r.json()), fetch('/api/key-verifications').then(r => r.json())]);
  reportSongs = Object.values(report.songs || {}).filter(song => song.status !== 'removed').reverse();
  reportKeyVerificationStats = keyStats;
  const verificationMap = new Map((keyStats.items || []).map(item => [item.source_name.toLowerCase(), item]));
  reportJobs = jobs;
  const keyRuns=new Map(jobs.filter(job=>job.key_analyzed_at).map(job=>[job.source_name.toLowerCase(),job]));
  reportSongs.forEach(song => { const run=keyRuns.get(song.source_name.toLowerCase());if(run){song.key=run.detected_key;song.key_confidence=Number(run.key_confidence||0)/100;song.key_analyzed_at=run.key_analyzed_at;}const verification = verificationMap.get(song.source_name.toLowerCase()); song.detected_key = song.key; song.key_verification = verification || null; song.key_verified = Boolean(verification); if (verification) { song.key = verification.verified_key; song.key_confidence = 1; } });
  reportFeedback = feedback;
  const averageFraction = values => values.length ? `${Math.round(100 * values.reduce((a,b) => a + b, 0) / values.length)}%` : '—';
  const gridConfidence = reportSongs.filter(song => song.beat_grid_confidence != null).map(song => Number(song.beat_grid_confidence)).filter(Number.isFinite);
  const keyConfidence = reportSongs.filter(song => song.key_confidence != null).map(song => Number(song.key_confidence)).filter(Number.isFinite);
  const needsAttention = reportSongs.filter(song => !song.bpm || !song.key || Number(song.beat_grid_confidence || 0) < .6 || Number(song.key_confidence || 0) < .5 || Number(song.tempo_drift || 0) > .08).length;
  const cards = [[reportSongs.length, 'Analyzed tracks'], [averageFraction(gridConfidence), 'Average beat-grid confidence'], [averageFraction(keyConfidence), 'Average key confidence'], [needsAttention, 'Need attention']];
  $('#report-summary').innerHTML = cards.map(([value, label]) => `<div class="stat-card"><strong>${value}</strong><span>${label}</span></div>`).join('');
  const rate = analytics.acceptance_rate == null ? '—' : `${Math.round(analytics.acceptance_rate*100)}%`;
  const detectorAccuracy = Object.entries(keyStats.detector_accuracy || {}).map(([name,value]) => `${name} ${value.correct}/${value.total}`).join(' · ');
  $('#feedback-analytics').innerHTML = `<div><strong>${rate}</strong><span> feedback acceptance</span></div><div><strong>${analytics.feedback_count}</strong><span> listening decisions</span></div><div><strong>${keyStats.total || 0}</strong><span> manually verified keys</span></div><div class="tag-cloud">${detectorAccuracy ? `<span>${escapeHtml(detectorAccuracy)}</span>` : '<span>Verify keys to measure detector accuracy</span>'}</div>`;
  renderReports();
}
const resetAndRenderReports = () => { reportPage = 1; renderReports(); };
$('#report-search').addEventListener('input', resetAndRenderReports);
$('#report-issue').addEventListener('change', resetAndRenderReports);
$('#report-filter').addEventListener('change', resetAndRenderReports);
$('#report-sort').addEventListener('change', resetAndRenderReports);
$('#report-page-size').addEventListener('change', event => { reportPageSize = Number(event.target.value) || 50; resetAndRenderReports(); });

$('#settings-form').addEventListener('submit', async event => {
  event.preventDefault();
  const values = {
    music_library_path: $('#setting-library-path').value.trim(),
    preset: $('#setting-preset').value, intro_bars: Number($('#setting-intro').value),
    outro_bars: Number($('#setting-outro').value), use_stems: $('#setting-stems').checked,
    auto_bars: $('#setting-auto-bars').checked,
    minimum_intro_loop_quality: Number($('#setting-intro-quality').value),
    minimum_outro_loop_quality: Number($('#setting-outro-quality').value),
    pcm_bits: Number($('#setting-bits').value), preview_seconds: Number($('#setting-preview').value),
    export_cues: $('#setting-cues').checked,
    maximum_repetitions: Number($('#setting-repetitions').value),
    crossfade_ms: Number($('#setting-crossfade').value),
    candidate_count: Number($('#setting-candidate-count').value),
    intro_search_seconds: Number($('#setting-intro-search').value),
    outro_search_seconds: Number($('#setting-outro-search').value),
    maximum_vocal_coverage_percent: Number($('#setting-vocal-coverage').value),
    maximum_vocal_boundary_risk_percent: Number($('#setting-vocal-risk').value),
    maximum_buildup_risk_percent: Number($('#setting-buildup-risk').value),
    maximum_bass_reset_risk_percent: Number($('#setting-bass-risk').value),
    minimum_stem_reliability_percent: Number($('#setting-stem-reliability').value),
  };
  const response = await fetch('/api/settings', { method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(values) });
  const payload = await response.json();
  if (!response.ok) { $('#settings-message').textContent = apiErrorMessage(payload, 'Could not save settings.'); return; }
  const pageSize = $('#setting-page-size').value;
  localStorage.setItem('music-files-page-size', pageSize);
  localStorage.setItem('dj-library-page-size', pageSize);
  localStorage.setItem('audioextender-key-view', $('#setting-key-display').value);
  downloadedUiState.pageSize = Number(pageSize);
  if ($('#downloaded-page-size')) $('#downloaded-page-size').value = pageSize;
  if ($('#library-page-size')) $('#library-page-size').value = pageSize;
  if ($('#library-key-display')) $('#library-key-display').value = $('#setting-key-display').value;
  appConfig.effective = payload.effective; appConfig.overrides = payload.overrides;
  applyEffectiveSettings(payload.effective);
  $('#settings-form').classList.remove('is-dirty');
  $('#settings-message').textContent = 'Settings saved · checking the music library…';
  libraryStatusRequest=null;
  const status=await loadLibraryStatus();
  if(status?.online){
    $('#settings-message').textContent=`Music library connected · ${status.available_tracks} of ${status.cataloged_tracks} tracks available at ${status.path}`;
    if(!status.offline_tracks){
      const errors=$('#downloaded-retag-errors');errors.hidden=true;errors.open=false;errors.querySelector('ul')?.replaceChildren();
      $('#downloaded-rescan-message').textContent='Library location verified · all cataloged tracks are available.';
    }
  }else{
    $('#settings-message').textContent=`Settings saved, but this folder is not currently available: ${payload.effective.music_library_path}`;
  }
});

$('#settings-form').addEventListener('input', () => {
  $('#settings-form').classList.add('is-dirty');
  $('#settings-message').textContent = 'Unsaved changes';
});

$('#reset-settings').addEventListener('click', async () => {
  const payload = await fetch('/api/settings', { method:'DELETE' }).then(r => r.json());
  localStorage.setItem('music-files-page-size', '50'); localStorage.setItem('dj-library-page-size', '50');
  localStorage.setItem('audioextender-key-view', 'both'); downloadedUiState.pageSize = 50;
  appConfig.effective = payload.effective; appConfig.overrides = {};
  applyEffectiveSettings(payload.effective); $('#settings-form').classList.remove('is-dirty'); $('#settings-message').textContent = 'Application defaults restored.';
});

let relocationPollTimer = null;
let libraryStatusRequest = null;
const formatBytes = value => { const units=['B','KB','MB','GB','TB']; let amount=Number(value||0),index=0; while(amount>=1024&&index<units.length-1){amount/=1024;index++;} return `${amount.toFixed(index?1:0)} ${units[index]}`; };
function renderAudioQualitySummary(summary={}) {
  const analyzed=Number(summary.analyzed||0),total=Number(summary.total||0),average=Number(summary.average_score||0);
  $('#quality-average').textContent=analyzed?`${Math.round(average)}/100`:'—';
  $('#quality-coverage').textContent=`${analyzed} of ${total} tracks analyzed`;
  $('#quality-excellent').textContent=Number(summary.excellent||0);
  $('#quality-good').textContent=Number(summary.good||0);
  $('#quality-review').textContent=Number(summary.review||0)+Number(summary.poor||0);
}
async function loadLibraryStatus() {
  if(libraryStatusRequest)return libraryStatusRequest;
  libraryStatusRequest=(async()=>{
  try {
    const status=await fetch('/api/settings/library-status',{cache:'no-store'}).then(response=>response.json());
    $('#relocation-current-path').textContent=status.path||'—';
    $('#relocation-current-detail').textContent=`${status.available_tracks} of ${status.cataloged_tracks} tracks available${status.offline_tracks?` · ${status.offline_tracks} offline`:''}`;
    $('#library-song-storage').textContent=formatBytes(status.song_bytes);
    $('#library-song-storage-detail').textContent=`${status.available_tracks} available audio file${status.available_tracks===1?'':'s'}`;
    $('#library-support-storage').textContent=formatBytes(status.supporting_bytes);
    $('#library-total-storage').textContent=formatBytes(status.total_bytes);
    $('#library-total-storage-detail').textContent=`${status.file_count||0} managed file${status.file_count===1?'':'s'}`;
    $('#library-free-storage').textContent=formatBytes(status.free_bytes);
    $('#library-free-storage-detail').textContent=status.capacity_bytes?`of ${formatBytes(status.capacity_bytes)} drive capacity`:'Drive capacity unavailable';
    renderAudioQualitySummary(status.audio_quality);
    const integrity=status.location_integrity||{};const locationPanel=$('#library-location-integrity');const outside=Number(integrity.outside_count||0);locationPanel.hidden=!outside;$('#library-location-message').textContent=outside?`${outside} track${outside===1?' is':'s are'} stored outside ${integrity.configured_root}. Copy, verify, relink, then remove the old files.`:'';
    const badge=$('#library-online-state');badge.textContent=status.online?'Library online':'Library offline';badge.className=`library-state ${status.online?'online':'offline'}`;
    $('#library-offline-banner').hidden=status.online;document.body.classList.toggle('library-is-offline',!status.online);
    return status;
  } catch { $('#library-online-state').textContent='Status unavailable'; return null; }
  finally { libraryStatusRequest=null; }
  })();
  return libraryStatusRequest;
}
async function pollLibraryConsolidation(batchId){const button=$('#library-consolidate');const response=await fetch(`/api/settings/library-locations/consolidate/${batchId}`,{cache:'no-store'});const batch=await response.json();if(!response.ok){button.disabled=false;button.textContent=batch.detail||'Consolidation failed';return;}button.textContent=`Verified ${batch.processed}/${batch.total}`;if(batch.status==='processing'){setTimeout(()=>pollLibraryConsolidation(batchId),800);return;}button.disabled=false;button.textContent=batch.failed?`${batch.moved} moved · ${batch.failed} failed`:'Consolidation complete';downloadedLoadedAt=0;libraryLoadedAt=0;await Promise.all([loadLibraryStatus(),loadDownloadedLibrary(),loadLibrary()]);}
$('#library-consolidate').addEventListener('click',async()=>{const button=$('#library-consolidate');if(!confirm('Copy every out-of-library track to the configured library, verify its SHA-256 checksum, relink catalog and analysis records, then remove the original file?'))return;button.disabled=true;button.textContent='Preparing…';const response=await fetch('/api/settings/library-locations/consolidate',{method:'POST'});const batch=await response.json();if(!response.ok){button.disabled=false;button.textContent=batch.detail||'Could not consolidate';return;}if(batch.batch_id)pollLibraryConsolidation(batch.batch_id);else{button.disabled=false;button.textContent='Nothing to consolidate';await loadLibraryStatus();}});
let qualityScanTimer=null;
async function pollAudioQualityScan(batchId){
  const batch=await fetch(`/api/downloaded-library/audio-quality/${batchId}`,{cache:'no-store'}).then(response=>response.json());
  const panel=$('#quality-scan-progress'),total=Math.max(1,Number(batch.total||0));panel.hidden=false;
  $('#quality-scan-bar').value=100*Number(batch.processed||0)/total;
  $('#quality-scan-message').textContent=batch.status==='complete'?`Complete · ${batch.processed} analyzed${batch.failed?` · ${batch.failed} unavailable`:''}`:`${batch.processed} of ${batch.total} · ${batch.current||'Preparing…'}`;
  $('#scan-audio-quality').disabled=batch.status==='processing';$('#scan-audio-quality').textContent=batch.status==='processing'?'Analyzing…':'Analyze audio quality';
  if(batch.summary)renderAudioQualitySummary(batch.summary);
  if(batch.status==='processing'){clearTimeout(qualityScanTimer);qualityScanTimer=setTimeout(()=>pollAudioQualityScan(batchId),900);}else{downloadedLoadedAt=0;await loadLibraryStatus();}
}
$('#scan-audio-quality').addEventListener('click',async()=>{const button=$('#scan-audio-quality');button.disabled=true;button.textContent='Starting…';const response=await fetch('/api/downloaded-library/audio-quality',{method:'POST'});const batch=await response.json();if(!response.ok){button.disabled=false;button.textContent='Analyze audio quality';$('#quality-scan-message').textContent=batch.detail||'Could not start quality analysis.';return;}pollAudioQualityScan(batch.batch_id);});
fetch('/api/downloaded-library/audio-quality-latest',{cache:'no-store'}).then(response=>response.json()).then(batch=>{if(batch.summary)renderAudioQualitySummary(batch.summary);if(batch.status==='processing')pollAudioQualityScan(batch.batch_id);}).catch(()=>{});
function renderRelocationState(state) {
  if(!state?.status){resetRelocationUi();return;}
  const panel=$('#relocation-progress');panel.hidden=false;panel.classList.toggle('complete',state.status==='complete');panel.classList.toggle('failed',['failed','canceled'].includes(state.status));
  $('#relocation-stage').textContent=state.stage||state.status;$('#relocation-percent').textContent=`${Math.round(Number(state.progress||0))}%`;$('#relocation-progress-bar').value=Number(state.progress||0);
  $('#relocation-detail').textContent=state.error||`${state.processed||0}${state.total?` of ${state.total}`:''}${state.original_retained?' · Original library retained':''}`;
  $('#relocation-start').hidden=!['planned','failed','canceled'].includes(state.status);$('#relocation-cancel').hidden=state.status!=='processing';
  $('#relocation-rollback').hidden=!(state.status==='complete'&&state.database_backup);
  if(state.status==='processing'){clearTimeout(relocationPollTimer);relocationPollTimer=setTimeout(loadRelocationState,750);}else if(state.status==='complete'){loadLibraryStatus();loadConfig();downloadedLoadedAt=0;libraryLoadedAt=0;}
}
function resetRelocationUi(){clearTimeout(relocationPollTimer);$('#relocation-progress').hidden=true;$('#relocation-plan-summary').hidden=true;$('#relocation-plan-summary').replaceChildren();$('#relocation-stage').textContent='Preparing…';$('#relocation-percent').textContent='0%';$('#relocation-progress-bar').value=0;$('#relocation-detail').textContent='';$('#relocation-start').hidden=false;$('#relocation-cancel').hidden=false;$('#relocation-rollback').hidden=true;}
async function loadRelocationState(){try{const response=await fetch('/api/settings/library-relocation',{cache:'no-store'});if(!response.ok)return;const state=await response.json();if(state.status==='canceled'){await fetch('/api/settings/library-relocation',{method:'DELETE'});resetRelocationUi();return;}renderRelocationState(state);}catch{} }
$('#library-relocation-form').addEventListener('submit',async event=>{
  event.preventDefault();const button=$('#relocation-plan');button.disabled=true;button.textContent='Checking…';
  const response=await fetch('/api/settings/library-relocation/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({destination:$('#relocation-destination').value.trim(),mode:$('#relocation-mode').value,verification:$('#relocation-verification').value})});
  const plan=await response.json();button.disabled=false;button.textContent='Review plan';
  if(!response.ok){$('#relocation-plan-summary').hidden=false;$('#relocation-plan-summary').innerHTML=`<b>Cannot continue</b><span>${escapeHtml(plan.detail||'The relocation plan could not be created.')}</span>`;return;}
  const labels={copy:'Copy only · current library remains active',move:'Copy, verify, and activate destination',relink:'Relink existing files without copying'};
  const summary=$('#relocation-plan-summary');summary.hidden=false;summary.innerHTML=`<span><b>${escapeHtml(labels[plan.mode])}</b></span><span>${plan.track_count} cataloged tracks</span><span>${plan.file_count} files</span><span>${formatBytes(plan.total_bytes)}</span><span>${plan.verification==='full'?'Full content verification':'Fast verification'}</span>${plan.missing_source_tracks?`<span>${plan.missing_source_tracks} source tracks already missing</span>`:''}`;
  renderRelocationState(plan);
});
$('#relocation-start').addEventListener('click',async()=>{
  const response=await fetch('/api/settings/library-relocation/start',{method:'POST'});const state=await response.json();if(!response.ok){renderRelocationState({status:'failed',stage:'Could not start',error:state.detail});return;}renderRelocationState(state);
});
$('#relocation-cancel').addEventListener('click',async()=>renderRelocationState(await fetch('/api/settings/library-relocation/cancel',{method:'POST'}).then(response=>response.json())));
$('#relocation-rollback').addEventListener('click',async()=>{if(!await confirmAction('Restore the catalog and settings to the original library? The copied destination will be kept.', {title:'Roll back relocation', acceptLabel:'Restore catalog', danger:true}))return;const response=await fetch('/api/settings/library-relocation/rollback',{method:'POST'});const state=await response.json();renderRelocationState(response.ok?state:{status:'failed',stage:'Rollback failed',error:state.detail});await loadLibraryStatus();await loadConfig();});

let pendingBackupToken='';
function backupHistoryMarkup(backups){
  if(!backups.length)return '<p class="empty">No recovery backups have been created yet.</p>';
  return backups.map(item=>`<article class="backup-history-row ${item.valid?'':'invalid'}"><div><strong>${escapeHtml(item.filename)}</strong><span>${item.valid?`${reportDate(item.created_at)} · ${item.track_count||0} tracks · ${item.file_count||0} protected files`:'Validation failed'}</span></div><b>${formatBytes(item.size)}</b>${item.valid?`<a class="button secondary" href="/api/settings/backups/${encodeURIComponent(item.filename)}/download">Download</a>`:'<span>Do not restore</span>'}</article>`).join('');
}
async function loadBackups(){
  const root=$('#backup-history');if(!root)return;
  try{const response=await fetch('/api/settings/backups',{cache:'no-store'});const payload=await response.json();if(!response.ok)throw new Error(payload.detail||'Backups could not be loaded.');$('#backup-directory').textContent=payload.directory||'';root.innerHTML=backupHistoryMarkup(payload.backups||[]);}catch(error){root.innerHTML=`<p class="empty">${escapeHtml(error.message)}</p>`;}
}
$('#refresh-backups').addEventListener('click',loadBackups);
$('#create-backup').addEventListener('click',async()=>{
  const button=$('#create-backup');button.disabled=true;button.textContent='Creating & validating…';$('#backup-message').textContent='Taking a consistent database snapshot and checking every protected file.';
  try{const response=await fetch('/api/settings/backups',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({include_analysis_cache:$('#backup-include-cache').checked,retention:Number($('#backup-retention').value)})});const result=await response.json();if(!response.ok)throw new Error(result.detail||'Backup could not be created.');$('#backup-message').innerHTML=`Backup verified · ${result.track_count} tracks · ${formatBytes(result.size)} · <a href="${escapeHtml(result.download_url)}">Download a copy</a>`;await loadBackups();}catch(error){$('#backup-message').textContent=error.message;}finally{button.disabled=false;button.textContent='Create backup';}
});
$('#backup-restore-file').addEventListener('change',async event=>{
  const file=event.target.files?.[0],preview=$('#backup-restore-preview');pendingBackupToken='';if(!file){preview.hidden=true;return;}preview.hidden=false;preview.innerHTML='<p>Uploading and validating every protected file…</p>';
  const body=new FormData();body.append('file',file);
  try{const response=await fetch('/api/settings/backups/preview',{method:'POST',body});const result=await response.json();if(!response.ok)throw new Error(result.detail||'Backup validation failed.');pendingBackupToken=result.token;const difference=Number(result.track_difference||0);preview.innerHTML=`<div class="backup-preview-summary"><strong>Valid recovery backup</strong><span>${reportDate(result.created_at)} · ${result.track_count} tracks · ${result.file_count} files · ${formatBytes(result.size)}</span><small>Original library: ${escapeHtml(result.library_path||'Unknown')}</small><small>${difference===0?'Same catalog size as today':difference>0?`${difference} more tracks than the current catalog`:`${Math.abs(difference)} fewer tracks than the current catalog`}${result.includes_analysis_cache?' · analysis cache included':' · analysis cache will rebuild as needed'}</small></div><label>Type <b>RESTORE BACKUP</b> to confirm<input class="backup-restore-confirmation" autocomplete="off" spellcheck="false" placeholder="RESTORE BACKUP"></label><button type="button" class="restore-backup" disabled>Restore validated backup</button><p class="backup-restore-message"></p>`;const input=preview.querySelector('input'),button=preview.querySelector('.restore-backup');input.oninput=()=>button.disabled=input.value!=='RESTORE BACKUP';button.onclick=()=>restoreSelectedBackup(button,input,preview.querySelector('.backup-restore-message'));}catch(error){preview.innerHTML=`<p class="backup-error">${escapeHtml(error.message)}</p>`;}
});
async function restoreSelectedBackup(button,input,message){
  if(!pendingBackupToken||input.value!=='RESTORE BACKUP')return;
  button.disabled=true;button.textContent='Creating safety snapshot…';message.textContent='The current state is being backed up before restoration.';
  try{const response=await fetch('/api/settings/backups/restore',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:pendingBackupToken,confirmation:input.value})});const result=await response.json();if(!response.ok)throw new Error(result.detail||'Restore failed.');pendingBackupToken='';message.textContent=`Restore complete. A pre-restore backup was saved as ${result.pre_restore_backup.filename}.`;button.textContent='Restored';await loadConfig();await loadBackups();downloadedLoadedAt=0;libraryLoadedAt=0;}catch(error){message.textContent=error.message;button.disabled=false;button.textContent='Restore validated backup';}
}

let storageManagerRequest=null;
function renderStorageManager(storage){
  $('#storage-manager-summary').innerHTML=`<div><span>Analysis cache</span><strong>${formatBytes(storage.analysis_cache_bytes)}</strong><small>${storage.analysis_cache_files} files</small></div><div><span>Generated output</span><strong>${formatBytes(storage.generated_output_bytes)}</strong><small>${storage.generated_output_files} files</small></div><div class="reclaimable"><span>Safely reclaimable</span><strong>${formatBytes(storage.reclaimable_bytes)}</strong><small>${storage.stale_cache_files} stale cache · ${storage.orphaned_output_files} old output files</small></div>`;
  const cacheButton=$('#clear-stale-cache'),outputButton=$('#clear-orphaned-output');
  cacheButton.disabled=!storage.stale_cache_files;cacheButton.textContent=storage.stale_cache_files?`Clear ${formatBytes(storage.stale_cache_bytes)}`:'No stale cache';
  outputButton.disabled=!storage.orphaned_output_files;outputButton.textContent=storage.orphaned_output_files?`Clear ${formatBytes(storage.orphaned_output_bytes)}`:'No old output';
}
async function loadStorageManager(){
  if(storageManagerRequest)return storageManagerRequest;
  storageManagerRequest=fetch('/api/settings/storage',{cache:'no-store'}).then(async response=>{if(!response.ok)throw new Error('Storage details could not be loaded.');const storage=await response.json();renderStorageManager(storage);return storage;}).catch(error=>{$('#storage-manager-summary').innerHTML=`<p>${escapeHtml(error.message)}</p>`;}).finally(()=>{storageManagerRequest=null;});
  return storageManagerRequest;
}
async function cleanManagedStorage(target,label){
  if(!await confirmAction(`Remove ${label}? Your songs, catalog metadata, and current analysis will be preserved.`, {title:'Clean application storage', acceptLabel:'Remove files', danger:true}))return;
  const button=target==='stale-cache'?$('#clear-stale-cache'):$('#clear-orphaned-output');button.disabled=true;button.textContent='Cleaning…';$('#storage-manager-message').textContent='';
  const response=await fetch('/api/settings/storage/cleanup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target})});const payload=await response.json();
  if(!response.ok){$('#storage-manager-message').textContent=payload.detail||'Storage cleanup failed.';await loadStorageManager();return;}
  renderStorageManager(payload.storage);$('#storage-manager-message').textContent=`Removed ${payload.removed_files} files and reclaimed ${formatBytes(payload.removed_bytes)}.`;
}
$('#clear-stale-cache').addEventListener('click',()=>cleanManagedStorage('stale-cache','stale analysis cache files'));
$('#clear-orphaned-output').addEventListener('click',()=>cleanManagedStorage('orphaned-output','old generated output files'));

const cleanupConfirmation = $('#cleanup-confirmation');
const cleanupButton = $('#cleanup-application');
cleanupConfirmation.addEventListener('input', () => {
  cleanupButton.disabled = cleanupConfirmation.value !== 'DELETE EVERYTHING';
  $('#cleanup-message').textContent = '';
});
cleanupButton.addEventListener('click', async () => {
  if (cleanupConfirmation.value !== 'DELETE EVERYTHING') return;
  if (!await confirmAction('This permanently removes every song, edit, track report, cache entry, and processing-history item managed by DJ Library Studio. Your presets and settings will be kept. Continue?', {title:'Remove all managed track data', acceptLabel:'Remove everything', danger:true})) return;
  cleanupButton.disabled = true; cleanupButton.textContent = 'Cleaning up…';
  const response = await fetch('/api/settings/cleanup', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({confirmation:cleanupConfirmation.value})});
  const payload = await response.json();
  if (!response.ok) {
    $('#cleanup-message').textContent = payload.detail || 'The application could not be cleaned up.';
    cleanupButton.textContent = 'Remove all tracks'; cleanupButton.disabled = false; return;
  }
  cleanupConfirmation.value = '';
  $('#cleanup-message').textContent = `Reset complete. Removed ${payload.removed_files || 0} managed files.`;
  cleanupButton.textContent = 'Remove all tracks'; cleanupButton.disabled = true;
  await loadConfig(); await loadPresets(); await Promise.all([loadJobs(), loadAnalysis()]);
});

$('#new-preset').addEventListener('click', () => editPreset());
$('#preset-editor').addEventListener('submit', async event => {
  event.preventDefault();
  const current = $('#preset-original-name').value || '__new__';
  const body = {name:$('#preset-name').value.trim(), intro_bars:Number($('#preset-intro').value), outro_bars:Number($('#preset-outro').value), use_stems:$('#preset-stems').checked, minimum_loop_quality:Number($('#preset-quality').value), maximum_repetitions:Number($('#preset-copies').value)};
  const response = await fetch(`/api/presets/${encodeURIComponent(current)}`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  const payload = await response.json();
  if (!response.ok) { $('#preset-message').textContent = payload.detail || 'Could not save preset.'; return; }
  $('#preset-message').textContent = 'Preset saved.'; await loadConfig(); await loadPresets(); editPreset(presetLibrary.find(preset => preset.name === body.name));
});
$('#delete-preset').addEventListener('click', async () => {
  const name = $('#preset-original-name').value;
  if (!name || name === '__new__' || !await confirmAction(`Remove the ${name} preset? Existing processed generations will keep their saved configuration.`, {title:'Delete preset', acceptLabel:'Delete preset', danger:true})) return;
  const response = await fetch(`/api/presets/${encodeURIComponent(name)}`, {method:'DELETE'});
  if (!response.ok) { $('#preset-message').textContent = (await response.json()).detail || 'Could not remove preset.'; return; }
  await loadConfig(); await loadPresets(); editPreset(presetLibrary[0] || null);
});
$('#restore-presets').addEventListener('click', async () => {
  if (!await confirmAction('Restore every maintained built-in preset and remove all custom preset definitions?', {title:'Restore built-in presets', acceptLabel:'Restore presets', danger:true})) return;
  await fetch('/api/presets/restore', {method:'POST'}); await loadConfig(); await loadPresets(); editPreset(presetLibrary[0] || null);
});

async function refresh() { const jobs = await loadJobs(); await loadAnalysis(jobs); }
loadConfig().then(refresh);loadLibraryStatus();loadRelocationState();
