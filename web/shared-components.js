import {apiErrorMessage} from './api-client.js';
import {createFrontendServices} from './frontend-services.js';

export const $ = selector => document.querySelector(selector);
export const $$ = selector => [...document.querySelectorAll(selector)];

export function composeFrontendServices(api) {
  return createFrontendServices({
    api,
    dom: {$, $$},
    feedback: {notify, confirmAction, operationReceiptText},
    descriptors: {
      chipsMarkup: descriptorChipsMarkup,
      editorMarkup: descriptorEditorMarkup,
      openEditorDialog: openDescriptorEditorDialog,
      saveEditor: saveDescriptorEditor,
      inferEditor: inferDescriptorEditor,
    },
  });
}

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

export function descriptorEditorMarkup(descriptors = [], {bulk = false, protectedFromInference = null} = {}) {
  const grouped=Object.fromEntries(DESCRIPTOR_CATEGORIES.map(([category])=>[category,descriptors.filter(item=>item.category===category).map(item=>item.value).join(', ')]));
  return `<section class="track-descriptor-editor" hidden><header><div><strong>${bulk?'Edit identity for selected tracks':'Edit musical identity'}</strong><small>Use short, specific tags. Separate multiple values with commas.</small></div><button type="button" class="close-descriptor-editor" aria-label="Close identity editor">×</button></header>${bulk?'<fieldset class="descriptor-operation"><legend>How should these tags be applied?</legend><label><input class="descriptor-mode" type="radio" name="descriptor-mode" value="add" checked><span><b>Add</b><small>Keep existing identity</small></span></label><label><input class="descriptor-mode" type="radio" name="descriptor-mode" value="remove"><span><b>Remove</b><small>Only matching tags</small></span></label><label><input class="descriptor-mode" type="radio" name="descriptor-mode" value="replace"><span><b>Replace</b><small>Clear existing identity</small></span></label></fieldset>':''}${bulk?'':`<label class="descriptor-inference-protection"><input type="checkbox"${protectedFromInference===false?'':' checked'}><span><b>Manually tagged—do not infer</b><small>Bulk and automatic re-inference will skip this track.</small></span></label>`}<div class="track-descriptor-fields">${DESCRIPTOR_CATEGORIES.map(([category,label])=>`<label><span>${escapeHtml(label)}</span><input data-descriptor-category="${category}" value="${escapeHtml(grouped[category]||'')}" placeholder="Add tags…"></label>`).join('')}</div><div class="descriptor-editor-actions"><button type="button" class="button secondary infer-descriptors">${bulk?'Infer for selection':'Suggest tags'}</button><button type="button" class="save-descriptors">${bulk?'Apply to selection':'Save changes'}</button><button type="button" class="button secondary cancel-descriptors">Cancel</button></div><p class="descriptor-editor-status" role="status"></p></section>`;
}

export function openDescriptorEditorDialog({descriptors = [], bulk = false, protectedFromInference = null, title = 'Edit musical identity', subtitle = ''} = {}) {
  document.querySelector('.descriptor-dialog-backdrop')?.remove();
  const backdrop=document.createElement('div');
  backdrop.className='descriptor-dialog-backdrop';
  backdrop.innerHTML=`<section class="descriptor-dialog" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}"><header class="descriptor-dialog-heading"><div><strong>${escapeHtml(title)}</strong>${subtitle?`<small>${escapeHtml(subtitle)}</small>`:''}</div><button type="button" class="descriptor-dialog-close" aria-label="Close identity editor">×</button></header>${!bulk?descriptorChipsMarkup(descriptors,{detailed:true}):''}${descriptorEditorMarkup(descriptors,{bulk,protectedFromInference})}</section>`;
  document.body.append(backdrop);
  document.body.classList.add('descriptor-dialog-open');
  const editor=backdrop.querySelector('.track-descriptor-editor');
  editor.hidden=false;
  const close=()=>{backdrop.remove();if(!document.querySelector('.descriptor-dialog-backdrop'))document.body.classList.remove('descriptor-dialog-open');};
  backdrop.querySelector('.descriptor-dialog-close').onclick=close;
  backdrop.addEventListener('click',event=>{if(event.target===backdrop)close();});
  backdrop.addEventListener('keydown',event=>{if(event.key==='Escape')close();});
  requestAnimationFrame(()=>editor.querySelector('input')?.focus());
  return {backdrop,editor,close};
}

