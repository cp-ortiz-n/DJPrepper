import test from 'node:test';
import assert from 'node:assert/strict';

import { setTrackAudioUrl } from '../../../../frontend/features/set-builder/track-media.js';

test('set track playback prefers the durable catalog endpoint after regeneration', () => {
  assert.equal(
    setTrackAudioUrl({ _downloadedId: 42, _job: { id: 9001 } }),
    '/api/downloaded-library/tracks/42/audio',
  );
});

test('set track playback falls back to job audio for uncataloged tracks', () => {
  assert.equal(setTrackAudioUrl({ _job: { id: 77 } }), '/api/jobs/77/audio/wav');
});

test('set track playback rejects missing and invalid media identities', () => {
  assert.equal(setTrackAudioUrl(null), '');
  assert.equal(setTrackAudioUrl({ _downloadedId: 0, _job: { id: 'missing' } }), '');
});
