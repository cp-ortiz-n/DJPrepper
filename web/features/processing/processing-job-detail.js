export function createProcessingJobDetail({
  WaveSurfer,
  RegionsPlugin,
  TimelinePlugin,
  HoverPlugin,
  clock,
  escapeHtml,
  fetchImpl = fetch,
}) {
  function renderArrangementTimeline(root, timeline, duration, wavesurfer) {
    const lanes = [
      ['behavior', 'Musical feel'],
      ['arrangement', 'Song section'],
      ['edits', 'Generated'],
    ];
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
      'Extended intro': '#b7d93d',
      'Extended outro': '#8fb32f',
    };
    const markup = lanes
      .map(([key, label]) => {
        const items = (timeline?.[key] || [])
          .filter((item) => item.end > item.start)
          .map((item) => {
            const name = item.style || item.label || item.name || 'section';
            const left = (100 * item.start) / duration;
            const width = (100 * (item.end - item.start)) / duration;
            const confidence = item.confidence == null ? '' : ` · ${Math.round(100 * item.confidence)}%`;
            const detail = `${name} · ${clock(item.start)}–${clock(item.end)}${confidence}`;
            return `<button type="button" class="arrangement-segment" style="left:${left}%;width:${Math.max(width, 0.35)}%;background:${colors[name] || '#657064'}" data-time="${item.start}" title="${escapeHtml(detail)}"><span>${width >= 8 ? escapeHtml(name) : ''}</span></button>`;
          })
          .join('');
        return items ? `<div class="arrangement-row"><b>${label}</b><div>${items}</div></div>` : '';
      })
      .join('');
    root.innerHTML = markup || '<p>Section timeline appears after this track is reprocessed.</p>';
    root.querySelectorAll('.arrangement-segment').forEach((segment) => {
      segment.onclick = () => wavesurfer.setTime(Number(segment.dataset.time));
    });
  }

  function createWaveform(container, timeline, arrangement, wave, cues, media) {
    const regions = RegionsPlugin.create();
    const wavesurfer = WaveSurfer.create({
      container,
      media,
      peaks: [wave.peaks],
      duration: wave.duration,
      height: 104,
      waveColor: '#62695a',
      progressColor: '#d6ff44',
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
        TimelinePlugin.create({ container: timeline, style: { color: '#989991', fontSize: '10px' } }),
        HoverPlugin.create({ lineColor: '#ffb65c', labelBackground: '#202320', labelColor: '#d6ff44' }),
      ],
    });
    renderArrangementTimeline(arrangement, wave.timeline, wave.duration, wavesurfer);
    wavesurfer.on('ready', () => {
      cues.forEach((cue) =>
        regions.addRegion({
          start: cue.start,
          end: cue.end || Math.min(wave.duration, cue.start + 0.06),
          content: cue.kind === 'loop' ? cue.name : '',
          color: cue.kind === 'loop' ? 'rgba(214,255,68,.18)' : 'rgba(255,182,92,.24)',
          drag: false,
          resize: false,
        }),
      );
    });
    return wavesurfer;
  }

  function renderCues(root, jobId, cues) {
    const cueName = (cue) => (cue.name === 'First Reliable Downbeat' ? 'Beat Grid Anchor' : cue.name);
    root.innerHTML = `<div class="cue-list">${cues.map((cue, index) => `<label class="cue-chip">${escapeHtml(cueName(cue))} <input data-index="${index}" type="number" min="0" step="0.01" value="${cue.start}"></label>`).join('')}</div><button class="button secondary save-cues">Save cue positions</button><span class="override-message"></span>`;
    root.querySelector('.save-cues').onclick = async () => {
      root.querySelectorAll('input').forEach((input) => {
        cues[Number(input.dataset.index)].start = Number(input.value);
      });
      const response = await fetchImpl(`/api/jobs/${jobId}/cues`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cues }),
      });
      root.querySelector('.override-message').textContent = response.ok
        ? 'Cue sheet and Rekordbox XML updated.'
        : 'Could not save cues.';
    };
  }

  async function hydrate(node, job) {
    let jobConfig = {};
    try {
      jobConfig = JSON.parse(job.config_json || '{}');
    } catch (_) {
      jobConfig = {};
    }
    const hasExtendedAudio = !jobConfig.analysis_only && Boolean(job.extended_path);
    const [sourceWave, extendedWave, cues, override] = await Promise.all([
      fetchImpl(`/api/jobs/${job.id}/waveform/wav`).then((response) => (response.ok ? response.json() : null)),
      hasExtendedAudio
        ? fetchImpl(`/api/jobs/${job.id}/waveform/extended`).then((response) => (response.ok ? response.json() : null))
        : Promise.resolve(null),
      fetchImpl(`/api/jobs/${job.id}/cues`).then((response) => response.json()),
      fetchImpl(`/api/overrides/${encodeURIComponent(job.source_name)}`).then((response) => response.json()),
    ]);
    if (!node.isConnected) return;
    const sourceSurface = sourceWave
      ? createWaveform(
          node.querySelector('.waveform-source'),
          node.querySelector('.timeline-source'),
          node.querySelector('.arrangement-source'),
          sourceWave,
          [],
          node.querySelector('.source-player audio'),
        )
      : null;
    const extendedSurface = extendedWave
      ? createWaveform(
          node.querySelector('.waveform-extended'),
          node.querySelector('.timeline-extended'),
          node.querySelector('.arrangement-extended'),
          extendedWave,
          cues.cues || [],
          node.querySelector('.extended-player audio'),
        )
      : null;
    let activeSurface = extendedSurface || sourceSurface;
    renderCues(node.querySelector('.cue-editor'), job.id, cues.cues || []);
    const form = node.querySelector('.override-editor');
    Object.entries(override).forEach(([key, value]) => {
      form.elements[key].value = value ?? '';
    });
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const values = {};
      ['intro_before', 'outro_after', 'outro_before'].forEach((key) => {
        values[key] = form.elements[key].value ? Number(form.elements[key].value) : null;
      });
      const response = await fetchImpl(`/api/overrides/${encodeURIComponent(job.source_name)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      });
      form.querySelector('.override-message').textContent = response.ok
        ? 'Saved. Reprocess to apply these boundaries.'
        : (await response.json()).detail;
    });
    const surfaces = [sourceSurface, extendedSurface];
    const pauseAll = (except) =>
      surfaces.forEach((surface) => {
        if (surface && surface !== except) surface.pause();
      });
    const playSurface = (surface) => {
      if (!surface) return;
      pauseAll(surface);
      activeSurface = surface;
      surface.play();
    };
    sourceSurface?.on('interaction', () => {
      pauseAll(sourceSurface);
      activeSurface = sourceSurface;
    });
    extendedSurface?.on('interaction', () => {
      pauseAll(extendedSurface);
      activeSurface = extendedSurface;
    });
    node.querySelector('.play-source').onclick = () => playSurface(sourceSurface);
    node.querySelector('.play-extended').onclick = () => playSurface(extendedSurface);
    node.querySelector('.wave-play').onclick = () => activeSurface?.playPause();
    node.querySelector('.sync-audio').onclick = () => {
      const current = activeSurface?.getCurrentTime() || 0;
      surfaces.forEach((surface) => surface?.setTime(Math.min(surface.getDuration(), current)));
    };
    node.querySelector('.wave-zoom').oninput = (event) =>
      surfaces.forEach((surface) => surface?.zoom(Number(event.target.value)));
    const time = node.querySelector('.wave-time');
    surfaces.forEach((surface) => {
      surface?.on('timeupdate', (current) => {
        if (surface === activeSurface) time.textContent = `${clock(current)} / ${clock(surface.getDuration())}`;
      });
      surface?.on('play', () => {
        activeSurface = surface;
        node.querySelector('.wave-play').textContent = 'Ⅱ Pause';
      });
      surface?.on('pause', () => {
        if (surface === activeSurface) node.querySelector('.wave-play').textContent = '▶ Play';
      });
    });
  }

  return { hydrate, renderArrangementTimeline };
}
