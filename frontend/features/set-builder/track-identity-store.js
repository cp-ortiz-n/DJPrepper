/** Browser recovery storage for identities attached to tracks without durable catalog descriptors. */

export function createTrackIdentityStore({ storage, storageKey, trackId, parseTerms }) {
  function load() {
    try {
      return JSON.parse(storage?.getItem(storageKey) || '{}');
    } catch (_) {
      return {};
    }
  }

  function terms(track) {
    return load()[trackId(track)] || [];
  }

  function save(track, values) {
    const store = load();
    store[trackId(track)] = parseTerms(values);
    storage?.setItem(storageKey, JSON.stringify(store));
    track._manualIdentity = store[trackId(track)];
    return track._manualIdentity;
  }

  return Object.freeze({ load, save, terms });
}
