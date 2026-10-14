const ACTIVE_STATUSES = new Set(['queued', 'processing']);

export function annotateProcessingJobs(jobs) {
  const generations = new Map();
  [...jobs].reverse().forEach((job) => {
    const key = String(job.source_name || '').toLowerCase();
    const generation = (generations.get(key) || 0) + 1;
    generations.set(key, generation);
    job._generation = generation;
  });

  const durations = jobs
    .filter((job) => job.status === 'complete')
    .map((job) => (new Date(job.updated_at) - new Date(job.created_at)) / 1000)
    .filter((value) => Number.isFinite(value) && value > 0);
  const averageSeconds = durations.length
    ? durations.reduce((total, value) => total + value, 0) / durations.length
    : 120;
  let queuePosition = 0;
  [...jobs].reverse().forEach((job) => {
    if (job.status === 'queued') {
      queuePosition += 1;
      job._eta = `~${Math.round((queuePosition * averageSeconds) / 60)} min`;
    }
  });
  return jobs;
}

export function categorizeProcessingJobs(jobs) {
  const newestByTrack = new Map();
  jobs.forEach((job) => {
    const key = String(job.source_name || '').toLowerCase();
    if (!newestByTrack.has(key) || job.id > newestByTrack.get(key)) newestByTrack.set(key, job.id);
  });
  return {
    active: jobs.filter((job) => ACTIVE_STATUSES.has(job.status)),
    attention: jobs.filter(
      (job) => ['pending', 'rejected'].includes(job.review_status) || ['failed', 'canceled'].includes(job.status),
    ),
    history: jobs.filter((job) => {
      const key = String(job.source_name || '').toLowerCase();
      return (
        job.status === 'complete' &&
        !['pending', 'rejected'].includes(job.review_status) &&
        newestByTrack.get(key) === job.id
      );
    }),
  };
}

export function sortProcessingJobs(jobs) {
  const priority = { processing: 0, queued: 1, review: 2, failed: 3, canceled: 4 };
  return [...jobs].sort((left, right) => {
    const leftState = left.review_status === 'pending' ? 'review' : left.status;
    const rightState = right.review_status === 'pending' ? 'review' : right.status;
    const stateOrder = (priority[leftState] ?? 9) - (priority[rightState] ?? 9);
    if (stateOrder) return stateOrder;
    if (left.status === 'queued') return (left.queue_index ?? 9999) - (right.queue_index ?? 9999);
    return right.id - left.id;
  });
}

export function createProcessingWorkspaceApi(api) {
  return {
    list: () => api.get('/api/jobs', { cache: 'no-store' }),
    action: (id, action, body) => api.post(`/api/jobs/${id}/${action}`, body),
    remove: (id) => api.request(`/api/jobs/${id}`, { method: 'DELETE' }),
    clear: () => api.post('/api/jobs/clear'),
    reorder: (jobIds) => api.post('/api/jobs/reorder', { job_ids: jobIds }),
    candidates: (id) => api.get(`/api/jobs/${id}/candidates`),
    feedback: (id) => api.get(`/api/jobs/${id}/feedback`),
    rejectReview: (id) => api.post(`/api/jobs/${id}/review/reject`),
    saveFeedback: (id, body) => api.post(`/api/jobs/${id}/feedback`, body),
    reprocess: (id, body) => api.post(`/api/jobs/${id}/reprocess`, body),
  };
}

export function createProcessingWorkspaceController({
  workspaceApi,
  render,
  onAnalysisRefresh = async () => {},
  clock = globalThis,
  documentRef = globalThis.document,
  pollVisibleMs = 2000,
  pollHiddenMs = 15000,
}) {
  let filter = 'active';
  let loadPromise = null;
  let pollTimer = null;
  let pollInFlight = false;
  let analysisRefreshAt = 0;

  const schedule = (active) => {
    clock.clearTimeout(pollTimer);
    pollTimer = null;
    if (!active) return;
    pollTimer = clock.setTimeout(
      async () => {
        if (pollInFlight) return schedule(true);
        pollInFlight = true;
        try {
          const jobs = await load();
          const stillActive = jobs.some((job) => ACTIVE_STATUSES.has(job.status));
          if (!documentRef?.hidden && Date.now() >= analysisRefreshAt) {
            analysisRefreshAt = Date.now() + 15000;
            await onAnalysisRefresh(jobs);
          }
          if (!stillActive) clock.clearTimeout(pollTimer);
        } finally {
          pollInFlight = false;
        }
      },
      documentRef?.hidden ? pollHiddenMs : pollVisibleMs,
    );
  };

  const snapshot = async () => {
    const jobs = annotateProcessingJobs(await workspaceApi.list());
    const categories = categorizeProcessingJobs(jobs);
    const sorted = sortProcessingJobs(categories[filter]);
    const visible = filter === 'history' ? sorted.slice(0, 20) : sorted;
    await render({ jobs, categories, filter, sorted, visible });
    schedule(jobs.some((job) => ACTIVE_STATUSES.has(job.status)));
    return jobs;
  };

  const load = () => {
    if (loadPromise) return loadPromise;
    loadPromise = snapshot().finally(() => {
      loadPromise = null;
    });
    return loadPromise;
  };

  return {
    load,
    getFilter: () => filter,
    setFilter(value) {
      filter = value;
      return load();
    },
    refreshWhenVisible() {
      if (pollTimer) return load();
      return Promise.resolve([]);
    },
    stop() {
      clock.clearTimeout(pollTimer);
      pollTimer = null;
    },
  };
}
