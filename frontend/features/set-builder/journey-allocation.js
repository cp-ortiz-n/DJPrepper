/** Section-aware candidate allocation for confirmed Set Builder journeys. */

import { journeySectionForIndex } from './planning-request.js';

export function shortlistJourneyPool({ eligiblePool, requiredIds, setTrackId, score, limit = 800 }) {
  const pool =
    eligiblePool.length <= limit
      ? [...eligiblePool]
      : [...eligiblePool].sort((left, right) => score(right) - score(left)).slice(0, limit);
  eligiblePool
    .filter((track) => requiredIds.has(setTrackId(track)) && !pool.includes(track))
    .forEach((track) => pool.push(track));
  return pool;
}

export function deterministicTrackCount(pool, lengthMinutes, protectedCount) {
  const averageSeconds =
    pool.reduce((sum, track) => sum + Math.max(90, Number(track.duration_seconds || 210) - 30), 0) / pool.length;
  return Math.max(2, protectedCount, Math.min(pool.length, Math.ceil((lengthMinutes * 60) / averageSeconds)));
}

export function createJourneyAllocation({ journey, count, pool, trackMatchesIntendedGenre, setTrackId }) {
  const sections = new Map((journey.sections || []).map((section) => [String(section.id), section]));
  const positionSections = Array.from({ length: count }, (_, index) =>
    sections.get(journeySectionForIndex(journey, index, count)),
  );
  const strict = String(journey.genrePolicy?.mode || '').toLowerCase() === 'strict';
  const matchesSection = (track, section) =>
    !(section?.genres || []).length ||
    section.genres.some((genre) => trackMatchesIntendedGenre(track, String(genre || '')));
  const slotCounts = new Map();
  positionSections.forEach((section) => {
    if (section) slotCounts.set(String(section.id), (slotCounts.get(String(section.id)) || 0) + 1);
  });
  const reservation = new Map();
  let scarcity = null;
  if (strict) {
    const trackSections = new Map(
      pool.map((track) => [
        setTrackId(track),
        [...sections.values()].filter((section) => matchesSection(track, section)).length,
      ]),
    );
    const visit = (slotIndex, seen) => {
      const section = positionSections[slotIndex];
      const candidates = pool
        .filter((track) => matchesSection(track, section))
        .sort((left, right) => trackSections.get(setTrackId(left)) - trackSections.get(setTrackId(right)));
      for (const track of candidates) {
        const trackId = setTrackId(track);
        if (seen.has(trackId)) continue;
        seen.add(trackId);
        const occupiedSlot = reservation.get(trackId);
        if (occupiedSlot == null || visit(occupiedSlot, seen)) {
          reservation.set(trackId, slotIndex);
          return true;
        }
      }
      return false;
    };
    const failedIndex = positionSections.findIndex((_section, index) => !visit(index, new Set()));
    if (failedIndex >= 0) {
      const section = positionSections[failedIndex];
      scarcity = {
        section,
        slots: slotCounts.get(String(section.id)) || 0,
        available: pool.filter((track) => matchesSection(track, section)).length,
      };
    }
  }
  const reservedSection = new Map(
    [...reservation].map(([trackId, slotIndex]) => [trackId, String(positionSections[slotIndex]?.id || '')]),
  );
  return Object.freeze({ matchesSection, positionSections, reservedSection, scarcity, strict });
}

export function sectionCandidatePool({
  available,
  section,
  allocation,
  identityTargeted,
  globallyTargeted,
  setTrackId,
}) {
  if (!section) return identityTargeted.length ? identityTargeted : globallyTargeted.length ? globallyTargeted : available;
  const sectionId = String(section.id || '');
  const sectionTargeted = available.filter((track) => {
    const reservedFor = allocation.reservedSection.get(setTrackId(track));
    return allocation.matchesSection(track, section) && (!reservedFor || reservedFor === sectionId);
  });
  if (sectionTargeted.length) return sectionTargeted;
  if (allocation.strict) return [];
  return identityTargeted.length ? identityTargeted : globallyTargeted.length ? globallyTargeted : available;
}

export function journeyPlanSnapshot(plan, lockedIds, setTrackId) {
  return {
    tracks: plan.map(setTrackId),
    sections: Object.fromEntries(
      plan.filter((track) => track._planSectionId).map((track) => [setTrackId(track), track._planSectionId]),
    ),
    locked: [...lockedIds],
    transitions: {},
  };
}

export function journeySectionFallbacks(plan, positionSections, matchesSection) {
  return plan
    .map((track, index) => ({ track, index, section: positionSections[index] }))
    .filter(({ track, section }) => section && !matchesSection(track, section));
}

export function ensureRequestedGenreCoverage({
  plan,
  remaining,
  intendedGenres,
  trackMatchesIntendedGenre,
  coarseScore,
  candidateScore,
  canReplace,
  replacementAllowed,
  setTrackId,
}) {
  intendedGenres.forEach((term) => {
    if (plan.some((track) => trackMatchesIntendedGenre(track, term))) return;
    const replacement = [...remaining.values()]
      .filter((track) => trackMatchesIntendedGenre(track, term))
      .sort((left, right) => coarseScore(right) - coarseScore(left))[0];
    if (!replacement) return;
    const replaceIndex = plan
      .map((track, index) => ({ track, index, score: candidateScore(track, index) }))
      .filter(({ track, index }) => index > 0 && canReplace(track) && replacementAllowed(replacement, index))
      .sort((left, right) => left.score - right.score)[0]?.index;
    if (replaceIndex == null) return;
    remaining.set(setTrackId(plan[replaceIndex]), plan[replaceIndex]);
    remaining.delete(setTrackId(replacement));
    plan[replaceIndex] = replacement;
  });
  return plan;
}
