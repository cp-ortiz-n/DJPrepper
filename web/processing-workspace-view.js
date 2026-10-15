import { useFrontendServices } from './frontend-services.js';

export function processingJobSignature(job) {
  return JSON.stringify([
    job.status,
    job.progress,
    job.stage,
    job.error,
    job.pause_requested,
    job.queue_index,
    job.review_status,
    job.updated_at,
  ]);
}

export function processingJobViewModel(job, now = Date.now()) {
  let config = {};
  try {
    config = JSON.parse(job.config_json || '{}');
  } catch (_) {
    config = {};
  }
  const intro = config.intro_bars_auto ? 'auto intro' : `${job.intro_bars} bar intro`;
  const outro = config.outro_bars_auto ? 'auto outro' : `${job.outro_bars} bar outro`;
  const suffix = `${job.use_stems ? ' · stems' : ''}${job._eta ? ` · ETA ${job._eta}` : ''}`;
  const status =
    job.review_status === 'pending'
      ? 'awaiting review'
      : job.review_status === 'rejected'
        ? 'review dismissed'
        : job.status;
  let stage =
    job.review_status === 'pending'
      ? 'Candidate review requested · choose options in Review'
      : job.review_status === 'rejected'
        ? 'Review dismissed · processed audio remains available in Library'
        : job.stage;
  if (job.status === 'processing' && now - new Date(job.created_at).getTime() > 300000) {
    stage = `${job.stage} · long analysis, still working`;
  }
  return {
    config,
    meta: config.analysis_only
      ? `analysis only${suffix}`
      : `${job.preset} · ${intro} · ${outro}${job.use_stems ? ' · stems' : ''} · generation ${job._generation || 1}${job._eta ? ` · ETA ${job._eta}` : ''}`,
    status,
    stage,
    reviewLabel:
      job.review_status === 'pending'
        ? 'Open review'
        : job.review_status === 'rejected'
          ? 'Reopen review'
          : 'Create review',
    reprocessLabel: job.review_status === 'rejected' ? 'Process automatically' : 'Reprocess',
  };
}

