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

test('identity editing keeps saved single-track values and opens without page relocation', () => {
  const musicPath = fileURLToPath(new URL('../web/music-files.js', import.meta.url));
  const libraryPath = fileURLToPath(new URL('../web/dj-library.js', import.meta.url));
  const sharedPath = fileURLToPath(new URL('../web/shared-components.js', import.meta.url));
  const musicSource = readFileSync(musicPath, 'utf8');
  const librarySource = readFileSync(libraryPath, 'utf8');
  const sharedSource = readFileSync(sharedPath, 'utf8');
  assert.match(sharedSource, /export function openDescriptorEditorDialog/);
  assert.match(sharedSource, /descriptorChipsMarkup\(descriptors,\{detailed:true\}\)/);
  assert.match(musicSource, /descriptors:single\?\(selected\[0\]\.descriptors\|\|\[\]\)/);
  assert.match(librarySource, /currentTrack=single\?visibleDownloadedTracks\.find\(track=>Number\(track\.id\)===trackIds\[0\]\):null,saved=currentTrack\?\.descriptors/);
  assert.equal(musicSource.includes("document.querySelector('.downloaded-selection').after(panel)"), false);
  assert.equal(librarySource.includes("document.querySelector('.library-selection').after(panel)"), false);
  assert.match(sharedSource, /type="radio" name="descriptor-mode" value="add" checked/);
  assert.match(sharedSource, /querySelector\('\.descriptor-mode:checked'\)/);
  assert.match(musicSource, /inspector-edit-identity">Musical identity/);
  assert.equal(musicSource.includes("identitySection.className='inspector-identity'"), false);
  assert.match(musicSource, /nextButton\.textContent='Save & next →'/);
  assert.match(musicSource, /previousButton\.textContent='← Save & previous'/);
  assert.match(musicSource, /if\(offset\)openIdentityEditor\(targetIndex\+offset\)/);
  assert.match(musicSource, /downloadedSelection\.set\(Number\(target\.id\),target\)/);
  assert.match(librarySource, /targetBox\.checked=true;refreshSelection\(\);identityButton\.onclick\(\)/);
});

test('confirmation action labels remain legible for every tone', () => {
  const stylesPath = fileURLToPath(new URL('../web/styles.css', import.meta.url));
  const styles = readFileSync(stylesPath, 'utf8');
  assert.match(styles, /\.app-dialog footer button\[data-tone="success"\]\s*\{[^}]*color:#11140a;[^}]*background:var\(--lime\)/);
  assert.match(styles, /\.app-dialog footer button\[data-tone="danger"\]\s*\{[^}]*color:#22100f;[^}]*background:var\(--status-danger\)/);
});

test('Music Files exposes a guarded identity vocabulary review workflow', () => {
  const musicPath = fileURLToPath(new URL('../web/music-files.js', import.meta.url));
  const indexPath = fileURLToPath(new URL('../web/index.html', import.meta.url));
  const musicSource = readFileSync(musicPath, 'utf8');
  const indexSource = readFileSync(indexPath, 'utf8');
  assert.match(indexSource, /id="downloaded-vocabulary-review"/);
  assert.match(indexSource, /id="identity-vocabulary-dialog"/);
  assert.match(musicSource, /\/api\/downloaded-library\/descriptors\/vocabulary/);
  assert.match(musicSource, /No suggestion changes tracks until you approve|Vocabulary rule could not be saved/);
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

test('DJ Library extraction keeps runtime actions and cross-page navigation wired', () => {
  const modulePath = fileURLToPath(new URL('../web/dj-library.js', import.meta.url));
  const appPath = fileURLToPath(new URL('../web/app.js', import.meta.url));
  const source = readFileSync(modulePath, 'utf8');
  const appSource = readFileSync(appPath, 'utf8');
  const signature = source.slice(source.indexOf('createDjLibraryFeature({'), source.indexOf('}) {', source.indexOf('createDjLibraryFeature({')));
  assert.match(signature, /jobAction/);
  assert.match(signature, /jobElement/);
  assert.match(appSource, /jobAction: \(\.\.\.args\) => jobAction\(\.\.\.args\)/);
  assert.match(appSource, /jobElement: \(\.\.\.args\) => jobElement\(\.\.\.args\)/);
  assert.match(appSource, /hasExtendedAudio \? fetch\(`\/api\/jobs\/\$\{job\.id\}\/waveform\/extended`/);
  assert.match(source, /async function revealLibraryTrack/);
  assert.match(source, /libraryRequestState\.update\(\{search:/);
  assert.match(source, /data-closed-label/);
  assert.match(source, /Survives restart: Yes/);
});

test('Set Builder creates isolated mutable state', () => {
  const left = setBuilder.createSetBuilderState();
  const right = setBuilder.createSetBuilderState();
  left.requiredIds.add('track-a');
  assert.equal(right.requiredIds.size, 0);
  assert.equal(setBuilder.setTrackId({source_name:'Track.WAV'}), 'track.wav');
  assert.equal(setBuilder.setCatalogTrackId({_downloadedId:42}), 'downloaded:42');
  assert.equal(setBuilder.setCatalogTrackId({_job:{id:7}}), 'job:7');
});

test('Set Builder exposes explicit safe planning modes and cancellation', () => {
  const indexPath = fileURLToPath(new URL('../web/index.html', import.meta.url));
  const modulePath = fileURLToPath(new URL('../web/set-builder.js', import.meta.url));
  const indexSource = readFileSync(indexPath, 'utf8');
  const moduleSource = readFileSync(modulePath, 'utf8');
  assert.match(indexSource, /AI Planned · chooses and orders tracks/);
  assert.match(indexSource, /AI Interpreted · rules choose tracks/);
  assert.match(indexSource, /Classic · rules only/);
  assert.match(indexSource, /id="set-cancel-planning"/);
  assert.match(moduleSource, /await generateAITrackPlan\(\)/);
  assert.match(moduleSource, /await generateDeterministicSetPlan\(\)/);
  assert.match(moduleSource, /track\._aiSelectionReason=item\.selectionReason/);
  assert.match(moduleSource, /planningReceipt:currentPlanningReceipt/);
  assert.match(moduleSource, /currentPlanningReceipt=record\.planningReceipt\|\|null/);
  assert.match(moduleSource, /evaluation\?\.disclosures/);
  assert.match(moduleSource, /comparison\.deterministic\?\.qualityScore/);
  assert.match(moduleSource, /modelRepairs:result\.modelRepairs\|\|\[\]/);
  assert.match(moduleSource, /currentPlanningReceipt\?\.warnings/);
});

test('Set Builder converts exact percentages into track allocations', () => {
  assert.deepEqual(setBuilder.genreAllocationTargets(
    ['Latin / Cumbia', 'Latin / Salsa', 'Latin / Dembow', 'Electronic / House / Latin House'],
    {
      'Latin / Cumbia': 25,
      'Latin / Salsa': 25,
      'Latin / Dembow': 25,
      'Electronic / House / Latin House': 25,
    },
    16,
  ), {
    'Latin / Cumbia': 4,
    'Latin / Salsa': 4,
    'Latin / Dembow': 4,
    'Electronic / House / Latin House': 4,
  });
  assert.deepEqual(
    setBuilder.genreAllocationTargets(['A', 'B', 'C'], {A:33, B:33, C:34}, 10),
    {A:3, B:3, C:4},
  );
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
  const tags = setBuilder.inferredTrackIdentity({
    source_name: 'Cumbia Anthem (Techno Edit).wav',
    _genre: 'Electronic / Techno',
    _detailedGenre: 'Latin Techno',
  }, ['Ecuadorian Party']);
  assert.ok(tags.includes('techno foundation'));
  assert.ok(tags.includes('latin identity'));
  assert.ok(tags.includes('recognizable material'));
  assert.ok(tags.includes('ecuadorian party'));
});

test('Set Builder keeps a mixed chill party brief instead of dropping adjacent genres and context', () => {
  const result=setBuilder.interpretSetIntention(
    'Build a latin reggaeton and dembow mix that also includes some rab/rap, hip hop for a chill party, kickback. Some dancing will take place as well. Add something melodic in the beginning.',
  );
  for(const term of ['dembow','reggaeton','r&b','rap','hip hop','chill kickback','dance-friendly'])assert.ok(result.preferred.includes(term),term);
  assert.equal(result.vibe,'balanced');
  assert.equal(result.opening,'melodic');
  assert.deepEqual(result.requestedGenres,['reggaeton','dembow','r&b','hip hop','rap']);
  assert.deepEqual(result.avoided,[]);
});

test('Set Builder keeps Latin Techno, Latin House, and available Schranz distinct from generic Latin genres', () => {
  const result=setBuilder.interpretSetIntention(
    'We need a latin techno, latin house set that combines a bit of schranz if we have any. Start with something melodic to warm up and have varying waves',
    ['Latin Techno','Latin House','Schranz','Bachata','Reggaeton'],
  );
  assert.deepEqual(result.requestedGenres,['latin techno','latin house','schranz']);
  assert.equal(result.opening,'melodic');
  assert.equal(result.vibe,'warm-up');
  assert.equal(result.curve,'waves');
  assert.equal(setBuilder.trackMatchesIntendedGenre({_genre:'Electronic / Techno',_detailedGenre:'Latin Techno'},'latin techno'),true);
  assert.equal(setBuilder.trackMatchesIntendedGenre({_genre:'Latin / Bachata',_detailedGenre:'Bachata'},'latin techno'),false);
  assert.equal(setBuilder.trackMatchesIntendedGenre({_genre:'Latin / Reggaeton',_detailedGenre:'Reggaeton'},'latin house'),false);
});

test('Set Builder preserves a multi-section Latin party journey in performance order', () => {
  const result=setBuilder.interpretSetIntention(
    'Start with melodic Latin songs. From there add cumbia and merengue. Then bachata and salsa. End with Latin Techno and Schranz.',
    ['Cumbia','Merengue','Bachata','Salsa','Latin Techno','Schranz'],
  );
  assert.deepEqual(result.genreSequence,['cumbia','merengue','bachata','salsa','latin techno','schranz']);
  assert.equal(result.opening,'melodic');
  assert.equal(setBuilder.intendedGenreForPosition(result,0,12),'cumbia');
  assert.equal(setBuilder.intendedGenreForPosition(result,5,12),'bachata');
  assert.equal(setBuilder.intendedGenreForPosition(result,11,12),'schranz');
});

test('Set Builder follows editable journey sections for genre and energy placement', () => {
  const identity={journey:{sections:[
    {durationPercent:30,genres:['cumbia'],energyStart:3,energyEnd:4},
    {durationPercent:40,genres:['salsa'],energyStart:5,energyEnd:7},
    {durationPercent:30,genres:['latin techno'],energyStart:7,energyEnd:9},
  ]}};
  assert.equal(setBuilder.intendedGenreForPosition(identity,0,10),'cumbia');
  assert.equal(setBuilder.intendedGenreForPosition(identity,4,10),'salsa');
  assert.equal(setBuilder.intendedGenreForPosition(identity,9,10),'latin techno');
  assert.ok(setBuilder.targetSetEnergy(9,10,{identity,vibe:'balanced',curve:'steady'})>.8);
});

test('Set Builder recognizes future catalog vocabulary without another hard-coded parser rule', () => {
  const result=setBuilder.interpretSetIntention(
    'Start with jersey club, then bridge into something unfamiliar.',
    ['Jersey Club','Future Genre Not Requested'],
  );
  assert.ok(result.preferred.includes('jersey club'));
  assert.ok(!result.preferred.includes('future genre not requested'));
});

test('Set Builder converts exact percentages into track allocations', () => {
  assert.deepEqual(setBuilder.genreAllocationTargets(
    ['Latin / Cumbia', 'Latin / Salsa', 'Latin / Dembow', 'Electronic / House / Latin House'],
    {
      'Latin / Cumbia': 25,
      'Latin / Salsa': 25,
      'Latin / Dembow': 25,
      'Electronic / House / Latin House': 25,
    },
    16,
  ), {
    'Latin / Cumbia': 4,
    'Latin / Salsa': 4,
    'Latin / Dembow': 4,
    'Electronic / House / Latin House': 4,
  });
  assert.deepEqual(
    setBuilder.genreAllocationTargets(['A', 'B', 'C'], {A:33, B:33, C:34}, 10),
    {A:3, B:3, C:4},
  );
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
  const tags = setBuilder.inferredTrackIdentity({
    source_name: 'Cumbia Anthem (Techno Edit).wav',
    _genre: 'Electronic / Techno',
    _detailedGenre: 'Latin Techno',
  }, ['Ecuadorian Party']);
  assert.ok(tags.includes('techno foundation'));
  assert.ok(tags.includes('latin identity'));
  assert.ok(tags.includes('recognizable material'));
  assert.ok(tags.includes('ecuadorian party'));
});

test('Set Builder keeps a mixed chill party brief instead of dropping adjacent genres and context', () => {
  const result=setBuilder.interpretSetIntention(
    'Build a latin reggaeton and dembow mix that also includes some rab/rap, hip hop for a chill party, kickback. Some dancing will take place as well. Add something melodic in the beginning.',
  );
  for(const term of ['dembow','reggaeton','r&b','rap','hip hop','chill kickback','dance-friendly'])assert.ok(result.preferred.includes(term),term);
  assert.equal(result.vibe,'balanced');
  assert.equal(result.opening,'melodic');
  assert.deepEqual(result.requestedGenres,['reggaeton','dembow','r&b','hip hop','rap']);
  assert.deepEqual(result.avoided,[]);
});

test('Set Builder keeps Latin Techno, Latin House, and available Schranz distinct from generic Latin genres', () => {
  const result=setBuilder.interpretSetIntention(
    'We need a latin techno, latin house set that combines a bit of schranz if we have any. Start with something melodic to warm up and have varying waves',
    ['Latin Techno','Latin House','Schranz','Bachata','Reggaeton'],
  );
  assert.deepEqual(result.requestedGenres,['latin techno','latin house','schranz']);
  assert.equal(result.opening,'melodic');
  assert.equal(result.vibe,'warm-up');
  assert.equal(result.curve,'waves');
  assert.equal(setBuilder.trackMatchesIntendedGenre({_genre:'Electronic / Techno',_detailedGenre:'Latin Techno'},'latin techno'),true);
  assert.equal(setBuilder.trackMatchesIntendedGenre({_genre:'Latin / Bachata',_detailedGenre:'Bachata'},'latin techno'),false);
  assert.equal(setBuilder.trackMatchesIntendedGenre({_genre:'Latin / Reggaeton',_detailedGenre:'Reggaeton'},'latin house'),false);
});

test('Set Builder preserves a multi-section Latin party journey in performance order', () => {
  const result=setBuilder.interpretSetIntention(
    'Start with melodic Latin songs. From there add cumbia and merengue. Then bachata and salsa. End with Latin Techno and Schranz.',
    ['Cumbia','Merengue','Bachata','Salsa','Latin Techno','Schranz'],
  );
  assert.deepEqual(result.genreSequence,['cumbia','merengue','bachata','salsa','latin techno','schranz']);
  assert.equal(result.opening,'melodic');
  assert.equal(setBuilder.intendedGenreForPosition(result,0,12),'cumbia');
  assert.equal(setBuilder.intendedGenreForPosition(result,5,12),'bachata');
  assert.equal(setBuilder.intendedGenreForPosition(result,11,12),'schranz');
});

test('Set Builder recognizes future catalog vocabulary without another hard-coded parser rule', () => {
  const result=setBuilder.interpretSetIntention(
    'Start with jersey club, then bridge into something unfamiliar.',
    ['Jersey Club','Future Genre Not Requested'],
  );
  assert.ok(result.preferred.includes('jersey club'));
  assert.ok(!result.preferred.includes('future genre not requested'));
});

test('Set Builder converts exact percentages into track allocations', () => {
  assert.deepEqual(setBuilder.genreAllocationTargets(
    ['Latin / Cumbia', 'Latin / Salsa', 'Latin / Dembow', 'Electronic / House / Latin House'],
    {
      'Latin / Cumbia': 25,
      'Latin / Salsa': 25,
      'Latin / Dembow': 25,
      'Electronic / House / Latin House': 25,
    },
    16,
  ), {
    'Latin / Cumbia': 4,
    'Latin / Salsa': 4,
    'Latin / Dembow': 4,
    'Electronic / House / Latin House': 4,
  });
  assert.deepEqual(
    setBuilder.genreAllocationTargets(['A', 'B', 'C'], {A:33, B:33, C:34}, 10),
    {A:3, B:3, C:4},
  );
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
  assert.match(source, /\/api\/set-builder\/intention-provider/);
  assert.match(source, /Local AI ready/);
  assert.match(source, /resultName\.addEventListener\('input'/);
  assert.match(source, /briefName\.value=resultName\.value/);
  assert.match(source, /function setSelectionExplanation/);
  assert.match(source, /Selected because it is a must-play track/);
  assert.match(source, /Compatible key:/);
  assert.match(source, /Moves from \$\{fromBpm\.toFixed\(1\)\} to \$\{toBpm\.toFixed\(1\)\} BPM/);
  assert.match(source, /Why this track/);
  assert.match(source, /Why this transition:/);
  assert.match(source, /input\.step='1'/);
  assert.match(source, /function renderSetSelectionSummary/);
  assert.match(source, /allocating the requested genre balance first/);
  assert.match(source, /function intentionEvaluation/);
  assert.match(source, /shortlistLimit=800/);
  assert.match(source, /attempts<10/);
  assert.match(source, /function openTrackIdentityEditor/);
  assert.match(source, /applyIntentionInterpretation/);
  assert.match(source, /\/api\/set-builder\/plan-journey/);
  assert.match(source, /function renderJourney/);
  assert.match(source, /Journey section durations total/);
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
