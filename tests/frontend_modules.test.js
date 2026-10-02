import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.localStorage = {
  values: new Map(),
  getItem(key) { return this.values.get(key) ?? null; },
  setItem(key, value) { this.values.set(key, String(value)); },
};

const musicFiles = await import('../web/music-files.js');
const library = await import('../web/dj-library.js');
const setBuilder = await import('../web/set-builder.js');
const settings = await import('../web/settings.js');
const shared = await import('../web/shared-components.js');

test('Music Files owns filter state and API serialization', () => {
  const state = musicFiles.createMusicFilesUiState(25);
  state.genre = 'Electronic / House';
  state.quality = 'below-target';
  const query = musicFiles.musicFilesQuery(state);
  assert.equal(query.get('paged'), 'true');
  assert.equal(query.get('genre'), 'Electronic / House');
  assert.equal(query.get('quality'), 'below-target');
  assert.equal(query.get('page_size'), '25');
});

test('DJ Library exposes stable musical compatibility helpers', () => {
  assert.equal(library.camelotKey('A minor'), '8A');
  assert.equal(library.formatLibraryKey('G minor', 'both'), 'G minor · 6A');
  const result = library.compatibility(
    {bpm:120,key:'A minor',_energy:.5,_roles:['melodic']},
    {bpm:121,key:'C major',_energy:.55,_roles:['melodic']},
  );
  assert.ok(result.score >= 70);
  assert.equal(result.key, 'relative key');
});

test('Set Builder creates isolated mutable state', () => {
  const left = setBuilder.createSetBuilderState();
  const right = setBuilder.createSetBuilderState();
  left.requiredIds.add('track-a');
  assert.equal(right.requiredIds.size, 0);
  assert.equal(setBuilder.setTrackId({source_name:'Track.WAV'}), 'track.wav');
});

test('Settings controller preserves startup ordering', async () => {
  const calls = [];
  const controller = settings.createSettingsController({
    loadConfig: async () => { calls.push('config'); },
    loadPresets: async () => { calls.push('presets'); },
    loadLibraryStatus: () => { calls.push('status'); },
    loadRelocationState: () => { calls.push('relocation'); },
  });
  await controller.initialize(() => calls.push('ready'));
  assert.deepEqual(calls, ['config', 'status', 'relocation', 'ready']);
});

test('library reconnect hides offline state and clears stale errors', () => {
  assert.deepEqual(settings.libraryAvailabilityView({online:false,offline_tracks:4}), {
    online:false,bannerHidden:false,clearStaleErrors:false,label:'Library offline',
  });
  assert.deepEqual(settings.libraryAvailabilityView({online:true,offline_tracks:0}), {
    online:true,bannerHidden:true,clearStaleErrors:true,label:'Library online',
  });
});

test('focused search keeps every character while an older response renders', () => {
  const input = {value:'abcdef'};
  const state = {search:'abc'};
  shared.captureTextFilter(input, state);
  assert.equal(state.search, 'abcdef');
  assert.equal(shared.syncControlUnlessEditing(input, 'abc', input), false);
  assert.equal(input.value, 'abcdef');

  input.value = 'abcdefghijklmnopqrstuvwxyz1234567890';
  shared.captureTextFilter(input, state);
  shared.syncControlUnlessEditing(input, 'abcdef', input);
  assert.equal(input.value, 'abcdefghijklmnopqrstuvwxyz1234567890');
  assert.equal(state.search, 'abcdefghijklmnopqrstuvwxyz1234567890');
});