export async function inferDescriptorEditor(editor, trackIds) {
  const ids=[...new Set(trackIds.map(Number).filter(Boolean))],status=editor.querySelector('.descriptor-editor-status');
  const bulkMode=Boolean(editor.querySelector('.descriptor-mode'));
  if(ids.length===1&&!bulkMode){
    const response=await fetch(`/api/downloaded-library/tracks/${ids[0]}/descriptor-suggestions`,{cache:'no-store'}),payload=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(response.status===404?'Identity inference is not loaded in the running server. Restart AudioExtender, then try again.':apiErrorMessage(payload,'Identity suggestions could not be created.'));
    for(const suggestion of payload.suggestions||[]){const input=editor.querySelector(`[data-descriptor-category="${suggestion.category}"]`);if(!input)continue;const values=String(input.value||'').split(',').map(value=>value.trim()).filter(Boolean);if(!values.some(value=>value.toLowerCase()===suggestion.value.toLowerCase()))values.push(suggestion.value);input.value=values.join(', ');}
    const crates=(payload.playlists_considered||[]).join(', ');status.textContent=`Suggested ${payload.suggestions?.length||0} tags from catalog, analysis${crates?`, and playlists: ${crates}`:''}. Review them, then save.`;
    return {...payload,applied:false};
  }
  const response=await fetch('/api/downloaded-library/descriptors/infer',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_ids:ids,apply:true})}),payload=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(response.status===404?'Identity inference is not loaded in the running server. Restart AudioExtender, then try again.':apiErrorMessage(payload,'Identity inference could not be applied.'));
  status.textContent=`Added inferred tags to ${payload.applied} of ${payload.processed} tracks.${payload.skipped_protected?.length?` Skipped ${payload.skipped_protected.length} manually protected track${payload.skipped_protected.length===1?'':'s'}.`:''} Manual tags were preserved.`;
  return payload;
}

export async function saveDescriptorEditor(editor, trackIds) {
  const ids=[...new Set(trackIds.map(Number).filter(Boolean))];
  const descriptors=[...editor.querySelectorAll('[data-descriptor-category]')].flatMap(input=>String(input.value||'').split(',').map(value=>value.trim()).filter(Boolean).map(value=>({category:input.dataset.descriptorCategory,value,provenance:'manual',confidence:1})));
  const mode=editor.querySelector('.descriptor-mode:checked')?.value||'replace';
  const url=ids.length===1?`/api/downloaded-library/tracks/${ids[0]}/descriptors`:'/api/downloaded-library/descriptors/bulk';
  const protection=editor.querySelector('.descriptor-inference-protection input');
  const response=await fetch(url,{method:ids.length===1?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...(ids.length===1?{protect_from_inference:Boolean(protection?.checked)}:{track_ids:ids}),descriptors,mode})});
  const payload=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(apiErrorMessage(payload,'Musical identity could not be saved.'));
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

export {apiErrorMessage};

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
    if (!response.ok) throw new Error(apiErrorMessage(batch, 'Could not start key analysis.'));
    while (batch.status === 'processing') {
      button.textContent = `Analyzing keys ${batch.processed}/${batch.total}`;
      await new Promise(resolve => setTimeout(resolve, 700));
      const status = await fetch(`/api/downloaded-library/key-analysis/${batch.batch_id}`, {cache:'no-store'});
      batch = await status.json();
      if (!status.ok) throw new Error(apiErrorMessage(batch, 'Key-analysis status was lost.'));
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
