/** Stable identity and deletion behavior for durable saved Set Builder plans. */
import { createSetBuilderId } from './state.js';

export function savedSetRecordIdentity(state, selectedId = '') {
  const id = state.activeSavedSetId || state.draftId || selectedId || String(Date.now());
  return {
    id,
    draftId: state.draftId || `draft-${id}`,
    planRevision: state.planRevision ? structuredClone(state.planRevision) : null,
  };
}

export function restoreSavedSetIdentity(state, record) {
  state.activeSavedSetId = record.id;
  state.draftId = record.draftId || `draft-${record.id}`;
  state.planRevision = structuredClone(
    record.planRevision ||
      record.planningReceipt?.planRevision || {
        id: `revision-${record.id}-1`,
        number: 1,
        parentId: null,
        createdAt: record.updatedAt || null,
      },
  );
}

export function createSavedSetLifecycle({ state, api, savedSets, cacheSavedSets }) {
  async function duplicateSavedSet(record) {
    const copy = {
      ...record,
      id: String(Date.now()),
      draftId: createSetBuilderId('draft'),
      planRevision: {
        id: createSetBuilderId('revision'),
        number: 1,
        parentId: record.planRevision?.id || null,
        createdAt: new Date().toISOString(),
      },
      name: `${record.name} Copy`,
      brief: { ...record.brief, name: `${record.name} Copy` },
      updatedAt: new Date().toISOString(),
    };
    await api.saveSet(copy);
    cacheSavedSets([copy, ...savedSets()]);
    return copy;
  }

  async function deleteSavedSet(id) {
    if (!id) return { deleted: false, wasActive: false };
    const wasActive = state.activeSavedSetId === id;
    const result = await api.deleteSet(id);
    cacheSavedSets(savedSets().filter((set) => set.id !== id));
    return { ...result, deleted: result?.deleted !== false, wasActive };
  }

  return Object.freeze({ deleteSavedSet, duplicateSavedSet });
}
