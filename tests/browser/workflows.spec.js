import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

const openView = async (page, name) => {
  const button = page
    .getByRole('navigation', { name: 'Primary navigation' })
    .getByRole('button', { name, exact: true });
  await button.click();
  await expect(page.locator(`#${await button.getAttribute('data-view')}`)).toHaveClass(/active/);
};

const openSettings = async (page) => {
  await openView(page, 'Settings');
  await expect(page.locator('#setting-library-path')).not.toHaveValue('');
};

const putSettings = (page, overrides) =>
  page.evaluate(async (values) => {
    const config = await fetch('/api/config').then((response) => response.json());
    const response = await fetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...config.effective, ...values }),
    });
    if (!response.ok) throw new Error(`Settings update failed with ${response.status}`);
    return response.json();
  }, overrides);

test.beforeEach(async ({ page }) => {
  page.on('pageerror', (error) => console.error(`Browser page error: ${error.stack}`));
  await page.addInitScript(() => {
    HTMLMediaElement.prototype.load = () => {};
    HTMLMediaElement.prototype.play = function play() {
      Object.defineProperty(this, 'paused', { configurable: true, value: false });
      this.dispatchEvent(new Event('play'));
      return Promise.resolve();
    };
    HTMLMediaElement.prototype.pause = function pause() {
      Object.defineProperty(this, 'paused', { configurable: true, value: true });
      this.dispatchEvent(new Event('pause'));
    };
  });
  await page.goto('/');
  await expect(page.getByRole('navigation', { name: 'Primary navigation' })).toBeVisible();
});

test('persisted settings render after browser refresh', async ({ page }) => {
  await openSettings(page);
  const result = await putSettings(page, { intro_search_seconds: 39, outro_search_seconds: 31 });
  expect(result.receipt.survives_restart).toBe(true);

  await page.reload();
  await openSettings(page);
  const duplicateIds = await page.locator('[id]').evaluateAll((nodes) => {
    const counts = nodes.reduce((result, node) => ({ ...result, [node.id]: (result[node.id] || 0) + 1 }), {});
    return Object.entries(counts)
      .filter(([, count]) => count > 1)
      .map(([id]) => id);
  });
  expect(duplicateIds).toEqual([]);
  await expect(page.locator('#setting-intro-search')).toHaveValue('39');
  await expect(page.locator('#setting-outro-search')).toHaveValue('31');
});

