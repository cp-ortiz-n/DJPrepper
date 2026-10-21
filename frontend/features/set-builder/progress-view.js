/** Focused, accessible progress presentation for Set Builder's long-running work. */

const JOURNEY_STAGES = Object.freeze([
  'Interpret musical direction',
  'Shape the section journey',
  'Prepare the editable brief',
]);

const TRACK_STAGES = Object.freeze([
  'Retrieve eligible tracks',
  'Rank musical matches',
  'Validate the running order',
  'Optimize transitions',
]);

export function normalizeProgressPercent(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? Math.max(0, Math.min(100, Math.round(numeric))) : null;
}

export function formatProgressElapsed(totalSeconds) {
  const seconds = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

export function progressMarkup(
  { title, detail, stages, activeStep = 0, percent = null, elapsedSeconds = 0 },
  escapeHtml,
) {
  const normalizedPercent = normalizeProgressPercent(percent);
  const safeStep = Math.max(0, Math.min(stages.length - 1, Number(activeStep) || 0));
  const stageMarkup = stages
    .map((stage, index) => {
      const status = index < safeStep ? 'complete' : index === safeStep ? 'active' : 'pending';
      const marker = status === 'complete' ? '✓' : index + 1;
      return `<li class="${status}"><span aria-hidden="true">${marker}</span>${escapeHtml(stage)}</li>`;
    })
    .join('');
  const progressStyle = normalizedPercent == null ? '' : ` style="--set-progress:${normalizedPercent}%"`;
  const progressLabel = normalizedPercent == null ? 'Working' : `${normalizedPercent}% complete`;
  return `<header><span class="set-progress-spinner" aria-hidden="true"></span><div><strong>${escapeHtml(title)}</strong><small>${escapeHtml(detail)}</small></div><time>${formatProgressElapsed(elapsedSeconds)}</time></header><div class="set-progress-bar${normalizedPercent == null ? ' indeterminate' : ''}" role="progressbar" aria-label="${progressLabel}"${normalizedPercent == null ? '' : ` aria-valuenow="${normalizedPercent}" aria-valuemin="0" aria-valuemax="100"`}><span${progressStyle}></span></div><ol>${stageMarkup}</ol>`;
}

export function createSetBuilderProgressView({ $, escapeHtml, clock = () => Date.now(), timers = globalThis }) {
  const operations = new Map();

  function render(kind) {
    const operation = operations.get(kind);
    if (!operation) return;
    const root = $(operation.selector);
    if (!root) return;
    root.hidden = false;
    root.innerHTML = progressMarkup(
      {
        ...operation,
        elapsedSeconds: (clock() - operation.startedAt) / 1000,
      },
      escapeHtml,
    );
  }

  function start(kind, specification) {
    stop(kind);
    const operation = { ...specification, startedAt: clock(), timer: null };
    operations.set(kind, operation);
    render(kind);
    operation.timer = timers.setInterval?.(() => render(kind), 1000) ?? null;
  }

  function update(kind, patch) {
    const operation = operations.get(kind);
    if (!operation) return;
    Object.assign(operation, patch);
    render(kind);
  }

  function stop(kind) {
    const operation = operations.get(kind);
    if (operation?.timer != null) timers.clearInterval?.(operation.timer);
    operations.delete(kind);
    const selector = operation?.selector || (kind === 'journey' ? '#set-intention-progress' : '#set-planning-progress');
    const root = $(selector);
    if (root) {
      root.hidden = true;
      root.innerHTML = '';
    }
  }

  return Object.freeze({
    startJourney() {
      start('journey', {
        selector: '#set-intention-progress',
        title: 'Understanding your set brief',
        detail: 'The local model is translating your words into genres, energy, and a playable journey.',
        stages: JOURNEY_STAGES,
        activeStep: 0,
        percent: null,
      });
    },
    finishJourney() {
      stop('journey');
    },
    startTrackPlanning(mode) {
      start('tracks', {
        selector: '#set-planning-progress',
        title: mode === 'ai-planned' ? 'Building a validated AI set' : 'Building a deterministic set',
        detail:
          mode === 'ai-planned'
            ? 'AI can choose only from real, eligible catalog tracks; every result is checked before it is shown.'
            : 'Compatibility rules are ranking eligible tracks without an AI planning call.',
        stages: TRACK_STAGES,
        activeStep: 0,
        percent: mode === 'ai-planned' ? 0 : null,
      });
    },
    updateTrackPlanning({ title, detail, activeStep, percent } = {}) {
      const patch = {};
      if (title) patch.title = title;
      if (detail) patch.detail = detail;
      if (activeStep != null) patch.activeStep = activeStep;
      if (percent !== undefined) patch.percent = percent;
      update('tracks', patch);
    },
    showEligibilityScan() {
      update('tracks', {
        title: 'Finding eligible tracks',
        detail: 'Applying availability, BPM, vocal, timing, required-track, and exclusion rules.',
        activeStep: 0,
      });
    },
    showCandidatePool() {
      update('tracks', {
        title: 'Preparing the candidate pool',
        detail: 'Only real catalog IDs that pass hard filters can be sent to the planner.',
        activeStep: 0,
        percent: 5,
      });
    },
    updateRemotePlanning(stage, percent) {
      const normalized = normalizeProgressPercent(percent);
      const activeStep = normalized == null ? 1 : normalized >= 90 ? 2 : normalized >= 35 ? 1 : 0;
      update('tracks', {
        title: stage || 'Planning the running order',
        detail: 'The background planner is selecting and validating catalog-backed tracks.',
        activeStep,
        percent: normalized,
      });
    },
    startTransitionOptimization() {
      update('tracks', {
        title: 'Finishing the running order',
        detail: 'The track list is valid. Set Builder is now choosing safer transition settings.',
        activeStep: 3,
        percent: 96,
      });
    },
    finishTrackPlanning() {
      stop('tracks');
    },
  });
}
