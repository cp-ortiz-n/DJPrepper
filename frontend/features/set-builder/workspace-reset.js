import { resetSetBuilderWorkspace } from './state.js';
import { SET_BRIEF_MODES } from './workflow.js';

/** Owns the UI and state transition back to a clean Set Builder draft. */
export function createSetBuilderResetController({
  state,
  $,
  workflow,
  authoring,
  rendering,
  planning,
}) {
  const {
    populateSetDetailedGenres,
    renderExcludedSetGenres,
    renderFallbackPolicy,
    renderSetDetailedGenres,
    renderSetGenreMix,
  } = authoring;
  const { renderSetPlan, renderSetProposals, renderSetRules, updateSetHistoryButtons } = rendering;
  const { resetSetReviewDraft, setPlanningReceipt, stopTransitionPreview } = planning;

  function resetBriefControls(message = 'Set brief reset.') {
    $('#set-builder-form').reset();
    workflow.applyBriefMode(SET_BRIEF_MODES.AI, { announce: false });
    $('#set-intention-interpretation').hidden = true;
    $('#set-journey-preview').hidden = true;
    renderFallbackPolicy();
    [...$('#set-genre').options].forEach((option) => {
      option.selected = option.value === 'all';
    });
    populateSetDetailedGenres();
    [...$('#set-excluded-genres').options].forEach((option) => {
      option.selected = false;
    });
    state.genreSelectionOrder = [];
    renderSetGenreMix();
    renderSetDetailedGenres();
    renderExcludedSetGenres();
    state.requiredIds.clear();
    state.excludedIds.clear();
    state.lockedIds.clear();
    state.proposals = [];
    state.activeProposal = '';
    renderSetRules();
    renderSetProposals();
    $('#set-builder-message').textContent = message;
  }

  function resetActiveWorkspace(message) {
    stopTransitionPreview();
    setPlanningReceipt(null);
    resetSetReviewDraft();
    resetSetBuilderWorkspace(state);
    resetBriefControls(message);
    $('#saved-set-select').value = '';
    $('#set-result-name').value = 'New DJ Set';
    renderSetPlan();
    updateSetHistoryButtons();
  }

  return Object.freeze({ resetActiveWorkspace, resetBriefControls });
}
