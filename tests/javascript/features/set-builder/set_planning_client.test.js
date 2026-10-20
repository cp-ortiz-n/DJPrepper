import test from 'node:test';
import assert from 'node:assert/strict';

import { SetPlanningCanceled, createSetPlanningClient } from '../../../../frontend/features/set-builder/planning-client.js';

function response(payload, ok = true) {
  return { ok, json: async () => payload };
}

test('planning client starts and waits for a completed validated plan', async () => {
  const calls = [];
  const states = [
    { status: 'processing', stage: 'Selecting tracks', progress: 55 },
    { status: 'complete', result: { mode: 'ai-planned', plan: [{ id: 'downloaded:1' }] } },
  ];
  const client = createSetPlanningClient({
    pollInterval: 0,
    fetchImpl: async (path, options = {}) => {
      calls.push({ path, options });
      if (options.method === 'POST') return response({ jobId: 'job-1' });
      return response(states.shift());
    },
  });
  const started = await client.start({ journey: { sections: [] } });
  const progress = [];
  const result = await client.wait(started.jobId, { onProgress: (state) => progress.push(state.progress) });
  assert.equal(result.mode, 'ai-planned');
  assert.deepEqual(progress, [55, undefined]);
  assert.equal(calls[0].path, '/api/set-builder/plan-tracks');
  assert.equal(JSON.parse(calls[0].options.body).journey.sections.length, 0);
});

test('planning client stops stale polling when aborted', async () => {
  const controller = new AbortController();
  const client = createSetPlanningClient({
    pollInterval: 100,
    fetchImpl: async () => response({ status: 'processing', progress: 25 }),
  });
  const waiting = client.wait('job-2', { signal: controller.signal });
  setTimeout(() => controller.abort(), 0);
  await assert.rejects(waiting, SetPlanningCanceled);
});

test('planning client surfaces server validation details', async () => {
  const client = createSetPlanningClient({
    fetchImpl: async () => response({ detail: 'Required track is unavailable.' }, false),
  });
  await assert.rejects(client.start({}), /Required track is unavailable/);
});

test('planning client exposes cancel and retry lifecycle endpoints', async () => {
  const calls = [];
  const client = createSetPlanningClient({
    fetchImpl: async (path, options = {}) => {
      calls.push({ path, method: options.method });
      return response({ jobId: 'job with spaces' });
    },
  });
  await client.cancel('job with spaces');
  await client.retry('job with spaces');
  assert.deepEqual(calls, [
    { path: '/api/set-builder/plan-tracks/job%20with%20spaces/cancel', method: 'POST' },
    { path: '/api/set-builder/plan-tracks/job%20with%20spaces/retry', method: 'POST' },
  ]);
});

test('planning client loads AI observability through its public endpoint', async () => {
  const calls = [];
  const client = createSetPlanningClient({
    fetchImpl: async (url) => {
      calls.push(url);
      return response({ completedCount: 4, fallbackRate: 0.25 });
    },
  });
  assert.deepEqual(await client.observability(), { completedCount: 4, fallbackRate: 0.25 });
  assert.deepEqual(calls, ['/api/set-builder/ai-observability']);
});
