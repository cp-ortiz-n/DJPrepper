export class SetPlanningCanceled extends Error {
  constructor(message = 'Set planning was canceled.') {
    super(message);
    this.name = 'SetPlanningCanceled';
  }
}

async function responseJson(response, fallback) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail?.message || payload.detail || fallback;
    throw new Error(typeof detail === 'string' ? detail : fallback);
  }
  return payload;
}

export function createSetPlanningClient({fetchImpl = fetch, pollInterval = 500} = {}) {
  const request = async (path, options, fallback) => responseJson(await fetchImpl(path, options), fallback);

  return {
    start(payload) {
      return request('/api/set-builder/plan-tracks', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      }, 'The set-planning job could not be started.');
    },

    status(jobId) {
      return request(`/api/set-builder/plan-tracks/${encodeURIComponent(jobId)}`, {
        cache: 'no-store',
      }, 'The set-planning status could not be loaded.');
    },

    cancel(jobId) {
      return request(`/api/set-builder/plan-tracks/${encodeURIComponent(jobId)}/cancel`, {
        method: 'POST',
      }, 'The set-planning job could not be canceled.');
    },

    retry(jobId) {
      return request(`/api/set-builder/plan-tracks/${encodeURIComponent(jobId)}/retry`, {
        method: 'POST',
      }, 'The set-planning job could not be retried.');
    },

    async wait(jobId, {signal, onProgress = () => {}} = {}) {
      while (true) {
        if (signal?.aborted) throw new SetPlanningCanceled();
        const state = await this.status(jobId);
        if (signal?.aborted) throw new SetPlanningCanceled();
        onProgress(state);
        if (state.status === 'complete') return state.result;
        if (state.status === 'failed') throw new Error(state.error || 'Set planning failed.');
        if (state.status === 'canceled') throw new SetPlanningCanceled();
        await new Promise((resolve, reject) => {
          const timer = setTimeout(resolve, pollInterval);
          signal?.addEventListener('abort', () => {
            clearTimeout(timer);
            reject(new SetPlanningCanceled());
          }, {once: true});
        });
      }
    },
  };
}
