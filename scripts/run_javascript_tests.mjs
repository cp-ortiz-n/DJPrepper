import { readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const projectRoot = resolve(fileURLToPath(new URL('..', import.meta.url)));
const testRoot = join(projectRoot, 'tests', 'javascript');

function testFiles(directory) {
  return readdirSync(directory, { withFileTypes: true })
    .flatMap((entry) => {
      const path = join(directory, entry.name);
      return entry.isDirectory() ? testFiles(path) : entry.name.endsWith('.test.js') ? [path] : [];
    })
    .sort();
}

const files = testFiles(testRoot);
const result = spawnSync(process.execPath, ['--test', ...files], {
  cwd: projectRoot,
  encoding: 'utf8',
  stdio: 'inherit',
});
process.exit(result.status ?? 1);
