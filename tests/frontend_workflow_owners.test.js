import test from 'node:test';
import assert from 'node:assert/strict';

import { createBackgroundTaskController } from '../web/background-task-controller.js';
import { importFailureKind } from '../web/import-issues.js';
import { createLocalAudioImportFeature } from '../web/local-audio-import.js';
import { creativeCommonsTracks } from '../web/playlist-import.js';
import {
  authorizedSourceUrls,
  createAuthorizedImportFeature,
  createImportWorkspaceApi,
  sourceUrlType,
} from '../web/import-workspace.js';

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
    services: { $: (selector) => elements.get(selector) },
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
    services: { $: (selector) => elements.get(selector) },
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
