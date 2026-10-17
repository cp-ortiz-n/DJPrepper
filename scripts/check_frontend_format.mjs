import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

const baseline = JSON.parse(readFileSync(new URL('./format_baseline.json', import.meta.url), 'utf8')).frontend;
const targets = [
  'web/**/*.js',
  'web/**/*.html',
  'web/**/*.css',
  'tests/javascript/*.test.js',
  'scripts/*.mjs',
  '.eslintrc.cjs',
];
const command = process.platform === 'win32' ? 'prettier.cmd' : 'prettier';
const result = spawnSync(command, ['--list-different', ...targets], {
  cwd: new URL('..', import.meta.url),
  encoding: 'utf8',
  shell: true,
});

if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}
const actual = new Set(
  result.stdout
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean),
);
const expected = new Set(baseline);
const regressions = [...actual].filter((file) => !expected.has(file)).sort();
const resolved = [...expected].filter((file) => !actual.has(file)).sort();
if (regressions.length) {
  console.error(`New Prettier formatting debt:\n${regressions.map((file) => `  ${file}`).join('\n')}`);
  process.exit(1);
}
if (resolved.length) {
  console.error(
    `Remove these now-formatted files from scripts/format_baseline.json:\n${resolved
      .map((file) => `  ${file}`)
      .join('\n')}`,
  );
  process.exit(1);
}
console.log(`Frontend formatting ratchet passed (${actual.size} known legacy files remain).`);
