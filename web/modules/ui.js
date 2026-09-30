export const $ = selector => document.querySelector(selector);
export const $$ = selector => [...document.querySelectorAll(selector)];

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

export function pct(value) { return value == null ? '—' : `${Math.round(value)}%`; }
export function fraction(value) { return value == null ? '—' : `${Math.round(100 * value)}%`; }
export function reportDate(value) { return value ? new Date(value).toLocaleString([], {dateStyle:'medium', timeStyle:'short'}) : 'Not processed yet'; }
export function clock(seconds) {
  if (seconds == null) return '—';
  const total = Math.max(0, Math.round(seconds));
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
}
