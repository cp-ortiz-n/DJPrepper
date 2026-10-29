import { reconcileSetRecordingFamilies } from './recording-identity.js';

export function createSetBuilderId(prefix = 'set') {
  const value = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${value}`;
}

export function createSetBuilderStore({ storage = globalThis.localStorage, createId = createSetBuilderId } = {}) {
  return {
    library: [],
    catalogVocabulary: [],
    plan: [],
    draftId: createId('draft'),
    activeSavedSetId: '',
    planRevision: null,
    revisionComparison: null,
    selectedTrackId: '',
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
    trackReviews: new Map(),
    manualCurationActive: false,
    manualSearchQuery: '',
    manualSearchRequireAll: false,
    manualSuggestionsRequested: false,
  };
}

export function snapshotSetPlan(store, trackId) {
  return {
    tracks: store.plan.map(trackId),
    sections: Object.fromEntries(
      store.plan.filter((track) => track._planSectionId).map((track) => [trackId(track), track._planSectionId]),
    ),
    locked: [...store.lockedIds],
    transitions: structuredClone(store.transitionSettings),
    revision: store.planRevision ? structuredClone(store.planRevision) : null,
    comparison: store.revisionComparison ? structuredClone(store.revisionComparison) : null,
    excluded: [...store.excludedIds],
    trackReviews: Object.fromEntries(
      [...(store.trackReviews || [])].map(([id, review]) => [id, structuredClone(review)]),
    ),
  };
}

export function restoreSetPlan(store, snapshot, library, trackId, recordingKey = trackId) {
  const byId = new Map(library.map((track) => [trackId(track), track]));
  const resolved = (snapshot?.tracks || []).map((id) => byId.get(id)).filter(Boolean);
  store.plan = reconcileSetRecordingFamilies(resolved, {
    preferredTrackIds: new Set(snapshot?.locked || []),
    trackId,
    recordingKey,
  }).plan;
  if (snapshot && Object.hasOwn(snapshot, 'sections')) {
    store.plan.forEach((track) => {
      track._planSectionId = snapshot.sections?.[trackId(track)] || null;
    });
  }
  const retained = new Set(store.plan.map(trackId));
  store.lockedIds = new Set((snapshot?.locked || []).filter((id) => retained.has(id)));
  store.transitionSettings = structuredClone(snapshot?.transitions || {});
  if (snapshot && Object.hasOwn(snapshot, 'excluded')) store.excludedIds = new Set(snapshot.excluded || []);
  if (snapshot && Object.hasOwn(snapshot, 'trackReviews')) {
    (store.trackReviews ||= new Map()).clear();
    Object.entries(snapshot.trackReviews || {}).forEach(([id, review]) => store.trackReviews.set(id, review));
  }
  if (snapshot && Object.hasOwn(snapshot, 'revision')) {
    store.planRevision = snapshot.revision ? structuredClone(snapshot.revision) : null;
  }
  if (snapshot && Object.hasOwn(snapshot, 'comparison')) {
    store.revisionComparison = snapshot.comparison ? structuredClone(snapshot.comparison) : null;
  }
  return store.plan;
}

export function advanceSetPlanRevision(
  store,
  { createId = createSetBuilderId, now = () => new Date().toISOString() } = {},
) {
  const previous = store.planRevision;
  store.planRevision = {
    id: createId('revision'),
    number: Number(previous?.number || 0) + 1,
    parentId: previous?.id || null,
    createdAt: now(),
  };
  return structuredClone(store.planRevision);
}

export function resetSetBuilderWorkspace(store, { createId = createSetBuilderId } = {}) {
  store.plan = [];
  store.draftId = createId('draft');
  store.activeSavedSetId = '';
  store.planRevision = null;
  store.revisionComparison = null;
  store.selectedTrackId = '';
  store.requiredIds.clear();
  store.excludedIds.clear();
  store.lockedIds.clear();
  store.genreSelectionOrder = [];
  store.generationNonce += 1;
  store.proposals = [];
  store.activeProposal = '';
  store.history = [];
  store.future = [];
  store.transitionSettings = {};
  store.trackReviews?.clear();
  store.manualCurationActive = false;
  store.manualSearchQuery = '';
  store.manualSearchRequireAll = false;
  store.manualSuggestionsRequested = false;
  return store;
}
