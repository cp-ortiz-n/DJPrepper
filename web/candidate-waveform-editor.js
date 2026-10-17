export function createCandidateWaveformEditor({
  processingWorkspaceApi,
  decodedAudio,
  renderArrangementTimeline,
  clock,
  escapeHtml,
  WaveSurfer,
  RegionsPlugin,
  TimelinePlugin,
}) {
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

  return Object.freeze({
    isPreviewing: (button) => arrangementPreview?.button === button,
    initializeCustomWaveform,
    initializeInsertionWaveform,
    previewArrangementInsertion,
    stopArrangementPreview,
    updateInsertionVisualization,
  });
}
