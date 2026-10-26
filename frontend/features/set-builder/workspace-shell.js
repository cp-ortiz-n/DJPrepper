/** Compact Set Builder workspace presentation and selected-track ownership. */

import { revisionComparisonLabel } from './regeneration.js';

export function workspaceIdentity(state) {
  const revision = Number(state.planRevision?.number || 0);
  return {
    stateLabel: state.activeSavedSetId ? 'Saved plan' : 'Draft plan',
    revisionLabel: revision ? `Revision ${revision}` : 'Unversioned draft',
  };
}

export function trackStateChips({ locked, decision, changed = false }) {
  return [
    locked ? { kind: 'locked', label: 'Locked' } : null,
    decision === 'accept' ? { kind: 'kept', label: 'Kept' } : null,
    decision === 'reject' ? { kind: 'rejected', label: 'Rejected' } : null,
    decision === 'replaced' ? { kind: 'changed', label: 'Replaced' } : null,
    changed ? { kind: 'changed', label: 'Changed' } : null,
  ].filter(Boolean);
}

export function compactTrackSummaryMarkup({
  track,
  transition,
  locked,
  review,
  formatKey,
  energyLabel,
  healthThreshold,
  changed = false,
  escapeHtml,
}) {
  const chips = trackStateChips({ locked, decision: review?.decision, changed });
  const match = transition.score == null ? 'Opening' : `${transition.score}% match`;
  return `<div class="set-track-summary"><span>${escapeHtml(track._genre || 'Other')}</span><span>${Number(track.bpm || 0).toFixed(1)} BPM</span><span>${escapeHtml(formatKey(track.key))}</span><span>${escapeHtml(energyLabel)} energy</span><strong class="${transition.score != null && transition.score < healthThreshold ? 'warning' : ''}">${match}</strong></div><div class="set-track-chips">${chips
    .map((chip) => `<span class="${chip.kind}">${chip.label}</span>`)
    .join('')}</div>`;
}

