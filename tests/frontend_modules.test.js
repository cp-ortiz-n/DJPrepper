import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';

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
const requests = await import('../web/request-state-controller.js');

test('app.js remains a feature composition root', () => {
  const path = fileURLToPath(new URL('../web/app.js', import.meta.url));
  const source = readFileSync(path, 'utf8');
  assert.ok(source.split('\n').length < 1900, 'app.js exceeded the composition-root size ceiling');
  for (const factory of ['createMusicFilesFeature', 'createDjLibraryFeature', 'createSetBuilderFeature', 'createSettingsFeature', 'createReportingFeature']) {
    assert.match(source, new RegExp(`${factory}\\(`));
  }
  for (const extracted of ['function loadDownloadedLibrary(', 'function loadLibrary()', 'function loadReports()', "$('#settings-form').addEventListener"]) {
    assert.equal(source.includes(extracted), false, `${extracted} belongs in its feature module`);
  }
});

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

test('Set Builder feature declares every musical classifier used during generation', () => {
  const path = fileURLToPath(new URL('../web/set-builder.js', import.meta.url));
  const source = readFileSync(path, 'utf8');
  const signature = source.slice(source.indexOf('createSetBuilderFeature({'), source.indexOf('}) {', source.indexOf('createSetBuilderFeature({')));
  assert.match(signature, /timingProfile/);
  assert.match(signature, /vocalProfile/);
  assert.match(signature, /formatLibraryKey/);
  assert.match(signature, /LIBRARY_ROLE_INFO/);
  assert.match(signature, /stopCompactAudio/);
  assert.match(signature, /WaveSurfer/);
  assert.match(source, /Set generation failed:/);
  assert.match(source, /Transition preview failed/);
  assert.match(source, /renderSetPlan\(\);\s*\$\('#set-builder-message'\).*Optimizing its transitions in the background/);
  assert.match(source, /proposalSwitchNonce/);
  assert.match(source, /resultName\.addEventListener\('input'/);
  assert.match(source, /briefName\.value=resultName\.value/);
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

test('library availability keeps verify disabled until the drive is connected', () => {
  assert.equal(settings.libraryAvailabilityView({online:false}).online,false);
  assert.equal(settings.libraryAvailabilityView({online:true,offline_tracks:2}).clearStaleErrors,false);
  assert.equal(settings.libraryAvailabilityView({online:true,offline_tracks:0}).clearStaleErrors,true);
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

test('operation receipts expose requested, changed, written, failed, and restart facts', () => {
  const text = shared.operationReceiptText({
    requested:{summary:'Save settings'}, changed:{summary:'Changed 2 settings'},
    written_to:['/tmp/settings.sqlite3'], failures:[], survives_restart:true,
    durability:'Stored in SQLite.',
  });
  assert.match(text, /Requested: Save settings/);
  assert.match(text, /Changed: Changed 2 settings/);
  assert.match(text, /Written to: \/tmp\/settings.sqlite3/);
  assert.match(text, /Failed: 0/);
  assert.match(text, /Survives restart: Yes/);
});

test('shared request controller resets pagination when filters change', () => {
  const state={search:'',page:7};
  const controller=requests.createRequestStateController({
    namespace:'test',state,defaults:{search:'',page:1},
    storage:{getItem:()=>null,setItem:()=>{}},location:null,history:null,
  });
  controller.update({search:'all characters 123'});
  assert.deepEqual(state,{search:'all characters 123',page:1});
});
