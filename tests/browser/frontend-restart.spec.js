import { spawn } from 'node:child_process';
import { once } from 'node:events';
import process from 'node:process';
import { expect, test } from '@playwright/test';

const PORT = 4174;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const CACHEABLE_ASSETS = 'public, max-age=31536000, immutable';

const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

const stopServer = async (server) => {
  if (!server || server.exitCode !== null) return;
  const exited = once(server, 'exit');
  server.kill('SIGTERM');
  if (await Promise.race([exited.then(() => true), wait(5_000).then(() => false)])) return;
  server.kill('SIGKILL');
  await once(server, 'exit');
};

const startServer = async (revision) => {
  const server = spawn('.venv/bin/python', ['scripts/development/serve_browser_smoke.py'], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      AUDIOEXTENDER_BROWSER_SMOKE_PORT: String(PORT),
      AUDIOEXTENDER_BROWSER_SMOKE_ASSET_REVISION: revision,
      AUDIOEXTENDER_BROWSER_SMOKE_ASSET_CACHE_CONTROL: CACHEABLE_ASSETS,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let output = '';
  server.stdout.on('data', (chunk) => (output += chunk));
  server.stderr.on('data', (chunk) => (output += chunk));
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (server.exitCode !== null) throw new Error(`Browser restart server exited early:\n${output}`);
    try {
      const response = await fetch(BASE_URL);
      if (response.ok) return server;
    } catch {
      // The isolated server is still starting.
    }
    await wait(100);
  }
  await stopServer(server);
  throw new Error(`Browser restart server did not become ready:\n${output}`);
};

test('a warm browser cache stays coherent across a frontend revision restart', async ({ browser }) => {
  test.setTimeout(60_000);
  const context = await browser.newContext();
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  let server = null;
  try {
    server = await startServer('warm-cache-a');
    await page.goto(BASE_URL);
    await expect(page.locator('meta[name="djls-asset-revision"]')).toHaveAttribute('content', 'warm-cache-a');
    await expect(page.locator('#app-startup-status')).toBeHidden();
    expect(pageErrors).toEqual([]);

    await stopServer(server);
    server = await startServer('warm-cache-b');
    // Background polling can observe the deliberate outage. The restart
    // contract begins once the replacement server is ready for the reload.
    pageErrors.length = 0;
    const moduleRequests = [];
    page.on('request', (request) => {
      const url = new URL(request.url());
      if (url.pathname.startsWith('/assets/') && url.pathname.endsWith('.js')) moduleRequests.push(url);
    });
    await page.reload();
    await expect(page.locator('meta[name="djls-asset-revision"]')).toHaveAttribute('content', 'warm-cache-b');
    await expect(page.locator('#app-startup-status')).toBeHidden();

    const navigation = page.getByRole('navigation', { name: 'Primary navigation' });
    const names = await navigation.getByRole('button').allTextContents();
    for (const name of names) {
      const button = navigation.getByRole('button', { name: name.trim(), exact: true });
      await button.click();
      await expect(page.locator(`#${await button.getAttribute('data-view')}`)).toHaveClass(/active/);
    }
    expect(moduleRequests.length).toBeGreaterThan(10);
    expect([...new Set(moduleRequests.map((url) => url.searchParams.get('v')))]).toEqual(['warm-cache-b']);
    expect(pageErrors).toEqual([]);
  } finally {
    await stopServer(server);
    await context.close();
  }
});
