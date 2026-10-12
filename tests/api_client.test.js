import test from 'node:test';
import assert from 'node:assert/strict';

import { ApiRequestError, apiErrorMessage, apiRequest, apiResponseJson } from '../web/api-client.js';

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