export function createProcessingWorkspaceView({
  services,
  template,
  jobsRoot,
  action,
  remove,
  move,
  hydrate,
  showView,
  loadLibrary,
}) {
  const { $, $$ } = useFrontendServices(services);

  const jobElement = (job) => {
    const node = template.content.firstElementChild.cloneNode(true);
    const view = processingJobViewModel(job);
    let detailsHydrated = false;
    node.dataset.status = job.status;
    node.dataset.jobId = job.id;
    node.dataset.renderSignature = processingJobSignature(job);
    if (job.review_status === 'pending') node.classList.add('review-awaiting');
    if (job.review_status === 'rejected') node.classList.add('review-dismissed');
    node.querySelector('.track-title strong').textContent = job.source_name;
    node.querySelector('.meta').textContent = view.meta;
    node.querySelector('.status').textContent = view.status;
    node.querySelector('.progress-track span').style.width = `${job.progress}%`;
    node.querySelector('.stage').textContent = view.stage;
    node.querySelector('.percent').textContent = `${Math.round(job.progress)}%`;
    node.querySelector('.job-error').textContent = job.error || '';
    node.querySelector('.cancel-job').addEventListener('click', () => action(job.id, 'cancel'));
    const pauseButton = node.querySelector('.pause-job');
    pauseButton.textContent = job.pause_requested ? 'Resume' : 'Pause';
    pauseButton.addEventListener('click', () => action(job.id, job.pause_requested ? 'resume' : 'pause'));
    const reprocessButton = node.querySelector('.reprocess-job');
    reprocessButton.textContent = view.reprocessLabel;
    reprocessButton.addEventListener('click', () =>
      action(job.id, 'reprocess', job.review_status === 'rejected' ? { review_candidates: false } : null),
    );
    node.querySelector('.remove-job').addEventListener('click', () => remove(job.id));
    node.querySelector('.details-job').addEventListener('click', async (event) => {
      const open = node.classList.toggle('details-open');
      event.currentTarget.textContent = open ? 'Hide details' : 'Show details';
      if (open && job.status === 'complete' && !detailsHydrated) {
        detailsHydrated = true;
        await hydrate(node, job);
      }
    });
    node.querySelector('.library-job').addEventListener('click', async () => {
      showView('library-view');
      await loadLibrary();
    });
    node.querySelector('.review-job').addEventListener('click', () => {
      if (job.review_status === 'pending') showView('review-view');
      else action(job.id, 'reprocess', { review_candidates: true });
    });
    node.querySelector('.review-job').textContent = view.reviewLabel;
    node.querySelector('.move-up').addEventListener('click', () => move(job.id, -1));
    node.querySelector('.move-down').addEventListener('click', () => move(job.id, 1));
    if (job.status === 'complete' && job.review_status !== 'pending') {
      node.querySelector('.downloads').classList.add('visible');
      node.querySelector('.players').classList.add('visible');
      [
        ['.source-player', 'wav', job.wav_path],
        ['.extended-player', 'extended', job.extended_path],
        ['.intro-player', 'intro-preview', job.intro_preview_path],
        ['.outro-player', 'outro-preview', job.outro_preview_path],
      ].forEach(([selector, kind, available]) => {
        const row = node.querySelector(selector);
        if (available) row.querySelector('audio').src = `/api/jobs/${job.id}/audio/${kind}`;
        else row.classList.add('unavailable');
      });
      node.querySelector('.wav-link').href = `/api/jobs/${job.id}/download/wav`;
      node.querySelector('.extended-link').href = `/api/jobs/${job.id}/download/extended`;
      node.querySelector('.cue-link').href = `/api/jobs/${job.id}/download/cue-sheet`;
      node.querySelector('.rekordbox-link').href = `/api/jobs/${job.id}/download/rekordbox`;
      if (!job.cue_sheet_path) node.querySelector('.cue-link').style.display = 'none';
      if (!job.rekordbox_path) node.querySelector('.rekordbox-link').style.display = 'none';
    }
    return node;
  };

  const render = async ({ jobs, categories, filter, sorted, visible }) => {
    Object.entries(categories).forEach(([name, items]) => {
      const count = $(`#queue-${name}-count`);
      if (count) count.textContent = items.length;
    });
    const processingCount = jobs.filter((job) => job.status === 'processing').length;
    const queuedCount = jobs.filter((job) => job.status === 'queued').length;
    $('#queue-count').textContent =
      filter === 'active'
        ? `${processingCount} analyzing · ${queuedCount} queued`
        : filter === 'history' && sorted.length > visible.length
          ? `${visible.length} newest of ${sorted.length}`
          : `${visible.length} track${visible.length === 1 ? '' : 's'}`;
    $('#clear-queue').disabled = !jobs.some((job) => !job.is_active);
    const emptyMessages = {
      active: 'No tracks are currently queued or processing.',
      attention: 'Nothing needs your attention.',
      history: 'No completed processing history yet.',
    };
    if (visible.length) {
      const existing = new Map(
        [...jobsRoot.querySelectorAll('.job-card[data-job-id]')].map((node) => [Number(node.dataset.jobId), node]),
      );
      const nodes = visible.map((job) => {
        const current = existing.get(Number(job.id));
        return current?.dataset.renderSignature === processingJobSignature(job) ? current : jobElement(job);
      });
      jobsRoot.replaceChildren(...nodes);
    } else {
      jobsRoot.replaceChildren(
        Object.assign(document.createElement('div'), {
          className: 'empty',
          textContent: emptyMessages[filter],
        }),
      );
    }
  };

  const bindFilters = (controller) => {
    $$('[data-queue-filter]').forEach((button) =>
      button.addEventListener('click', () => {
        $$('[data-queue-filter]').forEach((item) => item.classList.toggle('active', item === button));
        controller.setFilter(button.dataset.queueFilter);
      }),
    );
  };

  return Object.freeze({ bindFilters, jobElement, render });
}
