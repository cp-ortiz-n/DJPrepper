/** Guided Keep/Reject workflow and validated single-slot replacement. */

import { applyExplicitSetPlanChoice } from './plan-integrity.js';
import { beginButtonAction } from './ui-state.js';

export function selectValidatedReplacement({
  state,
  index,
  candidates,
  excludedIds,
  setTrackId,
  setRecordingKey,
  trackMatchesIntendedGenre = () => false,
  setCandidateScore,
  compatibility,
  brief,
}) {
  const current = state.plan[index];
  const previous = state.plan[index - 1];
  const next = state.plan[index + 1];
  const usedFamilies = new Set(state.plan.filter((_, position) => position !== index).map(setRecordingKey));
  let available = (candidates || [])
    .filter((track) => setTrackId(track) !== setTrackId(current))
    .filter((track) => !excludedIds.has(setTrackId(track)))
    .filter((track) => !usedFamilies.has(setRecordingKey(track)));
  const journey = brief.identity?.journey;
  const section = (journey?.sections || []).find((item) => String(item.id) === String(current._planSectionId));
  if (section?.genres?.length) {
    const targeted = available.filter((track) =>
      section.genres.some((genre) => trackMatchesIntendedGenre(track, String(genre || ''))),
    );
    if (targeted.length || String(journey.genrePolicy?.mode).toLowerCase() === 'strict') available = targeted;
  }
  return available
    .map((track) => ({
      track,
      score:
        setCandidateScore(track, previous, index, state.plan.length, brief) +
        (next ? compatibility(track, next).score * 0.3 : 0),
    }))
    .sort((left, right) => right.score - left.score)[0]?.track;
}

