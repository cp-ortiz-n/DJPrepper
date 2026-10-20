export function createSetBuilderStore({ storage = globalThis.localStorage } = {}) {
  return {
    library: [],
    plan: [],
    requiredIds: new Set(),
    excludedIds: new Set(),
    lockedIds: new Set(),
    bound: false,
    genreSelectionOrder: [],
    generationNonce: 0,
    proposals: [],
    activeProposal: '',
    history: [],
    future: [],
    compactMode: storage?.getItem('set-builder-compact') === 'true',
    transitionSettings: {},
  };
}

export function snapshotSetPlan(store, trackId) {
  return {
    tracks: store.plan.map(trackId),
    locked: [...store.lockedIds],
    transitions: structuredClone(store.transitionSettings),
  };
}

export function restoreSetPlan(store, snapshot, library, trackId) {
  const byId = new Map(library.map((track) => [trackId(track), track]));
  store.plan = (snapshot?.tracks || []).map((id) => byId.get(id)).filter(Boolean);
  store.lockedIds = new Set(snapshot?.locked || []);
  store.transitionSettings = structuredClone(snapshot?.transitions || {});
  return store.plan;
}
