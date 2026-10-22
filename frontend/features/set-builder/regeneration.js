/** Explicit revision regeneration with comparison and rollback-safe orchestration. */

export function comparePlanRevisions({ before, after, lockedIds }) {
  const previousIds = before.tracks || [];
  const nextIds = after.tracks || [];
  const previous = new Set(previousIds);
  const next = new Set(nextIds);
  const stayed = nextIds.filter((id) => previous.has(id));
  const added = nextIds.filter((id) => !previous.has(id));
  const removed = previousIds.filter((id) => !next.has(id));
  const locked = [...lockedIds];
  const lockedPreserved = locked.filter((id) => next.has(id));
  return {
    fromRevision: before.revision?.number || 0,
    toRevision: after.revision?.number || 0,
    stayed: stayed.length,
    changed: Math.max(added.length, removed.length),
    added,
    removed,
    locked: locked.length,
    lockedPreserved: lockedPreserved.length,
    lockedMissing: locked.filter((id) => !next.has(id)),
    changedTrackIds: added,
  };
}

export function revisionComparisonLabel(comparison) {
  if (!comparison) return '';
  const locked = comparison.locked
    ? ` · ${comparison.lockedPreserved}/${comparison.locked} locked preserved`
    : '';
  return `Revision ${comparison.toRevision} · ${comparison.stayed} stayed · ${comparison.changed} changed${locked}`;
}

export function createSetRegenerationCommand({ state, snapshot, restore, generate, render, getReceipt, setReceipt }) {
  return async function regenerateUnlocked() {
    if (!state.plan.length) throw new Error('Build a set before regenerating it.');
    const protectedIds = new Set([...state.lockedIds, ...state.requiredIds]);
    const conflicts = [...protectedIds].filter((id) => state.excludedIds.has(id));
    if (conflicts.length) throw new Error('A locked or required track is also excluded. Resolve the rule conflict first.');
    const before = snapshot();
    const beforeReceipt = getReceipt();
    const historyDepth = state.history.length;
    const previousFuture = [...state.future];
    const rollback = () => {
      restore(before);
      state.history.splice(historyDepth);
      state.future = previousFuture;
      setReceipt(beforeReceipt);
      render();
    };
    const lockedIds = new Set(state.lockedIds);
    try {
      await generate();
    } catch (error) {
      rollback();
      throw error;
    }
    const after = snapshot();
    if ((after.revision?.number || 0) <= (before.revision?.number || 0)) {
      rollback();
      throw new Error('No new revision was generated. The current set was left unchanged.');
    }
    const comparison = comparePlanRevisions({ before, after, lockedIds });
    if (comparison.lockedMissing.length) {
      rollback();
      throw new Error(`Regeneration tried to drop ${comparison.lockedMissing.length} locked track(s), so it was rolled back.`);
    }
    state.revisionComparison = comparison;
    setReceipt({ ...getReceipt(), regeneration: comparison });
    render();
    return comparison;
  };
}
