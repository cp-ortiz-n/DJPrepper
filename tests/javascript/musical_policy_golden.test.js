import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

globalThis.localStorage = {
  getItem() {
    return null;
  },
};

const policy = await import('../../web/dj-library.js');
const fixture = JSON.parse(readFileSync(new URL('../fixtures/musical_policy_golden.json', import.meta.url), 'utf8'));

function assertClose(actual, expected, message) {
  assert.ok(Math.abs(actual - expected) < 1e-12, `${message}: expected ${expected}, received ${actual}`);
}

test('browser musical profiles match the versioned golden fixture', () => {
  assert.equal(fixture.schema_version, 1);
  for (const item of fixture.keys) {
    assert.equal(policy.normalizedKey(item.input), item.normalized, item.input);
    assert.equal(policy.camelotKey(item.input), item.camelot, item.input);
  }
  for (const item of fixture.profiles) {
    assert.deepEqual([...policy.libraryRoles(item.song)].sort(), item.roles, `${item.name}: roles`);
    assertClose(policy.songEnergy(item.song), item.energy, `${item.name}: energy`);
    assert.equal(policy.energyBand(policy.songEnergy(item.song)), item.energy_band, `${item.name}: band`);
    assert.equal(policy.vocalProfile(item.song), item.vocals, `${item.name}: vocals`);
    assert.equal(policy.timingProfile(item.song), item.timing, `${item.name}: timing`);
  }
});

test('serialized backend profile values take precedence in the browser', () => {
  const { song, roles, energy, energy_band: band, vocals, timing } = fixture.browser_overrides;
  assert.deepEqual(policy.libraryRoles(song), roles);
  assert.equal(policy.songEnergy(song), energy);
  assert.equal(policy.energyBand(policy.songEnergy(song)), band);
  assert.equal(policy.vocalProfile(song), vocals);
  assert.equal(policy.timingProfile(song), timing);
  assert.equal(policy.normalizedKey(song), 'C# major');
  assert.equal(policy.camelotKey(song), '3B');
  assert.equal(policy.formatLibraryKey(song, 'both'), 'C# major · 3B');
});

test('unknown profile versions fall back to legacy catalog facts', () => {
  const song = {
    key: 'A minor',
    _energy: 0.25,
    _roles: ['warm-up'],
    musical_profile: { version: 99, key: 'C# major', camelot: '3B', energy: 0.9, roles: ['peak-time'] },
  };
  assert.equal(policy.formatLibraryKey(song, 'both'), 'A minor · 8A');
  assert.equal(policy.songEnergy(song), 0.25);
  assert.deepEqual(policy.libraryRoles(song), ['warm-up']);
});

test('DJ Library match scores match the versioned golden fixture', () => {
  for (const item of fixture.library_matches) {
    assert.deepEqual(policy.compatibility(item.left, item.right), item.expected, item.name);
  }
});
