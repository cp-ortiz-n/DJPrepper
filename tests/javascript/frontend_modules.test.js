import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

globalThis.localStorage = {
  values: new Map(),
  getItem(key) {
    return this.values.get(key) ?? null;
  },
  setItem(key, value) {
    this.values.set(key, String(value));
  },
};
globalThis.document = {
  createElement() {
    return {
      value: '',
      set textContent(value) {
        this.value = String(value);
      },
      get innerHTML() {
        return this.value
          .replaceAll('&', '&amp;')
          .replaceAll('<', '&lt;')
          .replaceAll('>', '&gt;')
          .replaceAll('"', '&quot;');
      },
    };
  },
};

const musicFiles = await import('../../web/music-files.js');
const setBuilder = await import('../../web/set-builder.js');
const settings = await import('../../web/settings.js');
const shared = await import('../../web/shared-components.js');
const requests = await import('../../web/request-state-controller.js');
const frontendServices = await import('../../web/frontend-services.js');
const reporting = await import('../../web/reporting.js');

test('feature factories share a validated immutable services contract', () => {
  const noop = () => {};
  const services = frontendServices.createFrontendServices({
    api: { raw: noop, request: noop, errorMessage: noop },
    dom: { $: noop, $$: noop },
    feedback: { notify: noop, confirmAction: noop, operationReceiptText: noop },
    descriptors: {
      chipsMarkup: noop,
      editorMarkup: noop,
      openEditorDialog: noop,
      saveEditor: noop,
      inferEditor: noop,
    },
  });

  assert.equal(Object.isFrozen(services), true);
  assert.equal(Object.isFrozen(services.api), true);
  assert.equal(frontendServices.useFrontendServices(services).notify, noop);
  assert.throws(
    () => frontendServices.createFrontendServices({ api: {}, dom: {}, feedback: {}, descriptors: {} }),
    /require raw/,
  );
  assert.throws(() => frontendServices.useFrontendServices({}), /shared frontend services contract/);
});

test('app.js remains a feature composition root', () => {
  const path = fileURLToPath(new URL('../../web/app.js', import.meta.url));
  const source = readFileSync(path, 'utf8');
  assert.ok(source.split('\n').length <= 919, 'app.js exceeded the composition-root size ceiling');
  for (const factory of [
    'createMusicFilesFeature',
    'createDjLibraryFeature',
    'createSetBuilderFeature',
    'createSettingsFeature',
    'createReportingFeature',
  ]) {
    assert.match(source, new RegExp(`${factory}\\(`));
  }
  for (const extracted of [
    'function loadDownloadedLibrary(',
    'function loadLibrary()',
    'function loadReports()',
    'function loadImportFailures()',
    'function retryImportFailures(',
    'function runBackgroundTask(',
    'function pollAuthorizedImport(',
    'async function matchSpotifySource(',
    'async function inspectSoundCloudSource(',
    'new AuthorizedImportQueue(',
    'function stageLocalAudio(',
    'function pollLocalAudioImport(',
    'function renderSpotifyMatches(',
    'function pollCreativeCommonsBatch(',
    'function pollSpotifyMatches(',
    'function renderCandidates(',
    'function initializeInsertionWaveform(',
    'function initializeCustomWaveform(',
    'function previewArrangementInsertion(',
    "$('#settings-form').addEventListener",
  ]) {
    assert.equal(source.includes(extracted), false, `${extracted} belongs in its feature module`);
  }
});

