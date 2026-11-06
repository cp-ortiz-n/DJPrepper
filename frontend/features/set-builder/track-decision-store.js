/** Durable, idempotent Set Builder track decisions and Undo reconciliation. */

function decisionEventId() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function durableEvents(entries) {
  return new Map(
    [...entries]
      .map(([, review]) => review?.eventPayload)
      .filter((event) => event?.id)
      .map((event) => [event.id, event]),
  );
}

export function createTrackDecisionStore({ api, context, features, trackId, recordingKey, setIdentity, refresh }) {
  let reconciliation = Promise.resolve();

  async function record(track, { decision, reason = '', scope = 'version', eventId = '' }) {
    const payload = {
      id: eventId || decisionEventId(),
      action: decision === 'accept' ? 'keep' : 'reject',
      trackId: trackId(track),
      context: context(),
      features: features(track),
      reason,
      scope,
      recordingKey: recordingKey(track),
      setId: setIdentity().setId,
      revisionId: setIdentity().revisionId,
    };
    await api.recordPreference([payload]);
    await refresh();
    return { decision, reason, scope, saved: true, eventId: payload.id, eventPayload: payload };
  }

  function reconcile(previousEntries, nextEntries) {
    const previous = durableEvents(previousEntries);
    const next = durableEvents(nextEntries);
    const apply = async () => {
      try {
        await Promise.all([...previous.keys()].filter((id) => !next.has(id)).map((id) => api.deletePreferenceEvent(id)));
        const restored = [...next.entries()].filter(([id]) => !previous.has(id)).map(([, event]) => event);
        if (restored.length) await api.recordPreference(restored);
        if (previous.size !== next.size || restored.length) await refresh();
      } catch (error) {
        console.warn('Set track-decision reconciliation failed:', error);
      }
    };
    reconciliation = reconciliation.then(apply, apply);
    return reconciliation;
  }

  return Object.freeze({ record, reconcile });
}
