/** Transition scoring, preview playback, cue optimization, and editor ownership. */

export function createSetTransitionEditor({
  state,
  setBuilderApi,
  $,
  $$,
  notify,
  escapeHtml,
  clock,
  WaveSurfer,
  compatibility,
  harmonicCompatibility,
  songEnergy,
  targetSetEnergy,
  intendedGenreForPosition,
  trackMatchesIntendedGenre,
  identityTermMatches,
  optimizePlanOrder,
  setTrackId,
  setVocalProfile,
  timingProfile,
  stopCompactAudio,
  transitionReviewFeatures,
  transitionPreferenceAdjustment,
}) {
  let transitionPreviewAudio = [];
  let transitionPreviewFrame = 0;
  let transitionPreviewTimer = 0;
  let transitionPreviewPlayheadFrame = 0;
  let transitionPreviewState = null;
  let transitionEditorSurfaces = [];
  const transitionWaveCache = new Map();

  function closeTransitionEditors() {
    transitionEditorSurfaces.forEach((surface) => surface.destroy());
    transitionEditorSurfaces = [];
    document.querySelectorAll('.transition-editor').forEach((editor) => editor.remove());
  }

  function setTransitionOverlap(left, right) {
    const duration = Number(left?.duration_seconds || 0);
    const tail =
      Number.isFinite(Number(left?.mix_out)) && Number(left.mix_out) > 0 && duration > Number(left.mix_out)
        ? duration - Number(left.mix_out)
        : 0;
    const lead = Number(right?.mix_in || 0);
    const bpm = Math.max(60, Number(left?.bpm || right?.bpm || 120));
    const bars = Math.min(
      Number(left?.outro?.mixable_bars || left?.dj_readiness?.outro_mixable_bars || 0),
      Number(right?.intro?.mixable_bars || right?.dj_readiness?.intro_mixable_bars || 0),
    );
    const musical = bars > 0 ? (bars * 4 * 60) / bpm : 0;
    return Math.max(8, Math.min(90, Math.max(tail, lead, musical, 30)));
  }
  function setRuntime(plan = state.plan) {
    return plan.reduce(
      (sum, track, index) =>
        sum + Number(track.duration_seconds || 210) - (index ? setTransitionOverlap(plan[index - 1], track) : 0),
      0,
    );
  }
  function setHealth(plan = state.plan) {
    if (plan.length < 2) return { score: 100, transitions: [], vocalClashes: 0 };
    const transitions = plan
      .slice(1)
      .map((track, index) => ({ ...compatibility(plan[index], track), from: index, to: index + 1 }));
    const average = transitions.reduce((sum, item) => sum + item.score, 0) / transitions.length;
    const vocalClashes = plan
      .slice(1)
      .filter(
        (track, index) =>
          setVocalProfile(plan[index]) === 'vocal-forward' && setVocalProfile(track) === 'vocal-forward',
      ).length;
    const score = Math.max(0, Math.min(100, Math.round(average - vocalClashes * 3)));
    return { score, transitions, vocalClashes };
  }
  function setOrderFitness(plan, brief) {
    const health = setHealth(plan);
    const energyPenalty =
      plan.reduce(
        (sum, track, index) => sum + Math.abs(songEnergy(track) - targetSetEnergy(index, plan.length, brief)),
        0,
      ) * 3;
    const journeyFit = plan.reduce((sum, track, index) => {
      const target = intendedGenreForPosition(brief.identity, index, plan.length);
      return sum + (target && trackMatchesIntendedGenre(track, target) ? 16 : 0);
    }, 0);
    const openingCount = Math.max(1, Math.ceil(plan.length * 0.18));
    const openingFit = String(brief.identity?.opening || '').includes('melodic')
      ? plan.slice(0, openingCount).filter((track) => identityTermMatches(track, 'melodic')).length * 12
      : 0;
    return health.score * 5 - energyPenalty + journeyFit + openingFit;
  }
  function improveSetOrder(plan, brief) {
    return optimizePlanOrder(plan, {
      fitness: (candidate) => setOrderFitness(candidate, brief),
      isFixed: (track) => state.lockedIds.has(setTrackId(track)),
      maximumPasses: 16,
    });
  }
  function setHealthIssues(health, threshold) {
    const issues = [];
    health.transitions
      .filter((item) => item.score < threshold)
      .sort((a, b) => a.score - b.score)
      .slice(0, 4)
      .forEach((item) => {
        const weakest = Object.entries(item.components).sort((a, b) => a[1] - b[1])[0]?.[0] || 'compatibility';
        issues.push(
          `${item.from + 1}→${item.to + 1} ${item.score}% (${weakest}${item.key === 'distant key' ? ', distant keys' : ''})`,
        );
      });
    if (health.vocalClashes) issues.push(`${health.vocalClashes} vocal clash${health.vocalClashes === 1 ? '' : 'es'}`);
    return issues;
  }
  function transitionSettingKey(left, right) {
    return `${setTrackId(left)}→${setTrackId(right)}`;
  }
  function transitionSettings(index) {
    const left = state.plan[index - 1],
      right = state.plan[index];
    const key = transitionSettingKey(left, right);
    const bars = Number($('#set-transition-bars')?.value || 16);
    const bpm = Math.max(60, Number(left?.bpm || 120));
    const overlap = (bars * 4 * 60) / bpm;
    return (
      state.transitionSettings[key] || {
        mixOut: Math.max(0, Number(left?.mix_out || Number(left?.duration_seconds || 210) - overlap)),
        mixIn: Math.max(0, Number(right?.mix_in || 0)),
        bars,
        curve: 'smooth',
        technique: 'crossfade',
        tempoSync: true,
        notes: '',
      }
    );
  }
  function saveTransitionSettings(index, values) {
    const key = transitionSettingKey(state.plan[index - 1], state.plan[index]);
    state.transitionSettings[key] = { ...transitionSettings(index), ...values };
  }
  function stopTransitionPreview(nextPreviewLabel = '▶ Preview mix') {
    if (transitionPreviewFrame) cancelAnimationFrame(transitionPreviewFrame);
    if (transitionPreviewPlayheadFrame) cancelAnimationFrame(transitionPreviewPlayheadFrame);
    if (transitionPreviewTimer) clearTimeout(transitionPreviewTimer);
    transitionPreviewFrame = 0;
    transitionPreviewPlayheadFrame = 0;
    transitionPreviewTimer = 0;
    const previewEditor = transitionPreviewState?.button.closest('.transition-editor');
    if (previewEditor)
      updateTransitionFadePlayhead(
        previewEditor,
        0,
        transitionPreviewState.settings.curve,
        false,
        transitionPreviewState.settings.technique || 'crossfade',
      );
    transitionPreviewState?.audioGraph?.context?.close?.().catch(() => {});
    transitionPreviewAudio.forEach((audio) => {
      audio.pause();
      audio.removeAttribute('src');
    });
    transitionPreviewAudio = [];
    transitionPreviewState = null;
    $$('.set-audition').forEach((button) => {
      button.disabled = false;
      button.textContent = 'Mix transition';
      button.style.removeProperty('--mix-progress');
      button.classList.remove('playing', 'paused');
    });
    $$('.preview-transition').forEach((button) => {
      button.disabled = false;
      button.textContent = nextPreviewLabel;
      button.style.removeProperty('--mix-progress');
      button.classList.remove('playing', 'paused');
    });
  }
  function audioMetadata(audio) {
    return audio.readyState >= 1
      ? Promise.resolve()
      : new Promise((resolve, reject) => {
          audio.addEventListener('loadedmetadata', resolve, { once: true });
          audio.addEventListener('error', () => reject(new Error('Transition audio unavailable')), { once: true });
          audio.load();
        });
  }
  function createTransitionAudioGraph(outgoing, incoming, technique) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass || technique === 'crossfade' || technique === 'vocal-duck' || technique === 'drop-swap')
      return null;
    try {
      const context = new AudioContextClass(),
        outSource = context.createMediaElementSource(outgoing),
        inSource = context.createMediaElementSource(incoming),
        outFilter = context.createBiquadFilter(),
        inFilter = context.createBiquadFilter(),
        outEq = context.createBiquadFilter(),
        inEq = context.createBiquadFilter(),
        outGain = context.createGain(),
        inGain = context.createGain();
      outFilter.type = 'lowpass';
      outFilter.frequency.value = 20000;
      inFilter.type = 'highpass';
      inFilter.frequency.value = 20;
      outEq.type = 'lowshelf';
      outEq.frequency.value = 180;
      inEq.type = 'lowshelf';
      inEq.frequency.value = 180;
      outSource.connect(outFilter).connect(outEq).connect(outGain).connect(context.destination);
      inSource.connect(inFilter).connect(inEq).connect(inGain).connect(context.destination);
      const graph = { context, outFilter, inFilter, outEq, inEq, outGain, inGain };
      if (technique === 'echo-out') {
        const delay = context.createDelay(1),
          feedback = context.createGain(),
          echoGain = context.createGain();
        delay.delayTime.value = 0.32;
        feedback.gain.value = 0.28;
        echoGain.gain.value = 0;
        outEq.connect(delay);
        delay.connect(feedback).connect(delay);
        delay.connect(echoGain).connect(context.destination);
        Object.assign(graph, { delay, feedback, echoGain });
      }
      return graph;
    } catch (_) {
      return null;
    }
  }
  async function auditionTransition(index, button) {
    if (transitionPreviewState?.button === button) {
      toggleTransitionPreview();
      return;
    }
    stopTransitionPreview();
    const previous = state.plan[index - 1],
      next = state.plan[index];
    if (!previous?._job?.id || !next?._job?.id) return;
    stopCompactAudio();
    document.querySelectorAll('audio').forEach((audio) => audio.pause());
    const settings = transitionSettings(index);
    const bars = Number(settings.bars || 16);
    const outgoingBpm = Math.max(60, Number(previous.bpm || 120));
    const incomingBpm = Math.max(60, Number(next.bpm || outgoingBpm));
    const overlap = (bars * 4 * 60) / outgoingBpm;
    const lead = Math.min(6, overlap * 0.25);
    const outgoing = new Audio(`/api/jobs/${previous._job.id}/audio/wav`);
    const incoming = new Audio(`/api/jobs/${next._job.id}/audio/wav`);
    outgoing.preload = 'auto';
    incoming.preload = 'auto';
    incoming.volume = 0;
    incoming.playbackRate = settings.tempoSync ? Math.max(0.92, Math.min(1.08, outgoingBpm / incomingBpm)) : 1;
    transitionPreviewAudio = [outgoing, incoming];
    button.disabled = true;
    button.textContent = `Preparing ${bars}-bar mix…`;
    try {
      await Promise.all([audioMetadata(outgoing), audioMetadata(incoming)]);
      const outgoingStart = Math.max(0, Number(settings.mixOut || 0) - lead);
      outgoing.currentTime = Math.min(outgoingStart, Math.max(0, outgoing.duration - 1));
      incoming.currentTime = Math.min(Math.max(0, Number(settings.mixIn || 0)), Math.max(0, incoming.duration - 1));
      const audioGraph = createTransitionAudioGraph(outgoing, incoming, settings.technique || 'crossfade');
      transitionPreviewState = {
        button,
        outgoing,
        incoming,
        settings,
        bars,
        overlap,
        lead,
        outgoingBpm,
        audioGraph,
        phase: 'lead',
        remaining: lead,
        progress: 0,
        paused: false,
      };
      button.disabled = false;
      button.classList.add('playing');
      await audioGraph?.context?.resume?.();
      await outgoing.play();
      followTransitionPreviewPlayheads();
      runTransitionPreviewPhase();
    } catch (error) {
      console.error('Transition preview failed', error);
      stopTransitionPreview();
      const message = error?.message || 'Transition audio unavailable';
      button.textContent = 'Preview unavailable';
      button.title = message;
      notify(`Mix preview could not play: ${message}`, 'danger');
      setTimeout(() => {
        button.textContent = button.classList.contains('preview-transition') ? '▶ Preview mix' : 'Mix transition';
      }, 2400);
    }
  }
  function followTransitionPreviewPlayheads() {
    if (transitionPreviewPlayheadFrame) cancelAnimationFrame(transitionPreviewPlayheadFrame);
    const tick = () => {
      const state = transitionPreviewState;
      if (!state || state.paused) return;
      const editor = state.button.closest('.transition-editor');
      if (editor) {
        const outgoingInput = editor.querySelector('.transition-mix-out'),
          incomingInput = editor.querySelector('.transition-mix-in');
        [
          [outgoingInput, state.outgoing],
          [incomingInput, state.incoming],
        ].forEach(([input, audio]) => {
          const surface = input?._transitionSurface;
          if (!surface) return;
          const localTime = Math.max(
            0,
            Math.min(60, Number(audio.currentTime || 0) - Number(input._transitionWindowStart || 0)),
          );
          surface.setTime(localTime);
        });
        const fadeProgress = state.phase === 'lead' ? 0 : state.phase === 'tail' ? 1 : state.progress;
        updateTransitionFadePlayhead(
          editor,
          fadeProgress,
          state.settings.curve,
          true,
          state.settings.technique || 'crossfade',
        );
      }
      transitionPreviewPlayheadFrame = requestAnimationFrame(tick);
    };
    transitionPreviewPlayheadFrame = requestAnimationFrame(tick);
  }
  function applyTransitionFade(state, progress) {
    const { outgoing, incoming, settings, audioGraph } = state,
      technique = settings.technique || 'crossfade';
    let { outgoing: outLevel, incoming: inLevel } = transitionFadeLevels(settings.curve, progress, technique);
    if (technique === 'echo-out' && audioGraph?.echoGain) {
      audioGraph.echoGain.gain.setTargetAtTime(
        Math.max(0, (progress - 0.45) * 1.35),
        audioGraph.context.currentTime,
        0.03,
      );
    } else if (technique === 'bass-swap' && audioGraph) {
      const swap = Math.max(0, Math.min(1, (progress - 0.4) / 0.2));
      audioGraph.outEq.gain.setTargetAtTime(-20 * swap, audioGraph.context.currentTime, 0.03);
      audioGraph.inEq.gain.setTargetAtTime(-20 * (1 - swap), audioGraph.context.currentTime, 0.03);
    } else if (technique === 'filter-blend' && audioGraph) {
      audioGraph.outFilter.frequency.setTargetAtTime(
        20000 * Math.pow(0.025, progress),
        audioGraph.context.currentTime,
        0.03,
      );
      audioGraph.inFilter.frequency.setTargetAtTime(
        20 * Math.pow(75, 1 - progress),
        audioGraph.context.currentTime,
        0.03,
      );
    } else if (technique === 'loop-assist' && progress > 0.05 && progress < 0.72) {
      const beat = 60 / Math.max(60, Number(state.outgoingBpm || 120)),
        loopEnd = Number(settings.mixOut || 0),
        loopStart = Math.max(0, loopEnd - beat * 8);
      state.loopRepeats ??= 0;
      if (outgoing.currentTime >= loopEnd - 0.045 && state.loopRepeats < 2 && !state.loopPending) {
        state.loopPending = true;
        const gain = audioGraph?.outGain?.gain,
          now = audioGraph?.context?.currentTime || 0;
        if (gain) {
          gain.cancelScheduledValues(now);
          gain.setValueAtTime(gain.value, now);
          gain.linearRampToValueAtTime(0, now + 0.035);
        }
        setTimeout(() => {
          if (transitionPreviewState !== state) return;
          outgoing.currentTime = loopStart;
          state.loopRepeats += 1;
          state.loopPending = false;
          if (gain) {
            const resumeAt = audioGraph.context.currentTime;
            gain.cancelScheduledValues(resumeAt);
            gain.setValueAtTime(0, resumeAt);
            gain.linearRampToValueAtTime(1, resumeAt + 0.045);
          }
        }, 38);
      }
    }
    outgoing.volume = Math.max(0, Math.min(1, outLevel));
    incoming.volume = Math.max(0, Math.min(1, inLevel));
  }
  function runTransitionPreviewPhase() {
    const state = transitionPreviewState;
    if (!state || state.paused) return;
    const { button, outgoing, incoming } = state;
    button.classList.add('playing');
    button.classList.remove('paused');
    if (state.phase === 'lead') {
      button.textContent = `❚❚ Outgoing · mix in ${Math.ceil(state.remaining)}s`;
      state.started = performance.now();
      transitionPreviewTimer = setTimeout(async () => {
        if (!transitionPreviewState || state.paused) return;
        state.phase = 'mix';
        state.progress = 0;
        try {
          await incoming.play();
          runTransitionPreviewPhase();
        } catch (_) {
          stopTransitionPreview();
        }
      }, state.remaining * 1000);
      return;
    }
    button.textContent = `❚❚ Mixing ${state.bars} bars…`;
    state.started = performance.now() - state.progress * state.overlap * 1000;
    const fade = (now) => {
      if (!transitionPreviewState || state.paused) return;
      state.progress = Math.max(0, Math.min(1, (now - state.started) / (state.overlap * 1000)));
      applyTransitionFade(state, state.progress);
      button.style.setProperty('--mix-progress', `${Math.round(state.progress * 100)}%`);
      if (state.progress < 1) transitionPreviewFrame = requestAnimationFrame(fade);
      else stopTransitionPreview();
    };
    transitionPreviewFrame = requestAnimationFrame(fade);
  }
  function toggleTransitionPreview() {
    const state = transitionPreviewState;
    if (!state) return;
    if (!state.paused) {
      state.paused = true;
      if (transitionPreviewTimer) clearTimeout(transitionPreviewTimer);
      if (transitionPreviewFrame) cancelAnimationFrame(transitionPreviewFrame);
      if (transitionPreviewPlayheadFrame) cancelAnimationFrame(transitionPreviewPlayheadFrame);
      transitionPreviewTimer = 0;
      transitionPreviewFrame = 0;
      transitionPreviewPlayheadFrame = 0;
      if (state.phase !== 'mix')
        state.remaining = Math.max(0, (state.remaining * 1000 - (performance.now() - state.started)) / 1000);
      state.outgoing.pause();
      state.incoming.pause();
      state.audioGraph?.context?.suspend?.();
      state.button.classList.remove('playing');
      state.button.classList.add('paused');
      state.button.textContent = '▶ Resume mix';
      return;
    }
    state.paused = false;
    state.audioGraph?.context?.resume?.();
    state.button.classList.remove('paused');
    if (state.phase === 'lead') state.outgoing.play().catch(stopTransitionPreview);
    else if (state.phase === 'mix')
      Promise.all([state.outgoing.play(), state.incoming.play()]).catch(stopTransitionPreview);
    else state.incoming.play().catch(stopTransitionPreview);
    followTransitionPreviewPlayheads();
    runTransitionPreviewPhase();
  }
  async function initializeTransitionWave(container, track, input, color) {
    container.textContent = 'Loading waveform…';
    try {
      const wave = await transitionWaveData(track);
      if (!wave) throw new Error();
      container.replaceChildren();
      const windowSeconds = 60,
        halfWindow = windowSeconds / 2,
        sourcePeaks = Array.from(wave.peaks || []),
        peaksPerSecond = sourcePeaks.length / Math.max(1, wave.duration),
        windowPeakCount = Math.max(240, Math.round(peaksPerSecond * windowSeconds));
      const surface = WaveSurfer.create({
        container,
        height: 58,
        waveColor: '#77806f',
        progressColor: color,
        cursorColor: '#f2f3ed',
        cursorWidth: 2,
        barWidth: 2,
        barGap: 1,
        barRadius: 2,
        normalize: true,
        dragToSeek: true,
        minPxPerSec: 0,
      });
      transitionEditorSurfaces.push(surface);
      input._transitionSurface = surface;
      const renderWindow = (position) => {
        const center = Math.max(0, Math.min(wave.duration, Number(position) || 0)),
          windowStart = center - halfWindow,
          windowPeaks = Array.from({ length: windowPeakCount }, (_, index) => {
            const absoluteTime = windowStart + (index / windowPeakCount) * windowSeconds;
            if (absoluteTime < 0 || absoluteTime >= wave.duration) return 0;
            const sourceIndex = Math.min(
              sourcePeaks.length - 1,
              Math.max(0, Math.floor(absoluteTime * peaksPerSecond)),
            );
            return sourcePeaks[sourceIndex] || 0;
          });
        input._transitionWindowStart = windowStart;
        surface
          .load('', [Float32Array.from(windowPeaks)], windowSeconds)
          .then(() => surface.setTime(halfWindow))
          .catch(() => {});
      };
      input._renderTransitionWindow = renderWindow;
      surface.on('interaction', (seconds) => {
        input._recordTransitionUndo?.();
        const actual = Math.max(0, Math.min(wave.duration, input._transitionWindowStart + Number(seconds)));
        input.value = actual.toFixed(1);
        input.dispatchEvent(new Event('input', { bubbles: true }));
      });
      renderWindow(input.value);
    } catch (_) {
      container.textContent = 'Waveform unavailable · use the timing slider below.';
    }
  }
  function transitionFadeLevels(curve, progress, technique = 'crossfade') {
    let outgoing = 1 - progress,
      incoming = progress;
    if (curve === 'quick-cut') {
      outgoing = progress < 0.55 ? 1 : Math.max(0, 1 - (progress - 0.55) / 0.2);
      incoming = progress < 0.45 ? 0 : Math.min(1, (progress - 0.45) / 0.2);
    } else if (curve === 'long-blend') {
      outgoing = Math.cos((progress * Math.PI) / 2) * 0.9;
      incoming = Math.sin((progress * Math.PI) / 2) * 0.9;
    } else if (curve === 'smooth') {
      outgoing = Math.cos((progress * Math.PI) / 2);
      incoming = Math.sin((progress * Math.PI) / 2);
    }
    if (technique === 'vocal-duck') {
      const duck = 1 - 0.32 * Math.sin(progress * Math.PI) ** 2;
      outgoing *= duck;
      incoming *= duck;
    } else if (technique === 'drop-swap') {
      outgoing = progress < 0.5 ? 1 : 0;
      incoming = progress < 0.5 ? 0 : 1;
    } else if (technique === 'echo-out') outgoing *= progress < 0.55 ? 1 : Math.max(0, 1 - (progress - 0.55) / 0.3);
    return { outgoing, incoming };
  }
  function renderTransitionFadeCurve(panel, curve, bars, technique = 'crossfade') {
    const outgoing = panel.querySelector('.fade-out-path'),
      incoming = panel.querySelector('.fade-in-path'),
      label = panel.querySelector('.fade-curve-length');
    if (!outgoing || !incoming) return;
    const points = 48,
      path = (key) =>
        Array.from({ length: points + 1 }, (_, index) => {
          const progress = index / points,
            x = progress * 100,
            y = 22 - transitionFadeLevels(curve, progress, technique)[key] * 20;
          return `${index ? 'L' : 'M'}${x.toFixed(2)} ${y.toFixed(2)}`;
        }).join(' ');
    outgoing.setAttribute('d', path('outgoing'));
    incoming.setAttribute('d', path('incoming'));
    label.textContent = `${bars} bars`;
    updateTransitionFadePlayhead(panel, 0, curve, false, technique);
  }
  function updateTransitionFadePlayhead(panel, progress, curve, isActive = true, technique = 'crossfade') {
    const cursor = panel?.querySelector('.fade-live-line'),
      outgoing = panel?.querySelector('.fade-live-out'),
      incoming = panel?.querySelector('.fade-live-in'),
      status = panel?.querySelector('.fade-live-status');
    if (!cursor || !outgoing || !incoming) return;
    const value = Math.max(0, Math.min(1, Number(progress) || 0)),
      x = value * 100,
      levels = transitionFadeLevels(curve, value, technique);
    cursor.setAttribute('x1', x);
    cursor.setAttribute('x2', x);
    outgoing.setAttribute('cx', x);
    outgoing.setAttribute('cy', 22 - levels.outgoing * 20);
    incoming.setAttribute('cx', x);
    incoming.setAttribute('cy', 22 - levels.incoming * 20);
    cursor.closest('svg')?.classList.toggle('is-live', isActive);
    if (status)
      status.textContent = isActive ? `${Math.round(value * 100)}% through fade` : 'Preview to follow the fade';
  }
  function transitionWaveEnergy(wave, time, windowSeconds = 8) {
    const peaks = Array.from(wave?.peaks || []);
    if (!peaks.length || !wave?.duration) return 0.5;
    const start = Math.max(0, Math.floor(((time - windowSeconds / 2) / wave.duration) * peaks.length)),
      end = Math.min(peaks.length, Math.ceil(((time + windowSeconds / 2) / wave.duration) * peaks.length));
    const values = peaks.slice(start, Math.max(start + 1, end)).map((value) => Math.abs(Number(value) || 0));
    return values.reduce((sum, value) => sum + value, 0) / Math.max(1, values.length);
  }
  function transitionWaveData(track) {
    const id = track?._job?.id;
    if (!id) return Promise.resolve(null);
    if (!transitionWaveCache.has(id))
      transitionWaveCache.set(
        id,
        setBuilderApi.waveform(id).catch(() => null),
      );
    return transitionWaveCache.get(id);
  }
  function transitionCueCandidates(track, side = 'in') {
    const duration = Math.max(1, Number(track?.duration_seconds || 210));
    const bpm = Math.max(60, Number(track?.bpm || 120));
    const bar = (4 * 60) / bpm,
      phrase = bar * 8;
    const points = [];
    const add = (time, label, reason, score) => {
      const value = Math.max(0, Math.min(duration, Math.round(Number(time || 0) / bar) * bar));
      if (!Number.isFinite(value)) return;
      points.push({ time: value, label, reason, score });
    };
    if (side === 'in') {
      add(0, 'Track start', 'Opening downbeat', 100);
      add(Number(track?.mix_in || 0), 'Primary mix in', 'Existing analyzed cue', 105);
      add(phrase, 'First clean phrase', 'Eight bars after the opening', 96);
      add(phrase * 2, 'Second phrase', 'Sixteen bars after the opening', 90);
    } else {
      add(Number(track?.mix_out ?? duration - phrase), 'Primary mix out', 'Existing analyzed cue', 105);
      add(duration - phrase * 2, 'Earlier exit', 'Sixteen bars before the ending', 90);
      add(duration - phrase, 'Final clean phrase', 'Eight bars before the ending', 96);
      add(duration, 'Track end', 'End of the recording', 100);
    }
    (track?.arrangement_sections || []).forEach((section) => {
      const label = String(section.label || 'section').toLowerCase(),
        confidence = Number(section.confidence || 0.5);
      if (side === 'in') {
        if (section.start <= duration * 0.8 && /drop|chorus|groove|main|verse/.test(label))
          add(
            section.start,
            `${label.includes('drop') ? 'Drop' : 'Groove'} entry`,
            `${section.label} begins`,
            80 + confidence * 12,
          );
        if (section.end <= duration * 0.8 && /intro|break|build/.test(label))
          add(section.end, `After ${section.label}`, `Clean boundary after ${section.label}`, 76 + confidence * 12);
      } else {
        if (section.start >= duration * 0.25 && /break|outro|build/.test(label))
          add(section.start, `${section.label} begins`, `Exit at the start of ${section.label}`, 82 + confidence * 12);
        if (section.end >= duration * 0.25 && /drop|chorus|groove|main|verse/.test(label))
          add(section.end, `After ${section.label}`, `Exit after ${section.label}`, 74 + confidence * 12);
      }
    });
    (track?.section_profiles || []).forEach((section) => {
      const name = String(section.name || section.style || 'section'),
        style = String(section.style || '').toLowerCase(),
        confidence = Number(section.confidence || 0.5);
      if (side === 'in' && section.start <= duration * 0.8 && /instrument|sparse|groove|steady|break/.test(style))
        add(section.start, `${name} entry`, `Low-conflict section · ${section.style}`, 72 + confidence * 10);
      if (side === 'out' && section.start >= duration * 0.25 && /closing|break|sparse|transition/.test(style))
        add(section.start, `${name} exit`, `Transition-safe section · ${section.style}`, 76 + confidence * 10);
    });
    const deduped = new Map();
    points.forEach((point) => {
      const key = Math.round(point.time * 2) / 2,
        existing = deduped.get(key);
      if (!existing || point.score > existing.score) deduped.set(key, point);
    });
    const ranked = [...deduped.values()].sort((a, b) => b.score - a.score),
      chosen = [];
    ranked.forEach((point) => {
      const repeated = chosen.filter((item) => item.label === point.label).length >= 2,
        tooClose = chosen.some((item) => Math.abs(item.time - point.time) < phrase / 2);
      if (chosen.length < 8 && (!repeated || point.score >= 100) && (!tooClose || point.score >= 96))
        chosen.push(point);
    });
    return chosen.sort((a, b) => a.time - b.time);
  }
  async function optimizeTransitionCandidates(left, right) {
    const [leftWave, rightWave] = await Promise.all([transitionWaveData(left), transitionWaveData(right)]);
    const bpmA = Math.max(60, Number(left.bpm || 120)),
      bpmB = Math.max(60, Number(right.bpm || bpmA)),
      durationA = Math.max(1, Number(left.duration_seconds || leftWave?.duration || 210)),
      durationB = Math.max(1, Number(right.duration_seconds || rightWave?.duration || 210)),
      tempoDifference = Math.min(
        Math.abs(bpmA - bpmB) / bpmA,
        Math.abs(bpmA - bpmB * 2) / bpmA,
        Math.abs(bpmA - bpmB / 2) / bpmA,
      ),
      harmonic = harmonicCompatibility(left.key, right.key),
      energyDifference = Math.abs(songEnergy(left) - songEnergy(right)),
      vocalCollision = setVocalProfile(left) === 'vocal-forward' && setVocalProfile(right) === 'vocal-forward',
      outroInstrumental = Math.max(
        Number(left.outro?.instrumentalness || 0),
        Number(left.intro?.instrumentalness || 0),
      ),
      variableTiming = timingProfile(left) === 'variable' || timingProfile(right) === 'variable',
      genre = `${left._genre || ''} ${right._genre || ''}`.toLowerCase(),
      danceGenre = /house|techno|electronic|reggaeton|salsa|bachata|dance/.test(genre),
      techniques = ['crossfade', 'bass-swap', 'filter-blend', 'vocal-duck', 'echo-out', 'drop-swap', 'loop-assist'],
      curves = ['smooth', 'linear', 'quick-cut', 'long-blend'],
      outCues = transitionCueCandidates(left, 'out'),
      inCues = transitionCueCandidates(right, 'in'),
      candidates = [];
    for (const bars of [8, 16, 32]) {
      const overlap = (bars * 4 * 60) / bpmA,
        eligibleOut = outCues.filter((cue) => cue.time >= overlap && cue.time < durationA),
        eligibleIn = inCues.filter((cue) => cue.time + overlap <= durationB);
      for (const outCue of eligibleOut.length ? eligibleOut : outCues.slice(-1))
        for (const inCue of eligibleIn.length ? eligibleIn : inCues.slice(0, 1)) {
          const mixOut = Math.max(overlap, Math.min(durationA - 1, outCue.time)),
            mixIn = Math.max(0, Math.min(durationB - 1, inCue.time)),
            outEnergy = transitionWaveEnergy(leftWave, mixOut),
            inEnergy = transitionWaveEnergy(rightWave, mixIn),
            loudnessScore = 15 * Math.max(0, 1 - Math.abs(outEnergy - inEnergy) / Math.max(0.05, outEnergy, inEnergy));
          for (const technique of techniques)
            for (const curve of curves) {
              let phraseScore =
                20 *
                  Math.min(
                    1,
                    Math.min(Number(left.beat_grid_confidence ?? 0.75), Number(right.beat_grid_confidence ?? 0.75)) +
                      0.2,
                  ) +
                5 * Math.min(1, (Number(outCue.score || 0) + Number(inCue.score || 0)) / 210);
              const availableBars = Math.min(
                Number(left.outro?.mixable_bars || left.dj_readiness?.outro_mixable_bars || 32),
                Number(right.intro?.mixable_bars || right.dj_readiness?.intro_mixable_bars || 32),
              );
              if (bars > availableBars) phraseScore -= Math.min(10, (bars - availableBars) / 2);
              const tempoScore = 25 * Math.max(0, 1 - tempoDifference / 0.12),
                keyScore = 15 * (harmonic.score / 40),
                energyScore = 10 * Math.max(0, 1 - energyDifference / 0.65),
                timingScore = variableTiming ? 3 : 5;
              let vocalScore = vocalCollision
                  ? technique === 'vocal-duck'
                    ? 10
                    : technique === 'echo-out' || technique === 'drop-swap'
                      ? 8
                      : 3
                  : 10,
                techniqueBonus = 0;
              if (technique === 'bass-swap' && danceGenre) techniqueBonus += 5;
              if (technique === 'filter-blend' && !variableTiming) techniqueBonus += 4;
              if (technique === 'echo-out' && tempoDifference > 0.05) techniqueBonus += 5;
              if (technique === 'drop-swap') {
                techniqueBonus -= 16;
                if (
                  tempoDifference > 0.1 &&
                  energyDifference > 0.4 &&
                  Number(left.beat_grid_confidence || 0) > 0.85 &&
                  Number(right.beat_grid_confidence || 0) > 0.85
                )
                  techniqueBonus += 8;
              }
              if (technique === 'loop-assist') {
                techniqueBonus -= 22;
                if (variableTiming && outroInstrumental >= 0.85 && Number(left.beat_grid_confidence || 0) > 0.9)
                  techniqueBonus += 6;
                if (vocalCollision) techniqueBonus -= 6;
              }
              if (technique === 'crossfade' && tempoDifference < 0.025 && !vocalCollision) techniqueBonus += 3;
              if (curve === 'quick-cut' && (technique === 'drop-swap' || tempoDifference > 0.07)) techniqueBonus += 3;
              if (
                curve === 'smooth' &&
                (technique === 'crossfade' || technique === 'bass-swap' || technique === 'filter-blend')
              )
                techniqueBonus += 2;
              const rawScore =
                  phraseScore +
                  tempoScore +
                  keyScore +
                  loudnessScore +
                  vocalScore +
                  energyScore +
                  timingScore +
                  techniqueBonus,
                score = Math.max(0, Math.min(100, Math.round(rawScore / 1.15)));
              candidates.push({
                score,
                mixOut,
                mixIn,
                outCueLabel: outCue.label,
                inCueLabel: inCue.label,
                bars,
                curve,
                technique,
                tempoSync: tempoDifference > 0.008,
                components: {
                  phrase: Math.round(phraseScore),
                  tempo: Math.round(tempoScore),
                  key: Math.round(keyScore),
                  loudness: Math.round(loudnessScore),
                  vocals: Math.round(vocalScore),
                  energy: Math.round(energyScore),
                  timing: Math.round(timingScore),
                },
                reason: `${outCue.label} → ${inCue.label} · ${harmonic.label} · ${Math.round(loudnessScore)}/15 loudness · ${vocalCollision ? 'vocal protection' : 'clear vocals'}`,
              });
            }
        }
    }
    return candidates
      .sort((a, b) => b.score - a.score)
      .filter((candidate, index, list) => list.findIndex((item) => item.technique === candidate.technique) === index)
      .slice(0, 3);
  }
  async function runBounded(tasks, limit = 3) {
    let cursor = 0;
    const worker = async () => {
      while (cursor < tasks.length) {
        const task = tasks[cursor++];
        await task();
      }
    };
    await Promise.all(Array.from({ length: Math.min(limit, tasks.length) }, worker));
  }
  function personalizeTransitionCandidates(candidates, left, right) {
    return candidates
      .map((candidate) => {
        const features = {
          ...transitionReviewFeatures(left, right, 1),
          bars: String(candidate.bars),
          technique: candidate.technique,
        };
        const preferenceAdjustment = transitionPreferenceAdjustment(features);
        return {
          ...candidate,
          preferenceAdjustment,
          score: Math.max(0, Math.min(100, candidate.score + preferenceAdjustment)),
        };
      })
      .sort((a, b) => b.score - a.score);
  }
  async function autoOptimizeSetTransitions() {
    const pending = [];
    for (let index = 1; index < state.plan.length; index += 1) {
      const key = transitionSettingKey(state.plan[index - 1], state.plan[index]),
        existing = state.transitionSettings[key];
      if (existing && (!existing.optimized || Number(existing.optimizedVersion || 0) >= 4)) continue;
      pending.push(async () => {
        const candidates = personalizeTransitionCandidates(
          await optimizeTransitionCandidates(state.plan[index - 1], state.plan[index]),
          state.plan[index - 1],
          state.plan[index],
        );
        if (candidates[0])
          state.transitionSettings[key] = {
            ...transitionSettings(index),
            ...candidates[0],
            optimized: true,
            optimizedVersion: 5,
          };
      });
    }
    await runBounded(pending, 3);
    return pending.length;
  }
  function openTransitionEditor(index, card) {
    document.querySelectorAll('.transition-editor').forEach((editor) => editor.remove());
    transitionEditorSurfaces.forEach((surface) => surface.destroy());
    transitionEditorSurfaces = [];
    const left = state.plan[index - 1],
      right = state.plan[index],
      settings = transitionSettings(index);
    const panel = document.createElement('section');
    panel.className = 'transition-editor';
    const leftDuration = Math.max(1, Number(left.duration_seconds || 210)),
      rightDuration = Math.max(1, Number(right.duration_seconds || 210));
    const titleId = `transition-editor-title-${index}`;
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-labelledby', titleId);
    panel.innerHTML = `<header><div><strong id="${titleId}">Transition ${index} → ${index + 1}</strong><span>${escapeHtml(left.source_name.replace(/\.[^.]+$/, ''))} into ${escapeHtml(right.source_name.replace(/\.[^.]+$/, ''))}</span></div><div class="transition-header-actions"><button type="button" class="optimize-transition">✦ Find best</button><button type="button" class="undo-transition-timing" disabled>↶ Undo timing</button><button type="button" class="close-transition-editor" aria-label="Close transition editor">×</button></div></header><div class="transition-wave-stack"><span class="transition-point-label">Mix starts here · matched 60-second view</span><span class="transition-point-line" aria-hidden="true"></span><div class="transition-wave-row"><label>Outgoing mix-out <b class="mix-out-label">${clock(settings.mixOut)}</b></label><div class="transition-wave outgoing-wave"></div><input class="transition-mix-out" type="range" min="0" max="${leftDuration}" step="0.1" value="${settings.mixOut}"><div class="transition-cue-options outgoing-cues" aria-label="Alternative outgoing cue points"></div></div><div class="transition-wave-row"><label>Incoming mix-in <b class="mix-in-label">${clock(settings.mixIn)}</b></label><div class="transition-wave incoming-wave"></div><input class="transition-mix-in" type="range" min="0" max="${rightDuration}" step="0.1" value="${settings.mixIn}"><div class="transition-cue-options incoming-cues" aria-label="Alternative incoming cue points"></div></div></div><div class="transition-fade-visual"><div><span>Fade shape</span><b class="fade-curve-length">${settings.bars} bars</b></div><svg viewBox="0 0 100 24" preserveAspectRatio="none" aria-label="Transition fade curve"><path class="fade-grid" d="M0 12 H100 M50 1 V23"></path><path class="fade-out-path"></path><path class="fade-in-path"></path><line class="fade-live-line" x1="0" x2="0" y1="1" y2="23"></line><circle class="fade-live-out" cx="0" cy="2" r="1.6"></circle><circle class="fade-live-in" cx="0" cy="22" r="1.6"></circle></svg><div class="fade-legend"><span class="fade-out-key">Outgoing</span><span class="fade-in-key">Incoming</span><small class="fade-live-status">Preview to follow the fade</small></div></div><div class="transition-optimizer-results" hidden></div><div class="transition-editor-controls"><label>Length<select class="transition-bars"><option value="8">8 bars</option><option value="16">16 bars</option><option value="32">32 bars</option></select></label><label>Fade curve<select class="transition-curve"><option value="smooth">Smooth equal-power</option><option value="linear">Linear</option><option value="quick-cut">Quick cut</option><option value="long-blend">Long blend</option></select></label><label>Technique<select class="transition-technique"><option value="crossfade">Classic crossfade</option><option value="bass-swap">Bass swap</option><option value="filter-blend">Filter blend</option><option value="vocal-duck">Vocal duck</option><option value="echo-out">Echo out</option><option value="drop-swap">Drop swap</option><option value="loop-assist">Loop-assisted blend</option></select></label><label class="transition-tempo"><input type="checkbox" class="transition-tempo-sync"> Tempo match</label><label class="transition-notes">Transition notes<input class="transition-note" type="text" maxlength="300" placeholder="Loop 8 bars, swap bass on phrase…" value="${escapeHtml(settings.notes || '')}"></label><button type="button" class="preview-transition">▶ Preview mix</button><button type="button" class="close-transition-editor-bottom">Done editing</button></div>`;
    card.append(panel);
    const mixOut = panel.querySelector('.transition-mix-out'),
      mixIn = panel.querySelector('.transition-mix-in'),
      bars = panel.querySelector('.transition-bars'),
      curve = panel.querySelector('.transition-curve'),
      technique = panel.querySelector('.transition-technique'),
      sync = panel.querySelector('.transition-tempo-sync'),
      notes = panel.querySelector('.transition-note'),
      undo = panel.querySelector('.undo-transition-timing'),
      optimizer = panel.querySelector('.optimize-transition'),
      optimizerResults = panel.querySelector('.transition-optimizer-results');
    bars.value = String(settings.bars);
    curve.value = settings.curve;
    technique.value = settings.technique || 'crossfade';
    sync.checked = settings.tempoSync;
    const withCurrentCue = (cues, time) =>
      cues.some((cue) => Math.abs(cue.time - Number(time)) < 0.25)
        ? cues
        : [
            ...cues,
            {
              time: Number(time),
              label: 'Current selection',
              reason: 'Current optimized or manually selected cue',
              score: 110,
            },
          ].sort((a, b) => a.time - b.time);
    const cueBindings = [
      [
        panel.querySelector('.outgoing-cues'),
        withCurrentCue(transitionCueCandidates(left, 'out'), settings.mixOut),
        mixOut,
      ],
      [
        panel.querySelector('.incoming-cues'),
        withCurrentCue(transitionCueCandidates(right, 'in'), settings.mixIn),
        mixIn,
      ],
    ];
    const refreshCueButtons = () =>
      cueBindings.forEach(([root, cues, input]) =>
        root
          .querySelectorAll('button')
          .forEach((button) =>
            button.classList.toggle('active', Math.abs(Number(button.dataset.time) - Number(input.value)) < 0.25),
          ),
      );
    cueBindings.forEach(([root, cues, input]) => {
      root.innerHTML = cues
        .map(
          (cue) =>
            `<button type="button" data-time="${cue.time.toFixed(2)}" title="${escapeHtml(cue.reason)}"><b>${escapeHtml(cue.label)}</b><span>${clock(cue.time)}</span></button>`,
        )
        .join('');
      root.querySelectorAll('button').forEach(
        (button) =>
          (button.onclick = () => {
            recordTimingUndo();
            input.value = button.dataset.time;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            refreshCueButtons();
          }),
      );
    });
    const persist = () =>
      saveTransitionSettings(index, {
        mixOut: Number(mixOut.value),
        mixIn: Number(mixIn.value),
        bars: Number(bars.value),
        curve: curve.value,
        technique: technique.value,
        tempoSync: sync.checked,
        notes: notes.value,
        optimized: false,
      });
    const restartPreview = () => {
      if (transitionPreviewState?.button.closest('.transition-editor') === panel)
        stopTransitionPreview('↻ Preview updated mix');
    };
    const timingHistory = [];
    const timingSnapshot = () => ({ mixOut: Number(mixOut.value), mixIn: Number(mixIn.value) });
    const recordTimingUndo = () => {
      const snapshot = timingSnapshot(),
        last = timingHistory.at(-1);
      if (last && last.mixOut === snapshot.mixOut && last.mixIn === snapshot.mixIn) return;
      timingHistory.push(snapshot);
      undo.disabled = false;
    };
    mixOut._recordTransitionUndo = recordTimingUndo;
    mixIn._recordTransitionUndo = recordTimingUndo;
    const syncWave = (input) => input._renderTransitionWindow?.(Number(input.value));
    const refreshTiming = () => {
      panel.querySelector('.mix-out-label').textContent = clock(Number(mixOut.value));
      panel.querySelector('.mix-in-label').textContent = clock(Number(mixIn.value));
      syncWave(mixOut);
      syncWave(mixIn);
      restartPreview();
      persist();
    };
    mixOut.oninput = () => {
      panel.querySelector('.mix-out-label').textContent = clock(Number(mixOut.value));
      syncWave(mixOut);
      restartPreview();
      persist();
      refreshCueButtons();
    };
    mixIn.oninput = () => {
      panel.querySelector('.mix-in-label').textContent = clock(Number(mixIn.value));
      syncWave(mixIn);
      restartPreview();
      persist();
      refreshCueButtons();
    };
    undo.onclick = () => {
      const previous = timingHistory.pop();
      if (!previous) return;
      mixOut.value = previous.mixOut;
      mixIn.value = previous.mixIn;
      refreshTiming();
      undo.disabled = !timingHistory.length;
    };
    panel
      .querySelectorAll('input,select,button,.transition-wave')
      .forEach((control) => control.addEventListener('pointerdown', (event) => event.stopPropagation()));
    panel.querySelectorAll('input[type="range"]').forEach((control) => {
      control.addEventListener('pointerdown', () => {
        recordTimingUndo();
        card.draggable = false;
      });
      control.addEventListener('keydown', (event) => {
        if (event.key.startsWith('Arrow') || event.key === 'Home' || event.key === 'End') recordTimingUndo();
      });
      control.addEventListener('pointerup', () => {
        card.draggable = !card.classList.contains('locked');
      });
      control.addEventListener('pointercancel', () => {
        card.draggable = !card.classList.contains('locked');
      });
    });
    [bars, curve, technique, sync].forEach((control) =>
      control.addEventListener('change', () => {
        restartPreview();
        persist();
      }),
    );
    notes.addEventListener('change', persist);
    [bars, curve, technique].forEach((control) =>
      control.addEventListener('change', () =>
        renderTransitionFadeCurve(panel, curve.value, Number(bars.value), technique.value),
      ),
    );
    renderTransitionFadeCurve(panel, curve.value, Number(bars.value), technique.value);
    refreshCueButtons();
    optimizer.onclick = async () => {
      optimizer.disabled = true;
      optimizer.textContent = 'Scoring…';
      optimizerResults.hidden = false;
      optimizerResults.innerHTML =
        '<p>Comparing timing, phrasing, harmony, loudness, vocals, energy, and technique…</p>';
      try {
        const candidates = await optimizeTransitionCandidates(left, right);
        optimizerResults.innerHTML = candidates
          .map(
            (candidate, candidateIndex) =>
              `<article class="${candidateIndex ? '' : 'recommended'}" data-candidate="${candidateIndex}"><div><b>${candidateIndex ? 'Alternative ' + (candidateIndex + 1) : 'Recommended'} · ${candidate.score}/100</b><strong>${escapeHtml(candidate.technique.replaceAll('-', ' '))} · ${candidate.bars} bars · ${escapeHtml(candidate.curve.replaceAll('-', ' '))}</strong><span>${clock(candidate.mixOut)} → ${clock(candidate.mixIn)} · ${escapeHtml(candidate.reason)}</span><small>Phrase ${candidate.components.phrase}/25 · tempo ${candidate.components.tempo}/25 · key ${candidate.components.key}/15 · loudness ${candidate.components.loudness}/15 · vocals ${candidate.components.vocals}/10</small></div><button type="button">Apply</button></article>`,
          )
          .join('');
        optimizerResults.querySelectorAll('[data-candidate]').forEach(
          (row) =>
            (row.querySelector('button').onclick = () => {
              const candidate = candidates[Number(row.dataset.candidate)];
              recordTimingUndo();
              mixOut.value = candidate.mixOut;
              mixIn.value = candidate.mixIn;
              bars.value = String(candidate.bars);
              curve.value = candidate.curve;
              technique.value = candidate.technique;
              sync.checked = candidate.tempoSync;
              refreshTiming();
              renderTransitionFadeCurve(panel, curve.value, Number(bars.value), technique.value);
              optimizerResults
                .querySelectorAll('article')
                .forEach((item) => item.classList.toggle('applied', item === row));
            }),
        );
      } catch (error) {
        optimizerResults.innerHTML = `<p>Could not score this transition: ${escapeHtml(error.message)}</p>`;
      } finally {
        optimizer.disabled = false;
        optimizer.textContent = '✦ Find best';
      }
    };
    const closeEditor = () => {
      stopTransitionPreview();
      transitionEditorSurfaces.forEach((surface) => surface.destroy());
      transitionEditorSurfaces = [];
      panel.remove();
      card.querySelector('.edit-transition')?.focus();
    };
    panel.querySelectorAll('.close-transition-editor, .close-transition-editor-bottom').forEach((button) => {
      button.onclick = closeEditor;
    });
    panel.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      closeEditor();
    });
    panel.querySelector('.preview-transition').onclick = (event) => {
      persist();
      auditionTransition(index, event.currentTarget);
    };
    initializeTransitionWave(panel.querySelector('.outgoing-wave'), left, mixOut, '#ffb45c');
    initializeTransitionWave(panel.querySelector('.incoming-wave'), right, mixIn, '#d6ff44');
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    panel.querySelector('.close-transition-editor').focus({ preventScroll: true });
  }
  function setSvgCurve(selector, values, color) {
    const svg = $(selector);
    if (!values.length) {
      svg.replaceChildren();
      return;
    }
    const low = Math.min(...values);
    const high = Math.max(...values);
    const range = Math.max(0.001, high - low);
    const points = values
      .map((value, index) => `${(index * 600) / Math.max(1, values.length - 1)},${80 - ((value - low) / range) * 65}`)
      .join(' ');
    svg.innerHTML = `<polyline points="${points}" fill="none" stroke="${color}" stroke-width="3" vector-effect="non-scaling-stroke"/><line x1="0" y1="80" x2="600" y2="80" stroke="#30332f"/>`;
  }

  return Object.freeze({
    autoOptimizeSetTransitions,
    auditionTransition,
    closeTransitionEditors,
    improveSetOrder,
    openTransitionEditor,
    setHealth,
    setHealthIssues,
    setRuntime,
    setSvgCurve,
    stopTransitionPreview,
    transitionSettings,
  });
}
