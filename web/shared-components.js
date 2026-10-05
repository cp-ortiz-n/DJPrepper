export const $ = selector => document.querySelector(selector);
export const $$ = selector => [...document.querySelectorAll(selector)];

export const DESCRIPTOR_CATEGORIES = [
  ['cultural','Cultural / regional influence'], ['rhythm','Rhythmic influence'],
  ['sound','Sound character'], ['vocal','Vocal identity'], ['role','Energy / DJ role'],
  ['context','Context or personal crate'], ['familiarity','Familiarity'],
];

export function descriptorChipsMarkup(descriptors = [], {detailed = false} = {}) {
  if(detailed){
    const groups=DESCRIPTOR_CATEGORIES.map(([category,label])=>({label,items:descriptors.filter(item=>item.category===category)})).filter(group=>group.items.length);
    return `<section class="track-descriptor-summary"><header><div><strong>Current identity</strong><small>${descriptors.length?`${descriptors.length} saved descriptor${descriptors.length===1?'':'s'}`:'Nothing has been defined yet'}</small></div>${descriptors.length?'<span>Saved to catalog</span>':''}</header>${groups.length?`<div class="track-descriptor-groups">${groups.map(group=>`<div><small>${escapeHtml(group.label)}</small><div>${group.items.map(item=>`<span>${escapeHtml(item.value)}<i>${escapeHtml(item.provenance||'manual')}${item.confidence==null?'':` · ${Math.round(Number(item.confidence)*100)}%`}</i></span>`).join('')}</div></div>`).join('')}</div>`:'<p class="track-descriptor-empty">No musical identity is saved for this track. Add cultural, rhythmic, vocal, contextual, or DJ-role descriptors to improve Set Builder matching.</p>'}</section>`;
  }
  return descriptors.length
    ? `<div class="track-descriptor-chips">${descriptors.map(item=>`<span title="${escapeHtml(`${item.category} · ${item.provenance} · ${Math.round(Number(item.confidence||0)*100)}% confidence`)}">${escapeHtml(item.value)}</span>`).join('')}</div>`
    : '<div class="track-descriptor-chips is-empty"><span>No musical identity tags yet</span></div>';
}

export function descriptorEditorMarkup(descriptors = [], {bulk = false} = {}) {
  const grouped=Object.fromEntries(DESCRIPTOR_CATEGORIES.map(([category])=>[category,descriptors.filter(item=>item.category===category).map(item=>item.value).join(', ')]));
  return `<section class="track-descriptor-editor" hidden><header><div><strong>${bulk?'Edit identity for selected tracks':'Edit musical identity'}</strong><small>Use short, specific tags. Separate multiple values with commas.</small></div><button type="button" class="close-descriptor-editor" aria-label="Close identity editor">×</button></header>${bulk?'<label class="descriptor-operation">Operation<select class="descriptor-mode"><option value="add">Add these tags</option><option value="remove">Remove these tags</option><option value="replace">Replace all identity tags</option></select></label>':''}<div class="track-descriptor-fields">${DESCRIPTOR_CATEGORIES.map(([category,label])=>`<label><span>${escapeHtml(label)}</span><input data-descriptor-category="${category}" value="${escapeHtml(grouped[category]||'')}" placeholder="Add tags…"></label>`).join('')}</div><div class="descriptor-editor-actions"><button type="button" class="save-descriptors">${bulk?'Apply to selection':'Save changes'}</button><button type="button" class="button secondary cancel-descriptors">Cancel</button></div><p class="descriptor-editor-status" role="status"></p></section>`;
}

export async function saveDescriptorEditor(editor, trackIds) {
  const ids=[...new Set(trackIds.map(Number).filter(Boolean))];
  const descriptors=[...editor.querySelectorAll('[data-descriptor-category]')].flatMap(input=>String(input.value||'').split(',').map(value=>value.trim()).filter(Boolean).map(value=>({category:input.dataset.descriptorCategory,value,provenance:'manual',confidence:1})));
  const mode=editor.querySelector('.descriptor-mode')?.value||'replace';
  const url=ids.length===1?`/api/downloaded-library/tracks/${ids[0]}/descriptors`:'/api/downloaded-library/descriptors/bulk';
  const response=await fetch(url,{method:ids.length===1?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...(ids.length===1?{}:{track_ids:ids}),descriptors,mode})});
  const payload=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(payload.detail?.message||payload.detail||'Musical identity could not be saved.');
  return payload;
}

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
