/** Shared recording-family integrity boundary for editable Set Builder plans. */

import { reconcileSetRecordingFamilies, setRecordingKey, setTrackId } from './recording-identity.js';

export function applySetPlanIntegrity(
  state,
  { preferredTrackIds = new Set(), trackId, recordingKey, clearTransitions = false },
) {
  const lockedTrackIds = state.lockedIds || new Set();
  const requiredTrackIds = state.requiredIds || new Set();
  const protectedTrackIds = new Set([...lockedTrackIds, ...requiredTrackIds, ...preferredTrackIds]);
  const integrity = reconcileSetRecordingFamilies(state.plan, {
    preferredTrackIds: protectedTrackIds,
    trackId,
    recordingKey,
  });
  if (!integrity.valid) {
    state.plan = integrity.plan;
    const retained = new Set(state.plan.map(trackId));
    state.lockedIds = new Set([...lockedTrackIds].filter((id) => retained.has(id)));
    if (clearTransitions) state.transitionSettings = {};
  }
  return integrity;
}

export function applyExplicitSetPlanChoice(state, track) {
  return applySetPlanIntegrity(state, {
    preferredTrackIds: new Set([setTrackId(track)]),
    trackId: setTrackId,
    recordingKey: setRecordingKey,
  });
}

export function applyDefaultSetPlanIntegrity(state, clearTransitions = false) {
  return applySetPlanIntegrity(state, { trackId: setTrackId, recordingKey: setRecordingKey, clearTransitions });
}

export function requireUniqueSetPlan(plan, { preferredTrackIds, trackId, recordingKey, source }) {
  const integrity = reconcileSetRecordingFamilies(plan, { preferredTrackIds, trackId, recordingKey });
  if (!integrity.valid) {
    throw new Error(
      `${source} returned ${integrity.removed.length} duplicate song version${integrity.removed.length === 1 ? '' : 's'}. The existing set was left unchanged.`,
    );
  }
  return integrity.plan;
}

export function recoverSavedSetPlan({ record, library, trackId, recordingKey, recoveryScore }) {
  const candidates = Array.isArray(library) ? library : [];
  const byId = new Map(candidates.map((track) => [trackId(track), track]));
  const details = new Map((record.trackDetails || []).map((item) => [item.id, item]));
  const preferredTrackIds = new Set([...(record.locked || []), ...(record.required || [])]);
  const exact = reconcileSetRecordingFamilies(
    (record.tracks || []).map((id) => byId.get(id)).filter(Boolean),
    { preferredTrackIds, trackId, recordingKey },
  );
  const selectedExact = new Set(exact.plan);
  const used = new Set(exact.plan.map(recordingKey));
  const plan = [];
  let recovered = 0;
  (record.tracks || []).forEach((id) => {
    let track = byId.get(id);
    if (track && !selectedExact.has(track)) return;
    if (!track) {
      track = candidates
        .filter((candidate) => !used.has(recordingKey(candidate)))
        .map((candidate) => ({ candidate, score: recoveryScore(candidate, details.get(id) || { id }, plan.at(-1)) }))
        .sort((left, right) => right.score - left.score)[0]?.candidate;
      if (track) recovered += 1;
    }
    if (!track) return;
    const detail = details.get(id);
    track._aiSelectionReason = detail?.selectionReason || null;
    track._planSectionId = detail?.sectionId || null;
    used.add(recordingKey(track));
    plan.push(track);
  });
  const final = reconcileSetRecordingFamilies(plan, { preferredTrackIds, trackId, recordingKey });
  return { plan: final.plan, recovered, duplicatesRemoved: exact.removed.length + final.removed.length };
}
