export const $ = selector => document.querySelector(selector);
export const $$ = selector => [...document.querySelectorAll(selector)];

export function captureTextFilter(input, state, key = 'search') {
  state[key] = String(input.value || '').trim();
  return state[key];
}

export function syncControlUnlessEditing(control, value, activeElement = document.activeElement) {
  if (activeElement === control) return false;
  control.value = value ?? '';
  return true;
}

export function notify(message, tone = 'info', options = {}) {
  const region = $('#app-toast-region');
  if (!region || !message) return;
  const toast = document.createElement('article');
  toast.className = 'app-toast';
  toast.dataset.tone = tone;
  toast.setAttribute('role', tone === 'danger' ? 'alert' : 'status');
  const text = document.createElement('span');
  text.textContent = String(message);
  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'toast-close';
  close.setAttribute('aria-label', 'Dismiss notification');
  close.textContent = '×';
  close.addEventListener('click', () => toast.remove());
  toast.append(text, close);
  region.append(toast);
  requestAnimationFrame(() => toast.classList.add('visible'));
  const timeout = Number(options.timeout ?? (tone === 'danger' ? 7000 : 4200));
  if (timeout > 0) setTimeout(() => {
    toast.classList.remove('visible');
    setTimeout(() => toast.remove(), 180);
  }, timeout);
}

export function confirmAction(message, options = {}) {
  const dialog = $('#app-confirm-dialog');
  if (!dialog?.showModal) return Promise.resolve(window.confirm(message));
  $('#app-confirm-title').textContent = options.title || 'Confirm action';
  $('#app-confirm-message').textContent = message;
  const accept = $('#app-confirm-accept');
  accept.textContent = options.acceptLabel || 'Continue';
  accept.dataset.tone = options.danger ? 'danger' : 'success';
  return new Promise(resolve => {
    dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), {once:true});
    dialog.showModal();
  });
}

export function option(value, label = value) {
  const node = document.createElement('option');
  node.value = value;
  node.textContent = label;
  return node;
}

export function escapeHtml(value) {
  const node = document.createElement('span');
  node.textContent = String(value ?? '');
  return node.innerHTML;
}

export function apiErrorMessage(payload, fallback = 'The request could not be completed.') {
  const detail = payload?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(item => {
    const field = Array.isArray(item?.loc) ? item.loc.filter(value => value !== 'body').join(' → ') : '';
    return `${field ? `${field}: ` : ''}${item?.msg || 'Invalid value'}`;
  }).join(' · ');
  if (detail && typeof detail === 'object') return detail.message || JSON.stringify(detail);
  return fallback;
}

export function operationReceiptText(receipt) {
  if (!receipt) return '';
  const requested = receipt.requested?.summary || 'Operation requested';
  const changed = receipt.changed?.summary || 'No reported changes';
  const targets = receipt.written_to?.length ? receipt.written_to.join(', ') : 'No files written';
  const failed = receipt.failures?.length || 0;
  const restart = receipt.survives_restart ? 'Yes' : 'No';
  return `Requested: ${requested} · Changed: ${changed} · Written to: ${targets} · Failed: ${failed} · Survives restart: ${restart} — ${receipt.durability || 'No durability details supplied.'}`;
}

export async function startKeyAnalysis(trackIds, button, onComplete = async () => {}) {
  if (!trackIds.length) return;
  const original = button.textContent;
  button.disabled = true;
  button.textContent = 'Starting key analysis…';
  try {
    const response = await fetch('/api/downloaded-library/key-analysis', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({track_ids:trackIds}),
    });
    let batch = await response.json();
    if (!response.ok) throw new Error(batch.detail || 'Could not start key analysis.');
    while (batch.status === 'processing') {
      button.textContent = `Analyzing keys ${batch.processed}/${batch.total}`;
      await new Promise(resolve => setTimeout(resolve, 700));
      const status = await fetch(`/api/downloaded-library/key-analysis/${batch.batch_id}`, {cache:'no-store'});
      batch = await status.json();
      if (!status.ok) throw new Error(batch.detail || 'Key-analysis status was lost.');
    }
    button.textContent = batch.failed
      ? `${batch.completed} complete · ${batch.failed} failed`
      : `${batch.completed} keys analyzed`;
    await onComplete(batch);
  } catch (error) {
    button.textContent = error.message || 'Key analysis failed';
  } finally {
    setTimeout(() => { button.textContent=original;button.disabled=false; }, 1600);
  }
}

export const pct = value => value == null ? '—' : `${Math.round(value)}%`;
export const fraction = value => value == null ? '—' : `${Math.round(100 * value)}%`;
export const reportDate = value => value
  ? new Date(value).toLocaleString([], {dateStyle:'medium', timeStyle:'short'})
  : 'Not processed yet';
export function clock(seconds) {
  if (seconds == null) return '—';
  const total = Math.max(0, Math.round(seconds));
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
}

export function renderTrackPagination(container, page, totalPages, totalItems, onPage) {
  container.hidden = totalPages <= 1;
  if (container.hidden) {
    container.replaceChildren();
    return;
  }
  const candidates = [...new Set([1,page-2,page-1,page,page+1,page+2,totalPages]
    .filter(value => value >= 1 && value <= totalPages))].sort((a,b) => a-b);
  let previous = 0;
  const pages = candidates.map(value => {
    const gap = previous && value - previous > 1 ? '<span class="page-gap">…</span>' : '';
    previous = value;
    return `${gap}<button type="button" class="page-number${value === page ? ' active' : ''}" data-page="${value}"${value === page ? ' aria-current="page"' : ''}>${value}</button>`;
  }).join('');
  container.innerHTML = `<button type="button" class="page-previous"${page <= 1 ? ' disabled' : ''}>← Previous</button><span class="page-numbers">${pages}</span><span class="page-summary">Page ${page} of ${totalPages} · ${totalItems} tracks</span><button type="button" class="page-next"${page >= totalPages ? ' disabled' : ''}>Next →</button>`;
  container.querySelector('.page-previous').onclick = () => onPage(page - 1);
  container.querySelector('.page-next').onclick = () => onPage(page + 1);
  container.querySelectorAll('.page-number').forEach(button => {
    button.onclick = () => onPage(Number(button.dataset.page));
  });
}