test('stylesheet entry point preserves explicit owner order without dead audit selectors', () => {
  const entryPath = fileURLToPath(new URL('../../web/styles.css', import.meta.url));
  const entry = readFileSync(entryPath, 'utf8');
  const imports = [...entry.matchAll(/@import url\(['"]\.\/styles\/([^'"]+)['"]\);/g)].map((match) => match[1]);
  assert.deepEqual(imports, [
    '00-base-shell.css',
    '10-shared-collections.css',
    '20-processing-media.css',
    '21-shared-secondary-actions.css',
    '30-library-reporting.css',
    '22-processing-detail.css',
    '23-processing-primary-actions.css',
    '40-settings-foundations.css',
    '24-processing-status.css',
    '50-music-files-workflows.css',
    '60-set-builder-brief.css',
    '70-reporting-analysis.css',
    '61-set-builder-workspace.css',
    '41-settings-secondary.css',
    '51-music-files-rows.css',
    '52-music-files-filters.css',
    '80-shared-interactions.css',
    '81-shared-components.css',
    '82-shared-action-hierarchy.css',
  ]);
  const source = imports
    .map((name) => readFileSync(fileURLToPath(new URL(`../../web/styles/${name}`, import.meta.url)), 'utf8'))
    .join('\n');
  for (const selector of [
    'downloaded-bulk-identity',
    'downloaded-duration',
    'downloaded-group',
    'import-boundary',
    'import-guidance',
    'import-layout',
    'inspector-identity',
    'library-bulk-identity',
    'optional-metric',
    'performance-diagnostics-head',
    'preset-manager-head',
    'set-identity-editor-actions',
    'status-danger,',
    'status-info,',
    'status-success,',
    'status-warning,',
    'track-quality',
  ]) {
    assert.equal(source.includes(selector), false, `${selector} was confirmed unused by ARCH-013A`);
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

test('identity editor renders saved values and safe single/bulk operations', () => {
  const descriptors = [
    { category: 'cultural', value: 'indian / south asian', provenance: 'manual', confidence: 1 },
    { category: 'role', value: 'party-ready', provenance: 'inferred', confidence: 0.78 },
  ];
  const summary = shared.descriptorChipsMarkup(descriptors, { detailed: true });
  const single = shared.descriptorEditorMarkup(descriptors, { protectedFromInference: true });
  const bulk = shared.descriptorEditorMarkup(descriptors, { bulk: true });
  assert.match(summary, /2 saved descriptors/);
  assert.match(summary, /indian \/ south asian/);
  assert.match(single, /value="indian \/ south asian"/);
  assert.match(single, /Manually tagged—do not infer/);
  assert.doesNotMatch(single, /descriptor-operation/);
  assert.match(bulk, /value="add" checked/);
  assert.match(bulk, /value="remove"/);
  assert.match(bulk, /value="replace"/);
});

test('Set Builder creates isolated mutable state', () => {
  const left = setBuilder.createSetBuilderState();
  const right = setBuilder.createSetBuilderState();
  left.requiredIds.add('track-a');
  assert.equal(right.requiredIds.size, 0);
  assert.equal(setBuilder.setTrackId({ source_name: 'Track.WAV' }), 'track.wav');
  assert.equal(setBuilder.setCatalogTrackId({ _downloadedId: 42 }), 'downloaded:42');
  assert.equal(setBuilder.setCatalogTrackId({ _job: { id: 7 } }), 'job:7');
});

test('Set Builder reports provider availability and validates editable journey duration', () => {
  assert.deepEqual(
    setBuilder.SET_PROPOSAL_STRATEGIES.map((item) => item.label),
    ['Safe Flow', 'Energy Journey', 'Adventurous Mix'],
  );
  assert.deepEqual(setBuilder.intentionProviderView({ available: true, provider: 'ollama', model: 'qwen3.5:4b' }), {
    className: 'set-provider-status ready',
    text: 'Local AI ready · qwen3.5:4b',
    title: 'Ollama is answering with qwen3.5:4b.',
  });
  assert.equal(setBuilder.intentionProviderView({ available: false }).text, 'Offline rules · Ollama unavailable');
  assert.deepEqual(
    setBuilder.journeyDurationStatus([{ durationPercent: 30 }, { durationPercent: 40 }, { durationPercent: 30 }], 60),
    {
      total: 100,
      valid: true,
      text: '3 sections · 100% of 60 minutes · edits drive track placement',
    },
  );
  assert.equal(setBuilder.journeyDurationStatus([{ durationPercent: 65 }], 45).valid, false);
});

test('Set Builder converts exact percentages into track allocations', () => {
  assert.deepEqual(
    setBuilder.genreAllocationTargets(
      ['Latin / Cumbia', 'Latin / Salsa', 'Latin / Dembow', 'Electronic / House / Latin House'],
      {
        'Latin / Cumbia': 25,
        'Latin / Salsa': 25,
        'Latin / Dembow': 25,
        'Electronic / House / Latin House': 25,
      },
      16,
    ),
    {
      'Latin / Cumbia': 4,
      'Latin / Salsa': 4,
      'Latin / Dembow': 4,
      'Electronic / House / Latin House': 4,
    },
  );
  assert.deepEqual(setBuilder.genreAllocationTargets(['A', 'B', 'C'], { A: 33, B: 33, C: 34 }, 10), {
    A: 3,
    B: 3,
    C: 4,
  });
});

test('Set Builder interprets an intention into editable deterministic preferences', () => {
  const result = setBuilder.interpretSetIntention(
    'Build a driving Latin electronic set with a Techno foundation. Favor Spanish vocals, dembow or Latin percussion for an Ecuadorian party crowd. Avoid generic instrumental Techno.',
  );
  assert.equal(result.drift, 'moderate');
  assert.ok(result.preferred.includes('techno foundation'));
  assert.ok(result.preferred.includes('spanish vocals'));
  assert.ok(result.preferred.includes('dembow'));
  assert.ok(result.preferred.includes('ecuadorian party'));
  assert.deepEqual(result.avoided, ['generic instrumental techno']);
  assert.equal(result.fallbackPolicy.length, 5);
});

test('Set Builder derives identity separately from catalog genre', () => {
  const tags = setBuilder.inferredTrackIdentity(
    {
      source_name: 'Cumbia Anthem (Techno Edit).wav',
      _genre: 'Electronic / Techno',
      _detailedGenre: 'Latin Techno',
    },
    ['Ecuadorian Party'],
  );
  assert.ok(tags.includes('techno foundation'));
  assert.ok(tags.includes('latin identity'));
  assert.ok(tags.includes('recognizable material'));
  assert.ok(tags.includes('ecuadorian party'));
});

test('Set Builder keeps a mixed chill party brief instead of dropping adjacent genres and context', () => {
  const result = setBuilder.interpretSetIntention(
    'Build a latin reggaeton and dembow mix that also includes some rab/rap, hip hop for a chill party, kickback. Some dancing will take place as well. Add something melodic in the beginning.',
  );
  for (const term of ['dembow', 'reggaeton', 'r&b', 'rap', 'hip hop', 'chill kickback', 'dance-friendly'])
    assert.ok(result.preferred.includes(term), term);
  assert.equal(result.vibe, 'balanced');
  assert.equal(result.opening, 'melodic');
  assert.deepEqual(result.requestedGenres, ['reggaeton', 'dembow', 'r&b', 'hip hop', 'rap']);
  assert.deepEqual(result.avoided, []);
});

test('Set Builder keeps Latin Techno, Latin House, and available Schranz distinct from generic Latin genres', () => {
  const result = setBuilder.interpretSetIntention(
    'We need a latin techno, latin house set that combines a bit of schranz if we have any. Start with something melodic to warm up and have varying waves',
    ['Latin Techno', 'Latin House', 'Schranz', 'Bachata', 'Reggaeton'],
  );
  assert.deepEqual(result.requestedGenres, ['latin techno', 'latin house', 'schranz']);
  assert.equal(result.opening, 'melodic');
  assert.equal(result.vibe, 'warm-up');
  assert.equal(result.curve, 'waves');
  assert.equal(
    setBuilder.trackMatchesIntendedGenre(
      { _genre: 'Electronic / Techno', _detailedGenre: 'Latin Techno' },
      'latin techno',
    ),
    true,
  );
  assert.equal(
    setBuilder.trackMatchesIntendedGenre({ _genre: 'Latin / Bachata', _detailedGenre: 'Bachata' }, 'latin techno'),
    false,
  );
  assert.equal(
    setBuilder.trackMatchesIntendedGenre({ _genre: 'Latin / Reggaeton', _detailedGenre: 'Reggaeton' }, 'latin house'),
    false,
  );
});

test('Set Builder preserves a multi-section Latin party journey in performance order', () => {
  const result = setBuilder.interpretSetIntention(
    'Start with melodic Latin songs. From there add cumbia and merengue. Then bachata and salsa. End with Latin Techno and Schranz.',
    ['Cumbia', 'Merengue', 'Bachata', 'Salsa', 'Latin Techno', 'Schranz'],
  );
  assert.deepEqual(result.genreSequence, ['cumbia', 'merengue', 'bachata', 'salsa', 'latin techno', 'schranz']);
  assert.equal(result.opening, 'melodic');
  assert.equal(setBuilder.intendedGenreForPosition(result, 0, 12), 'cumbia');
  assert.equal(setBuilder.intendedGenreForPosition(result, 5, 12), 'bachata');
  assert.equal(setBuilder.intendedGenreForPosition(result, 11, 12), 'schranz');
});

test('Set Builder follows editable journey sections for genre and energy placement', () => {
  const identity = {
    journey: {
      sections: [
        { durationPercent: 30, genres: ['cumbia'], energyStart: 3, energyEnd: 4 },
        { durationPercent: 40, genres: ['salsa'], energyStart: 5, energyEnd: 7 },
        { durationPercent: 30, genres: ['latin techno'], energyStart: 7, energyEnd: 9 },
      ],
    },
  };
  assert.equal(setBuilder.intendedGenreForPosition(identity, 0, 10), 'cumbia');
  assert.equal(setBuilder.intendedGenreForPosition(identity, 4, 10), 'salsa');
  assert.equal(setBuilder.intendedGenreForPosition(identity, 9, 10), 'latin techno');
  assert.ok(setBuilder.targetSetEnergy(9, 10, { identity, vibe: 'balanced', curve: 'steady' }) > 0.8);
});

test('Set Builder recognizes future catalog vocabulary without another hard-coded parser rule', () => {
  const result = setBuilder.interpretSetIntention('Start with jersey club, then bridge into something unfamiliar.', [
    'Jersey Club',
    'Future Genre Not Requested',
  ]);
  assert.ok(result.preferred.includes('jersey club'));
  assert.ok(!result.preferred.includes('future genre not requested'));
});

test('Settings controller preserves startup ordering', async () => {
  const calls = [];
  const controller = settings.createSettingsController({
    loadConfig: async () => {
      calls.push('config');
    },
    loadPresets: async () => {
      calls.push('presets');
    },
    loadLibraryStatus: () => {
      calls.push('status');
    },
    loadRelocationState: () => {
      calls.push('relocation');
    },
  });
  await controller.initialize(() => calls.push('ready'));
  assert.deepEqual(calls, ['config', 'status', 'relocation', 'ready']);
});

test('library reconnect hides offline state and clears stale errors', () => {
  assert.deepEqual(settings.libraryAvailabilityView({ online: false, offline_tracks: 4 }), {
    online: false,
    bannerHidden: false,
    clearStaleErrors: false,
    label: 'Library offline',
  });
  assert.deepEqual(settings.libraryAvailabilityView({ online: true, offline_tracks: 0 }), {
    online: true,
    bannerHidden: true,
    clearStaleErrors: true,
    label: 'Library online',
  });
});

test('library availability keeps verify disabled until the drive is connected', () => {
  assert.equal(settings.libraryAvailabilityView({ online: false }).online, false);
  assert.equal(settings.libraryAvailabilityView({ online: true, offline_tracks: 2 }).clearStaleErrors, false);
  assert.equal(settings.libraryAvailabilityView({ online: true, offline_tracks: 0 }).clearStaleErrors, true);
});

test('focused search keeps every character while an older response renders', () => {
  const input = { value: 'abcdef' };
  const state = { search: 'abc' };
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
    requested: { summary: 'Save settings' },
    changed: { summary: 'Changed 2 settings' },
    written_to: ['/tmp/settings.sqlite3'],
    failures: [],
    survives_restart: true,
    durability: 'Stored in SQLite.',
  });
  assert.match(text, /Requested: Save settings/);
  assert.match(text, /Changed: Changed 2 settings/);
  assert.match(text, /Written to: \/tmp\/settings.sqlite3/);
  assert.match(text, /Failed: 0/);
  assert.match(text, /Survives restart: Yes/);
});

test('shared request controller resets pagination when filters change', () => {
  const state = { search: '', page: 7 };
  const controller = requests.createRequestStateController({
    namespace: 'test',
    state,
    defaults: { search: '', page: 1 },
    storage: { getItem: () => null, setItem: () => {} },
    location: null,
    history: null,
  });
  controller.update({ search: 'all characters 123' });
  assert.deepEqual(state, { search: 'all characters 123', page: 1 });
});

test('verified BPM overrides reanalysis while preserving detected evidence', () => {
  const result = reporting.applyReportVerifications(
    [{ source_name: 'Track.wav', bpm: 132, key: 'C major', key_confidence: 0.8 }],
    [],
    { items: [] },
    { items: [{ source_name: 'track.wav', verified_bpm: 126.25, detected_bpm: 124 }] },
  );
  assert.equal(result[0].bpm, 126.25);
  assert.equal(result[0].detected_bpm, 132);
  assert.equal(result[0].bpm_verified, true);
});
