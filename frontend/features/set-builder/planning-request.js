/** Pure request-building helpers for initial planning and revision regeneration. */

export function planningJourney(brief) {
  if (brief.identity?.journey?.sections?.length) return brief.identity.journey;
  const genres = [...brief.detailedGenres, ...brief.genres];
  const energy = { rise: [3.5, 7.5], 'peak-release': [4, 8], waves: [4.5, 7], steady: [5.5, 5.5] }[
    brief.curve
  ] || [4.5, 6.5];
  return {
    version: 1,
    summary: 'Single editable journey derived from the structured set brief.',
    durationMinutes: brief.length,
    sections: [
      {
        id: 'section-1',
        name: 'Full set',
        durationPercent: 100,
        energyStart: energy[0],
        energyEnd: energy[1],
        genres,
        characteristics: [brief.vibe, brief.curve].filter(Boolean),
        purpose: 'Honor the structured brief while maintaining a playable flow.',
      },
    ],
  };
}

export function planningTrackCount({ brief, pool, protectedIds, journey, lockedSections = {} }) {
  if (pool.length < 2)
    throw new Error(
      `Only ${pool.length} analyzed track${pool.length === 1 ? '' : 's'} passed the hard filters. Check BPM, vocals, timing, exclusions, and manually selected genres.`,
    );
  const averageSeconds =
    pool.reduce((sum, track) => sum + Math.max(90, Number(track.duration_seconds || 210) - 30), 0) / pool.length;
  if (protectedIds.size > 100) throw new Error('AI-curated planning supports at most 100 required or locked tracks.');
  const occupiedSections = new Set(Object.values(lockedSections));
  const sectionMinimum = Object.keys(lockedSections).length +
    Math.max(0, (journey?.sections?.length || 0) - occupiedSections.size);
  return Math.max(
    2,
    protectedIds.size,
    sectionMinimum,
    Math.min(pool.length, Math.ceil((brief.length * 60) / averageSeconds)),
  );
}

export function catalogIds(ids, library, { setTrackId, setCatalogTrackId }) {
  const bySetId = new Map(library.map((track) => [setTrackId(track), setCatalogTrackId(track)]));
  return [...ids].map((id) => bySetId.get(id)).filter(Boolean);
}

export function journeySectionForIndex(journey, index, count) {
  const sections = journey.sections || [];
  if (!sections.length) return '';
  const midpoint = ((index + 0.5) / Math.max(1, count)) * 100;
  let boundary = 0;
  return (
    sections.find((section) => {
      boundary += Number(section.durationPercent || 0);
      return midpoint <= boundary;
    })?.id || sections.at(-1)?.id || ''
  );
}

export function assignPlanSections(plan, journey, preserveIds = new Set(), setTrackId = (track) => track.id) {
  plan.forEach((track, index) => {
    if (!preserveIds.has(setTrackId(track)) || !track._planSectionId) {
      track._planSectionId = journeySectionForIndex(journey, index, plan.length);
    }
  });
  return plan;
}

export function lockedTrackSections({ plan, lockedIds, journey, setTrackId, setCatalogTrackId }) {
  return Object.fromEntries(
    plan
      .map((track, index) => ({
        track,
        setId: setTrackId(track),
        catalogId: setCatalogTrackId(track),
        sectionId: track._planSectionId || journeySectionForIndex(journey, index, plan.length),
      }))
      .filter(({ setId, catalogId, sectionId }) => lockedIds.has(setId) && catalogId && sectionId)
      .map(({ catalogId, sectionId }) => [String(catalogId), String(sectionId)]),
  );
}

export function aiPlanningContext({ state, brief, eligiblePool, setTrackId, setCatalogTrackId }) {
  const journey = planningJourney(brief);
  const lockedSections = lockedTrackSections({
    plan: state.plan,
    lockedIds: state.lockedIds,
    journey,
    setTrackId,
    setCatalogTrackId,
  });
  return {
    journey,
    lockedSections,
    targetTrackCount: planningTrackCount({
      brief,
      pool: eligiblePool,
      protectedIds: new Set([...state.requiredIds, ...state.lockedIds]),
      journey,
      lockedSections,
    }),
  };
}
