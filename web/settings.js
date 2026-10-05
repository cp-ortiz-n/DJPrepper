export function createSettingsController({loadConfig, loadPresets, loadLibraryStatus, loadRelocationState}) {
  return {
    initialize(afterConfig) {
      const configured = loadConfig().then(() => afterConfig?.());
      loadLibraryStatus();
      loadRelocationState();
      return configured;
    },
    loadPresets,
    async refreshStorage() {
      return loadLibraryStatus();
    },
  };
}

export function libraryAvailabilityView(status = {}) {
  const online = Boolean(status.online);
  const offlineTracks = Number(status.offline_tracks || 0);
  return {
    online,
    bannerHidden: online,
    clearStaleErrors: online && offlineTracks === 0,
    label: online ? 'Library online' : 'Library offline',
  };
}

export function createSettingsFeature({
  $, apiErrorMessage, operationReceiptText, downloadedUiState, setAppConfig,
  applyEffectiveSettings, loadConfig, loadPresets, editPreset, getPresetLibrary,
  loadJobs, loadAnalysis, loadDownloadedLibrary, loadLibrary, invalidateCatalogs,
  loadPerformanceDiagnostics, escapeHtml, confirmAction, reportDate,
  libraryAvailabilityView,
}) {
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
    setAppConfig(payload);
    applyEffectiveSettings(payload.effective);
    $('#settings-form').classList.remove('is-dirty');
    const receiptMessage = operationReceiptText(payload.receipt);
    $('#settings-message').textContent = `${receiptMessage} · Checking the music library…`;
    libraryStatusRequest=null;
    const status=await loadLibraryStatus();
    await loadLibraryHealth();
    if(status?.online){
      $('#settings-message').textContent=`${receiptMessage} · Library connected: ${status.available_tracks} of ${status.cataloged_tracks} tracks available at ${status.path}`;
      if(!status.offline_tracks){
        const errors=$('#downloaded-retag-errors');errors.hidden=true;errors.open=false;errors.querySelector('ul')?.replaceChildren();
        $('#downloaded-rescan-message').textContent='Library location verified · all cataloged tracks are available.';
      }
    }else{
      $('#settings-message').textContent=`${receiptMessage} · Folder currently unavailable: ${payload.effective.music_library_path}`;
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
    applyEffectiveSettings(payload.effective); $('#settings-form').classList.remove('is-dirty'); $('#settings-message').textContent = operationReceiptText(payload.receipt);
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
  function renderLibraryHealth(health={}) {
    const online=Boolean(health.online),dot=$('#health-connection-dot');
    dot.className=online?'online':'offline';
    $('#health-connection').textContent=online?'Configured library connected':'Configured library disconnected';
    $('#health-path').textContent=health.configured_folder||'No library folder configured';
    $('#health-outside').textContent=Number(health.outside_folder||0);
    $('#health-missing').textContent=Number(health.missing_files||0);
    $('#health-pending').textContent=Number(health.pending_metadata_writes||0);
    const active=health.active_operations||[];
    $('#health-pending-detail').textContent=active.length?active.map(item=>`${String(item.kind).replaceAll('-',' ')} · ${item.remaining} remaining`).join(' · '):'No active metadata writes';
    $('#health-failed').textContent=Number(health.failed_metadata_operations||0);
    const failures=health.failed_operations||[];
    $('#health-failed-detail').textContent=failures.length?failures.map(item=>`${String(item.kind).replaceAll('-',' ')} · ${item.count}`).join(' · '):'No failed artwork or tag operations';
    const setCard=(name,tone)=>{const card=document.querySelector(`[data-health-card="${name}"]`);card?.classList.remove('good','warning','active');if(tone)card?.classList.add(tone);};
    setCard('outside',Number(health.outside_folder||0)?'warning':'good');setCard('missing',Number(health.missing_files||0)?'warning':'good');setCard('pending',Number(health.pending_metadata_writes||0)?'active':'good');setCard('failed',Number(health.failed_metadata_operations||0)?'warning':'good');
    const storage=health.storage||{};
    $('#health-storage').textContent=formatBytes(storage.total_bytes||storage.song_bytes||0);
    $('#health-storage-detail').textContent=`${formatBytes(storage.free_bytes||0)} available${storage.reclaimable_bytes?` · ${formatBytes(storage.reclaimable_bytes)} reclaimable`:''}`;
    const quality=health.audio_quality||{},analyzed=Number(quality.analyzed||0),total=Number(quality.total||0);
    $('#health-quality').textContent=analyzed?`${Math.round(Number(quality.average_score||0))}/100`:'—';
    $('#health-quality-detail').textContent=analyzed?`${analyzed} of ${total} tracks analyzed`:'No tracks analyzed yet';
    setCard('storage','good');setCard('quality',analyzed?'good':'');
    const button=$('#verify-library');button.disabled=!online;button.textContent='Verify library';
    $('#library-health-message').textContent=!online?'Connect the configured drive to enable verification.':health.verified?'Library connected and every cataloged track is available.':'Library connected, but some catalog or file issues need attention.';
  }
  let libraryHealthRequest=null;
  async function loadLibraryHealth(){
    if(libraryHealthRequest)return libraryHealthRequest;
    libraryHealthRequest=fetch('/api/settings/library-health',{cache:'no-store'}).then(async response=>{const payload=await response.json();if(!response.ok)throw new Error(response.status===404?'Restart the app once to enable the new library health service.':payload.detail||'Library health could not be loaded.');renderLibraryHealth(payload);return payload;}).catch(async error=>{
      if(error.message.startsWith('Restart the app'))try{const status=await fetch('/api/settings/library-status',{cache:'no-store'}).then(response=>response.json());renderLibraryHealth({configured_folder:status.path,online:status.online,outside_folder:status.location_integrity?.outside_count||0,missing_files:status.offline_tracks||0,pending_metadata_writes:0,failed_metadata_operations:0,storage:status,audio_quality:status.audio_quality,verified:status.online&&!status.offline_tracks});const button=$('#verify-library');button.disabled=true;button.textContent='Restart required';}catch(_){/* Keep the actionable restart message. */}
      $('#library-health-message').textContent=error.message;return null;
    }).finally(()=>{libraryHealthRequest=null;});
    return libraryHealthRequest;
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
      const availability=libraryAvailabilityView(status);
      const badge=$('#library-online-state');badge.textContent=availability.label;badge.className=`library-state ${availability.online?'online':'offline'}`;
      $('#library-offline-banner').hidden=availability.bannerHidden;document.body.classList.toggle('library-is-offline',!availability.online);
      if(availability.clearStaleErrors){
        const errors=$('#downloaded-retag-errors');errors.hidden=true;errors.open=false;errors.querySelector('ul')?.replaceChildren();
        $('#downloaded-rescan-message').textContent='Library reconnected · all cataloged tracks are available.';
      }
      return status;
    } catch { $('#library-online-state').textContent='Status unavailable'; return null; }
    finally { libraryStatusRequest=null; }
    })();
    return libraryStatusRequest;
  }
  $('#verify-library').addEventListener('click',async()=>{
    const button=$('#verify-library');button.disabled=true;button.textContent='Verifying…';$('#library-health-message').textContent='Checking the configured folder, catalog paths, metadata operations, storage, and audio quality…';
    try{
      const response=await fetch('/api/settings/library-health/verify',{method:'POST'}),health=await response.json();
      if(!response.ok)throw new Error(health.detail||'The library could not be verified.');
      renderLibraryHealth(health);libraryStatusRequest=null;await loadLibraryStatus();
      $('#library-health-message').textContent=health.verified?'Verification complete · every cataloged track is available.':`Verification complete · ${health.missing_files} missing and ${health.outside_folder} outside the configured folder.`;
      invalidateCatalogs();
    }catch(error){$('#library-health-message').textContent=error.message;button.disabled=false;button.textContent='Verify library';}
  });
  async function pollLibraryConsolidation(batchId){const button=$('#library-consolidate');const response=await fetch(`/api/settings/library-locations/consolidate/${batchId}`,{cache:'no-store'});const batch=await response.json();if(!response.ok){button.disabled=false;button.textContent=batch.detail||'Consolidation failed';return;}button.textContent=`Verified ${batch.processed}/${batch.total}`;if(batch.status==='processing'){setTimeout(()=>pollLibraryConsolidation(batchId),800);return;}button.disabled=false;button.textContent=batch.failed?`${batch.moved} moved · ${batch.failed} failed`:'Consolidation complete';invalidateCatalogs();await Promise.all([loadLibraryStatus(),loadDownloadedLibrary(),loadLibrary()]);}
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
    if(['processing','canceling'].includes(state.status)){clearTimeout(relocationPollTimer);relocationPollTimer=setTimeout(loadRelocationState,750);}else if(state.status==='complete'){loadLibraryStatus();loadConfig();invalidateCatalogs();}
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
    try{const response=await fetch('/api/settings/backups/restore',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:pendingBackupToken,confirmation:input.value})});const result=await response.json();if(!response.ok)throw new Error(result.detail||'Restore failed.');pendingBackupToken='';message.textContent=`Restore complete. A pre-restore backup was saved as ${result.pre_restore_backup.filename}.`;button.textContent='Restored';await loadConfig();await loadBackups();invalidateCatalogs();}catch(error){message.textContent=error.message;button.disabled=false;button.textContent='Restore validated backup';}
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
    $('#preset-message').textContent = 'Preset saved.'; await loadConfig(); await loadPresets(); editPreset(getPresetLibrary().find(preset => preset.name === body.name));
  });
  $('#delete-preset').addEventListener('click', async () => {
    const name = $('#preset-original-name').value;
    if (!name || name === '__new__' || !await confirmAction(`Remove the ${name} preset? Existing processed generations will keep their saved configuration.`, {title:'Delete preset', acceptLabel:'Delete preset', danger:true})) return;
    const response = await fetch(`/api/presets/${encodeURIComponent(name)}`, {method:'DELETE'});
    if (!response.ok) { $('#preset-message').textContent = (await response.json()).detail || 'Could not remove preset.'; return; }
    await loadConfig(); await loadPresets(); editPreset(getPresetLibrary()[0] || null);
  });
  $('#restore-presets').addEventListener('click', async () => {
    if (!await confirmAction('Restore every maintained built-in preset and remove all custom preset definitions?', {title:'Restore built-in presets', acceptLabel:'Restore presets', danger:true})) return;
    await fetch('/api/presets/restore', {method:'POST'}); await loadConfig(); await loadPresets(); editPreset(getPresetLibrary()[0] || null);
  });


  return {
    loadLibraryHealth, loadLibraryStatus, loadRelocationState,
    loadBackups, loadStorageManager,
    initialize(afterConfig) {
      const configured = loadConfig().then(() => afterConfig?.());
      loadLibraryStatus();
      loadRelocationState();
      loadLibraryHealth();
      return configured;
    },
  };
}
