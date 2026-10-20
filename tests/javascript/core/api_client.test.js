import test from 'node:test';
import assert from 'node:assert/strict';

import {
  ApiRequestError,
  apiErrorMessage,
  apiRequest,
  apiResponseJson,
  createApiClient,
} from '../../../web/core/api-client.js';

function response(payload, { ok = true, status = 200 } = {}) {
  return { ok, status, json: async () => payload };
}

test('error parser prefers normalized messages while retaining legacy shapes', () => {
  assert.equal(
    apiErrorMessage({ error: { message: 'Library drive is offline.' }, detail: 'Legacy text' }),
    'Library drive is offline.',
  );
  assert.equal(apiErrorMessage({ detail: 'Legacy text' }), 'Legacy text');
  assert.equal(apiErrorMessage({ detail: { message: 'Missing playlist files.' } }), 'Missing playlist files.');
  assert.equal(
    apiErrorMessage({ detail: [{ loc: ['body', 'duration'], msg: 'Must be positive' }] }),
    'duration: Must be positive',
  );
  assert.equal(apiErrorMessage({}, 'Fallback'), 'Fallback');
});

test('API response errors expose recovery metadata to every feature', async () => {
  const payload = {
    detail: 'Connect the configured library drive first.',
    error: { code: 'resource_unavailable', category: 'unavailable', message: 'Drive offline.', retryable: true },
  };
  await assert.rejects(
    apiResponseJson(response(payload, { ok: false, status: 503 })),
    (error) =>
      error instanceof ApiRequestError &&
      error.message === 'Drive offline.' &&
      error.status === 503 &&
      error.code === 'resource_unavailable' &&
      error.category === 'unavailable' &&
      error.retryable,
  );
});

test('API request accepts an injected transport and returns successful JSON', async () => {
  const calls = [];
  const result = await apiRequest(
    '/api/example',
    { method: 'POST' },
    {
      fetchImpl: async (url, options) => {
        calls.push({ url, options });
        return response({ saved: true });
      },
    },
  );
  assert.deepEqual(result, { saved: true });
  assert.deepEqual(calls, [{ url: '/api/example', options: { method: 'POST' } }]);
});

test('feature API client provides one immutable transport and error contract', async () => {
  const calls = [];
  const api = createApiClient({
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return response({ saved: true });
    },
  });

  assert.equal(Object.isFrozen(api), true);
  assert.equal(api.errorMessage({ detail: 'Invalid track.' }), 'Invalid track.');
  assert.deepEqual(await api.post('/api/tracks', { title: 'Cumbia' }, { headers: { 'X-Request-Id': 'request-1' } }), {
    saved: true,
  });
  assert.deepEqual(calls, [
    {
      url: '/api/tracks',
      options: {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Request-Id': 'request-1' },
        body: JSON.stringify({ title: 'Cumbia' }),
      },
    },
  ]);
});

test('feature API client retains raw response access for streaming and compatibility workflows', async () => {
  const nativeResponse = response({ queued: true }, { status: 202 });
  const api = createApiClient({ fetchImpl: async () => nativeResponse });

  assert.equal(await api.raw('/api/jobs'), nativeResponse);
});

test('feature API client normalizes failed requests with recovery metadata', async () => {
  const api = createApiClient({
    fetchImpl: async () =>
      response(
        {
          error: {
            code: 'drive_offline',
            category: 'unavailable',
            message: 'Reconnect the library drive.',
            retryable: true,
          },
        },
        { ok: false, status: 503 },
      ),
  });

  await assert.rejects(
    api.get('/api/library', {}, 'Library unavailable.'),
    (error) =>
      error instanceof ApiRequestError &&
      error.message === 'Reconnect the library drive.' &&
      error.code === 'drive_offline' &&
      error.retryable === true,
  );
});
