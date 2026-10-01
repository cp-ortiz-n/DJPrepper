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