export function createTrackRejectionWorkflow({ state, dom, music, policy, lifecycle, persistence }) {
  const { $, escapeHtml } = dom;
  const { compatibility, setTrackId, setRecordingKey, trackMatchesIntendedGenre } = music;
  const { eligibleSetTracks, setCandidateScore } = policy;
  const { advancePlanRevision, pushSetHistory, renderSetPlan, setBrief } = lifecycle;
  let activeIndex = -1;

  function review(track) {
    return state.trackReviews.get(setTrackId(track)) || {};
  }

  function trackReviewMarkup(track) {
    const current = review(track);
    if (current.decision === 'replaced') {
      return `<div class="set-track-review-status success"><span><b>Replacement ready</b><small>${escapeHtml(current.message || 'Rejected track replaced · feedback saved')}</small></span></div>`;
    }
    if (current.decision === 'reject' && current.saved) {
      return `<div class="set-track-review-status danger"><span><b>Rejected · feedback saved</b><small>${escapeHtml(current.unresolved ? 'No valid replacement was available. Retry after relaxing a rule.' : 'This track will stay excluded from reruns.')}</small></span>${current.unresolved ? '<button type="button" class="button secondary set-retry-replacement">Retry replacement</button>' : ''}</div>`;
    }
    return `<div class="set-track-review"><button type="button" class="button secondary set-keep-track ${current.decision === 'accept' ? 'active' : ''}">${current.saved ? '✓ Kept · saved' : '✓ Keep'}</button><button type="button" class="button destructive set-reject-track">× Reject & replace</button><small>Keep teaches preference. Lock separately if this position must not change.</small></div>`;
  }

  function exclusionIds(track, scope) {
    if (scope === 'recording-family') {
      const family = setRecordingKey(track);
      return new Set(state.library.filter((candidate) => setRecordingKey(candidate) === family).map(setTrackId));
    }
    return new Set([setTrackId(track)]);
  }

  function dialog() {
    return $('#set-track-decision-dialog');
  }

  function openRejectDialog(index) {
    const track = state.plan[index];
    const panel = dialog();
    if (!track || !panel) return;
    activeIndex = index;
    const currentReview = review(track);
    const protectedTrack = state.lockedIds.has(setTrackId(track)) || state.requiredIds.has(setTrackId(track));
    panel.querySelector('.set-decision-track').textContent = track.source_name.replace(/\.[^.]+$/, '');
    panel.querySelector('.set-decision-artist').textContent = track.artist || track._genre || 'Catalog track';
    const reason = panel.querySelector('[name="set-reject-reason"]');
    reason.value = currentReview.reason || '';
    reason.disabled = Boolean(currentReview.saved);
    panel.querySelectorAll('[name="set-reject-scope"]').forEach((input) => {
      input.checked = input.value === (currentReview.scope || 'version');
      input.disabled = Boolean(currentReview.saved);
    });
    panel.querySelector('.set-decision-guidance').textContent = currentReview.saved
      ? 'Feedback is already saved. Retry searches again with the same scope; Undo first to change the decision.'
      : 'Feedback is saved first. The replacement must fit the same journey, pass every hard rule, and cannot duplicate another song in the set.';
    panel.querySelector('.set-decision-error').textContent = protectedTrack
      ? 'Unlock this track or remove its required rule before rejecting it.'
      : '';
    panel.querySelector('.confirm-track-rejection').disabled = protectedTrack;
    panel.showModal();
  }

  function clearAffectedTransitions(track) {
    const id = setTrackId(track);
    Object.keys(state.transitionSettings).forEach((key) => {
      if (key.startsWith(`${id}→`) || key.endsWith(`→${id}`)) delete state.transitionSettings[key];
    });
  }

  async function keepTrack(index, button) {
    const track = state.plan[index];
    if (!track) return;
    const prior = review(track);
    const restoreAction = beginButtonAction(button, 'Saving track feedback…');
    try {
      state.trackReviews.set(
        setTrackId(track),
        await persistence.record(track, { decision: 'accept', eventId: prior.eventId }),
      );
      renderSetPlan();
      $('#set-builder-message').textContent =
        'Kept · feedback saved. Lock the track separately to preserve its section.';
    } catch (error) {
      restoreAction();
      $('#set-builder-message').textContent = `Keep was not saved: ${error.message || error}. Try again.`;
    }
  }

  async function rejectAndReplace() {
    const track = state.plan[activeIndex];
    const panel = dialog();
    if (!track || !panel) return;
    const action = panel.querySelector('.confirm-track-rejection');
    const reason = panel.querySelector('[name="set-reject-reason"]').value;
    const scope = panel.querySelector('[name="set-reject-scope"]:checked')?.value || 'version';
    const prior = review(track);
    const restoreAction = beginButtonAction(action, prior.saved ? 'Finding a replacement…' : 'Saving feedback…');
    panel.querySelector('.set-decision-error').textContent = '';
    try {
      const saved = prior.saved
        ? prior
        : await persistence.record(track, { decision: 'reject', reason, scope, eventId: prior.eventId });
      const excluded = exclusionIds(track, scope);
      const replacement = selectValidatedReplacement({
        state,
        index: activeIndex,
        candidates: eligibleSetTracks(setBrief()),
        excludedIds: excluded,
        setTrackId,
        setRecordingKey,
        trackMatchesIntendedGenre,
        setCandidateScore,
        compatibility,
        brief: setBrief(),
      });
      if (!replacement && prior.saved) {
        panel.close();
        renderSetPlan();
        $('#set-builder-message').textContent =
          'No valid replacement is available yet. The saved rejection is unchanged; relax a rule and retry.';
        return;
      }
      pushSetHistory();
      excluded.forEach((id) => state.excludedIds.add(id));
      state.trackReviews.set(setTrackId(track), { ...saved, unresolved: !replacement });
      clearAffectedTransitions(track);
      if (replacement) {
        replacement._planSectionId = track._planSectionId || null;
        state.plan[activeIndex] = replacement;
        applyExplicitSetPlanChoice(state, replacement);
        state.trackReviews.set(setTrackId(replacement), {
          decision: 'replaced',
          saved: true,
          message: `${track.source_name.replace(/\.[^.]+$/, '')} rejected · replacement feedback saved`,
        });
      }
      advancePlanRevision();
      panel.close();
      renderSetPlan();
      $('#set-builder-message').textContent = replacement
        ? `Rejected and replaced with ${replacement.source_name.replace(/\.[^.]+$/, '')} · feedback saved. Undo restores both.`
        : 'Rejection saved, but no valid replacement is available. The track remains visibly rejected; relax a rule and retry.';
    } catch (error) {
      panel.querySelector('.set-decision-error').textContent =
        `${error.message || error}. Nothing in the set was changed; try again.`;
    } finally {
      restoreAction();
    }
  }

  function bindTrackReview(card, index) {
    card.querySelector('.set-keep-track')?.addEventListener('click', (event) => keepTrack(index, event.currentTarget));
    card.querySelector('.set-reject-track')?.addEventListener('click', () => openRejectDialog(index));
    card.querySelector('.set-retry-replacement')?.addEventListener('click', () => openRejectDialog(index));
  }

  function hasUnresolvedRejections() {
    return [...state.trackReviews.values()].some((item) => item.decision === 'reject' && item.unresolved);
  }

  const panel = dialog();
  panel?.querySelector('.cancel-track-rejection').addEventListener('click', () => panel.close());
  panel?.querySelector('.confirm-track-rejection').addEventListener('click', rejectAndReplace);
  panel?.addEventListener('close', () => {
    activeIndex = -1;
  });

  return Object.freeze({ bindTrackReview, hasUnresolvedRejections, openRejectDialog, trackReviewMarkup });
}
