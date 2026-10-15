import { useFrontendServices } from './frontend-services.js';
import { clock, escapeHtml, pct } from './shared-components.js';

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
  let arrangementPreview = null;

  function stopArrangementPreview() {
    if (!arrangementPreview) return;
    arrangementPreview.nodes.forEach((node) => {
      try {
        node.stop();
      } catch (_) {
        /* already stopped */
      }
    });
    clearTimeout(arrangementPreview.timer);
    cancelAnimationFrame(arrangementPreview.frame);
    if (arrangementPreview.button?.isConnected) arrangementPreview.button.textContent = arrangementPreview.label;
    arrangementPreview = null;
  }

  function schedulePreviewClip(context, buffer, offset, duration, when, fade = 0.015) {
    const safeDuration = Math.max(0.02, Math.min(duration, buffer.duration - offset));
    const edge = Math.min(fade, safeDuration / 3);
    const node = context.createBufferSource();
    const gain = context.createGain();
    node.buffer = buffer;
    node.connect(gain).connect(context.destination);
    gain.gain.setValueAtTime(0, when);
    gain.gain.linearRampToValueAtTime(1, when + edge);
    gain.gain.setValueAtTime(1, when + safeDuration - edge);
    gain.gain.linearRampToValueAtTime(0, when + safeDuration);
    node.start(when, Math.max(0, offset), safeDuration);
    return { node, duration: safeDuration };
  }

  function insertionWaveContent(editor, copies) {
    const wave = editor._insertWaveData?.source;
    if (!wave?.peaks?.length) return `ADDED ×${copies}`;
    const start = Number(editor.querySelector('.custom-start').value);
    const end = Number(editor.querySelector('.custom-end').value);
    const first = Math.max(0, Math.floor((start / wave.duration) * wave.peaks.length));
    const last = Math.min(wave.peaks.length, Math.ceil((end / wave.duration) * wave.peaks.length));
    const selected = wave.peaks.slice(first, last);
    const points = selected.filter((_, index) => index % Math.max(1, Math.ceil(selected.length / 48)) === 0);
    const copyMarkup = points
      .map((peak, index) => {
        const height = Math.max(8, Number(peak) * 72);
        const left = ((index + 0.5) * 100) / Math.max(points.length, 1);
        return `<i style="left:${left}%;height:${height}%"></i>`;
      })
      .join('');
    const element = document.createElement('span');
    element.className = 'inserted-wave-content';
    element.innerHTML = `<em>+ ×${copies}</em><span>${Array.from({ length: copies }, (_, index) => `<b data-copy="${index + 1}">${copyMarkup}</b>`).join('')}</span>`;
    return element;
  }

  function updateInsertionVisualization(editor) {
    const region = editor._insertMarker;
    const duration = editor._insertWaveData?.extended?.duration;
    if (!region || !duration || editor._syncingInsert) return;
    const destination = Math.max(0, Math.min(Number(editor.querySelector('.insert-destination').value) || 0, duration));
    const sourceLength = Math.max(
      0.08,
      Number(editor.querySelector('.custom-end').value) - Number(editor.querySelector('.custom-start').value),
    );
    const copies = Number(editor.querySelector('.insert-copies').value) || 1;
    const sourceWave = editor._insertWaveData.source;
    const extendedWave = editor._insertWaveData.extended;
    const sourceFirst = Math.max(
      0,
      Math.floor((Number(editor.querySelector('.custom-start').value) / sourceWave.duration) * sourceWave.peaks.length),
    );
    const sourceLast = Math.min(
      sourceWave.peaks.length,
      Math.ceil((Number(editor.querySelector('.custom-end').value) / sourceWave.duration) * sourceWave.peaks.length),
    );
    const insertAt = Math.max(
      0,
      Math.min(extendedWave.peaks.length, Math.round((destination / duration) * extendedWave.peaks.length)),
    );
    const insertedPeaks = Array.from({ length: copies }, () => sourceWave.peaks.slice(sourceFirst, sourceLast)).flat();
    const compositePeaks = [
      ...extendedWave.peaks.slice(0, insertAt),
      ...insertedPeaks,
      ...extendedWave.peaks.slice(insertAt),
    ];
    const compositeDuration = duration + sourceLength * copies;
    const applyRegion = () =>
      region.setOptions({
        start: destination,
        end: destination + sourceLength * copies,
        content: insertionWaveContent(editor, copies),
      });
    applyRegion();
    editor._insertSurface
      ?.load('', [Float32Array.from(compositePeaks)], compositeDuration)
      .then(() => {
        applyRegion();
        editor._insertSurface?.zoom(Number(editor.querySelector('.insert-zoom')?.value) || 0);
        if (Number(editor.querySelector('.insert-zoom')?.value) > 0)
          editor._insertSurface?.setScrollTime?.(destination);
        const previewTime = editor.querySelector('.insert-preview-time');
        if (previewTime && !arrangementPreview) previewTime.textContent = `00:00 / ${clock(compositeDuration)}`;
      })
      .catch(() => {
        editor.querySelector('.insert-message').textContent = 'Could not redraw the temporary edited waveform.';
      });
    if (Number(editor.querySelector('.insert-zoom')?.value) > 0) {
      editor._insertSurface?.setScrollTime?.(destination);
    }
    const added = editor.querySelector('.insert-added-time');
    if (added)
      added.textContent = `${clock(destination)} → ${clock(destination + sourceLength * copies)} · ${(sourceLength * copies).toFixed(1)}s added`;
    scheduleInsertionScore(editor);
  }

  function scheduleInsertionScore(editor) {
    if (!editor._insertJob || !editor.querySelector('.insert-score')) return;
    clearTimeout(editor._scoreTimer);
    const token = (editor._scoreToken || 0) + 1;
    editor._scoreToken = token;
    const root = editor.querySelector('.insert-score');
    root.className = 'insert-score score-loading';
    root.innerHTML =
      '<strong>Checking placement…</strong><span>Comparing bars, chords, energy, bass, rhythm, and vocals.</span>';
    editor._scoreTimer = setTimeout(async () => {
      const payload = {
        source_start: Number(editor.querySelector('.custom-start').value),
        source_end: Number(editor.querySelector('.custom-end').value),
        destination: Number(editor.querySelector('.insert-destination').value),
        copies: Number(editor.querySelector('.insert-copies').value),
      };
      try {
        const result = await processingWorkspaceApi.transitionScore(editor._insertJob.id, payload);
        if (token !== editor._scoreToken) return;
        const metrics = [
          ['Grid', result.grid],
          ['Harmony', result.harmony],
          ['Energy', result.energy],
          ['Bass', result.bass],
          ['Rhythm', result.rhythm],
          ['Vocals', result.vocals],
        ].filter(([, value]) => value != null);
        const level = result.score >= 75 ? 'score-good' : result.score >= 60 ? 'score-caution' : 'score-risky';
        root.className = `insert-score ${level}`;
        root.innerHTML = `<div class="score-verdict"><b>${result.score}%</b><span><strong>${escapeHtml(result.verdict)}</strong><small>Custom transition confidence</small></span></div><div class="score-metrics">${metrics.map(([label, value]) => `<span><b>${value}%</b><small>${label}</small></span>`).join('')}</div><ul>${(result.warnings.length ? result.warnings : ['No major transition risks detected']).map((warning) => `<li>${escapeHtml(warning)}</li>`).join('')}</ul>`;
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
    if (![start, end, destination, copies].every(Number.isFinite) || end <= start)
      throw new Error('Choose a valid source region first.');
    const cache = (editor._previewAudio ||= {});
    const [source, extended] = await Promise.all([
      decodedAudio(`/api/jobs/${job.id}/audio/wav`, cache, 'source'),
      decodedAudio(`/api/jobs/${job.id}/audio/extended`, cache, 'extended'),
    ]);
    if (destination > extended.duration) throw new Error('Choose a destination inside the current extended track.');
    const context = cache.context;
    const lead = Math.min(4, destination);
    const tail = 4;
    const fade = 0.015;
    const nodes = [];
    let when = context.currentTime + 0.04;
    if (lead > 0.02) {
      const clip = schedulePreviewClip(context, extended, destination - lead, lead, when, fade);
      nodes.push(clip.node);
      when += clip.duration - fade;
    }
    for (let copy = 0; copy < copies; copy += 1) {
      const clip = schedulePreviewClip(context, source, start, end - start, when, fade);
      nodes.push(clip.node);
      when += clip.duration - fade;
    }
    const remaining = Math.max(0, extended.duration - destination);
    if (remaining > 0.02) {
      const clip = schedulePreviewClip(context, extended, destination, Math.min(tail, remaining), when, fade);
      nodes.push(clip.node);
      when += clip.duration;
    }
    const previewStart = Math.max(0, destination - lead);
    const startedAt = context.currentTime + 0.04;
    const previewLength = when - startedAt;
    const surface = editor._insertSurface;
    const timeLabel = editor.querySelector('.insert-preview-time');
    editor._previewPlayhead ||= editor._insertRegions?.addRegion({
      start: previewStart,
      end: previewStart + 0.04,
      color: 'rgba(202,255,52,.95)',
      drag: false,
      resize: false,
    });
    const followPlayhead = () => {
      if (!arrangementPreview || arrangementPreview.button !== button) return;
      const elapsed = Math.max(0, context.currentTime - startedAt);
      const position = Math.min(previewStart + elapsed, previewStart + previewLength);
      surface?.setTime(position);
      surface?.setScrollTime?.(position);
      editor._previewPlayhead?.setOptions({ start: position, end: position + 0.04 });
      if (timeLabel) timeLabel.textContent = `${clock(position)} / ${clock(surface?.getDuration() || 0)}`;
      arrangementPreview.frame = requestAnimationFrame(followPlayhead);
    };
    const label = button.textContent;
    button.textContent = '■ Stop placement preview';
    const timer = setTimeout(stopArrangementPreview, Math.max(100, (when - context.currentTime) * 1000));
    arrangementPreview = { nodes, timer, button, label, frame: requestAnimationFrame(followPlayhead) };
  }

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
        if (arrangementPreview?.button === event.currentTarget) {
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

  async function initializeInsertionWaveform(editor, job) {
    if (editor._insertSurface) return;
    editor._insertJob = job;
    let wave;
    let sourceWave;
    try {
      [wave, sourceWave] = await Promise.all([
        processingWorkspaceApi.waveform(job.id, 'extended'),
        processingWorkspaceApi.waveform(job.id, 'wav'),
      ]);
    } catch (_) {
      return;
    }
    if (!editor.isConnected) return;
    editor._insertWaveData = { extended: wave, source: sourceWave };
    const regions = RegionsPlugin.create();
    editor._insertRegions = regions;
    const surface = WaveSurfer.create({
      container: editor.querySelector('.insert-waveform'),
      peaks: [wave.peaks],
      duration: wave.duration,
      height: 90,
      waveColor: '#697061',
      progressColor: '#697061',
      cursorColor: '#ffb65c',
      cursorWidth: 2,
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      normalize: false,
      dragToSeek: true,
      autoCenter: true,
      autoScroll: true,
      minPxPerSec: 0,
      plugins: [
        regions,
        TimelinePlugin.create({
          container: editor.querySelector('.insert-timeline'),
          style: { color: '#989991', fontSize: '9px' },
        }),
      ],
    });
    editor._insertSurface = surface;
    surface.once('ready', () => {
      editor._insertMarker = regions.addRegion({
        start: 0,
        end: 0.08,
        color: 'rgba(255,182,92,.24)',
        drag: true,
        resize: false,
        content: insertionWaveContent(editor, Number(editor.querySelector('.insert-copies').value)),
      });
      updateInsertionVisualization(editor);
    });
    surface.on('interaction', (current) => {
      editor.querySelector('.insert-destination').value = Number(current).toFixed(2);
      updateInsertionVisualization(editor);
    });
    regions.on('region-updated', (region) => {
      editor._syncingInsert = true;
      editor.querySelector('.insert-destination').value = region.start.toFixed(2);
      editor._syncingInsert = false;
    });
  }

  async function initializeCustomWaveform(editor, job) {
    if (editor._customSurface) return;
    editor.querySelector('.custom-waveform').textContent = 'Loading source waveform…';
    let wave;
    try {
      wave = await processingWorkspaceApi.waveform(job.id, 'wav');
    } catch (_) {
      editor.querySelector('.custom-waveform').textContent =
        'Waveform unavailable; exact timestamp controls still work.';
      return;
    }
    if (!editor.isConnected) return;
    const regions = RegionsPlugin.create();
    editor.querySelector('.custom-waveform').replaceChildren();
    const surface = WaveSurfer.create({
      container: editor.querySelector('.custom-waveform'),
      url: `/api/jobs/${job.id}/audio/wav`,
      peaks: [wave.peaks],
      duration: wave.duration,
      height: 128,
      waveColor: '#697061',
      progressColor: '#b9d63c',
      cursorColor: '#ffb65c',
      cursorWidth: 2,
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      normalize: false,
      dragToSeek: true,
      autoCenter: true,
      autoScroll: true,
      minPxPerSec: 0,
      plugins: [
        regions,
        TimelinePlugin.create({
          container: editor.querySelector('.custom-timeline'),
          style: { color: '#989991', fontSize: '10px' },
        }),
      ],
    });
    editor._customSurface = surface;
    renderArrangementTimeline(editor.querySelector('.custom-arrangement'), wave.timeline, wave.duration, surface);
    renderCustomLegend(editor.querySelector('.custom-legend'), wave.timeline);
    editor.querySelector('.custom-zoom').oninput = (event) => surface.zoom(Number(event.target.value));
    const time = editor.querySelector('.custom-wave-time');
    surface.on('timeupdate', (current) => {
      time.textContent = `${clock(current)} / ${clock(wave.duration)}`;
    });
    surface.on('ready', () => {
      const start = Number(editor.querySelector('.custom-start').value);
      const end = Number(editor.querySelector('.custom-end').value);
      editor._customRegion = regions.addRegion({
        start,
        end,
        color: 'rgba(214,255,68,.18)',
        drag: true,
        resize: true,
        minLength: 0.25,
      });
      editor.querySelector('.play-full-custom').disabled = false;
    });
    surface.on('play', () => {
      editor.querySelector('.play-full-custom').textContent = 'Ⅱ Pause full track';
    });
    surface.on('pause', () => {
      editor.querySelector('.play-full-custom').textContent = '▶ Play full track';
    });
    regions.on('region-updated', (region) => {
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
      'sparse/ambient': '#738c70',
      'melodic/harmonic': '#8f78bd',
      'rhythm-forward': '#4f9e91',
      'high-energy': '#c98545',
      'dynamic/transition': '#b56576',
      'vocal-forward': '#a66b8c',
      intro: '#718f72',
      verse: '#607d8b',
      buildup: '#b88445',
      drop: '#c45d43',
      breakdown: '#766da8',
      chorus: '#a85f73',
      closing: '#557f79',
      fade: '#59645f',
    };
    const labels = [
      ...new Set(
        [
          ...(timeline?.behavior || []).map((item) => item.style),
          ...(timeline?.arrangement || []).map((item) => item.label || item.name),
        ].filter(Boolean),
      ),
    ];
    root.innerHTML = labels
      .map((label) => `<span><i style="background:${colors[label] || '#657064'}"></i>${escapeHtml(label)}</span>`)
      .join('');
  }

  return Object.freeze({ load: loadReviews, stop: stopArrangementPreview });
}
