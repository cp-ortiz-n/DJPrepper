import test from 'node:test';
import assert from 'node:assert/strict';

import { createBackgroundTaskController } from '../web/background-task-controller.js';
import { createFrontendServices } from '../web/frontend-services.js';
import { importFailureKind } from '../web/import-issues.js';
import { createLocalAudioImportFeature } from '../web/local-audio-import.js';
import { creativeCommonsTracks } from '../web/playlist-import.js';
import { createCandidateReviewFeature, reviewableProcessingJobs } from '../web/candidate-review.js';
import {
  annotateProcessingJobs,
  categorizeProcessingJobs,
  createProcessingWorkspaceApi,
  createProcessingWorkspaceController,
  sortProcessingJobs,
} from '../web/processing-workspace.js';
import {
  createProcessingWorkspaceView,
  processingJobSignature,
  processingJobViewModel,
} from '../web/processing-workspace-view.js';
import {
  authorizedSourceUrls,
  createAuthorizedImportFeature,
  createImportWorkspaceApi,
  sourceUrlType,
} from '../web/import-workspace.js';

function frontendServicesFor(select) {
  return createFrontendServices({
    api: { raw() {}, request() {}, errorMessage() {} },
    dom: { $: select, $$: () => [] },
    feedback: { notify() {}, confirmAction() {}, operationReceiptText() {} },
    descriptors: {
      chipsMarkup() {},
      editorMarkup() {},
      openEditorDialog() {},
      saveEditor() {},
      inferEditor() {},
    },
  });
}

