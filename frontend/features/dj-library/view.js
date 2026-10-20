import { useFrontendServices } from '../../core/frontend-services.js';

import {
  LIBRARY_ROLE_INFO,
  camelotKey,
  effectivePreset,
  energyBand,
  formatLibraryKey,
  libraryRoles,
  normalizedKey,
  songEnergy,
  timingProfile,
  vocalProfile,
} from './model.js';

export function createDjLibraryView({
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
  reload,
  filters,
  selection,
}) {
  const { api, $, notify, confirmAction, descriptorChipsMarkup, descriptorEditorMarkup, saveDescriptorEditor } =
    useFrontendServices(services);
  const { bindIdentityInference } = selection;

  async function render({ catalog, grouped, jobs, analysisByTrack, downloadedByJob }) {
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
    const cards = [...grouped.values()].reverse().map((versions) => {
      const latest = versions.at(-1);
      const config = JSON.parse(latest.config_json || '{}');
      const analysisOnly = Boolean(config.analysis_only);
      const versioned = String(latest.extended_path || '').includes('/versions/');
      const reviewPending = latest.review_status === 'pending';
      const choice = config.manual_candidate_selection
        ? `Manual choices: intro ${config.intro_candidate ?? '—'} · outro ${config.outro_candidate ?? '—'}`
        : 'Automatic ranking';
      const generationCount = Number(latest.generation_count || versions.length);
      const reprocessLabel = analysisOnly ? 'Extend track' : 'Configure reprocess';
      return `<article class="panel library-card" data-job-id="${latest.id}"><div class="library-head"><div><p class="eyebrow">LATEST · GENERATION ${latest._generation}${analysisOnly ? ' · ANALYZED' : ''}</p><h2>${escapeHtml(latest.source_name)}</h2><span>${escapeHtml(analysisOnly ? 'DJ analysis complete · original preserved' : choice)}</span></div><div class="library-head-actions"><button class="button secondary library-reprocess" data-closed-label="${reprocessLabel}">${reprocessLabel}</button>${analysisOnly ? '' : `<button class="button secondary library-review">${reviewPending ? 'Open review' : 'Create review'}</button>`}<button class="button secondary open-latest">Show full details</button></div></div>${libraryReprocessForm(latest, config)}<div class="library-metrics"><p><b>${latest.bpm ? Number(latest.bpm).toFixed(1) : '—'}</b><span>BPM</span></p><p><b class="library-key-value">—</b><span>Key</span></p><p><b>${analysisOnly ? 'Not extended' : latest.intro_quality == null ? 'Preserved' : pct(latest.intro_quality)}</b><span>Intro</span></p><p><b>${analysisOnly ? 'Not extended' : latest.outro_quality == null ? 'Preserved' : pct(latest.outro_quality)}</b><span>Outro</span></p><p><b>${reportDate(latest.updated_at)}</b><span>Processed</span></p></div><div class="library-player"><span>${analysisOnly ? 'Original analyzed track' : 'Newest extended edit'}</span><audio controls preload="none" data-src="/api/jobs/${latest.id}/audio/${analysisOnly ? 'wav' : 'extended'}"></audio></div><div class="library-downloads"><a class="button secondary" href="/api/jobs/${latest.id}/download/wav">Source WAV</a>${!analysisOnly && versioned ? `<a class="button secondary" href="/api/jobs/${latest.id}/download/extended">Download newest extended WAV</a>` : analysisOnly ? '<span>Choose Extend track whenever you want to create an edit.</span>' : '<span>Reprocess once to create an immutable downloadable generation.</span>'}</div><div class="library-detail-host"></div><details class="version-history" data-loaded="false"><summary>${generationCount} generation${generationCount === 1 ? '' : 's'} · view version history</summary><ul><li class="muted-copy">Open to load version history.</li></ul></details></article>`;
    });
    root.innerHTML = cards.join('') || '<div class="empty">No tracks match these filters.</div>';
    root.querySelectorAll('.library-card').forEach((card) => {
      const latest = jobs.find((job) => String(job.id) === card.dataset.jobId);
      const analysis = analysisByTrack.get(latest.source_name.toLowerCase()) || {};
      let latestConfig = {};
      try {
        latestConfig = JSON.parse(latest.config_json || '{}');
      } catch (_) {
        latestConfig = {};
      }
      const analysisOnly = Boolean(latestConfig.analysis_only);
      const reviewPending = latest.review_status === 'pending';
      const downloadedTrack = downloadedByJob.get(Number(latest.id));
      const category = normalizedGenreCategory(
        downloadedTrack?.genre_category || analysis.detected_style || 'Unclassified',
      );
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
      card.dataset.result =
        latest.review_status === 'pending'
          ? 'review'
          : latest.intro_quality != null || latest.outro_quality != null
            ? 'extended'
            : 'preserved';
      card.dataset.quality = downloadedTrack?.audio_quality_label || 'unanalyzed';
      const description = card.querySelector('.library-head>div>span');
      const presetLabel = card.dataset.requestedPreset === 'auto' ? `auto → ${resolvedPreset}` : resolvedPreset;
      description.textContent = `${category}${downloadedTrack ? ' · library genre' : ' · detected category'} · ${presetLabel} · ${description.textContent}`;
      const keyValue = card.querySelector('.library-key-value');
      keyValue.dataset.standard = normalizedKey(analysis);
      keyValue.textContent = formatLibraryKey(analysis);
      card
        .querySelector('.library-head-actions')
        .insertAdjacentHTML(
          'beforeend',
          '<button class="button secondary remove-library-track">Remove from library</button>',
        );
      if (downloadedTrack) {
        card
          .querySelector('.library-head-actions')
          .insertAdjacentHTML(
            'afterbegin',
            '<button class="button secondary edit-library-identity">Edit identity</button><button class="button secondary edit-library-genre">Edit genre</button>',
          );
        card
          .querySelector('.library-head')
          .insertAdjacentHTML(
            'afterend',
            `<div class="library-identity-summary">${descriptorChipsMarkup(downloadedTrack.descriptors || [], { detailed: true })}</div>${genreEditorMarkup(downloadedTrack.genre_category || 'Other', downloadedTrack.suggested_genre || '', true)}${descriptorEditorMarkup(downloadedTrack.descriptors || [])}`,
          );
      }
      const resultLabel =
        latest.review_status === 'pending'
          ? 'Awaiting review'
          : analysisOnly
            ? 'Analyzed only'
            : latest.intro_quality != null || latest.outro_quality != null
              ? 'Extended'
              : 'Preserved';
      const sourceStem = latest.source_name.replace(/\.[^.]+$/, '');
      const sourceParts = sourceStem.split(' - ');
      const trackTitle =
        downloadedTrack?.title || (sourceParts.length > 1 ? sourceParts.slice(1).join(' - ') : sourceStem);
      const trackArtist = downloadedTrack?.artist || (sourceParts.length > 1 ? sourceParts[0] : 'Unknown artist');
      const trackArtwork = downloadedTrack?.artwork_available
        ? `<img src="/api/downloaded-library/tracks/${downloadedTrack.id}/artwork?thumbnail=true" alt="" loading="lazy" decoding="async">`
        : '♫';
      card.dataset.artist = String(trackArtist).toLowerCase();
      const body = document.createElement('div');
      body.className = 'library-card-body';
      body.hidden = true;
      [...card.children].forEach((child) => body.append(child));
      card.append(body);
      const identity = downloadedTrack?.recording_code
        ? `${downloadedTrack.recording_code}-${downloadedTrack.version_code || 'ORG'}`
        : '';
      const qualityScore = downloadedTrack?.audio_quality_score;
      const qualityTarget = downloadedTrack?.audio_quality?.target_status;
      const qualitySuffix =
        qualityTarget === 'meets_target'
          ? ' · Target met'
          : qualityTarget === 'below_target'
            ? ' · Below target'
            : qualityTarget === 'unverified'
              ? ' · Unverified'
              : '';
      const qualityText =
        qualityScore == null ? 'Quality pending' : `Quality ${Math.round(Number(qualityScore))}${qualitySuffix}`;
      card.insertAdjacentHTML(
        'afterbegin',
        `<div class="library-compact-row" role="button" tabindex="0" aria-expanded="false" aria-label="Show DJ details for ${escapeHtml(trackTitle)}"><label class="library-track-select"><input type="checkbox" value="${card.dataset.jobId}" aria-label="Select ${escapeHtml(trackTitle)}"><span></span></label><div class="library-row-icon">${trackArtwork}</div><div class="library-row-title"><h3>${escapeHtml(trackTitle)}</h3><span class="library-row-artist">${escapeHtml(trackArtist)}</span><small>${escapeHtml(category)}${identity ? ` · ${escapeHtml(identity)}` : ''}</small></div><div class="library-row-metric"><b>${Number(analysis.bpm || latest.bpm || 0).toFixed(1)}</b><span>BPM</span></div><div class="library-row-metric"><b>${escapeHtml(formatLibraryKey(analysis))}</b><span>Key / Camelot</span></div><div class="library-row-metric"><b>${escapeHtml(energyBand(energy))}</b><span>Energy</span></div><div class="library-row-role">${roles
          .slice(0, 2)
          .map((role) => `<span>${escapeHtml(LIBRARY_ROLE_INFO[role]?.[0] || role)}</span>`)
          .join(
            '',
          )}</div><span class="library-result" data-result="${card.dataset.result}">${resultLabel}<small>${escapeHtml(qualityText)}</small></span>${compactAudioMarkup(`/api/jobs/${latest.id}/audio/${analysisOnly ? 'wav' : 'extended'}`, latest.duration_seconds || analysis.duration_seconds || 0)}<details class="library-row-actions"><summary aria-label="Library track actions">•••</summary><div><button type="button" class="compact-remove danger-text">Remove from Library</button></div></details></div>`,
      );
      if (downloadedTrack?.descriptors?.length)
        card
          .querySelector('.library-row-title')
          .insertAdjacentHTML('beforeend', descriptorChipsMarkup(downloadedTrack.descriptors));
    });
    bindLazyAudio(root);
    bindCompactAudio(root);
    root.querySelectorAll('.version-history').forEach((history) =>
      history.addEventListener('toggle', async () => {
        if (!history.open || history.dataset.loaded === 'true') return;
        history.dataset.loaded = 'loading';
        const list = history.querySelector('ul');
        list.innerHTML = '<li class="muted-copy">Loading version history…</li>';
        try {
          const card = history.closest('.library-card');
          const payload = await api.raw(`/api/library/jobs/${card.dataset.jobId}/details`).then(async (response) => {
            if (!response.ok)
              throw new Error(api.errorMessage(await response.json(), 'Could not load version history.'));
            return response.json();
          });
          const versions = payload.versions || [];
          list.innerHTML =
            versions
              .map((job, index) => {
                const generation = versions.length - index;
                const stored = String(job.extended_path || '').includes('/versions/');
                let config = {};
                try {
                  config = JSON.parse(job.config_json || '{}');
                } catch (_) {
                  config = {};
                }
                const summary = config.analysis_only
                  ? 'analysis only'
                  : `${job.intro_quality == null ? 'intro preserved' : `${Math.round(job.intro_quality)}% intro`} · ${job.outro_quality == null ? 'outro preserved' : `${Math.round(job.outro_quality)}% outro`}`;
                return `<li><div><strong>Generation ${generation}${index === 0 ? ' · latest' : ''}</strong><span>${reportDate(job.updated_at)} · ${summary}</span></div>${stored ? `<a class="button secondary" href="/api/jobs/${job.id}/download/extended">Download</a>` : '<small>Original source</small>'}</li>`;
              })
              .join('') || '<li class="muted-copy">No version history is available.</li>';
          history.dataset.loaded = 'true';
        } catch (error) {
          list.innerHTML = `<li class="danger-text">${escapeHtml(error.message)}</li>`;
          history.dataset.loaded = 'false';
        }
      }),
    );
    const libraryCards = [...root.querySelectorAll('.library-card')];
    const roleCounts = catalog.facets?.roles || {};
    const categoryCounts = catalog.facets?.categories || {};
    $('#library-sidebar').innerHTML =
      `<div class="library-sidebar-head"><div><p class="eyebrow">DJ CRATES</p><h2>Browse Library</h2><span>${catalog.total} analyzed track${catalog.total === 1 ? '' : 's'}</span></div><button type="button" class="library-sidebar-toggle" aria-label="Collapse DJ crates" title="Collapse DJ crates">‹</button></div><nav><button type="button" class="library-side-all active"><span>All tracks</span><b>${catalog.total}</b></button><div class="folder-heading"><span>Set roles</span></div>${Object.entries(
        roleCounts,
      )
        .sort()
        .map(
          ([role, count]) =>
            `<button type="button" class="library-side-role" data-value="${escapeHtml(role)}"><span>${escapeHtml(LIBRARY_ROLE_INFO[role]?.[0] || role)}</span><b>${count}</b></button>`,
        )
        .join(
          '',
        )}<div class="folder-heading"><span>Genres</span></div>${genreFolderTree(Object.entries(categoryCounts), 'library-side-category')}</nav>`;
    const libraryLayout = document.querySelector('.library-layout');
    const sidebarToggle = $('#library-sidebar').querySelector('.library-sidebar-toggle');
    const setSidebarCollapsed = (collapsed) => {
      libraryLayout.classList.toggle('sidebar-collapsed', collapsed);
      sidebarToggle.textContent = collapsed ? '›' : '‹';
      sidebarToggle.setAttribute('aria-label', collapsed ? 'Expand DJ crates' : 'Collapse DJ crates');
      sidebarToggle.title = sidebarToggle.getAttribute('aria-label');
      localStorage.setItem('dj-library-crates-collapsed', String(collapsed));
    };
    setSidebarCollapsed(localStorage.getItem('dj-library-crates-collapsed') === 'true');
    sidebarToggle.onclick = () => setSidebarCollapsed(!libraryLayout.classList.contains('sidebar-collapsed'));
    bindGenreFolderState($('#library-sidebar'));
    filters.bind(catalog);
    selection.bind();
    root.querySelectorAll('.library-compact-row').forEach((row) => {
      const toggle = () => {
        const body = row.closest('.library-card').querySelector('.library-card-body');
        body.hidden = !body.hidden;
        row.setAttribute('aria-expanded', String(!body.hidden));
      };
      row.onclick = (event) => {
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
      row.onkeydown = (event) => {
        if ((event.key === 'Enter' || event.key === ' ') && event.target === row) {
          event.preventDefault();
          toggle();
        }
      };
    });
    const cardAction = (button, selector) => {
      const card = button.closest('.library-card');
      card.querySelector('.library-card-body').hidden = false;
      card.querySelector(selector)?.click();
      button.closest('details').open = false;
    };
    root
      .querySelectorAll('.compact-remove')
      .forEach((button) => (button.onclick = () => cardAction(button, '.remove-library-track')));
    $('#library-sidebar').querySelector('.library-side-all').onclick = () => {
      libraryUiState.role = 'all';
      libraryUiState.category = 'all';
      libraryUiState.detailedGenre = 'all';
      libraryUiState.page = 1;
      reload();
    };
    $('#library-sidebar')
      .querySelectorAll('.library-side-role')
      .forEach(
        (button) =>
          (button.onclick = () => {
            libraryUiState.role = button.dataset.value;
            libraryUiState.page = 1;
            reload();
          }),
      );
    $('#library-sidebar')
      .querySelectorAll('.library-side-category')
      .forEach(
        (button) =>
          (button.onclick = () => {
            libraryUiState.category = button.dataset.value;
            libraryUiState.detailedGenre = 'all';
            libraryUiState.page = 1;
            reload();
          }),
      );
    root.querySelectorAll('.library-reprocess').forEach(
      (button) =>
        (button.onclick = () => {
          const form = button.closest('.library-card').querySelector('.library-reprocess-form');
          form.hidden = !form.hidden;
          button.textContent = form.hidden ? button.dataset.closedLabel : 'Close configuration';
          if (!form.hidden) form.querySelector('select').focus();
        }),
    );
    root.querySelectorAll('.edit-library-genre').forEach(
      (button) =>
        (button.onclick = () => {
          const card = button.closest('.library-card');
          const editor = card.querySelector('.inline-genre-editor');
          editor.hidden = !editor.hidden;
          if (!editor.hidden) editor.querySelector('select').focus();
        }),
    );
    root.querySelectorAll('.edit-library-identity').forEach(
      (button) =>
        (button.onclick = () => {
          const card = button.closest('.library-card'),
            editor = card.querySelector('.track-descriptor-editor');
          editor.hidden = !editor.hidden;
          if (!editor.hidden) editor.querySelector('input')?.focus();
        }),
    );
    root
      .querySelectorAll('.library-card[data-downloaded-id]:not([data-downloaded-id=""]) .track-descriptor-editor')
      .forEach((editor) => {
        const card = editor.closest('.library-card');
        bindIdentityInference(editor, [Number(card.dataset.downloadedId)]);
        editor.querySelector('.cancel-descriptors').onclick = () => {
          editor.hidden = true;
        };
        editor.querySelector('.close-descriptor-editor').onclick = () => {
          editor.hidden = true;
        };
        editor.querySelector('.save-descriptors').onclick = async (event) => {
          const action = event.currentTarget;
          action.disabled = true;
          action.textContent = 'Saving…';
          try {
            const result = await saveDescriptorEditor(editor, [Number(card.dataset.downloadedId)]);
            card.querySelector('.library-row-title .track-descriptor-chips')?.remove();
            if (result.values?.length)
              card
                .querySelector('.library-row-title')
                .insertAdjacentHTML('beforeend', descriptorChipsMarkup(result.values));
            card.querySelector('.library-identity-summary').innerHTML = descriptorChipsMarkup(result.values || [], {
              detailed: true,
            });
            editor.hidden = true;
            invalidateMusicFiles();
            notify('Musical identity saved to the persistent catalog. It will survive restart.', 'success');
          } catch (error) {
            notify(error.message, 'danger');
          } finally {
            action.disabled = false;
            action.textContent = 'Save changes';
          }
        };
      });
    root.querySelectorAll('.library-card[data-downloaded-id]:not([data-downloaded-id=""])').forEach((card) =>
      bindGenreEditor(
        card.querySelector('.inline-genre-editor'),
        () => [Number(card.dataset.downloadedId)],
        async (payload) => {
          card.querySelector('.library-row-title small').textContent = payload.genre_category;
          card.querySelector('.inline-genre-editor').hidden = true;
          invalidateMusicFiles();
        },
      ),
    );
    root.querySelectorAll('.close-reprocess').forEach(
      (button) =>
        (button.onclick = () => {
          const card = button.closest('.library-card');
          card.querySelector('.library-reprocess-form').hidden = true;
          const trigger = card.querySelector('.library-reprocess');
          trigger.textContent = trigger.dataset.closedLabel;
        }),
    );
    root.querySelectorAll('.library-reprocess-form').forEach((reprocessForm) => {
      const submit = async (review) => {
        const card = reprocessForm.closest('.library-card');
        const latest = jobs.find((job) => String(job.id) === card.dataset.jobId);
        let latestConfig = {};
        try {
          latestConfig = JSON.parse(latest.config_json || '{}');
        } catch (_) {
          latestConfig = {};
        }
        const introAuto = reprocessForm.elements.intro_bars.value === 'auto';
        const outroAuto = reprocessForm.elements.outro_bars.value === 'auto';
        const body = {
          preset: reprocessForm.elements.preset.value,
          intro_bars: introAuto
            ? Number(latestConfig.analysis_only ? getAppConfig().effective.intro_bars : latest.intro_bars)
            : Number(reprocessForm.elements.intro_bars.value),
          outro_bars: outroAuto
            ? Number(latestConfig.analysis_only ? getAppConfig().effective.outro_bars : latest.outro_bars)
            : Number(reprocessForm.elements.outro_bars.value),
          intro_bars_auto: introAuto,
          outro_bars_auto: outroAuto,
          use_stems: reprocessForm.elements.use_stems.value === 'true',
          auto_bars: reprocessForm.elements.auto_bars.checked,
          minimum_intro_loop_quality: Number(reprocessForm.elements.minimum_intro_loop_quality.value),
          minimum_outro_loop_quality: Number(reprocessForm.elements.minimum_outro_loop_quality.value),
          maximum_repetitions: Number(reprocessForm.elements.maximum_repetitions.value),
          crossfade_ms: Number(reprocessForm.elements.crossfade_ms.value),
          candidate_count: Number(reprocessForm.elements.candidate_count.value),
          intro_search_seconds: Number(reprocessForm.elements.intro_search_seconds.value),
          outro_search_seconds: Number(reprocessForm.elements.outro_search_seconds.value),
          maximum_vocal_coverage_percent: Number(reprocessForm.elements.maximum_vocal_coverage_percent.value),
          maximum_vocal_boundary_risk_percent: Number(reprocessForm.elements.maximum_vocal_boundary_risk_percent.value),
          maximum_buildup_risk_percent: Number(reprocessForm.elements.maximum_buildup_risk_percent.value),
          maximum_bass_reset_risk_percent: Number(reprocessForm.elements.maximum_bass_reset_risk_percent.value),
          minimum_stem_reliability_percent: Number(reprocessForm.elements.minimum_stem_reliability_percent.value),
          pcm_bits: Number(reprocessForm.elements.pcm_bits.value),
          preview_seconds: Number(reprocessForm.elements.preview_seconds.value),
          export_cues: reprocessForm.elements.export_cues.value === 'true',
          review_candidates: review,
        };
        reprocessForm.querySelectorAll('button').forEach((item) => (item.disabled = true));
        reprocessForm.querySelector('.reprocess-message').textContent = review
          ? 'Queuing review…'
          : 'Queuing new generation…';
        try {
          const succeeded = await jobAction(latest.id, 'reprocess', body);
          if (succeeded === false)
            throw new Error(review ? 'The review request was not queued.' : 'The new generation was not queued.');
          showView('workspace-view');
        } catch (error) {
          notify(`Reprocessing failed: ${error.message}`, 'danger');
          reprocessForm.querySelectorAll('button').forEach((item) => (item.disabled = false));
          reprocessForm.querySelector('.reprocess-message').textContent =
            'Nothing was queued. Your existing track is unchanged.';
        }
      };
      reprocessForm.addEventListener('submit', (event) => {
        event.preventDefault();
        submit(false);
      });
      reprocessForm.querySelector('.reprocess-review').onclick = () => submit(true);
    });
    root.querySelectorAll('.library-review').forEach(
      (button) =>
        (button.onclick = async () => {
          const card = button.closest('.library-card');
          const latest = jobs.find((job) => String(job.id) === card.dataset.jobId);
          if (latest.review_status === 'pending') {
            showView('review-view');
            return;
          }
          try {
            const succeeded = await jobAction(latest.id, 'reprocess', { review_candidates: true });
            if (succeeded === false) throw new Error('The review request was not queued.');
            showView('workspace-view');
          } catch (error) {
            notify(`Review creation failed: ${error.message}`, 'danger');
          }
        }),
    );
    root.querySelectorAll('.open-latest').forEach(
      (button) =>
        (button.onclick = async () => {
          const card = button.closest('.library-card');
          const host = card.querySelector('.library-detail-host');
          if (host.childElementCount) {
            host.replaceChildren();
            button.textContent = 'Show full details';
            return;
          }
          const latest = jobs.find((job) => String(job.id) === card.dataset.jobId);
          try {
            const detail = jobElement(latest);
            detail.classList.add('library-embedded');
            host.append(detail);
            detail.querySelector('.details-job').click();
            button.textContent = 'Hide full details';
          } catch (error) {
            notify(`Track details could not be opened: ${error.message}`, 'danger');
          }
        }),
    );
    root.querySelectorAll('.remove-library-track').forEach(
      (button) =>
        (button.onclick = async () => {
          const card = button.closest('.library-card');
          const latest = jobs.find((job) => String(job.id) === card.dataset.jobId);
          if (
            !(await confirmAction(
              `Remove ${latest.source_name} and all of its generations from the Library? Exported audio files will remain in the output folder.`,
              { title: 'Remove Library track', acceptLabel: 'Remove', danger: true },
            ))
          )
            return;
          button.disabled = true;
          button.textContent = 'Removing…';
          const response = await api.raw(`/api/library/${encodeURIComponent(latest.source_name)}`, {
            method: 'DELETE',
          });
          if (!response.ok) {
            alert(api.errorMessage(await response.json(), 'Could not remove the track.'));
            button.disabled = false;
            button.textContent = 'Remove from library';
            return;
          }
          await Promise.all([reload(), loadAnalysis(), loadReports()]);
        }),
    );
  }

  return Object.freeze({ render });
}
