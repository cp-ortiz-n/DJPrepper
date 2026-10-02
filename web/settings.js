export function createSettingsController({loadConfig, loadPresets, loadLibraryStatus, loadRelocationState}) {
  return {
    initialize(afterConfig) {
      const configured = loadConfig().then(() => afterConfig?.());
      loadLibraryStatus();
      loadRelocationState();
      return configured;
    },
    loadPresets,
    async refreshStorage() {
      return loadLibraryStatus();
    },
  };
}

export function libraryAvailabilityView(status = {}) {
  const online = Boolean(status.online);
  const offlineTracks = Number(status.offline_tracks || 0);
  return {
    online,
    bannerHidden: online,
    clearStaleErrors: online && offlineTracks === 0,
    label: online ? 'Library online' : 'Library offline',
  };
}
