import {clock, escapeHtml, fraction, option, pct, renderTrackPagination, reportDate} from './shared-components.js';
import {useFrontendServices} from './frontend-services.js';

export function createReportingFeature({
  services, loadJobs, renderLibraryIntelligence, startKeyAnalysis,
}) {
  const {api, $, $$, notify} = useFrontendServices(services);
  let reportSongs = [];
  let reportJobs = [];
  let reportFeedback = [];
  let reportKeyVerificationStats = {items:[], total:0, detector_accuracy:{}};
  let reportDetailBodies = new Map();
  let reportPage = 1;
  let reportPageSize = 50;
  async function loadAnalysis(jobs = null) {
    const availableJobs = jobs || await api.raw('/api/jobs', {cache:'no-store'}).then(r => r.json());
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
  
  function candidateLabel(candidate) { return candidate ? `${candidate.extension_bars} bars · ${pct(candidate.loop_quality)}` : 'Preserved'; }
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
      const response = await api.raw('/api/report-feedback', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({source_name:form.dataset.source, position:form.elements.position.value, accepted:form.elements.accepted.value === 'true', tags:form.elements.tags.value, notes:form.elements.notes.value})});
      button.disabled = false;
      if (!response.ok) { message.textContent = api.errorMessage(await response.json(), 'Could not save feedback.'); return; }
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
        const response = await api.raw(`/api/key-verifications/${encodeURIComponent(form.dataset.source)}`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({source_name:form.dataset.source, verified_key:form.elements.verified_key.value, detected_key:form.dataset.detected, candidates:song?.key_candidates || [], notes:form.elements.notes.value})});
        if (!response.ok) { message.textContent = api.errorMessage(await response.json(), 'Could not verify key.'); return; }
        message.textContent = 'Key verified'; await loadReports();
      });
      const clear = form.querySelector('.clear-key-verification');
      if (clear) clear.onclick = async () => { clear.disabled = true; await api.raw(`/api/key-verifications/${encodeURIComponent(form.dataset.source)}`, {method:'DELETE'}); await loadReports(); };
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
  
  async function loadReports() {
    const [report, analytics, jobs, feedback, keyStats] = await Promise.all([api.raw('/api/report').then(r => r.json()), api.raw('/api/analytics').then(r => r.json()), api.raw('/api/report-audio-index').then(r => r.json()), api.raw('/api/report-feedback').then(r => r.json()), api.raw('/api/key-verifications').then(r => r.json())]);
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
  
  return {loadAnalysis, loadReports};
}
