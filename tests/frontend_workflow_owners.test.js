import test from 'node:test';
import assert from 'node:assert/strict';

import { createBackgroundTaskController } from '../web/background-task-controller.js';
import { importFailureKind } from '../web/import-issues.js';
import { authorizedSourceUrls, createImportWorkspaceApi, sourceUrlType } from '../web/import-workspace.js';

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
