import {useFrontendServices} from './frontend-services.js';

export const LIBRARY_ROLE_INFO = {
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
export const MUSICAL_PROFILE_VERSION = 1;

export function createLibraryUiState(pageSize = Number(localStorage.getItem('dj-library-page-size') || 50)) {
  return {search:'',role:'all',category:'all',detailedGenre:'all',preset:'all',sort:'newest',result:'all',quality:'all',bpmMin:'',bpmMax:'',key:'all',energy:'all',vocals:'all',timing:'all',page:1,pageSize};
}

export function libraryQuery(state) {
  const parameters=new URLSearchParams({
    page:String(state.page),page_size:String(state.pageSize),search:state.search,
    role:state.role,category:state.category,detailed_genre:state.detailedGenre,
    preset:state.preset,sort:state.sort,result:state.result,quality:state.quality,
    key:state.key,energy:state.energy,vocals:state.vocals,timing:state.timing,
  });
  if(state.bpmMin)parameters.set('bpm_min',state.bpmMin);
  if(state.bpmMax)parameters.set('bpm_max',state.bpmMax);
  return parameters;
}

export function libraryRoles(song) {
  if (Number(song.musical_profile?.version) === MUSICAL_PROFILE_VERSION && Array.isArray(song.musical_profile.roles)) return song.musical_profile.roles;
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

function serializedProfile(value) {
  return value && typeof value === 'object' && Number(value.musical_profile?.version) === MUSICAL_PROFILE_VERSION
    ? value.musical_profile
    : null;
}
export function normalizedKey(value) {
  const profile = serializedProfile(value);
  const key = profile ? profile.key : (value && typeof value === 'object' ? value.key : value);
  return String(key || '').replace(/^Db /,'C# ').replace(/^Eb /,'D# ').replace(/^Gb /,'F# ').replace(/^Ab /,'G# ').replace(/^Bb /,'A# ');
}
export function camelotKey(value) {
  const profile = serializedProfile(value);
  return String(profile?.camelot || CAMELOT_KEYS[normalizedKey(value)] || '—');
}
export function libraryKeyMode() { return localStorage.getItem('audioextender-key-view') || 'both'; }
export function formatLibraryKey(value, mode=libraryKeyMode()) {
  const standard = normalizedKey(value) || 'Unknown key';
  const camelot = camelotKey(value);
  if (mode === 'standard') return standard;
  if (mode === 'camelot') return camelot === '—' ? 'Unknown Camelot' : camelot;
  return camelot === '—' ? standard : `${standard} · ${camelot}`;
}

export function songEnergy(song) {
  if (Number(song.musical_profile?.version) === MUSICAL_PROFILE_VERSION && Number.isFinite(Number(song.musical_profile.energy))) return Number(song.musical_profile.energy);
  if (Number.isFinite(Number(song._energy))) return Number(song._energy);
  const values = (song.section_profiles || []).map(section => Number(String(section.reason || '').match(/energy\s+([\d.]+)/i)?.[1])).filter(Number.isFinite);
  if (values.length) return values.reduce((sum,value) => sum + value, 0) / values.length;
  const style = String(song.detected_style || '').toLowerCase();
  return style.includes('high-energy') || style.includes('peak') ? .8 : style.includes('ambient') || style.includes('sparse') ? .25 : .5;
}
export function energyBand(value) { return value >= .67 ? 'high' : value < .4 ? 'low' : 'medium'; }
export function vocalProfile(song) {
  if (Number(song.musical_profile?.version) === MUSICAL_PROFILE_VERSION && song.musical_profile.vocals) return song.musical_profile.vocals;
  if (song._vocals) return song._vocals;
  const instrumental = Math.max(Number(song.intro?.instrumentalness || 0), Number(song.outro?.instrumentalness || 0));
  return instrumental >= .72 ? 'vocal-safe' : instrumental < .45 ? 'vocal-forward' : 'mixed';
}
export function timingProfile(song) {
  if (Number(song.musical_profile?.version) === MUSICAL_PROFILE_VERSION && song.musical_profile.timing) return song.musical_profile.timing;
  if (song._timing) return song._timing;
  const timing = String(song.timing || '').toLowerCase();
  return timing.includes('live') || timing.includes('variable') || Number(song.tempo_drift || 0) >= .08 ? 'variable' : 'steady';
}
export function effectivePreset(song, job) {
  const analyzed = String(song.preset || '');
  const resolved = analyzed.includes('→') ? analyzed.split('→').at(-1).trim() : analyzed.trim();
  return String(resolved || job?.preset || 'default').toLowerCase();
}

export function harmonicCompatibility(left, right) {
  const notes = {C:0,'C#':1,Db:1,D:2,'D#':3,Eb:3,E:4,F:5,'F#':6,Gb:6,G:7,'G#':8,Ab:8,A:9,'A#':10,Bb:10,B:11};
  const parse = value => {
    const match = String(value || '').match(/^([A-G](?:#|b)?)\s+(major|minor)/i);
    return match ? {pitch:notes[match[1]], mode:match[2].toLowerCase()} : null;
  };
  const a = parse(left); const b = parse(right);
  if (!a || !b) return {score:10,label:'key unknown'};
  const distance = Math.min((a.pitch-b.pitch+12)%12,(b.pitch-a.pitch+12)%12);
  if (a.pitch === b.pitch && a.mode === b.mode) return {score:40,label:'same key'};
  if (a.mode !== b.mode && ((a.mode === 'minor' && (a.pitch+3)%12 === b.pitch) || (b.mode === 'minor' && (b.pitch+3)%12 === a.pitch))) return {score:36,label:'relative key'};
  if (distance === 5 && a.mode === b.mode) return {score:30,label:'neighboring key'};
  if (a.pitch === b.pitch) return {score:24,label:'parallel key'};
  return {score:0,label:'distant key'};
}

export function compatibility(left, right) {
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

export function createDjLibraryFeature({
  services, getAppConfig, libraryUiState, libraryRequestState, getLoadedAt, setLoadedAt,
  invalidateMusicFiles, VIEW_CACHE_MS, escapeHtml, genreFolderTree,
  bindGenreFolderState, option, refreshSearchableSelects, compactAudioMarkup,
  genreEditorMarkup, bindGenreEditor, bindCompactAudio, renderTrackPagination,
  clock, pct, loadJobs, loadDownloadedLibrary, loadReports,
  showView, startKeyAnalysis,
  compactAudioIsWithin, stopCompactAudio, normalizedGenreCategory,
  ELECTRONIC_GENRE_CATEGORIES, LATIN_GENRE_CATEGORIES, libraryReprocessForm, reportDate,
  bindLazyAudio,
  syncControlUnlessEditing, captureTextFilter, loadAnalysis,
  jobAction, jobElement,
}) {
  const {api, $, $$, notify, confirmAction, operationReceiptText, descriptorChipsMarkup, descriptorEditorMarkup, openDescriptorEditorDialog, saveDescriptorEditor, inferDescriptorEditor} = useFrontendServices(services);
  let visibleDownloadedTracks = [];
  const bindIdentityInference=(editor,trackIds,onApplied=async()=>{})=>{editor.querySelector('.infer-descriptors').onclick=async event=>{const action=event.currentTarget,original=action.textContent;action.disabled=true;action.textContent='Inferring…';try{const result=await inferDescriptorEditor(editor,typeof trackIds==='function'?trackIds():trackIds);if(result.applied){notify(`Added inferred identity tags to ${result.applied} tracks. Manual tags were preserved.`,'success');await onApplied(result);}}catch(error){notify(error.message,'danger');}finally{action.disabled=false;action.textContent=original;}};};
  const bindIdentityProtection=(editor,track)=>{const input=editor.querySelector('.descriptor-inference-protection input');if(!input||!track)return;input.checked=Boolean(track.identity_inference_locked);input.onchange=async()=>{const wanted=input.checked;input.disabled=true;try{const response=await api.raw(`/api/downloaded-library/tracks/${Number(track.id)}/inference-protection`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({protected:wanted})}),result=await response.json();if(!response.ok)throw new Error(api.errorMessage(result,'Inference protection could not be saved.'));track.identity_inference_locked=Boolean(result.protected_from_inference);input.checked=track.identity_inference_locked;notify(`${track.title||'Track'}: ${input.checked?'protected from automatic inference':'eligible for re-inference'}. Survives restart: Yes.`,'success');}catch(error){input.checked=!wanted;notify(error.message,'danger');}finally{input.disabled=false;}};};
  async function revealLibraryTrack(jobId, sourceName) {
    let card = document.querySelector(`.library-card[data-job-id="${jobId}"]`);
    if (!card) {
      libraryRequestState.reset();
      libraryRequestState.update({search:String(sourceName || '').replace(/\.[^.]+$/, ''), page:1});
      await loadLibrary();
      card = document.querySelector(`.library-card[data-job-id="${jobId}"]`);
    }
    if (!card) {
      notify(`Could not reveal ${String(sourceName || 'that track').replace(/\.[^.]+$/, '')}. Reset the Library filters and try again.`, 'danger');
      return;
    }
    card.scrollIntoView({behavior:'smooth',block:'start'});
    card.querySelector('.library-compact-row')?.focus();
  }

  function renderLibraryIntelligence(songs, latestByName) {
    const roleNames = ['warm-up','peak-time','closing','vocal-safe','melodic','ambient','live timing'];
    const groups = Object.fromEntries(roleNames.map(role => [role, []]));
    songs.forEach(song => libraryRoles(song).forEach(role => groups[role].push(song)));
    $('#role-groups').innerHTML = roleNames.map(role => {
      const [label,description] = LIBRARY_ROLE_INFO[role];
      return `<details class="role-card"><summary><strong>${groups[role].length}</strong><span>${label}</span><small>${escapeHtml(description)}</small></summary><div>${groups[role].length ? groups[role].map(song => `<button type="button" data-job-id="${latestByName.get(song.source_name.toLowerCase())?.id || ''}" data-source-name="${escapeHtml(song.source_name)}">${escapeHtml(song.source_name.replace(/\.[^.]+$/, ''))}<span>${Number(song.bpm || 0).toFixed(1)} BPM · ${escapeHtml(formatLibraryKey(song.key))}</span></button>`).join('') : '<p>No matching tracks yet.</p>'}<button type="button" class="role-filter" data-role="${role}">Filter DJ Library to ${label}</button></div></details>`;
    }).join('');
    $('#role-groups').querySelectorAll('[data-job-id]').forEach(button => button.onclick = () => revealLibraryTrack(button.dataset.jobId, button.dataset.sourceName));
    $('#role-groups').querySelectorAll('.role-filter').forEach(button => button.onclick = () => { $('#library-role').value = button.dataset.role; $('#library-role').dispatchEvent(new Event('change')); document.querySelector('.library-toolbar')?.scrollIntoView({behavior:'smooth',block:'start'}); });
    const select = $('#compatibility-source'); const previous = select.value;
    select.replaceChildren(option('', 'Choose a track'), ...songs.sort((a,b) => a.source_name.localeCompare(b.source_name)).map(song => option(song.source_name, song.source_name.replace(/\.[^.]+$/, ''))));
    if (songs.some(song => song.source_name === previous)) select.value = previous;
    const show = () => {
      const source = songs.find(song => song.source_name === select.value);
      if (!source) { $('#compatible-tracks').innerHTML = '<p>Select a track to see BPM and key-compatible suggestions.</p>'; return; }
      const matches = songs.filter(song => song !== source).map(song => ({song,...compatibility(source,song)})).filter(match => match.score >= 40).sort((a,b) => b.score-a.score).slice(0,8);
      $('#compatible-tracks').innerHTML = matches.length ? `<div class="compatibility-title"><div><strong>Mix suggestions for ${escapeHtml(source.source_name)}</strong><span>${Number(source.bpm || 0).toFixed(1)} BPM · ${escapeHtml(formatLibraryKey(source.key))}</span></div><p><b>How the score works:</b> tempo 45% · harmonic key 35% · energy 10% · shared role 10%. Treat it as a shortlist, then listen before mixing.</p></div>${matches.map(match => `<button type="button" data-job-id="${latestByName.get(match.song.source_name.toLowerCase())?.id || ''}" data-source-name="${escapeHtml(match.song.source_name)}"><strong>${escapeHtml(match.song.source_name.replace(/\.[^.]+$/, ''))}</strong><span>${match.score}% match · ${Number(match.song.bpm || 0).toFixed(1)} BPM · ${escapeHtml(formatLibraryKey(match.song.key))}</span><small>${match.difference <= .02 ? 'tempo locked' : `${(match.difference*100).toFixed(1)}% tempo move`} · ${match.key}</small><em>Tempo ${match.components.tempo}/45 · Key ${match.components.key}/35 · Energy ${match.components.energy}/10 · Role ${match.components.role}/10</em></button>`).join('')}` : '<p>No strong matches are available yet. Try another source track or relax the Library filters.</p>';
      $('#compatible-tracks').querySelectorAll('button').forEach(button => button.onclick = () => revealLibraryTrack(button.dataset.jobId, button.dataset.sourceName));
    };
    select.onchange = show; show();
  }

  async function loadLibrary() {
    let catalog;
    try {
      const result=await libraryRequestState.request(`/api/library/catalog?${libraryQuery(libraryUiState)}`,{errorMessage:'DJ Library could not be loaded.'});
      if(result.status!=='applied')return;
      catalog=result.payload;
      libraryRequestState.setPage(Number(catalog.page||1));
      setLoadedAt(Date.now());
    } catch(error) {
      $('#library-list').innerHTML=`<div class="empty danger-text">${escapeHtml(error.message||'DJ Library could not be loaded.')} <button type="button" class="button secondary library-retry">Retry</button></div>`;
      $('#library-list .library-retry')?.addEventListener('click',loadLibrary);
      return;
    }
    const allJobs = (catalog.tracks || []).map(track => track.job);
    const report = {songs:Object.fromEntries((catalog.tracks || []).map((track,index) => [index, track.analysis || {}]))};
    const downloadedTracks = (catalog.tracks || []).map(track => track.downloaded).filter(Boolean);
    visibleDownloadedTracks = downloadedTracks;
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
    if (compactAudioIsWithin('#library-list')) stopCompactAudio();
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
      const reprocessLabel = analysisOnly ? 'Extend track' : 'Configure reprocess';
      return `<article class="panel library-card" data-job-id="${latest.id}"><div class="library-head"><div><p class="eyebrow">LATEST · GENERATION ${latest._generation}${analysisOnly?' · ANALYZED':''}</p><h2>${escapeHtml(latest.source_name)}</h2><span>${escapeHtml(analysisOnly ? 'DJ analysis complete · original preserved' : choice)}</span></div><div class="library-head-actions"><button class="button secondary library-reprocess" data-closed-label="${reprocessLabel}">${reprocessLabel}</button>${analysisOnly?'':`<button class="button secondary library-review">${reviewPending?'Open review':'Create review'}</button>`}<button class="button secondary open-latest">Show full details</button></div></div>${libraryReprocessForm(latest, config)}<div class="library-metrics"><p><b>${latest.bpm ? Number(latest.bpm).toFixed(1) : '—'}</b><span>BPM</span></p><p><b class="library-key-value">—</b><span>Key</span></p><p><b>${analysisOnly?'Not extended':latest.intro_quality == null ? 'Preserved' : pct(latest.intro_quality)}</b><span>Intro</span></p><p><b>${analysisOnly?'Not extended':latest.outro_quality == null ? 'Preserved' : pct(latest.outro_quality)}</b><span>Outro</span></p><p><b>${reportDate(latest.updated_at)}</b><span>Processed</span></p></div><div class="library-player"><span>${analysisOnly?'Original analyzed track':'Newest extended edit'}</span><audio controls preload="none" data-src="/api/jobs/${latest.id}/audio/${analysisOnly?'wav':'extended'}"></audio></div><div class="library-downloads"><a class="button secondary" href="/api/jobs/${latest.id}/download/wav">Source WAV</a>${!analysisOnly && versioned ? `<a class="button secondary" href="/api/jobs/${latest.id}/download/extended">Download newest extended WAV</a>` : analysisOnly ? '<span>Choose Extend track whenever you want to create an edit.</span>' : '<span>Reprocess once to create an immutable downloadable generation.</span>'}</div><div class="library-detail-host"></div><details class="version-history" data-loaded="false"><summary>${generationCount} generation${generationCount===1?'':'s'} · view version history</summary><ul><li class="muted-copy">Open to load version history.</li></ul></details></article>`;
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
      card.dataset.key = normalizedKey(analysis);
      card.dataset.camelot = camelotKey(analysis);
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
      keyValue.dataset.standard = normalizedKey(analysis);
      keyValue.textContent = formatLibraryKey(analysis);
      card.querySelector('.library-head-actions').insertAdjacentHTML('beforeend', '<button class="button secondary remove-library-track">Remove from library</button>');
      if (downloadedTrack) {
        card.querySelector('.library-head-actions').insertAdjacentHTML('afterbegin', '<button class="button secondary edit-library-identity">Edit identity</button><button class="button secondary edit-library-genre">Edit genre</button>');
        card.querySelector('.library-head').insertAdjacentHTML('afterend', `<div class="library-identity-summary">${descriptorChipsMarkup(downloadedTrack.descriptors||[],{detailed:true})}</div>${genreEditorMarkup(downloadedTrack.genre_category || 'Other', downloadedTrack.suggested_genre || '', true)}${descriptorEditorMarkup(downloadedTrack.descriptors||[])}`);
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
      card.insertAdjacentHTML('afterbegin', `<div class="library-compact-row" role="button" tabindex="0" aria-expanded="false" aria-label="Show DJ details for ${escapeHtml(trackTitle)}"><label class="library-track-select"><input type="checkbox" value="${card.dataset.jobId}" aria-label="Select ${escapeHtml(trackTitle)}"><span></span></label><div class="library-row-icon">${trackArtwork}</div><div class="library-row-title"><h3>${escapeHtml(trackTitle)}</h3><span class="library-row-artist">${escapeHtml(trackArtist)}</span><small>${escapeHtml(category)}${identity?` · ${escapeHtml(identity)}`:''}</small></div><div class="library-row-metric"><b>${Number(analysis.bpm || latest.bpm || 0).toFixed(1)}</b><span>BPM</span></div><div class="library-row-metric"><b>${escapeHtml(formatLibraryKey(analysis))}</b><span>Key / Camelot</span></div><div class="library-row-metric"><b>${escapeHtml(energyBand(energy))}</b><span>Energy</span></div><div class="library-row-role">${roles.slice(0,2).map(role => `<span>${escapeHtml(LIBRARY_ROLE_INFO[role]?.[0] || role)}</span>`).join('')}</div><span class="library-result" data-result="${card.dataset.result}">${resultLabel}<small>${escapeHtml(qualityText)}</small></span>${compactAudioMarkup(`/api/jobs/${latest.id}/audio/${analysisOnly?'wav':'extended'}`,latest.duration_seconds||analysis.duration_seconds||0)}<details class="library-row-actions"><summary aria-label="Library track actions">•••</summary><div><button type="button" class="compact-remove danger-text">Remove from Library</button></div></details></div>`);
      if(downloadedTrack?.descriptors?.length)card.querySelector('.library-row-title').insertAdjacentHTML('beforeend',descriptorChipsMarkup(downloadedTrack.descriptors));
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
        const payload = await api.raw(`/api/library/jobs/${card.dataset.jobId}/details`).then(async response => {
          if (!response.ok) throw new Error(api.errorMessage(await response.json(), 'Could not load version history.'));
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
      button.textContent = form.hidden ? button.dataset.closedLabel : 'Close configuration';
      if (!form.hidden) form.querySelector('select').focus();
    });
    root.querySelectorAll('.edit-library-genre').forEach(button => button.onclick = () => {
      const card = button.closest('.library-card');
      const editor = card.querySelector('.inline-genre-editor'); editor.hidden = !editor.hidden;
      if (!editor.hidden) editor.querySelector('select').focus();
    });
    root.querySelectorAll('.edit-library-identity').forEach(button=>button.onclick=()=>{
      const card=button.closest('.library-card'),editor=card.querySelector('.track-descriptor-editor');editor.hidden=!editor.hidden;
      if(!editor.hidden)editor.querySelector('input')?.focus();
    });
    root.querySelectorAll('.library-card[data-downloaded-id]:not([data-downloaded-id=""]) .track-descriptor-editor').forEach(editor=>{
      const card=editor.closest('.library-card');
      bindIdentityInference(editor,[Number(card.dataset.downloadedId)]);
      editor.querySelector('.cancel-descriptors').onclick=()=>{editor.hidden=true;};editor.querySelector('.close-descriptor-editor').onclick=()=>{editor.hidden=true;};
      editor.querySelector('.save-descriptors').onclick=async event=>{const action=event.currentTarget;action.disabled=true;action.textContent='Saving…';try{const result=await saveDescriptorEditor(editor,[Number(card.dataset.downloadedId)]);card.querySelector('.library-row-title .track-descriptor-chips')?.remove();if(result.values?.length)card.querySelector('.library-row-title').insertAdjacentHTML('beforeend',descriptorChipsMarkup(result.values));card.querySelector('.library-identity-summary').innerHTML=descriptorChipsMarkup(result.values||[],{detailed:true});editor.hidden=true;invalidateMusicFiles();notify('Musical identity saved to the persistent catalog. It will survive restart.','success');}catch(error){notify(error.message,'danger');}finally{action.disabled=false;action.textContent='Save changes';}};
    });
    root.querySelectorAll('.library-card[data-downloaded-id]:not([data-downloaded-id=""])').forEach(card => bindGenreEditor(card.querySelector('.inline-genre-editor'), () => [Number(card.dataset.downloadedId)], async payload => {card.querySelector('.library-row-title small').textContent=payload.genre_category;card.querySelector('.inline-genre-editor').hidden=true;invalidateMusicFiles();}));
    root.querySelectorAll('.close-reprocess').forEach(button => button.onclick = () => {
      const card = button.closest('.library-card');
      card.querySelector('.library-reprocess-form').hidden = true;
      const trigger = card.querySelector('.library-reprocess');
      trigger.textContent = trigger.dataset.closedLabel;
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
          intro_bars:introAuto ? Number(latestConfig.analysis_only ? getAppConfig().effective.intro_bars : latest.intro_bars) : Number(reprocessForm.elements.intro_bars.value),
          outro_bars:outroAuto ? Number(latestConfig.analysis_only ? getAppConfig().effective.outro_bars : latest.outro_bars) : Number(reprocessForm.elements.outro_bars.value),
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
        try {
          const succeeded = await jobAction(latest.id, 'reprocess', body);
          if (succeeded === false) throw new Error(review ? 'The review request was not queued.' : 'The new generation was not queued.');
          showView('workspace-view');
        } catch (error) {
          notify(`Reprocessing failed: ${error.message}`, 'danger');
          reprocessForm.querySelectorAll('button').forEach(item => item.disabled = false);
          reprocessForm.querySelector('.reprocess-message').textContent = 'Nothing was queued. Your existing track is unchanged.';
        }
      };
      reprocessForm.addEventListener('submit', event => { event.preventDefault(); submit(false); });
      reprocessForm.querySelector('.reprocess-review').onclick = () => submit(true);
    });
    root.querySelectorAll('.library-review').forEach(button => button.onclick = async () => {
      const card = button.closest('.library-card');
      const latest = jobs.find(job => String(job.id) === card.dataset.jobId);
      if (latest.review_status === 'pending') { showView('review-view'); return; }
      try {
        const succeeded = await jobAction(latest.id, 'reprocess', {review_candidates:true});
        if (succeeded === false) throw new Error('The review request was not queued.');
        showView('workspace-view');
      } catch (error) {
        notify(`Review creation failed: ${error.message}`, 'danger');
      }
    });
    root.querySelectorAll('.open-latest').forEach(button => button.onclick = async () => {
      const card = button.closest('.library-card');
      const host = card.querySelector('.library-detail-host');
      if (host.childElementCount) {
        host.replaceChildren(); button.textContent = 'Show full details'; return;
      }
      const latest = jobs.find(job => String(job.id) === card.dataset.jobId);
      try {
        const detail = jobElement(latest); detail.classList.add('library-embedded');
        host.append(detail); detail.querySelector('.details-job').click();
        button.textContent = 'Hide full details';
      } catch (error) {
        notify(`Track details could not be opened: ${error.message}`, 'danger');
      }
    });
    root.querySelectorAll('.remove-library-track').forEach(button => button.onclick = async () => {
      const card = button.closest('.library-card');
      const latest = jobs.find(job => String(job.id) === card.dataset.jobId);
      if (!await confirmAction(`Remove ${latest.source_name} and all of its generations from the Library? Exported audio files will remain in the output folder.`, {title:'Remove Library track', acceptLabel:'Remove', danger:true})) return;
      button.disabled = true; button.textContent = 'Removing…';
      const response = await api.raw(`/api/library/${encodeURIComponent(latest.source_name)}`, {method:'DELETE'});
      if (!response.ok) { alert(api.errorMessage(await response.json(), 'Could not remove the track.')); button.disabled = false; button.textContent = 'Remove from library'; return; }
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
    Object.entries(controls).forEach(([name,control])=>{if(name==='category'||name==='preset'||name==='key'||name==='role')return;syncControlUnlessEditing(control,libraryUiState[name]??control.value);});
    $('#library-page-size').value=String(libraryUiState.pageSize); $('#library-key-display').value=libraryKeyMode();
    const request=(page=1)=>{libraryRequestState.setPage(page);loadLibrary();};
    controls.search.oninput=()=>{captureTextFilter(controls.search,libraryUiState);libraryRequestState.debounce(()=>request(1));};
    Object.entries(controls).filter(([name])=>!['search','category'].includes(name)).forEach(([name,control])=>control.onchange=()=>{libraryUiState[name]=control.value;request(1);});
    controls.category.onchange=()=>{libraryUiState.category=controls.category.value;libraryUiState.detailedGenre='all';request(1);};
    [controls.bpmMin,controls.bpmMax].forEach(input=>input.oninput=()=>{libraryRequestState.debounce(()=>{libraryRequestState.update({bpmMin:controls.bpmMin.value,bpmMax:controls.bpmMax.value});loadLibrary();});});
    $('#library-page-size').onchange=event=>{libraryRequestState.update({pageSize:Number(event.target.value)});localStorage.setItem('dj-library-page-size',String(libraryUiState.pageSize));loadLibrary();};
    $('#library-key-display').onchange=event=>{localStorage.setItem('audioextender-key-view',event.target.value);document.querySelectorAll('.library-key-value').forEach(node=>node.textContent=formatLibraryKey(node.dataset.standard,event.target.value));};
    const resetLibraryFilters=()=>{libraryRequestState.reset();loadLibrary();};
    $('#library-reset-filters').onclick=resetLibraryFilters;
    $('#library-reset-filters-top').onclick=resetLibraryFilters;
    const changePage=page=>{libraryRequestState.setPage(page);loadLibrary();document.querySelector('.library-toolbar').scrollIntoView({behavior:'smooth',block:'start'});};
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
    const identityButton=$('#library-edit-identity');
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
      identityButton.disabled = selected === 0 || catalogSelected !== selected;
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
        const response = await api.raw('/api/downloaded-library/genre', {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({track_ids:trackIds, genre_category:genre})});
        const payload = await response.json();
        if (!response.ok) throw new Error(api.errorMessage(payload, 'Could not change genre.'));
        notify(operationReceiptText(payload.receipt), payload.receipt?.failures?.length ? 'danger' : 'success', {timeout:9000});
        genreInput.value = '';
        await Promise.all([loadLibrary(), loadDownloadedLibrary()]);
      } catch (error) { alert(error.message); }
      finally { genreButton.textContent = 'Change genre'; }
    };
    identityButton.onclick=()=>{
      const selectedCards=boxes.filter(box=>box.checked).map(box=>box.closest('.library-card'));
      const trackIds=selectedCards.map(card=>Number(card.dataset.downloadedId)).filter(Boolean);
      if(!trackIds.length||trackIds.length!==selectedCards.length)return;
      const single=trackIds.length===1,currentTrack=single?visibleDownloadedTracks.find(track=>Number(track.id)===trackIds[0]):null,saved=currentTrack?.descriptors||[];
      const selectedBoxIndex=single?boxes.findIndex(box=>box.checked):-1,previousBox=selectedBoxIndex>0?boxes[selectedBoxIndex-1]:null,nextBox=selectedBoxIndex>=0?boxes[selectedBoxIndex+1]:null;
      const {editor,close}=openDescriptorEditorDialog({descriptors:saved,bulk:!single,protectedFromInference:single?Boolean(currentTrack?.identity_inference_locked):null,title:single?`Edit identity · ${currentTrack?.title||'Selected track'}`:'Edit identity for selected tracks',subtitle:single?`Track ${selectedBoxIndex+1} of ${boxes.length} in the current filtered list.`:`Apply descriptors to ${trackIds.length} selected tracks.`});
      if(single)bindIdentityProtection(editor,currentTrack);
      editor.querySelector('.cancel-descriptors').onclick=close;editor.querySelector('.close-descriptor-editor').onclick=close;
      const saveButton=editor.querySelector('.save-descriptors');let previousButton=null,nextButton=null;
      if(single){previousButton=document.createElement('button');previousButton.type='button';previousButton.className='button secondary save-previous-descriptors';previousButton.textContent='← Save & previous';previousButton.disabled=!previousBox;nextButton=document.createElement('button');nextButton.type='button';nextButton.className='save-next-descriptors';nextButton.textContent='Save & next →';nextButton.disabled=!nextBox;saveButton.after(previousButton,nextButton);}
      const save=async(destination,action)=>{const original=action.textContent,targetBox=destination<0?previousBox:destination>0?nextBox:null;action.disabled=true;saveButton.disabled=true;if(previousButton)previousButton.disabled=true;if(nextButton)nextButton.disabled=true;action.textContent='Saving…';try{const result=await saveDescriptorEditor(editor,trackIds);if(currentTrack){currentTrack.descriptors=result.values||[];currentTrack.identity_inference_locked=Boolean(result.protected_from_inference);}notify(`Requested: update identity for ${result.requested} tracks. Changed: ${result.updated}. Written to: persistent track catalog. Failed: ${result.missing?.length||0}. Survives restart: Yes.`,'success');close();setLoadedAt(0);invalidateMusicFiles();if(targetBox){boxes.forEach(box=>box.checked=false);targetBox.checked=true;refreshSelection();identityButton.onclick();}else await loadLibrary();}catch(error){notify(error.message,'danger');action.disabled=false;saveButton.disabled=false;if(previousButton)previousButton.disabled=!previousBox;if(nextButton)nextButton.disabled=!nextBox;action.textContent=original;}};
      saveButton.onclick=event=>save(0,event.currentTarget);if(previousButton)previousButton.onclick=event=>save(-1,event.currentTarget);if(nextButton)nextButton.onclick=event=>save(1,event.currentTarget);
      bindIdentityInference(editor,trackIds,async()=>{setLoadedAt(0);invalidateMusicFiles();await loadLibrary();});
    };
    removeButton.onclick = async () => {
      const selectedCards = boxes.filter(box => box.checked).map(box => box.closest('.library-card'));
      if (!selectedCards.length || !await confirmAction(`Remove ${selectedCards.length} selected track${selectedCards.length === 1 ? '' : 's'} and all of their generations from the Library? Exported audio files will remain in the output folder.`, {title:'Remove selected tracks', acceptLabel:'Remove', danger:true})) return;
      removeButton.disabled = true; removeButton.textContent = 'Removing…';
      const removed=[]; const failures=[];
      for (const card of selectedCards) {
        try {
          const response = await api.raw(`/api/library/${encodeURIComponent(card.dataset.sourceName)}`, {method:'DELETE'});
          if (!response.ok) throw new Error(api.errorMessage(await response.json(), 'Could not remove the track.'));
          removed.push(card.dataset.sourceName);
        } catch (error) { failures.push(`${card.dataset.sourceName}: ${error.message}`); }
      }
      await Promise.all([loadLibrary(), loadAnalysis(), loadReports()]);
      const summary=`Requested: remove ${selectedCards.length} Library track${selectedCards.length===1?'':'s'}. Changed: ${removed.length} removed. Written to: persistent Library catalog. Failed: ${failures.length}${failures.length?` (${failures.slice(0,3).join('; ')}${failures.length>3?'; …':''})`:''}. Survives restart: Yes.`;
      notify(summary, failures.length ? 'danger' : 'success', {timeout:10000});
    };
    reanalyzeButton.onclick = async () => {
      const selectedCards = boxes.filter(box => box.checked).map(box => box.closest('.library-card'));
      const trackIds = selectedCards.map(card => Number(card.dataset.downloadedId)).filter(Boolean);
      if (!trackIds.length || trackIds.length !== selectedCards.length || !await confirmAction(`Reanalyze ${trackIds.length} selected track${trackIds.length===1?'':'s'}? Audio files, metadata, artwork, and verified keys will be preserved.`, {title:'Reanalyze selected tracks', acceptLabel:'Reanalyze'})) return;
      reanalyzeButton.disabled=true; reanalyzeButton.textContent='Adding to queue…';
      try { const response=await api.raw('/api/downloaded-library/reanalyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_ids:trackIds})});const result=await response.json();if(!response.ok)throw new Error(api.errorMessage(result,'Could not queue reanalysis.'));showView('workspace-view');await loadJobs(); }
      catch(error){alert(error.message);reanalyzeButton.textContent='Reanalyze';refreshSelection();}
    };
    keyAnalyzeButton.onclick=()=>{const cards=boxes.filter(box=>box.checked).map(box=>box.closest('.library-card'));const ids=cards.map(card=>Number(card.dataset.downloadedId)).filter(Boolean);startKeyAnalysis(ids,keyAnalyzeButton,async()=>{setLoadedAt(0);await Promise.all([loadLibrary(),loadReports()]);});};
    button.onclick = async () => {
      const jobIds = boxes.filter(box => box.checked).map(box => Number(box.value));
      const fileTypes = typeBoxes.filter(box => box.checked).map(box => box.value);
      button.disabled = true; button.textContent = 'Preparing download…';
      try {
        const response = await api.raw('/api/library/download', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({job_ids:jobIds, file_types:fileTypes})});
        if (!response.ok) throw new Error(api.errorMessage(await response.json(), 'Could not prepare download.'));
        const url = URL.createObjectURL(await response.blob());
        const link = document.createElement('a'); link.href = url; link.download = 'DJ Library Studio Selected Tracks.zip'; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch (error) { alert(error.message); }
      finally { button.textContent = 'Download selected'; refreshSelection(); }
    };
    refreshSelection();
  }

  return {loadLibrary, renderLibraryIntelligence};
}