test('processing workspace derives generations, ETA, and durable queue groups', () => {
  const jobs = [
    {
      id: 5,
      source_name: 'Same.wav',
      status: 'processing',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:01:00Z',
    },
    {
      id: 4,
      source_name: 'Other.wav',
      status: 'queued',
      queue_index: 1,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
    {
      id: 3,
      source_name: 'Same.wav',
      status: 'complete',
      review_status: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:02:00Z',
    },
    {
      id: 2,
      source_name: 'Review.wav',
      status: 'complete',
      review_status: 'pending',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:02:00Z',
    },
    {
      id: 1,
      source_name: 'Same.wav',
      status: 'complete',
      review_status: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:02:00Z',
    },
    {
      id: 0,
      source_name: 'Finished.wav',
      status: 'complete',
      review_status: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:02:00Z',
    },
  ];
  annotateProcessingJobs(jobs);
  assert.equal(jobs[0]._generation, 3);
  assert.equal(jobs[2]._generation, 2);
  assert.equal(jobs[1]._eta, '~2 min');
  const groups = categorizeProcessingJobs(jobs);
  assert.deepEqual(
    groups.active.map((job) => job.id),
    [5, 4],
  );
  assert.deepEqual(
    groups.attention.map((job) => job.id),
    [2],
  );
  assert.deepEqual(
    groups.history.map((job) => job.id),
    [0],
  );
  assert.deepEqual(
    sortProcessingJobs(groups.active).map((job) => job.id),
    [5, 4],
  );
});

test('processing workspace API owns queue and candidate-review routes', async () => {
  const calls = [];
  const client = {
    get: async (path, options) => {
      calls.push(['get', path, options]);
      return [];
    },
    post: async (path, body) => {
      calls.push(['post', path, body]);
      return {};
    },
    request: async (path, options) => {
      calls.push(['request', path, options]);
      return {};
    },
  };
  const api = createProcessingWorkspaceApi(client);
  await api.list();
  await api.action(9, 'pause');
  await api.reorder([9, 4]);
  await api.saveFeedback(9, { accepted: true });
  await api.rejectReview(9);
  await api.waveform(9, 'extended');
  await api.transitionScore(9, { destination: 32 });
  assert.deepEqual(calls, [
    ['get', '/api/jobs', { cache: 'no-store' }],
    ['post', '/api/jobs/9/pause', undefined],
    ['post', '/api/jobs/reorder', { job_ids: [9, 4] }],
    ['post', '/api/jobs/9/feedback', { accepted: true }],
    ['post', '/api/jobs/9/review/reject', undefined],
    ['get', '/api/jobs/9/waveform/extended', undefined],
    ['post', '/api/jobs/9/transition-score', { destination: 32 }],
  ]);
});

test('candidate review feature selects only valid completed review jobs', () => {
  const jobs = [
    { id: 1, status: 'complete', review_status: 'pending', config_json: '{"review_candidates":true}' },
    { id: 2, status: 'complete', review_status: 'pending', config_json: '{"review_candidates":false}' },
    { id: 3, status: 'processing', review_status: 'pending', config_json: '{"review_candidates":true}' },
    { id: 4, status: 'complete', review_status: 'pending', config_json: '{broken' },
  ];
  assert.deepEqual(
    reviewableProcessingJobs(jobs).map((job) => job.id),
    [1],
  );
});

test('processing and candidate views consume the shared frontend services contract', () => {
  const services = Object.freeze({
    api: Object.freeze({}),
    dom: Object.freeze({ $: () => null, $$: () => [] }),
    feedback: Object.freeze({ notify() {}, confirmAction: async () => true }),
    descriptors: Object.freeze({}),
  });
  const processingView = createProcessingWorkspaceView({
    services,
    template: {},
    jobsRoot: {},
    action() {},
    remove() {},
    move() {},
    hydrate() {},
    showView() {},
    loadLibrary() {},
  });
  const review = createCandidateReviewFeature({
    services,
    processingWorkspaceApi: {},
    annotateJobs: (jobs) => jobs,
    decodedAudio() {},
    renderArrangementTimeline() {},
    WaveSurfer: {},
    RegionsPlugin: {},
    TimelinePlugin: {},
    jobAction() {},
    loadJobs() {},
    showView() {},
  });
  assert.equal(typeof processingView.render, 'function');
  assert.equal(typeof review.load, 'function');
});

test('processing workspace controller deduplicates loads and renders selected groups', async () => {
  let resolveList;
  let listCalls = 0;
  const workspaceApi = {
    list: () => {
      listCalls += 1;
      return new Promise((resolve) => {
        resolveList = resolve;
      });
    },
  };
  const renders = [];
  const timers = [];
  const controller = createProcessingWorkspaceController({
    workspaceApi,
    render: (state) => renders.push(state),
    clock: {
      setTimeout: (callback) => {
        timers.push(callback);
        return timers.length;
      },
      clearTimeout() {},
    },
    documentRef: { hidden: false },
  });
  const first = controller.load();
  const duplicate = controller.load();
  assert.equal(first, duplicate);
  resolveList([
    { id: 1, source_name: 'Track', status: 'complete', created_at: '2026-01-01', updated_at: '2026-01-02' },
  ]);
  await first;
  assert.equal(listCalls, 1);
  assert.equal(renders[0].filter, 'active');
  assert.deepEqual(renders[0].visible, []);
});

test('processing workspace view derives stable labels without mutating job data', () => {
  const job = {
    id: 8,
    status: 'complete',
    review_status: 'rejected',
    progress: 100,
    stage: 'Complete',
    preset: 'club',
    intro_bars: 16,
    outro_bars: 8,
    use_stems: true,
    _generation: 3,
    _eta: '~2 min',
    config_json: JSON.stringify({ intro_bars_auto: true }),
  };
  const view = processingJobViewModel(job);
  assert.equal(view.status, 'review dismissed');
  assert.equal(view.stage, 'Review dismissed · processed audio remains available in Library');
  assert.equal(view.reviewLabel, 'Reopen review');
  assert.equal(view.reprocessLabel, 'Process automatically');
  assert.match(view.meta, /auto intro · 8 bar outro · stems · generation 3 · ETA ~2 min/);
  assert.equal(job.config, undefined);
  assert.equal(
    processingJobSignature(job),
    JSON.stringify(['complete', 100, 'Complete', undefined, undefined, undefined, 'rejected', undefined]),
  );
});

test('processing workspace view reports long-running analysis without changing its status', () => {
  const now = Date.parse('2026-10-14T12:10:00Z');
  const view = processingJobViewModel(
    {
      status: 'processing',
      stage: 'Analyzing structure',
      created_at: '2026-10-14T12:00:00Z',
      preset: 'auto',
      intro_bars: 8,
      outro_bars: 8,
      progress: 40,
    },
    now,
  );
  assert.equal(view.status, 'processing');
  assert.equal(view.stage, 'Analyzing structure · long analysis, still working');
});

test('background task controller completes inactive work and releases ownership', async () => {
  let completeState = null;
  const controller = createBackgroundTaskController({
    loadJson: async () => ({ status: 'complete', changed: 3 }),
    schedule: (callback) => callback(),
    cancelSchedule: () => {},
  });

  controller.run({
    key: 'verify',
    url: '/status',
    complete: (state) => {
      completeState = state;
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.deepEqual(completeState, { status: 'complete', changed: 3 });
  assert.equal(controller.isRunning('verify'), false);
});

test('background task controller replaces and aborts work with the same key', async () => {
  let firstSignal;
  const controller = createBackgroundTaskController({
    loadJson: (_url, signal) => {
      firstSignal ||= signal;
      return new Promise(() => {});
    },
  });

  controller.run({ key: 'scan', url: '/first' });
  controller.run({ key: 'scan', url: '/second' });

  assert.equal(firstSignal.aborted, true);
  assert.equal(controller.isRunning('scan'), true);
  assert.equal(controller.stop('scan'), true);
  assert.equal(controller.isRunning('scan'), false);
});

test('import issue ownership maps technical failures to actionable labels', () => {
  assert.deepEqual(importFailureKind('Sign in to confirm your age'), ['Age-restricted source', 'Restricted']);
  assert.deepEqual(importFailureKind('HTTP 403 Forbidden'), ['Source blocked the download', 'Blocked']);
  assert.deepEqual(importFailureKind('No reliable YouTube match'), ['No reliable source match', 'No match']);
  assert.deepEqual(importFailureKind('connection reset'), ['Download could not complete', 'Failed']);
});

test('import workspace classifies sources and owns route serialization', async () => {
  assert.equal(sourceUrlType('https://youtu.be/example'), 'youtube');
  assert.equal(sourceUrlType('https://open.spotify.com/track/1'), 'spotify');
  assert.deepEqual(authorizedSourceUrls('https://youtu.be/a\nhttps://youtu.be/a'), ['https://youtu.be/a']);
  const calls = [];
  const api = {
    get: async (path) => {
      calls.push(['get', path]);
      return {};
    },
    post: async (path, body) => {
      calls.push(['post', path, body]);
      return {};
    },
    request: async (path, options) => {
      calls.push(['request', path, options.method]);
      return {};
    },
  };
  const client = createImportWorkspaceApi(api);
  await client.matchSource('https://youtu.be/a');
  await client.authorizedStatus('job-1');
  await client.startCreativeCommons([{ title: 'Track' }], 'Party');
  assert.deepEqual(calls, [
    ['post', '/api/imports/source-match', { url: 'https://youtu.be/a' }],
    ['get', '/api/imports/job-1'],
    ['post', '/api/imports/creative-commons', { tracks: [{ title: 'Track' }], playlist_name: 'Party' }],
  ]);
});

test('authorized import feature owns guidance, submission, and completion feedback', async () => {
  const elements = new Map();
  const element = (id, values = {}) => {
    const listeners = new Map();
    const node = {
      id,
      value: '',
      checked: false,
      disabled: false,
      hidden: false,
      textContent: '',
      innerHTML: '',
      addEventListener(type, listener) {
        listeners.set(type, listener);
      },
      listener(type) {
        return listeners.get(type);
      },
      focus() {},
      reset() {
        this.resetCalled = true;
      },
      ...values,
    };
    elements.set(`#${id}`, node);
    return node;
  };
  const source = element('authorized-url', { value: 'https://youtu.be/example' });
  const guidance = element('source-url-guidance');
  element('source-match-result');
  element('authorized-import-pause');
  element('authorized-import-retry');
  const form = element('authorized-import-form');
  const submit = element('authorized-import-submit');
  const message = element('authorized-import-message');
  element('rights-basis', { value: 'owned-recording' });
  element('rights-confirmation', { checked: true });
  element('process-import-with-extender', { checked: true });

  let queueOptions;
  let started;
  class Queue {
    constructor(options) {
      queueOptions = options;
    }
    async start(urls, payload, metadata) {
      started = { urls, payload, metadata };
    }
    togglePause() {}
    retryFailed() {}
  }
  const stopped = [];
  let jobsLoaded = 0;
  const feature = createAuthorizedImportFeature({
    services: frontendServicesFor((selector) => elements.get(selector)),
    importApi: { matchSource: async () => ({}), authorizedStatus: async () => ({ status: 'complete' }) },
    Queue,
    clock: String,
    loadJobs: async () => {
      jobsLoaded += 1;
    },
    stopTask: (key) => stopped.push(key),
    escapeHtml: String,
  });

  feature.bind();
  source.listener('input')({ target: source });
  assert.match(guidance.textContent, /YouTube source detected/);

  await form.listener('submit')({ preventDefault() {} });
  assert.deepEqual(stopped, ['authorized-import']);
  assert.equal(submit.disabled, true);
  assert.equal(message.textContent, 'Preparing 1 authorized source…');
  assert.deepEqual(started, {
    urls: ['https://youtu.be/example'],
    payload: {
      rights_basis: 'owned-recording',
      confirmation: true,
      process_with_extender: true,
    },
    metadata: { title: '', artist: '', spotify_uri: '', artwork_url: '' },
  });

  await queueOptions.onComplete({ items: [{ status: 'complete', importId: 'import-1' }] });
  assert.match(message.innerHTML, /\/api\/imports\/import-1\/download/);
  assert.equal(submit.disabled, false);
  assert.equal(form.resetCalled, true);
  assert.equal(jobsLoaded, 1);
});

test('local audio feature owns workspace import lifecycle and refresh', async () => {
  const elements = new Map([
    ['#workspace-import-submit', { disabled: false, textContent: '' }],
    ['#upload-message', { textContent: '' }],
  ]);
  let submitted;
  let task;
  let cleared = 0;
  let refreshed = 0;
  const feature = createLocalAudioImportFeature({
    services: frontendServicesFor((selector) => elements.get(selector)),
    importApi: {
      startLocal: async (data) => {
        submitted = data;
        return { batch_id: 'local-1', track_count: 2, playlist_name: 'Warmup' };
      },
      localStatus: async () => ({}),
    },
    runTask: (options) => {
      task = options;
    },
    stopTask() {},
    escapeHtml: String,
    showMusicFiles() {},
    clearWorkspaceFiles: () => {
      cleared += 1;
    },
    loadMusicFiles: async () => {
      refreshed += 1;
    },
  });
  const files = [
    Object.assign(new Blob(['one']), { name: 'one.mp3', lastModified: 1 }),
    Object.assign(new Blob(['two']), { name: 'two.wav', lastModified: 2 }),
  ];

  await feature.startWorkspace(files, 'Warmup');
  assert.deepEqual(
    submitted.getAll('files').map((file) => file.name),
    ['one.mp3', 'two.wav'],
  );
  assert.equal(submitted.get('playlist_name'), 'Warmup');
  assert.equal(task.key, 'workspace-local-import');
  assert.equal(elements.get('#upload-message').textContent, 'Converting 2 tracks from Warmup…');

  task.update({ stage: 'Converting', progress: 42 });
  assert.equal(elements.get('#upload-message').textContent, 'Converting · 42%');
  await task.complete({ status: 'complete', counts: { imported: 2, duplicates: 0, failed: 0 } });
  assert.equal(cleared, 1);
  assert.equal(refreshed, 1);
  assert.match(elements.get('#upload-message').textContent, /2 WAVs imported/);
});

test('playlist import sends only downloadable matches to Creative Commons verification', () => {
  assert.deepEqual(
    creativeCommonsTracks([
      { title: 'Ready', artist: 'DJ', youtube_url: 'https://youtu.be/ready', genre: 'House' },
      { title: 'Missing', artist: 'DJ', youtube_url: '' },
    ]),
    [
      {
        url: 'https://youtu.be/ready',
        title: 'Ready',
        artist: 'DJ',
        spotify_uri: '',
        genre: 'House',
        genre_category: 'Other',
        artwork_url: '',
      },
    ],
  );
});