export function createSetBuilderWorkspaceShell({ state, $, $$, setTrackId, regenerateUnlocked }) {
  let movedNodes = [];

  function inspector() {
    return $('#set-track-inspector');
  }

  function restoreMovedNodes() {
    if (!movedNodes.length) return;
    const { card, nodes } = movedNodes[0];
    if (card?.isConnected) nodes.forEach((node) => card.append(node));
    movedNodes = [];
  }

  function closeInspector({ restoreFocus = false } = {}) {
    const selectedId = state.selectedTrackId;
    restoreMovedNodes();
    $$('.set-track-card').forEach((card) => {
      card.classList.remove('selected');
      card.removeAttribute('aria-current');
    });
    const panel = inspector();
    if (!panel) return;
    panel.hidden = true;
    panel.querySelector('.set-track-inspector-content').replaceChildren();
    state.selectedTrackId = '';
    if (restoreFocus && selectedId) {
      $$('.set-track-card')
        .find((card) => setTrackId(state.plan[Number(card.dataset.index)]) === selectedId)
        ?.focus();
    }
  }

  function selectTrack(index, { focusInspector = false } = {}) {
    const card = $(`.set-track-card[data-index="${index}"]`);
    const track = state.plan[index];
    if (!card || !track) return;
    restoreMovedNodes();
    $$('.set-track-card').forEach((item) => {
      const selected = item === card;
      item.classList.toggle('selected', selected);
      if (selected) item.setAttribute('aria-current', 'true');
      else item.removeAttribute('aria-current');
    });
    state.selectedTrackId = setTrackId(track);
    const panel = inspector();
    if (!panel) return;
    panel.hidden = false;
    panel.querySelector('.set-track-inspector-position').textContent = `Track ${index + 1} of ${state.plan.length}`;
    panel.querySelector('.set-track-inspector-title').textContent = track.source_name.replace(/\.[^.]+$/, '');
    panel.querySelector('.set-track-inspector-artist').textContent = track.artist || track._genre || 'Catalog track';
    const content = panel.querySelector('.set-track-inspector-content');
    content.replaceChildren();
    const nodes = ['.set-track-meta', '.set-transition', '.set-row-actions']
      .map((selector) => card.querySelector(selector))
      .filter(Boolean);
    nodes.forEach((node) => content.append(node));
    movedNodes = [{ card, nodes }];
    if (focusInspector) panel.querySelector('.close-set-inspector').focus();
  }

  function refreshHeader() {
    const identity = workspaceIdentity(state);
    const stateLabel = $('#set-workspace-state');
    const revisionLabel = $('#set-workspace-revision');
    const comparison = $('#set-revision-comparison');
    if (stateLabel) stateLabel.textContent = identity.stateLabel;
    if (revisionLabel) revisionLabel.textContent = identity.revisionLabel;
    if (comparison) {
      comparison.textContent = revisionComparisonLabel(state.revisionComparison);
      comparison.hidden = !state.revisionComparison;
    }
  }

  function beforeRender() {
    restoreMovedNodes();
    const panel = inspector();
    if (!panel) return;
    panel.hidden = true;
    panel.querySelector('.set-track-inspector-content').replaceChildren();
  }

  function bindRows() {
    refreshHeader();
    const rows = $$('.set-track-card');
    rows.forEach((card, index) => {
      card.tabIndex = 0;
      card.setAttribute('role', 'listitem');
      card.setAttribute('aria-label', `Track ${index + 1}: ${state.plan[index].source_name.replace(/\.[^.]+$/, '')}`);
      card.querySelector('.set-inspect-track').onclick = () => selectTrack(index, { focusInspector: true });
      card.addEventListener('click', (event) => {
        if (!event.target.closest('button,input,select,audio,details,.compact-audio')) selectTrack(index);
      });
      card.addEventListener('keydown', (event) => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
          event.preventDefault();
          rows[Math.max(0, Math.min(rows.length - 1, index + (event.key === 'ArrowDown' ? 1 : -1)))]?.focus();
        } else if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          selectTrack(index, { focusInspector: true });
        }
      });
    });
    const selectedIndex = state.plan.findIndex((track) => setTrackId(track) === state.selectedTrackId);
    if (selectedIndex >= 0) selectTrack(selectedIndex);
    else state.selectedTrackId = '';
  }

  const inspectorPanel = inspector();
  if (inspectorPanel)
    inspectorPanel.querySelector('.close-set-inspector').onclick = () => closeInspector({ restoreFocus: true });
  globalThis.document?.addEventListener('pointerdown', (event) => {
    const panel = inspector();
    if (!panel || panel.hidden || panel.contains(event.target) || event.target.closest('.set-track-card')) return;
    closeInspector();
  });
  const reviewAction = $('#review-set-action');
  if (reviewAction)
    reviewAction.onclick = () => {
      const panel = $('#set-review-panel');
      panel.open = true;
      const behavior = globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
      panel.scrollIntoView({ behavior, block: 'center' });
      panel.querySelector('summary').focus();
    };
  const regenerateAction = $('#regenerate-set');
  if (regenerateAction)
    regenerateAction.onclick = async () => {
      regenerateAction.disabled = true;
      regenerateAction.textContent = 'Regenerating…';
      $('#set-builder-message').textContent = 'Keeping locked tracks and rebuilding the rest of this revision…';
      try {
        const comparison = await regenerateUnlocked();
        $('#set-builder-message').textContent =
          `${revisionComparisonLabel(comparison)}. Undo restores the complete previous revision.`;
      } catch (error) {
        $('#set-builder-message').textContent =
          `Regeneration failed: ${error?.message || error}. The previous revision remains available.`;
      } finally {
        regenerateAction.disabled = false;
        regenerateAction.textContent = 'Regenerate unlocked';
      }
    };
  inspectorPanel?.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      closeInspector({ restoreFocus: true });
    }
  });

  return Object.freeze({ beforeRender, bindRows, closeInspector, refreshHeader, selectTrack });
}