test('saved sets survive browser storage clearing and application reload', async ({ page }) => {
  const saved = await page.evaluate(async () => {
    const record = {
      id: 'browser-clear-proof',
      name: 'Browser Clear Proof',
      tracks: ['track-1'],
      planningReceipt: { provider: 'offline', validated: true },
      transitions: {},
    };
    const response = await fetch(`/api/set-builder/sets/${record.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ record }),
    });
    return response.json();
  });
  expect(saved.survives_restart).toBe(true);

  await page.evaluate(() => localStorage.clear());
  await page.reload();
  const records = await page.evaluate(() => fetch('/api/set-builder/sets').then((response) => response.json()));
  expect(records.sets).toEqual(
    expect.arrayContaining([expect.objectContaining({ id: 'browser-clear-proof', name: 'Browser Clear Proof' })]),
  );
});

test('search fields retain the complete query during overlapping requests', async ({ page }) => {
  await page.route('**/api/downloaded-library?*', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 180));
    await route.continue();
  });
  await openView(page, 'Music Files');
  const search = page.locator('#downloaded-search');
  await search.pressSequentially('abcdefghijklmnopqrstuvwxyz1234567890', { delay: 5 });
  await expect(search).toHaveValue('abcdefghijklmnopqrstuvwxyz1234567890');
  await page.waitForTimeout(350);
  await expect(search).toHaveValue('abcdefghijklmnopqrstuvwxyz1234567890');
});

test('disconnect and reconnect clear the stale offline presentation', async ({ page }) => {
  await openSettings(page);
  const original = await page.locator('#setting-library-path').inputValue();
  await putSettings(page, { music_library_path: '/tmp/audioextender-browser-smoke-missing-drive' });
  await page.reload();
  await openSettings(page);
  await expect(page.locator('#library-offline-banner')).toBeVisible();

  await putSettings(page, { music_library_path: original });
  await page.reload();
  await openSettings(page);
  await expect(page.locator('#library-offline-banner')).toBeHidden();
  await expect(page.locator('#health-connection')).toHaveText('Configured library connected');
});

test('dialogs trap initial focus, close by keyboard, and restore focus', async ({ page }) => {
  await page.evaluate(async () => {
    const { confirmAction } = await import('/assets/shared-components.js');
    document.querySelector('[data-view="settings-view"]').id = 'dialog-launcher';
    document.querySelector('#dialog-launcher').focus();
    window.__dialogResult = confirmAction('Confirm keyboard behavior', { title: 'Keyboard test' });
  });
  const dialog = page.locator('#app-confirm-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('button[value="cancel"]')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(page.locator('#dialog-launcher')).toBeFocused();
});

test('starting a preview transfers the single playback owner', async ({ page }) => {
  await page.evaluate(async () => {
    const playback = await import('/assets/playback.js');
    const host = document.createElement('section');
    host.id = 'playback-smoke';
    host.innerHTML = playback.compactAudioMarkup('/first.wav', 120) + playback.compactAudioMarkup('/second.wav', 180);
    document.body.append(host);
    playback.bindCompactAudio(host);
  });
  const controls = page.locator('#playback-smoke .compact-audio-play');
  await controls.nth(0).click();
  await expect(controls.nth(0)).toHaveAttribute('aria-label', 'Pause track');
  await controls.nth(1).click();
  await expect(controls.nth(0)).toHaveAttribute('aria-label', 'Play track');
  await expect(controls.nth(1)).toHaveAttribute('aria-label', 'Pause track');
});

test('primary workflows remain usable at supported viewports and pass serious accessibility checks', async ({
  page,
}) => {
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 720, height: 900 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await openSettings(page);
    await expect(page.locator('#settings-form')).toBeVisible();
    const saveSettings = page.getByRole('button', { name: 'Save settings' });
    await expect(saveSettings).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      `Settings overflowed horizontally at ${viewport.width}px`,
    ).toBe(true);
  }

  await page.evaluate(() => {
    const probe = document.createElement('button');
    probe.id = 'keyboard-focus-probe';
    probe.textContent = 'Keyboard focus probe';
    document.body.prepend(probe);
    document.body.tabIndex = -1;
    document.body.focus();
  });
  await page.keyboard.press('Tab');
  const focusProbe = page.locator('#keyboard-focus-probe');
  await expect(focusProbe).toBeFocused();
  expect(await focusProbe.evaluate((node) => getComputedStyle(node).outlineStyle)).toBe('solid');
  expect(await focusProbe.evaluate((node) => getComputedStyle(node).outlineWidth)).toBe('2px');
  await focusProbe.evaluate((node) => node.remove());

  const results = await new AxeBuilder({ page })
    .include('header')
    .include('#settings-view')
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();
  const serious = results.violations.filter((item) => ['serious', 'critical'].includes(item.impact));
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
});

test('reduced-motion preference suppresses application animation and transitions', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openSettings(page);
  const durations = await page.evaluate(() => {
    const probe = document.createElement('button');
    probe.className = 'button';
    probe.setAttribute('aria-busy', 'true');
    document.body.append(probe);
    const buttonStyle = getComputedStyle(probe);
    const spinnerStyle = getComputedStyle(probe, '::after');
    const result = {
      transition: buttonStyle.transitionDuration,
      animation: spinnerStyle.animationDuration,
      iterations: spinnerStyle.animationIterationCount,
    };
    probe.remove();
    return result;
  });
  expect(Number.parseFloat(durations.transition)).toBeLessThanOrEqual(0.00001);
  expect(Number.parseFloat(durations.animation)).toBeLessThanOrEqual(0.00001);
  expect(durations.iterations).toBe('1');
});
