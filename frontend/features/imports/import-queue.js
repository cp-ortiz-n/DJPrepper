import {apiErrorMessage} from '../../core/api-client.js';

const STORAGE_KEY = 'audioextender.authorized-import-queue.v1';
const TERMINAL = new Set(['complete', 'failed', 'canceled']);

export function artworkStatusText(item) {
  if (item.status !== 'complete' || typeof item.artwork_synced !== 'boolean') return '';
  if (!item.artwork_synced) return ' · Artwork unavailable';
  return ` · Artwork synced${item.artwork_source ? ` from ${item.artwork_source}` : ''}`;
}

export class AuthorizedImportQueue {
  constructor({select, escapeHtml, waitForImport, onComplete}) {
    this.$ = select;
    this.escapeHtml = escapeHtml;
    this.waitForImport = waitForImport;
    this.onComplete = onComplete;
    this.state = null;
    this.completion = null;
    this.resolveCompletion = null;
    this.restore();
    window.addEventListener('online', () => this.resumeAfterReconnect());
  }

  restore() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
      if (!saved?.items?.length) return;
      saved.active = 0;
      saved.finished = false;
      saved.items.forEach(item => {
        if (item.status === 'processing') {
          item.status = 'waiting';
          item.stage = item.importId ? 'Reconnecting to import' : 'Waiting to retry';
        }
      });
      this.state = saved;
      this.prepareCompletion();
      this.render();
      if (!saved.paused) this.schedule();
    } catch (_) {
      localStorage.removeItem(STORAGE_KEY);
    }
  }

  prepareCompletion() {
    this.completion = new Promise(resolve => { this.resolveCompletion = resolve; });
  }

  persist() {
    if (!this.state) return;
    const {items, paused, basePayload, metadata} = this.state;
    localStorage.setItem(STORAGE_KEY, JSON.stringify({items, paused, basePayload, metadata}));
  }

  start(urls, basePayload, metadata) {
    this.state = {
      items: urls.map(url => ({url, status:'waiting', stage:'Waiting', progress:0, error:'', importId:null})),
      active: 0,
      paused: false,
      finished: false,
      basePayload,
      metadata,
    };
    this.prepareCompletion();
    this.persist();
    this.render();
    this.schedule();
    return this.completion;
  }

  async run(item) {
    const queue = this.state;
    if (!queue) return;
    queue.active += 1;
    item.status = 'processing';
    item.stage = item.importId ? 'Reconnecting to import' : 'Preparing';
    item.progress = Math.max(1, Number(item.progress || 0));
    this.persist(); this.render();
    try {
      if (!item.importId) {
        const response = await fetch('/api/imports/authorized', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({...queue.basePayload, url:item.url, ...queue.metadata}),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(apiErrorMessage(payload, 'Could not start import.'));
        item.importId = payload.import_id;
        this.persist();
      }
      const result = await this.waitForImport(item.importId, item.url, (value, stage) => {
        item.progress = value; item.stage = stage; this.persist(); this.render();
      });
      Object.assign(item, result, {
        status:result.status, progress:100,
        stage:result.status === 'complete' ? 'Complete' : result.status === 'canceled' ? 'Canceled' : 'Failed',
        error:result.error || '',
      });
    } catch (error) {
      const offline = !navigator.onLine || /offline|disconnect|network|fetch/i.test(error.message);
      Object.assign(item, {
        status:offline ? 'waiting' : 'failed',
        stage:offline ? 'Waiting for library or network' : 'Failed',
        error:error.message,
      });
      if (/not found/i.test(error.message)) item.importId = null;
      if (offline) queue.paused = true;
    } finally {
      queue.active -= 1;
      this.persist(); this.render(); this.schedule();
    }
  }

  schedule() {
    const queue = this.state;
    if (!queue || queue.finished) return;
    while (!queue.paused && queue.active < 2) {
      const next = queue.items.find(item => item.status === 'waiting');
      if (!next) break;
      void this.run(next);
    }
    const pending = queue.items.some(item => ['waiting', 'processing'].includes(item.status));
    if (!pending && queue.active === 0) {
      queue.finished = true;
      this.persist();
      this.resolveCompletion?.();
      void this.onComplete(queue);
    }
  }

  resumeAfterReconnect() {
    if (!this.state) return;
    const reconnectable = this.state.items.some(item => item.status === 'waiting');
    if (reconnectable) {
      this.state.paused = false;
      this.state.finished = false;
      this.persist(); this.render(); this.schedule();
    }
  }

  togglePause() {
    if (!this.state) return;
    this.state.paused = !this.state.paused;
    this.persist(); this.render(); this.schedule();
  }

  retryFailed() {
    if (!this.state) return;
    this.state.finished = false;
    this.state.items.filter(item => ['failed', 'canceled'].includes(item.status)).forEach(item => {
      Object.assign(item, {status:'waiting', stage:'Waiting to retry', progress:0, error:'', importId:null});
    });
    this.prepareCompletion();
    this.persist(); this.render(); this.schedule();
  }

  async act(index, action) {
    const queue = this.state;
    if (!queue) return;
    const item = queue.items[index];
    if (action === 'up' && index > 0) [queue.items[index - 1], queue.items[index]] = [item, queue.items[index - 1]];
    if (action === 'down' && index < queue.items.length - 1) [queue.items[index + 1], queue.items[index]] = [item, queue.items[index + 1]];
    if (action === 'cancel') {
      if (item.importId) await fetch(`/api/imports/${item.importId}/cancel`, {method:'POST'});
      else Object.assign(item, {status:'canceled', stage:'Canceled before download', progress:100});
    }
    if (action === 'retry') Object.assign(item, {status:'waiting', stage:'Waiting to retry', progress:0, error:'', importId:null});
    this.persist(); this.render(); this.schedule();
  }

  render() {
    const queue = this.state;
    if (!queue) return;
    const panel = this.$('#authorized-import-queue');
    const list = this.$('#authorized-import-queue-list');
    const progress = this.$('#authorized-import-progress');
    if (!panel || !list || !progress) return;
    panel.hidden = false; progress.hidden = false;
    const terminal = queue.items.filter(item => TERMINAL.has(item.status));
    const percent = queue.items.reduce((sum, item) => sum + Number(item.progress || 0), 0) / Math.max(1, queue.items.length);
    progress.querySelector('span').style.width = `${Math.max(2, percent)}%`;
    progress.querySelector('small').textContent = `${terminal.length} of ${queue.items.length} finished · ${queue.paused ? 'Queue paused' : queue.active + ' active'} · ${Math.round(percent)}%`;
    this.$('#authorized-import-queue-summary').textContent = `${queue.items.filter(item => item.status === 'waiting').length} waiting · ${queue.active} active`;
    this.$('#authorized-import-pause').textContent = queue.paused ? 'Resume queue' : 'Pause queue';
    this.$('#authorized-import-retry').disabled = !queue.items.some(item => ['failed', 'canceled'].includes(item.status));
    list.innerHTML = queue.items.map((item, index) => `<article class="authorized-import-queue-item" data-index="${index}" data-status="${item.status}"><div><strong>${this.escapeHtml(item.url)}</strong><small>${this.escapeHtml(item.stage || item.status)}${this.escapeHtml(artworkStatusText(item))}${item.error ? ` · ${this.escapeHtml(item.error)}` : ''}</small></div><div class="authorized-import-queue-actions">${item.status === 'waiting' ? `<button type="button" data-action="up" aria-label="Move up" ${index === 0 ? 'disabled' : ''}>↑</button><button type="button" data-action="down" aria-label="Move down" ${index === queue.items.length - 1 ? 'disabled' : ''}>↓</button>` : ''}${['waiting', 'processing'].includes(item.status) ? '<button type="button" data-action="cancel">Cancel</button>' : ''}${['failed', 'canceled'].includes(item.status) ? '<button type="button" data-action="retry">Retry</button>' : ''}</div></article>`).join('');
    list.querySelectorAll('button').forEach(button => {
      button.onclick = () => this.act(Number(button.closest('article').dataset.index), button.dataset.action);
    });
  }
}
