import {useFrontendServices} from '../../core/frontend-services.js';

export function createMusicFilesUiState(pageSize = Number(localStorage.getItem('music-files-page-size') || 50)) {
  return {search:'', genre:'all', detailedGenre:'all', playlist:'all', analysis:'all', artwork:'all', quality:'all', sort:'newest', page:1, pageSize};
}

export function musicFilesQuery(state) {
  return new URLSearchParams({
    paged:'true', page:String(state.page), page_size:String(state.pageSize), search:state.search,
    genre:state.genre, detailed_genre:state.detailedGenre, playlist:state.playlist,
    analysis:state.analysis, artwork:state.artwork, quality:state.quality, sort:state.sort,
  });
}

export function createMusicFilesFeature({
  services, appConfig, downloadedUiState, downloadedSelection, downloadedRequestState,
  getLoadedAt, setLoadedAt, invalidateLibrary, VIEW_CACHE_MS,
  escapeHtml, genreFolderTree, detailedGenreSummary,
  compactAudioMarkup, genreEditorMarkup, metadataEditorMarkup, option,
  syncControlUnlessEditing, refreshSearchableSelects, runBackgroundTask,
  loadLibrary, renderTrackPagination, captureTextFilter,
  bindGenreEditor, startKeyAnalysis, showView, loadJobs, closeDownloadedInspector,
  clock, stopNativeAudio, bindCompactAudio, bindLazyAudio, compactAudioIsWithin, stopCompactAudio,
  collapsedGenreFolders, bindGenreFolderState,
}) {
  const {api, $, $$, notify, confirmAction, operationReceiptText, descriptorChipsMarkup, descriptorEditorMarkup, openDescriptorEditorDialog, saveDescriptorEditor, inferDescriptorEditor} = useFrontendServices(services);
  let metadataReview = null;
  const bindIdentityProtection=(editor,track)=>{const input=editor.querySelector('.descriptor-inference-protection input');if(!input||!track)return;input.checked=Boolean(track.identity_inference_locked);input.onchange=async()=>{const wanted=input.checked;input.disabled=true;try{const response=await api.raw(`/api/downloaded-library/tracks/${Number(track.id)}/inference-protection`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({protected:wanted})}),result=await response.json();if(!response.ok)throw new Error(api.errorMessage(result,'Inference protection could not be saved.'));track.identity_inference_locked=Boolean(result.protected_from_inference);input.checked=track.identity_inference_locked;notify(`${track.title||track.filename}: ${input.checked?'protected from automatic inference':'eligible for re-inference'}. Survives restart: Yes.`,'success');}catch(error){input.checked=!wanted;notify(error.message,'danger');}finally{input.disabled=false;}};};
  const bindIdentityInference=(editor,trackIds,onApplied=async()=>{})=>{editor.querySelector('.infer-descriptors').onclick=async event=>{const action=event.currentTarget,original=action.textContent;action.disabled=true;action.textContent='Inferring…';try{const result=await inferDescriptorEditor(editor,typeof trackIds==='function'?trackIds():trackIds);if(result.applied||result.skipped_protected?.length){notify(`Added inferred identity tags to ${result.applied} tracks.${result.skipped_protected?.length?` Skipped ${result.skipped_protected.length} manually protected.`:''}`,'success');await onApplied(result);}}catch(error){notify(error.message,'danger');}finally{action.disabled=false;action.textContent=original;}};};
  async function loadDownloadedLibrary() {
    const parameters = musicFilesQuery(downloadedUiState);
    try {
      const result=await downloadedRequestState.request(`/api/downloaded-library?${parameters}`,{errorMessage:'Music Files could not be loaded.'});
      if(result.status!=='applied')return;
      var payload=result.payload;
    } catch (error) {
      throw error;
    }
    setLoadedAt(Date.now());
    const tracks = payload.tracks || [];
    const paginationData = payload.pagination || {page:1,page_size:50,filtered_total:tracks.length,catalog_total:tracks.length,total_pages:1};
    const analyzableTotal = Number(paginationData.analyzable_total || 0);
    downloadedRequestState.setPage(paginationData.page);
    const root = $('#downloaded-list');
    if (compactAudioIsWithin('#downloaded-list')) stopCompactAudio();
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
    syncControlUnlessEditing(search, downloadedUiState.search);
    genreSelect.value = [...genreSelect.options].some(item => item.value === downloadedUiState.genre) ? downloadedUiState.genre : 'all';
    detailedGenreSelect.value=[...detailedGenreSelect.options].some(item=>item.value===downloadedUiState.detailedGenre)?downloadedUiState.detailedGenre:'all';
    playlistSelect.value = [...playlistSelect.options].some(item => item.value === downloadedUiState.playlist) ? downloadedUiState.playlist : 'all';
    analysisSelect.value = downloadedUiState.analysis;
    artworkSelect.value = downloadedUiState.artwork;
    qualitySelect.value = downloadedUiState.quality;
    sort.value = downloadedUiState.sort;
    const selectAll = $('#downloaded-select-all'); const clearSelection = $('#downloaded-clear-selection'); const analyzeSelected = $('#downloaded-analyze-selected'); const keyAnalyzeSelected=$('#downloaded-key-analyze-selected'); const analyzeMatching = $('#downloaded-analyze-matching'); const reanalyzeSelected = $('#downloaded-reanalyze-selected'); const reanalyzeMatching = $('#downloaded-reanalyze-matching'); const downloadSelected = $('#downloaded-download-selected'); const removeSelected = $('#downloaded-remove-selected'); const changeGenre = $('#downloaded-change-genre'); const editIdentity=$('#downloaded-edit-identity'); const retagSelected = $('#downloaded-retag-selected');
    const rescanGenres = $('#downloaded-rescan-genres');
    const inferMissingIdentities=$('#downloaded-infer-missing-identities');
    const reinferUnprotected=$('#downloaded-reinfer-unprotected');
    const vocabularyReview=$('#downloaded-vocabulary-review');
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
      const receipt = operationReceiptText(batch.receipt);
      $('#downloaded-progress-detail').textContent = receipt ? `${detail}\n${receipt}` : detail;
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
      const response=await api.raw('/api/downloaded-library/integrity-repair',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,item_ids:items.map(item=>item.id)})}); const payload=await response.json();
      if(!response.ok){integrityStatus.textContent=api.errorMessage(payload,'The repair could not be completed.');return;}
      integrityStatus.textContent=`${operationReceiptText(payload.receipt)} · Run the scan again to verify.`; await loadDownloadedLibrary(); integrityRoot.open=true;
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
      integrityResults.querySelectorAll('.merge-duplicate').forEach(button=>button.onclick=async()=>{const ids=button.dataset.ids.split(',').map(Number);const survivor=Number(button.closest('li').querySelector('input:checked')?.value||ids[0]);const duplicate=ids.find(id=>id!==survivor);if(!duplicate||!await confirmAction('Merge these catalog records? Analysis, playlists, feedback, and verified keys will follow the selected recording. The other WAV will remain on disk.', {title:'Merge duplicate records', acceptLabel:'Merge records'}))return;button.disabled=true;const response=await api.raw('/api/downloaded-library/merge-duplicate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({survivor_id:survivor,duplicate_id:duplicate})});const result=await response.json();if(!response.ok){button.disabled=false;alert(api.errorMessage(result,'Could not merge the duplicate.'));return;}await loadDownloadedLibrary();integrityButton.click();});
      integrityResults.querySelectorAll('.keep-duplicate-separate').forEach(button=>button.onclick=async()=>{const id=Number(button.dataset.id);if(!id)return;button.disabled=true;const response=await api.raw(`/api/downloaded-library/tracks/${id}/keep-separate`,{method:'POST'});const result=await response.json();if(!response.ok){button.disabled=false;alert(api.errorMessage(result,'Could not separate the recording.'));return;}await loadDownloadedLibrary();integrityButton.click();});
    };
    const watchIntegrityScan=batchId=>runBackgroundTask({key:'integrity-scan',url:`/api/downloaded-library/integrity-scan/${batchId}`,interval:700,update:batch=>{integrityRoot.open=true;integrityButton.disabled=true;integrityButton.textContent='Scanning…';integrityStatus.textContent=`${batch.stage} · ${Math.round(batch.progress||0)}%`;},complete:batch=>{integrityButton.disabled=false;integrityButton.textContent='Scan collection';renderIntegrityResults(batch);},fail:error=>{integrityButton.disabled=false;integrityButton.textContent='Scan collection';integrityStatus.textContent=error.message;}});
    integrityButton.onclick=async()=>{integrityButton.disabled=true;integrityButton.textContent='Starting…';integrityResults.replaceChildren();integrityStatus.textContent='Indexing catalog and music folders…';const response=await api.raw('/api/downloaded-library/integrity-scan',{method:'POST'});const batch=await response.json();if(!response.ok){integrityButton.disabled=false;integrityButton.textContent='Scan collection';integrityStatus.textContent=api.errorMessage(batch,'Could not start integrity scan.');return;}watchIntegrityScan(batch.batch_id);};
    summary.querySelector('.sidebar-rescan').onclick = () => rescanGenres.click();
    summary.querySelector('.sidebar-reconcile').onclick = () => reconcileFiles.click();
    summary.querySelector('.sidebar-artwork').onclick = () => syncArtwork.click();
    vocabularyReview.onclick=async()=>{
      const dialog=$('#identity-vocabulary-dialog'),list=dialog.querySelector('.identity-vocabulary-list'),summaryRoot=dialog.querySelector('.identity-vocabulary-summary');
      dialog.showModal();list.innerHTML='<p>Scanning playlist vocabulary…</p>';
      try{
        const response=await api.raw('/api/downloaded-library/descriptors/vocabulary',{cache:'no-store'}),payload=await response.json();if(!response.ok)throw new Error(api.errorMessage(payload,'Vocabulary review could not be loaded.'));
        summaryRoot.textContent=`${payload.unreviewed} unreviewed · ${payload.approved} approved · ${payload.ignored} ignored`;
        const categories=[['cultural','Cultural / regional'],['rhythm','Rhythmic influence'],['sound','Sound character'],['vocal','Vocal identity'],['role','Energy / DJ role'],['context','Context / crate'],['familiarity','Audience familiarity']];
        list.innerHTML=(payload.items||[]).map(item=>{const rule=item.rule||{},status=rule.status||'unreviewed';return `<article class="identity-vocabulary-row" data-signal="${escapeHtml(item.signal)}" data-status="${escapeHtml(status)}"><div><strong>${escapeHtml(item.signal)}</strong><span>${item.track_count} affected track${item.track_count===1?'':'s'}</span><small>${escapeHtml((item.examples||[]).join(' · '))}</small></div><label>Category<select class="vocabulary-category"><option value="">Choose a category…</option>${categories.map(([value,label])=>`<option value="${value}"${rule.category===value?' selected':''}>${label}</option>`).join('')}</select></label><label>Normalized meaning<input class="vocabulary-meaning" value="${escapeHtml(rule.value||item.signal)}" placeholder="Reusable identity tag"></label><div><button type="button" class="approve-vocabulary">Approve</button><button type="button" class="button secondary ignore-vocabulary">Ignore</button></div></article>`;}).join('')||'<p>No unreviewed playlist vocabulary remains.</p>';
        const saveRule=async(row,status,button)=>{const category=row.querySelector('.vocabulary-category')?.value||'',value=row.querySelector('.vocabulary-meaning')?.value.trim()||'';if(status==='approved'&&(!category||!value)){notify('Choose a category and a specific normalized meaning before approving.','danger');return;}button.disabled=true;const request={signal:row.dataset.signal,status,category:status==='approved'?category:'',value:status==='approved'?value:''};try{const result=await api.raw('/api/downloaded-library/descriptors/vocabulary',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request)}),body=await result.json();if(!result.ok)throw new Error(api.errorMessage(body,'Vocabulary rule could not be saved.'));row.remove();if(!list.querySelector('.identity-vocabulary-row'))list.innerHTML='<p>No unreviewed playlist vocabulary remains.</p>';notify(`${request.signal}: ${status}. ${body.updated_tracks} matching tracks refreshed. Survives restart: Yes.`,'success',{timeout:8000});setLoadedAt(0);invalidateLibrary();}catch(error){notify(error.message,'danger');button.disabled=false;}};
        list.querySelectorAll('.approve-vocabulary').forEach(button=>button.onclick=()=>saveRule(button.closest('.identity-vocabulary-row'),'approved',button));
        list.querySelectorAll('.ignore-vocabulary').forEach(button=>button.onclick=()=>saveRule(button.closest('.identity-vocabulary-row'),'ignored',button));
      }catch(error){list.innerHTML=`<p class="danger-text">${escapeHtml(error.message)}</p>`;}
    };
    $('#identity-vocabulary-dialog').querySelector('.identity-vocabulary-close').onclick=()=>$('#identity-vocabulary-dialog').close();
    inferMissingIdentities.onclick=async()=>{
      if(!paginationData.catalog_total||!await confirmAction(`Infer musical identity for every catalog track that has no inferred or playlist-derived tags? Existing manual tags will be preserved.`,{title:'Infer missing identities',acceptLabel:'Infer identities'}))return;
      inferMissingIdentities.disabled=true;inferMissingIdentities.textContent='Inferring identities…';
      renderMaintenanceProgress('Inferring missing identities',{total:paginationData.catalog_total,processed:0,status:'processing'},'Reading genre, playlist, title, vocal, energy, role, and timing evidence…');
      try{const response=await api.raw('/api/downloaded-library/descriptors/infer-missing',{method:'POST'}),result=await response.json();if(!response.ok)throw new Error(api.errorMessage(result,'Identity inference failed.'));renderMaintenanceProgress('Identity inference complete',{total:result.requested,processed:result.processed,status:'complete'},`${result.applied} tracks updated · ${result.suggestions_added} tags added · ${result.no_suggestions.length} had insufficient evidence · manual tags preserved · survives restart`);notify(`Identity inference complete: ${result.applied} tracks updated with ${result.suggestions_added} tags.`,'success',{timeout:9000});setLoadedAt(0);invalidateLibrary();await loadDownloadedLibrary();}
      catch(error){renderProgressError('Identity inference failed',error);notify(error.message,'danger');}
      finally{inferMissingIdentities.disabled=false;inferMissingIdentities.textContent='Infer missing identities';}
    };
    reinferUnprotected.onclick=async()=>{
      if(!paginationData.catalog_total||!await confirmAction('Replace machine-generated identity on every track that is not marked “Manually tagged—do not infer”? Manually protected tracks will be skipped.',{title:'Re-infer unprotected tracks',acceptLabel:'Re-infer tracks'}))return;
      reinferUnprotected.disabled=true;reinferUnprotected.textContent='Re-inferring…';
      renderMaintenanceProgress('Re-inferring unprotected identities',{total:paginationData.catalog_total,processed:0,status:'processing'},'Protected manual identities will not be changed.');
      try{const response=await api.raw('/api/downloaded-library/descriptors/reinfer-unprotected',{method:'POST'}),result=await response.json();if(!response.ok)throw new Error(api.errorMessage(result,'Identity re-inference failed.'));renderMaintenanceProgress('Identity re-inference complete',{total:result.requested,processed:result.processed,status:'complete'},`${result.updated} unprotected tracks refreshed · ${result.suggestions_added} tags added · ${result.no_suggestions.length} had insufficient evidence · protected tracks skipped · survives restart`);notify(`Re-inference complete: ${result.updated} unprotected tracks refreshed.`,'success',{timeout:9000});setLoadedAt(0);invalidateLibrary();await loadDownloadedLibrary();}
      catch(error){renderProgressError('Identity re-inference failed',error);notify(error.message,'danger');}
      finally{reinferUnprotected.disabled=false;reinferUnprotected.textContent='Re-infer unprotected';}
    };
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
        const response = await api.raw('/api/downloaded-library/rescan-genres', {method:'POST'});
        const result = await response.json();
        if (!response.ok) throw new Error(api.errorMessage(result, 'Genre rescan failed.'));
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
      try{const response=await api.raw('/api/downloaded-library/reconcile-files',{method:'POST'});const batch=await response.json();if(!response.ok)throw new Error(api.errorMessage(batch,'Could not start file reconciliation.'));reconcileFiles.textContent='Reconciling…';watchReconcile(batch.batch_id);}catch(error){renderProgressError('File reconciliation could not start',error);reconcileFiles.disabled=false;reconcileFiles.textContent='Reconcile files';}
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
        const response = await api.raw('/api/downloaded-library/tracks', {method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_ids:missing.map(item => item.id)})});
        if (!response.ok) { alert(api.errorMessage(await response.json(), 'Could not remove missing entries.')); return; }
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
        const response = await api.raw('/api/downloaded-library/retag-all', {method:'POST'});
        const batch = await response.json();
        if (!response.ok) throw new Error(api.errorMessage(batch, 'Could not start WAV metadata synchronization.'));
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
        const response=await api.raw('/api/downloaded-library/artwork-sync',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_ids:selectedIds})});
        const batch=await response.json();
        if(!response.ok) throw new Error(api.errorMessage(batch, 'Could not start artwork synchronization.'));
        syncArtwork.textContent='Syncing artwork…';
        watchArtworkBatch(batch.batch_id);
      } catch(error) { renderProgressError('Artwork sync could not start',error); syncArtwork.disabled=false; syncArtwork.textContent='Sync artwork'; rescanGenres.disabled=false; retagAll.disabled=false; }
    };
    api.raw('/api/downloaded-library/rescan-genres-latest', {cache:'no-store'}).then(response => response.json()).then(batch => {
      if (batch.status !== 'processing') return;
      rescanGenres.disabled=true; retagAll.disabled=true; rescanGenres.textContent='Rescanning…';
      watchGenreRescan(batch.batch_id);
    }).catch(() => {});
    api.raw('/api/downloaded-library/retag-all-latest', {cache:'no-store'}).then(response => response.json()).then(batch => {
      if (batch.status === 'none') return;
      renderTagFailures(batch,'wav-tags');
      if (batch.status === 'processing') {
        retagAll.disabled = true; retagAll.textContent = 'Syncing all…';
        watchTagBatch(batch.batch_id);
      } else if (batch.failed) {
        $('#downloaded-rescan-message').textContent = `Previous WAV metadata sync · ${batch.tagged} updated · ${batch.skipped || 0} already correct · ${batch.failed} unavailable/failed`;
      }
    }).catch(() => {});
    api.raw('/api/downloaded-library/artwork-sync-latest', {cache:'no-store'}).then(response => response.json()).then(batch => {
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
      editIdentity.disabled = !selected.length;
      retagSelected.disabled = !downloadable.length;
      if(syncArtwork.dataset.busy!=='true') syncArtwork.textContent=selected.length ? `Sync artwork${missingArtwork.length ? ` (${missingArtwork.length})` : ''}` : 'Sync artwork';
      document.querySelector('.downloaded-selection').classList.toggle('has-selection', selected.length > 0);
      cards.forEach(card => { const selected=card.querySelector('.downloaded-check input').checked; card.classList.toggle('is-selected',selected); card.setAttribute('aria-selected',String(selected)); });
      selectAll.checked = cards.length > 0 && cards.every(card => card.querySelector('input').checked);
      selectAll.indeterminate = cards.some(card => card.querySelector('input').checked) && !selectAll.checked;
    };
    editIdentity.onclick=()=>{
      const selected=[...downloadedSelection.values()],single=selected.length===1;
      const selectedIndex=single?tracks.findIndex(item=>Number(item.id)===Number(selected[0].id)):-1,previousTrack=selectedIndex>0?tracks[selectedIndex-1]:null,nextTrack=selectedIndex>=0?tracks[selectedIndex+1]:null;
      const {editor,close}=openDescriptorEditorDialog({descriptors:single?(selected[0].descriptors||[]):[],bulk:!single,protectedFromInference:single?Boolean(selected[0].identity_inference_locked):null,title:single?`Edit identity · ${selected[0].title||selected[0].filename||'Selected track'}`:'Edit identity for selected tracks',subtitle:single?`Track ${selectedIndex+1} of ${tracks.length} in the current filtered list.`:`Apply durable descriptors to ${selected.length} selected tracks.`});
      if(single)bindIdentityProtection(editor,selected[0]);
      editor.querySelector('.cancel-descriptors').onclick=close; editor.querySelector('.close-descriptor-editor').onclick=close;
      bindIdentityInference(editor,()=>[...downloadedSelection.keys()],async()=>{setLoadedAt(0);invalidateLibrary();await loadDownloadedLibrary();});
      const saveButton=editor.querySelector('.save-descriptors');let previousButton=null,nextButton=null;
      if(single){previousButton=document.createElement('button');previousButton.type='button';previousButton.className='button secondary save-previous-descriptors';previousButton.textContent='← Save & previous';previousButton.disabled=!previousTrack;nextButton=document.createElement('button');nextButton.type='button';nextButton.className='save-next-descriptors';nextButton.textContent='Save & next →';nextButton.disabled=!nextTrack;saveButton.after(previousButton,nextButton);}
      const save=async(destination,action)=>{const original=action.textContent,target=destination<0?previousTrack:destination>0?nextTrack:null;action.disabled=true;saveButton.disabled=true;if(previousButton)previousButton.disabled=true;if(nextButton)nextButton.disabled=true;action.textContent='Saving…';try{const result=await saveDescriptorEditor(editor,[...downloadedSelection.keys()]);if(single){selected[0].descriptors=result.values||[];selected[0].identity_inference_locked=Boolean(result.protected_from_inference);}notify(`Requested: update identity for ${result.requested} tracks. Changed: ${result.updated}. Written to: persistent track catalog. Failed: ${result.missing?.length||0}. Survives restart: Yes.`,'success');close();setLoadedAt(0);invalidateLibrary();if(target){downloadedSelection.clear();downloadedSelection.set(Number(target.id),target);cards.forEach(card=>card.querySelector('.downloaded-check input').checked=Number(card.dataset.id)===Number(target.id));refreshSelection();editIdentity.onclick();}else await loadDownloadedLibrary();}catch(error){notify(error.message,'danger');action.disabled=false;saveButton.disabled=false;if(previousButton)previousButton.disabled=!previousTrack;if(nextButton)nextButton.disabled=!nextTrack;action.textContent=original;}};
      saveButton.onclick=event=>save(0,event.currentTarget);
      if(previousButton)previousButton.onclick=event=>save(-1,event.currentTarget);
      if(nextButton)nextButton.onclick=event=>save(1,event.currentTarget);
    };
    const reloadCollectionViews = async () => {
      const previousScroll = window.scrollY;
      await Promise.all([loadDownloadedLibrary(), loadLibrary()]);
      requestAnimationFrame(() => window.scrollTo({top:previousScroll,behavior:'instant'}));
    };
    const matchesCurrentDownloadedFilters = track => {
      const query=downloadedUiState.search.trim().toLowerCase();
      const haystack=`${track.title||''} ${track.artist||''} ${track.genre||''} ${track.genre_category||''} ${(track.playlists||[]).join(' ')} ${(track.descriptors||[]).map(item=>item.value).join(' ')}`.toLowerCase();
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
      if(!matchesCurrentDownloadedFilters(track)){await loadDownloadedLibrary();invalidateLibrary();return false;}
      adjustTrackFacets(before,track);
      card.dataset.title=String(track.title||track.filename||'').toLowerCase();card.dataset.artist=String(track.artist||'').toLowerCase();card.dataset.genre=track.genre_category||'Other';card.dataset.playlists=(track.playlists||[]).join('|');
      card.querySelector('.downloaded-copy h3').textContent=track.title||track.filename;card.querySelector('.downloaded-copy p').textContent=track.artist||'Unknown artist';card.querySelectorAll('.downloaded-genre').forEach(button=>button.textContent=track.genre_category||'Other');const detailed=detailedGenreSummary(track.genre);const detailedButton=card.querySelector('.downloaded-detailed-genre');detailedButton.textContent=detailed.label;detailedButton.title=detailed.title;detailedButton.disabled=detailed.empty;detailedButton.classList.toggle('empty',detailed.empty);card.setAttribute('aria-label',`${track.title||track.filename} by ${track.artist||'Unknown artist'}`);
      const metadataEditor=card.querySelector('.track-metadata-editor');if(metadataEditor){metadataEditor.elements.title.value=track.title||'';metadataEditor.elements.artist.value=track.artist||'';metadataEditor.elements.genre_category.value=track.genre_category||'Other';metadataEditor.elements.genre.value=track.genre||'';metadataEditor.elements.playlist_name.value=(track.playlists||[])[0]||'Imported Singles';metadataEditor.elements.artwork_url.value=track.artwork_url||'';}
      const genreEditor=card.querySelector('.inline-genre-editor');if(genreEditor){const genreSelect=genreEditor.querySelector('.inline-genre-select');if(![...genreSelect.options].some(option=>option.value===track.genre_category))genreSelect.add(option(track.genre_category,track.genre_category));genreSelect.value=track.genre_category||'Other';genreEditor.querySelector('.inline-genre-custom').value='';genreEditor.querySelector('.genre-folder-preview').textContent=`Folder: ${String(track.genre_category||'Other').replace(' / ','/')}/`;}
      if(track.artwork_available){card.querySelector('.downloaded-row-icon').innerHTML=`<img src="/api/downloaded-library/tracks/${track.id}/artwork?thumbnail=true&v=${Date.now()}" alt="" loading="lazy" decoding="async">`;}
      if(downloadedSelection.has(Number(track.id)))downloadedSelection.set(Number(track.id),track);
      invalidateLibrary();refreshSelection();return true;
    };
    const requestPage = (page = 1) => { downloadedRequestState.setPage(page); loadDownloadedLibrary(); };
    const syncFilters = () => { downloadedUiState.search=search.value.trim();downloadedUiState.genre=genreSelect.value;downloadedUiState.detailedGenre=detailedGenreSelect.value;downloadedUiState.playlist=playlistSelect.value; downloadedUiState.analysis=analysisSelect.value; downloadedUiState.artwork=artworkSelect.value; downloadedUiState.quality=qualitySelect.value; downloadedUiState.sort=sort.value; requestPage(1); };
    search.oninput = () => {
      captureTextFilter(search, downloadedUiState);
      downloadedRequestState.debounce(syncFilters);
    };
    genreSelect.onchange = () => {downloadedUiState.detailedGenre='all';detailedGenreSelect.value='all';syncFilters();}; detailedGenreSelect.onchange=syncFilters; playlistSelect.onchange = syncFilters; analysisSelect.onchange = syncFilters; artworkSelect.onchange = syncFilters; qualitySelect.onchange=syncFilters; sort.onchange = syncFilters;
    $('#downloaded-reset-filters').onclick=()=>{downloadedRequestState.reset();loadDownloadedLibrary();};
    pageSizeSelect.onchange = () => { pageSize=Number(pageSizeSelect.value); downloadedRequestState.update({pageSize},{resetPage:true}); localStorage.setItem('music-files-page-size',String(pageSize)); loadDownloadedLibrary(); };
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
    const changePage = page => { downloadedRequestState.setPage(page); loadDownloadedLibrary(); document.querySelector('.downloaded-toolbar').scrollIntoView({behavior:'smooth',block:'start'}); };
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
        const response = await api.raw('/api/downloaded-library/retag', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_ids:trackIds})});
        const result = await response.json();
        if (!response.ok) throw new Error(api.errorMessage(result, 'Could not update WAV metadata.'));
        notify(operationReceiptText(result.receipt), result.failed.length ? 'danger' : 'success', {timeout:9000});
      } catch (error) { alert(error.message); }
      finally { retagSelected.textContent = 'Sync WAV tags'; refreshSelection(); }
    };
    downloadSelected.onclick = async () => {
      const trackIds = [...downloadedSelection.values()].filter(track => track.available).map(track => Number(track.id));
      downloadSelected.disabled = true; downloadSelected.textContent = 'Preparing ZIP…';
      try {
        const response = await api.raw('/api/downloaded-library/download', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_ids:trackIds})});
        if (!response.ok) throw new Error(api.errorMessage(await response.json(), 'Could not prepare the download.'));
        const url = URL.createObjectURL(await response.blob()); const link = document.createElement('a'); link.href = url; link.download = 'Selected Downloaded Tracks - WAVs.zip'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch (error) { alert(error.message); }
      finally { downloadSelected.textContent = 'Download WAVs'; refreshSelection(); }
    };
    analyzeSelected.onclick = async () => {
      const trackIds = [...downloadedSelection.values()].filter(track => track.available && !['queued','processing','complete'].includes(track.analysis_status)).map(track => Number(track.id));
      if (!trackIds.length) return;
      analyzeSelected.disabled = true; analyzeSelected.textContent = 'Adding to queue…';
      try {
        const response = await api.raw('/api/downloaded-library/analyze', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_ids:trackIds})});
        const payload = await response.json();
        if (!response.ok) throw new Error(api.errorMessage(payload, 'Could not queue analysis.'));
        showView('workspace-view'); await loadJobs();
      } catch (error) { alert(error.message); analyzeSelected.textContent = 'Analyze'; refreshSelection(); }
    };
    keyAnalyzeSelected.onclick=()=>{const ids=[...downloadedSelection.values()].filter(track=>track.available).map(track=>Number(track.id));startKeyAnalysis(ids,keyAnalyzeSelected,async()=>{setLoadedAt(0);invalidateLibrary();await loadDownloadedLibrary();});};
    analyzeMatching.onclick = async () => {
      if (!analyzableTotal || !await confirmAction(`Add all ${analyzableTotal} matching track${analyzableTotal===1?'':'s'} that still need analysis to the processing queue? Analysis will run with safe automatic concurrency.`, {title:'Analyze matching tracks', acceptLabel:'Add to queue'})) return;
      analyzeMatching.disabled=true; analyzeMatching.textContent='Adding all to queue…';
      try {
        const response=await api.raw('/api/downloaded-library/analyze-matching',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({search:downloadedUiState.search,genre:downloadedUiState.genre,detailed_genre:downloadedUiState.detailedGenre,playlist:downloadedUiState.playlist,analysis:downloadedUiState.analysis,quality:downloadedUiState.quality,sort:downloadedUiState.sort})});
        const result=await response.json();
        if(!response.ok)throw new Error(api.errorMessage(result,'Could not queue matching tracks.'));
        downloadedSelection.clear();
        showView('workspace-view'); await loadJobs();
      } catch(error) { alert(error.message); analyzeMatching.disabled=false; analyzeMatching.textContent=`Analyze all matching (${analyzableTotal})`; }
    };
    const queueReanalysis = async (url, body, button, count) => {
      const estimatedMinutes = Math.max(1, Math.ceil(count * 11 / 2 / 60));
      if (!count || !await confirmAction(`Reanalyze ${count} track${count===1?'':'s'} without changing the audio files? Estimated analysis time is about ${estimatedMinutes} minute${estimatedMinutes===1?'':'s'}. Existing artwork, genres, metadata, cues, and verified keys will be preserved.`, {title:'Reanalyze matching tracks', acceptLabel:'Reanalyze'})) return;
      const original = button.textContent; button.disabled = true; button.textContent = 'Adding to queue…';
      try {
        const response = await api.raw(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); const result=await response.json();
        if(!response.ok)throw new Error(api.errorMessage(result,'Could not queue reanalysis.'));
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
        const response = await api.raw('/api/downloaded-library/tracks', {method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_ids:trackIds})});
        if (!response.ok) throw new Error(api.errorMessage(await response.json(), 'Could not remove the selected tracks.'));
        trackIds.forEach(id => downloadedSelection.delete(Number(id)));
        await loadDownloadedLibrary();
      } catch (error) { alert(error.message); removeSelected.textContent = 'Remove'; refreshSelection(); }
    };
    root.querySelectorAll('.remove-downloaded').forEach(button => button.onclick = async () => {
      const card = button.closest('.downloaded-card');
      if (!await confirmAction('Remove this track from the master catalog? The WAV file will remain on disk.', {title:'Remove track', acceptLabel:'Remove', danger:true})) return;
      await api.raw(`/api/downloaded-library/tracks/${card.dataset.id}`, {method:'DELETE'}); await reloadCollectionViews();
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
          const response=await api.raw(`/api/downloaded-library/tracks/${card.dataset.id}/metadata`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
          const payload=await response.json(); if(!response.ok) throw new Error(api.errorMessage(payload,'Could not update metadata.'));
          notify(operationReceiptText(payload.receipt), payload.receipt?.failures?.length ? 'danger' : 'success', {timeout:9000});
          downloadedSelection.delete(Number(card.dataset.id));const nextCard=metadataCards[index+1]||null;
          if(advance)metadataReview={id:nextCard?Number(nextCard.dataset.id):null};
          const stayed=await applyTrackPatch(card,{...payload,playlists:[payload.playlist_name]});
          if(stayed){editor.hidden=true;if(advance&&nextCard?.isConnected){metadataReview=null;openMetadataAt(index+1);}else if(advance){await loadDownloadedLibrary();}else card.focus();}
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
      inspector.innerHTML = `<div class="inspector-head"><div><p class="eyebrow">QUICK VIEW · ${escapeHtml(identity)}</p><h2>${escapeHtml(track.title || track.filename)}</h2><span>${escapeHtml(track.artist || 'Unknown artist')}</span></div><button type="button" class="close-inspector" aria-label="Close inspector">×</button></div>${preview}<div class="inspector-metrics"><button type="button" class="inspector-genre-trigger" title="Change genre"><b>${escapeHtml(track.genre_category || 'Other')}</b><span>Genre</span></button><p><b>${clock(track.duration_seconds)}</b><span>Length</span></p><p><b>${escapeHtml((track.analysis_status || 'not_analyzed').replaceAll('_',' '))}</b><span>Analysis</span></p></div>${genreEditorMarkup(track.genre_category || 'Other', track.suggested_genre || '', true)}<section class="inspector-family" hidden><div class="inspector-family-heading"><div><b>Recording family</b><span>Originals, remixes, edits, and alternate versions</span></div><div class="inspector-family-heading-actions"><button type="button" class="button secondary inspector-family-toggle">Link as version of…</button><button type="button" class="button secondary inspector-family-close" aria-label="Close recording family">×</button></div></div><div class="inspector-family-content"><p>Loading related versions…</p></div><form class="inspector-family-link" hidden><label>Target track ID<input name="target" placeholder="HOU-002386-ORG"></label><label>Relationship<select name="relationship"><option value="RMX">Remix</option><option value="EXT">Extended mix</option><option value="RADIO">Radio edit</option><option value="LIVE">Live version</option><option value="INST">Instrumental</option><option value="ACAP">Acapella</option><option value="REM">Remaster</option><option value="ORG">Original / alternate original</option></select></label><button type="submit">Link version</button><small>Choose a suggestion below or enter the visible genre-based track ID.</small></form><div class="inspector-family-suggestions"></div></section><details class="inspector-metadata"><summary>File & source details</summary><dl><dt>Recording ID</dt><dd>${escapeHtml(identity)}</dd><dt>Identity basis</dt><dd>${escapeHtml(track.identity_reason || 'Catalog assignment')}</dd><dt>Detailed tags</dt><dd>${escapeHtml(track.genre || 'No metadata')}</dd><dt>Source playlist</dt><dd>${escapeHtml((track.playlists || []).join(', ') || 'Imported Singles')}</dd><dt>Filename</dt><dd>${escapeHtml(track.filename || '')}</dd><dt>Absolute path</dt><dd class="inspector-path">${escapeHtml(track.absolute_path || 'Path unavailable')}</dd></dl></details><div class="inspector-actions">${track.completed_library_job_id ? '<button type="button" class="button secondary inspector-library">View in DJ Library</button>' : ''}<button type="button" class="button secondary inspector-edit-metadata">Edit metadata</button><button type="button" class="button secondary inspector-edit-genre">Change genre only</button><button type="button" class="button secondary inspector-edit-identity">Musical identity${track.descriptors?.length?` (${track.descriptors.length})`:''}</button><button type="button" class="button secondary inspector-manage-family">Recording family</button>${track.available ? `<button type="button" class="button secondary inspector-copy-path">Copy path</button><button type="button" class="button secondary inspector-reveal">Reveal in Finder</button><a class="button secondary" href="/api/downloaded-library/tracks/${track.id}/download">Download WAV</a>` : ''}</div>`;
      inspector.querySelector('.inspector-edit-identity').onclick=()=>{
        const startingIndex=tracks.findIndex(item=>Number(item.id)===Number(track.id));
        const openIdentityEditor=targetIndex=>{
          const target=tracks[targetIndex];if(!target)return;
          const {editor,close}=openDescriptorEditorDialog({descriptors:target.descriptors||[],protectedFromInference:Boolean(target.identity_inference_locked),title:`Musical identity · ${target.title||target.filename}`,subtitle:`Track ${targetIndex+1} of ${tracks.length} in the current filtered list.`});
          bindIdentityProtection(editor,target);
          bindIdentityInference(editor,[Number(target.id)]);
          editor.querySelector('.cancel-descriptors').onclick=close;editor.querySelector('.close-descriptor-editor').onclick=close;
          const saveButton=editor.querySelector('.save-descriptors'),previousButton=document.createElement('button'),nextButton=document.createElement('button');
          previousButton.type='button';previousButton.className='button secondary save-previous-descriptors';previousButton.textContent='← Save & previous';previousButton.disabled=targetIndex<=0;
          nextButton.type='button';nextButton.className='save-next-descriptors';nextButton.textContent='Save & next →';nextButton.disabled=targetIndex>=tracks.length-1;
          saveButton.after(previousButton,nextButton);
          const save=async(offset,action)=>{const original=action.textContent;action.disabled=true;saveButton.disabled=true;previousButton.disabled=true;nextButton.disabled=true;action.textContent='Saving…';try{const result=await saveDescriptorEditor(editor,[Number(target.id)]);target.descriptors=result.values||[];target.identity_inference_locked=Boolean(result.protected_from_inference);if(Number(target.id)===Number(track.id))inspector.querySelector('.inspector-edit-identity').textContent=`Musical identity${target.descriptors.length?` (${target.descriptors.length})`:''}`;close();notify(`Musical identity saved for ${target.title||target.filename}. It will survive restart.`,'success');setLoadedAt(0);invalidateLibrary();if(offset)openIdentityEditor(targetIndex+offset);}catch(error){notify(error.message,'danger');action.disabled=false;saveButton.disabled=false;previousButton.disabled=targetIndex<=0;nextButton.disabled=targetIndex>=tracks.length-1;action.textContent=original;}};
          saveButton.onclick=event=>save(0,event.currentTarget);
          previousButton.onclick=event=>save(-1,event.currentTarget);
          nextButton.onclick=event=>save(1,event.currentTarget);
        };
        openIdentityEditor(Math.max(0,startingIndex));
      };
      inspector.querySelector('.close-inspector').onclick = () => closeDownloadedInspector({restoreFocus:true});
      inspector.querySelector('.inspector-edit-metadata').onclick = () => { const editor=card.querySelector('.track-metadata-editor'); closeDownloadedInspector(); editor.hidden=false; card.scrollIntoView({behavior:'smooth',block:'center'}); editor.elements.title.focus(); };
      const inspectorGenreEditor=inspector.querySelector('.inline-genre-editor');
      const openInspectorGenre=()=>{inspectorGenreEditor.hidden=false;refreshSearchableSelects();(inspectorGenreEditor.querySelector('.select-search-input')||inspectorGenreEditor.querySelector('.inline-genre-custom')).focus();};
      inspector.querySelector('.inspector-genre-trigger').onclick=openInspectorGenre;
      inspector.querySelector('.inspector-edit-genre').onclick=openInspectorGenre;
      bindGenreEditor(inspectorGenreEditor,()=>[Number(track.id)],async payload=>{await applyTrackPatch(card,{genre_category:payload.genre_category});inspectorGenreEditor.hidden=true;inspector.querySelector('.inspector-genre-trigger b').textContent=payload.genre_category;});
      inspector.querySelector('.inspector-library')?.addEventListener('click', () => { closeDownloadedInspector(); showView('library-view'); });
      inspector.querySelector('.inspector-copy-path')?.addEventListener('click', async event => {try{await navigator.clipboard.writeText(track.absolute_path||'');event.currentTarget.textContent='Path copied';}catch(_){event.currentTarget.textContent='Copy failed';}});
      inspector.querySelector('.inspector-reveal')?.addEventListener('click', async event => {const response=await api.raw(`/api/downloaded-library/tracks/${track.id}/reveal`,{method:'POST'}),payload=await response.json();event.currentTarget.textContent=response.ok?'Revealed in Finder':api.errorMessage(payload,'Could not reveal');});
      inspector.querySelector('.inspector-analyze-key')?.addEventListener('click',async event=>{const action=event.currentTarget,status=inspector.querySelector('.key-analysis-result');action.disabled=true;action.textContent='Analyzing key…';status.textContent='Comparing tonal estimates; all other analysis remains unchanged.';try{const response=await api.raw(`/api/downloaded-library/tracks/${track.id}/analyze-key`,{method:'POST'}),payload=await response.json();if(!response.ok)throw new Error(api.errorMessage(payload,'Key analysis failed.'));track.detected_key=payload.detected_key;track.key_confidence=payload.key_confidence;track.key_analyzed_at=payload.key_analyzed_at;inspector.querySelector('.inspector-key-value').textContent=payload.detected_key||'Unknown';inspector.querySelector('.inspector-key-value').nextElementSibling.textContent=`Key · ${Math.round(Number(payload.key_confidence||0))}%`;status.textContent=`Complete · ${payload.detected_key} is the current estimate.`;action.textContent='Analyze key again';}catch(error){status.textContent=error.message;action.textContent='Try key analysis again';}finally{action.disabled=false;}});
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
      const loadFamily=async()=>{const response=await api.raw(`/api/downloaded-library/tracks/${track.id}/family`),payload=await response.json();if(!response.ok){familyContent.innerHTML=`<p>${escapeHtml(api.errorMessage(payload,'Related versions could not be loaded.'))}</p>`;return;}familyContent.innerHTML=payload.family.map(member=>`<article><div><b>${escapeHtml(member.title||member.filename)}</b><span>${escapeHtml(member.artist||'Unknown artist')} · ${escapeHtml(member.recording_code)}-${escapeHtml(member.version_code||'ORG')}</span></div>${Number(member.id)===Number(track.id)?'<em>Current</em>':`<button type="button" data-family-target="${member.id}">View</button>`}</article>`).join('');if(payload.family.length>1)familyContent.insertAdjacentHTML('beforeend','<button type="button" class="button secondary inspector-family-unlink">Unlink current track</button>');familySuggestions.innerHTML=payload.suggestions.length?`<b>Suggested families</b>${payload.suggestions.map(item=>`<button type="button" data-suggestion-id="${escapeHtml(item.track.recording_code)}-${escapeHtml(item.track.version_code||'ORG')}"><span>${escapeHtml(item.track.title||item.track.filename)} · ${escapeHtml(item.track.artist||'Unknown artist')}</span><small>${item.score}% · ${escapeHtml(item.reasons.join(', '))}</small></button>`).join('')}`:'<small>No strong automatic suggestions. Enter a target track ID to link manually.</small>';familySuggestions.querySelectorAll('[data-suggestion-id]').forEach(option=>option.onclick=()=>{familyForm.hidden=false;familyForm.elements.target.value=option.dataset.suggestionId;familyForm.elements.relationship.focus();});familyContent.querySelector('.inspector-family-unlink')?.addEventListener('click',async()=>{if(!await confirmAction('Unlink this version into its own recording family? You can link it again later.', {title:'Unlink recording version', acceptLabel:'Unlink'}))return;const result=await api.raw(`/api/downloaded-library/tracks/${track.id}/unlink-version`,{method:'POST'});if(result.ok){await loadDownloadedLibrary();closeDownloadedInspector();}});};
      familyForm.onsubmit=async event=>{event.preventDefault();const target=familyForm.elements.target.value.trim();if(!target){familyForm.querySelector('small').textContent='Enter a valid track ID.';return;}const response=await api.raw(`/api/downloaded-library/tracks/${track.id}/link-version`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target_identity:target,relationship:familyForm.elements.relationship.value})}),payload=await response.json();if(!response.ok){familyForm.querySelector('small').textContent=api.errorMessage(payload,'Could not link this version.');return;}await loadDownloadedLibrary();closeDownloadedInspector();};
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
    if(metadataReview){const requested=root.querySelector(`.downloaded-card[data-id="${metadataReview.id}"]`)||metadataCards[0];metadataReview=null;requested?.querySelector('.edit-track-metadata')?.click();}
  }

  return {loadDownloadedLibrary};
}

export function resetMusicFilesFilters(state) {
  Object.assign(state, {search:'',genre:'all',detailedGenre:'all',playlist:'all',analysis:'all',artwork:'all',quality:'all',sort:'newest',page:1});
  return state;
}
