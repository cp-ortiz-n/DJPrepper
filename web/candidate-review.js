import { useFrontendServices } from './frontend-services.js';
import { clock, escapeHtml, pct } from './shared-components.js';
import { createCandidateWaveformEditor } from './candidate-waveform-editor.js';

export function reviewableProcessingJobs(jobs) {
  return jobs.filter((job) => {
    try {
      return (
        job.status === 'complete' &&
        job.review_status === 'pending' &&
        Boolean(JSON.parse(job.config_json || '{}').review_candidates)
      );
    } catch (_) {
      return false;
    }
  });
}

export function createCandidateReviewFeature({
  services,
  processingWorkspaceApi,
  annotateJobs,
  decodedAudio,
  renderArrangementTimeline,
  WaveSurfer,
  RegionsPlugin,
  TimelinePlugin,
  jobAction,
  loadJobs,
  showView,
}) {
  const { $, confirmAction, notify } = useFrontendServices(services);
  const waveformEditor = createCandidateWaveformEditor({
    processingWorkspaceApi,
    decodedAudio,
    renderArrangementTimeline,
    clock,
    escapeHtml,
    WaveSurfer,
    RegionsPlugin,
    TimelinePlugin,
  });
  const {
    isPreviewing,
    initializeCustomWaveform,
    initializeInsertionWaveform,
    previewArrangementInsertion,
    stopArrangementPreview,
    updateInsertionVisualization,
  } = waveformEditor;

  async function loadReviews() {
    const jobs = annotateJobs(await processingWorkspaceApi.list());
    const reviewJobs = reviewableProcessingJobs(jobs);
    const root = $('#review-list');
    if (!reviewJobs.length) {
      root.innerHTML =
        '<div class="empty">No candidate reviews requested. Use “Create review” on a completed track or enable review before uploading.</div>';
      return;
    }
    root.innerHTML = reviewJobs
      .map(
        (job) =>
          `<article class="panel review-card" data-job-id="${job.id}"><div class="panel-head"><div><p class="eyebrow">GENERATION ${job._generation || 1}</p><h2>${escapeHtml(job.source_name)}</h2></div><div class="review-actions"><button class="button secondary regenerate-review">Regenerate auditions</button><button class="button secondary reject-review">Dismiss review</button></div></div><div class="review-players"><label>Source WAV<audio controls preload="metadata" src="/api/jobs/${job.id}/audio/wav"></audio></label><label>Selected extended edit<audio controls preload="metadata" src="/api/jobs/${job.id}/audio/extended"></audio></label></div><div class="candidate-studio"><p class="muted-copy">Loading candidate auditions…</p></div></article>`,
      )
      .join('');
    await Promise.all(
      reviewJobs.map(async (job) => {
        const card = root.querySelector(`[data-job-id="${job.id}"]`);
        const [data, feedback] = await Promise.all([
          processingWorkspaceApi.candidates(job.id),
          processingWorkspaceApi.feedback(job.id),
        ]);
        renderCandidates(card.querySelector('.candidate-studio'), job, data, feedback);
        card.querySelector('.regenerate-review').onclick = async () => {
          await jobAction(job.id, 'reprocess', { review_candidates: true });
          await loadReviews();
        };
        card.querySelector('.reject-review').onclick = async () => {
          if (
            !(await confirmAction('Dismiss this candidate review? The processed track remains in Library.', {
              title: 'Dismiss candidate review',
              acceptLabel: 'Dismiss',
            }))
          )
            return;
          try {
            await processingWorkspaceApi.rejectReview(job.id);
            await Promise.all([loadReviews(), loadJobs()]);
            showView('workspace-view');
          } catch (error) {
            notify(error.message || 'Could not dismiss this review.', 'danger');
          }
        };
      }),
    );
  }

  function renderCandidates(root, job, data, feedback = []) {
    const selections = {};
    const customSelections = {};
    let arrangementInsertion = null;
    const sides = ['intro', 'outro']
      .map((position) => {
        const accepted = feedback.find((item) => item.position === position && item.accepted);
        if (accepted) selections[position] = accepted.candidate_rank;
        const cards = (data[position] || [])
          .map(
            (item) =>
              `<div class="candidate-card ${accepted?.candidate_rank === item.rank ? 'decision-accept' : ''}" data-rank="${item.rank}"><strong>Option ${item.rank} · ${clock(item.start)}–${clock(item.end)}</strong><p>Phrase ${pct(item.phrase)} · Loop ${pct(item.loop)} · Transition ${pct(item.transition)}</p><p>${escapeHtml(item.warnings.join(' · ') || 'All automatic checks passed')}</p><audio controls preload="none" src="/api/jobs/${job.id}/candidate/${position}/${item.rank}"></audio><div class="feedback-controls"><input class="tags" placeholder="tags"><input class="notes" placeholder="notes"><button class="candidate-choice ${accepted?.candidate_rank === item.rank ? 'decision-active' : ''}" data-choose>${accepted?.candidate_rank === item.rank ? 'Selected' : 'Accept option ' + item.rank}</button></div></div>`,
          )
          .join('');
        const suggestion = (data[position] || [])[0] || { start: 0, end: 8 };
        return `<section class="candidate-side" data-position="${position}"><div class="candidate-side-heading"><strong>${position} candidates</strong><span>${accepted ? `Option ${accepted.candidate_rank} selected` : 'Choose one option'}</span><div><button class="button secondary preserve-side">Preserve original</button><button class="button secondary open-custom">Build my own</button></div></div><div class="candidate-grid">${cards || '<p>No candidates generated.</p>'}</div><div class="custom-candidate" hidden><header><div class="custom-icon">✦</div><div><p class="eyebrow">CUSTOM EDITOR</p><strong>Build a custom ${position}</strong><small>Drag the highlighted waveform region or enter exact timestamps. Final rendering still applies boundary optimization and adaptive smoothing.</small></div><button class="button secondary discard-custom">Close editor</button></header><div class="custom-wave-shell"><div class="custom-waveform"></div><div class="custom-timeline"></div></div><div class="custom-fields"><label>Selection start<input class="custom-start" type="number" min="0" step="0.01" value="${Number(suggestion.start).toFixed(2)}"></label><label>Selection end<input class="custom-end" type="number" min="0.01" step="0.01" value="${Number(suggestion.end).toFixed(2)}"></label><label>Copies<select class="custom-copies"><option>1</option><option>2</option><option>3</option><option>4</option><option>6</option><option>8</option></select></label></div><div class="custom-stats"><p><b class="custom-duration">—</b><span>Selection</span></p><p><b class="custom-bars">—</b><span>Approx. bars</span></p><p><b class="custom-added">—</b><span>Audio added</span></p><p><b>${Number(job.bpm || 0).toFixed(1)}</b><span>Detected BPM</span></p></div><div class="custom-footer"><div class="custom-tools"><button class="button secondary snap-custom">⌁ Snap to bars</button><button class="button secondary play-custom">▶ Audition region</button></div><button class="button secondary use-custom">Use custom candidate →</button></div><p class="custom-message">Adjust the highlighted region, then audition it before selecting.</p></div></section>`;
      })
      .join('');
    root.innerHTML = `${sides}<div class="candidate-submit"><p>Select an automatic option, preserve the original, or build a custom candidate for each side.</p><button class="button secondary reprocess-candidates">Reprocess with selected candidates</button><span></span></div>`;
    root.querySelectorAll('.candidate-card audio').forEach((audio) =>
      audio.addEventListener(
        'error',
        () => {
          audio.hidden = true;
          const message = document.createElement('p');
          message.className = 'candidate-audio-error';
          message.textContent = 'Audition file is unavailable. Use “Regenerate auditions” above.';
          audio.after(message);
        },
        { once: true },
      ),
    );
    root.querySelectorAll('.candidate-card').forEach((card) => {
      const side = card.closest('.candidate-side');
      const position = side.dataset.position;
      const rank = Number(card.dataset.rank);
      card.querySelector('[data-choose]').onclick = async () => {
        try {
          await processingWorkspaceApi.saveFeedback(job.id, {
            position,
            candidate_rank: rank,
            accepted: true,
            tags: card.querySelector('.tags').value,
            notes: card.querySelector('.notes').value,
          });
        } catch (_) {
          return;
        }
        selections[position] = rank;
        delete customSelections[position];
        side.querySelectorAll('.candidate-card').forEach((optionCard) => {
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
    root.querySelectorAll('.candidate-side').forEach((side) => {
      const position = side.dataset.position;
      const editor = side.querySelector('.custom-candidate');
      editor
        .querySelector('.custom-wave-shell')
        .insertAdjacentHTML(
          'afterend',
          '<div class="custom-wave-controls"><div class="custom-wave-actions"><button class="button secondary play-full-custom" disabled>▶ Play full track</button></div><span class="custom-wave-time">00:00 / 00:00</span><label>Zoom <input class="custom-zoom" type="range" min="0" max="180" value="0"></label></div><div class="custom-arrangement"></div><div class="custom-legend"></div>',
        );
      const waveActions = editor.querySelector('.custom-wave-actions');
      waveActions.append(editor.querySelector('.snap-custom'), editor.querySelector('.play-custom'));
      editor.querySelector('.custom-tools').remove();
      editor.querySelector('.custom-bars').outerHTML =
        '<input class="custom-bars-input" aria-label="Approximate bars" type="number" min="0.25" max="64" step="0.25" value="1">';
      editor
        .querySelector('.custom-legend')
        .insertAdjacentHTML(
          'afterend',
          '<div class="insert-builder"><button class="button secondary open-insert">＋ Insert this section elsewhere</button><div class="insert-panel" hidden><div><p class="eyebrow">DESTINATION</p><strong>Place this source region in the extended arrangement</strong><small>Click the destination waveform or enter an exact output timestamp. The orange block is the material that will be added.</small></div><div class="insert-wave-shell"><div class="insert-waveform"></div><div class="insert-timeline"></div></div><div class="insert-preview-row"><button class="button secondary preview-insert">▶ Preview placement</button><span>Plays context before → selected region × copies → context after</span><output class="insert-preview-time">00:00 / 00:00</output><label>Zoom <input class="insert-zoom" type="range" min="0" max="180" value="0"></label><b class="insert-added-time">—</b></div><div class="insert-score score-loading"><strong>Checking placement…</strong><span>Comparing bars, chords, energy, bass, rhythm, and vocals.</span></div><div class="insert-controls"><label>Destination<input class="insert-destination" type="number" min="0" step="0.01" value="0"></label><label>Copies<select class="insert-copies"><option>1</option><option>2</option><option>3</option><option>4</option></select></label><label class="insert-also"><input type="checkbox"><span>Also use this region as the custom side extension</span></label><button class="button secondary snap-insert">Snap destination to bar</button><button class="button secondary use-insert">Use insertion</button></div><p class="insert-message"></p></div></div>',
        );
      const sourceAudio = root.closest('.review-card').querySelector('.review-players audio');
      const updateMap = () => {
        const start = Number(editor.querySelector('.custom-start').value);
        const end = Number(editor.querySelector('.custom-end').value);
        const copies = Number(editor.querySelector('.custom-copies').value);
        const seconds = Math.max(0, end - start);
        const bar = (4 * 60) / Math.max(Number(job.bpm) || 120, 1);
        editor.querySelector('.custom-duration').textContent = `${seconds.toFixed(2)}s`;
        editor.querySelector('.custom-bars-input').value = `${(seconds / bar).toFixed(2)}`;
        editor.querySelector('.custom-added').textContent = `${(seconds * copies).toFixed(1)}s`;
        const region = editor._customRegion;
        if (region && !editor._syncingRegion) {
          editor._syncingInputs = true;
          region.setOptions({ start, end });
          editor._syncingInputs = false;
        }
        updateInsertionVisualization(editor);
      };
      side.querySelector('.open-custom').onclick = () => {
        editor.hidden = false;
        side.classList.add('custom-open');
        updateMap();
        initializeCustomWaveform(editor, job);
      };
      side.querySelector('.discard-custom').onclick = () => {
        editor.hidden = true;
        side.classList.remove('custom-open');
      };
      side.querySelector('.preserve-side').onclick = () => {
        selections[position] = 0;
        delete customSelections[position];
        side.querySelector('.candidate-side-heading>span').textContent = 'Original preserved';
        side.querySelectorAll('.candidate-card').forEach((card) => card.classList.remove('decision-accept'));
        updateSubmit();
      };
      editor
        .querySelectorAll('.custom-start,.custom-end,.custom-copies')
        .forEach((input) => (input.oninput = updateMap));
      editor.querySelector('.custom-bars-input').oninput = (event) => {
        const bars = Number(event.target.value);
        if (!Number.isFinite(bars) || bars <= 0) return;
        const start = Number(editor.querySelector('.custom-start').value);
        const barSeconds = (4 * 60) / Math.max(Number(job.bpm) || 120, 1);
        editor.querySelector('.custom-end').value = (start + bars * barSeconds).toFixed(2);
        updateMap();
        editor.querySelector('.custom-message').textContent =
          `Selection resized to ${bars} bars on the detected 4/4 grid.`;
      };
      editor.querySelector('.snap-custom').onclick = () => {
        const beat = 60 / Math.max(Number(job.bpm) || 120, 1);
        const bar = beat * 4;
        const startInput = editor.querySelector('.custom-start');
        const endInput = editor.querySelector('.custom-end');
        const start = Math.max(0, Math.round(Number(startInput.value) / bar) * bar);
        const bars = Math.max(1, Math.round((Number(endInput.value) - Number(startInput.value)) / bar));
        startInput.value = start.toFixed(2);
        endInput.value = (start + bars * bar).toFixed(2);
        editor.querySelector('.custom-message').textContent =
          `Snapped to approximately ${bars} bar${bars === 1 ? '' : 's'} at ${Number(job.bpm || 120).toFixed(1)} BPM.`;
        updateMap();
      };
      editor.querySelector('.play-custom').onclick = () => {
        const start = Number(editor.querySelector('.custom-start').value);
        const end = Number(editor.querySelector('.custom-end').value);
        const surface = editor._customSurface;
        if (surface) {
          surface.setTime(start);
          surface.play();
          const stop = (current) => {
            if (current >= end) {
              surface.pause();
              surface.un('timeupdate', stop);
            }
          };
          surface.on('timeupdate', stop);
        } else {
          sourceAudio.currentTime = start;
          sourceAudio.play();
          const stop = () => {
            if (sourceAudio.currentTime >= end) {
              sourceAudio.pause();
              sourceAudio.removeEventListener('timeupdate', stop);
            }
          };
          sourceAudio.addEventListener('timeupdate', stop);
        }
      };
      editor.querySelector('.play-full-custom').onclick = (event) => {
        const surface = editor._customSurface;
        if (!surface) return;
        surface.playPause();
        event.currentTarget.textContent = surface.isPlaying() ? 'Ⅱ Pause full track' : '▶ Play full track';
      };
      const insertPanel = editor.querySelector('.insert-panel');
      editor.querySelector('.open-insert').onclick = (event) => {
        insertPanel.hidden = !insertPanel.hidden;
        event.currentTarget.textContent = insertPanel.hidden
          ? '＋ Insert this section elsewhere'
          : '− Hide destination editor';
        if (!insertPanel.hidden) initializeInsertionWaveform(editor, job);
      };
      editor.querySelector('.snap-insert').onclick = () => {
        const field = editor.querySelector('.insert-destination');
        const bar = (4 * 60) / Math.max(Number(job.bpm) || 120, 1);
        field.value = (Math.round(Number(field.value) / bar) * bar).toFixed(2);
        field.dispatchEvent(new Event('input'));
        editor.querySelector('.insert-message').textContent = 'Destination snapped to the nearest detected bar.';
      };
      editor.querySelector('.insert-destination').oninput = () => updateInsertionVisualization(editor);
      editor.querySelector('.insert-copies').oninput = () => updateInsertionVisualization(editor);
      editor.querySelector('.insert-zoom').oninput = (event) => {
        editor._insertSurface?.zoom(Number(event.target.value));
        updateInsertionVisualization(editor);
      };
      editor.querySelector('.preview-insert').onclick = async (event) => {
        if (isPreviewing(event.currentTarget)) {
          stopArrangementPreview();
          return;
        }
        const button = event.currentTarget;
        button.disabled = true;
        editor.querySelector('.insert-message').textContent = 'Preparing placement preview…';
        try {
          await previewArrangementInsertion(editor, job, button);
          editor.querySelector('.insert-message').textContent =
            'Previewing the exact destination with the selected copy count.';
        } catch (error) {
          editor.querySelector('.insert-message').textContent =
            error.message || 'Could not prepare the placement preview.';
        } finally {
          button.disabled = false;
        }
      };
      editor.querySelector('.use-insert').onclick = () => {
        const start = Number(editor.querySelector('.custom-start').value);
        const end = Number(editor.querySelector('.custom-end').value);
        const destination = Number(editor.querySelector('.insert-destination').value);
        const copies = Number(editor.querySelector('.insert-copies').value);
        const extendedDuration = editor._insertWaveData?.extended?.duration;
        if (end <= start || destination < 0 || (extendedDuration && destination > extendedDuration)) {
          editor.querySelector('.insert-message').textContent = 'Choose a valid source region and destination.';
          return;
        }
        arrangementInsertion = { start, end, destination, copies };
        if (editor.querySelector('.insert-also input').checked) {
          customSelections[position] = { start, end, copies: Number(editor.querySelector('.custom-copies').value) };
          delete selections[position];
        } else {
          selections[position] = 0;
          delete customSelections[position];
        }
        side.querySelector('.candidate-side-heading>span').textContent =
          `Insert ${clock(start)}–${clock(end)} at ${clock(destination)}`;
        editor.querySelector('.insert-message').textContent =
          'Insertion selected. Reprocess to render it in the extended arrangement.';
        updateSubmit();
      };
      editor.querySelector('.use-custom').onclick = () => {
        const start = Number(editor.querySelector('.custom-start').value);
        const end = Number(editor.querySelector('.custom-end').value);
        const copies = Number(editor.querySelector('.custom-copies').value);
        if (
          !Number.isFinite(start) ||
          !Number.isFinite(end) ||
          end <= start ||
          start < 0 ||
          (Number.isFinite(sourceAudio.duration) && end > sourceAudio.duration)
        ) {
          editor.querySelector('.custom-message').textContent = 'Choose a valid start and end inside the source track.';
          return;
        }
        customSelections[position] = { start, end, copies };
        delete selections[position];
        side.querySelector('.candidate-side-heading>span').textContent =
          `Custom ${clock(start)}–${clock(end)} ×${copies}`;
        side.querySelectorAll('.candidate-card').forEach((card) => card.classList.remove('decision-accept'));
        editor.querySelector('.custom-message').textContent =
          'Custom candidate selected. Reprocess to render and audition it in full context.';
        updateSubmit();
      };
    });
    const needed = ['intro', 'outro'].filter((position) => (data[position] || []).length);
    const submit = root.querySelector('.reprocess-candidates');
    const updateSubmit = () => {
      submit.disabled = needed.some((position) => !(position in selections) && !customSelections[position]);
    };
    updateSubmit();
    submit.onclick = async () => {
      submit.disabled = true;
      submit.nextElementSibling.textContent = 'Added to the processing queue…';
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
      try {
        await processingWorkspaceApi.reprocess(job.id, body);
      } catch (_) {
        submit.disabled = false;
        submit.nextElementSibling.textContent = 'Could not queue this selection.';
        return;
      }
      await loadJobs();
      showView('workspace-view');
    };
  }

  return Object.freeze({ load: loadReviews, stop: stopArrangementPreview });
}
