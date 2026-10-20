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

test('all primary tabs work with native browser media behavior', async ({ browser }) => {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('http://127.0.0.1:4173/');
  const navigation = page.getByRole('navigation', { name: 'Primary navigation' });
  await expect(navigation).toBeVisible();
  const names = await navigation.getByRole('button').allTextContents();
  for (const name of [...names, ...names.slice().reverse()]) await openView(page, name.trim());
  expect(errors).toEqual([]);
  await page.close();
});

test('tabs remain usable when the app module fails during startup and recover after reload', async ({ browser }) => {
  const page = await browser.newPage();
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: async (value) => {
          window.__copiedStartupDiagnostics = value;
        },
      },
    });
  });
  await page.route('**/assets/app.js?**', (route) => route.abort());
  await page.goto('http://127.0.0.1:4173/');
  await expect(page.locator('#app-startup-status')).toBeVisible();
  await expect(page.locator('#app-startup-detail')).toContainText('app.js');
  await openView(page, 'Import');
  await openView(page, 'Music Files');
  await openView(page, 'DJ Library');
  await page.getByRole('button', { name: 'Copy diagnostics' }).click();
  const diagnostics = JSON.parse(await page.evaluate(() => window.__copiedStartupDiagnostics));
  expect(diagnostics.assetRevision).toBeTruthy();
  expect(diagnostics.failures).toEqual(
    expect.arrayContaining([expect.objectContaining({ resource: expect.stringContaining('/assets/app.js') })]),
  );

  await page.unroute('**/assets/app.js?**');
  await page.getByRole('button', { name: 'Reload app' }).click();
  await expect(page.locator('#app-startup-status')).toBeHidden();
  await openView(page, 'Import');
  await page.close();
});

test('a stale unversioned Set Builder module cannot prevent app startup', async ({ browser }) => {
  const page = await browser.newPage();
  const viewModelRequests = [];
  await page.route(
    (url) => url.pathname === '/assets/features/set-builder/view-model.js' && !url.search,
    (route) => route.fulfill({ contentType: 'text/javascript', body: 'export {};' }),
  );
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/assets/features/set-builder/view-model.js')
      viewModelRequests.push(request.url());
  });
  await page.goto('http://127.0.0.1:4173/');
  await openView(page, 'Music Files');
  expect(viewModelRequests).toHaveLength(1);
  expect(new URL(viewModelRequests[0]).searchParams.has('v')).toBe(true);
  await expect(page.locator('#app-startup-status')).toBeHidden();
  await page.close();
});

test('Import and library tabs still work when Set Builder startup fails', async ({ browser }) => {
  const page = await browser.newPage();
  await page.route('**/api/library/catalog?**', (route) =>
    route.fulfill({ json: { tracks: [], total: 0, facets: {} } }),
  );
  const startupFailure = page.waitForEvent('pageerror');
  await page.addInitScript(() => {
    const getItem = Storage.prototype.getItem;
    Storage.prototype.getItem = function (key) {
      if (key === 'set-builder-compact') throw new Error('Set Builder storage unavailable');
      return getItem.call(this, key);
    };
  });
  await page.goto('http://127.0.0.1:4173/');
  expect((await startupFailure).message).toContain('Set Builder storage unavailable');
  await openView(page, 'Music Files');
  await expect(page.locator('#downloaded-summary')).toContainText('Browse collection');
  await openView(page, 'DJ Library');
  await expect(page.locator('#library-list')).toContainText('No completed tracks yet.');
  await openView(page, 'Import');
  await page.locator('#import-failures-panel > summary').click();
  await expect(page.locator('#import-failures-empty')).toBeVisible();
  await page.close();
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

test('Set Builder keeps brief authoring separate from track planning', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 900 });
  await openView(page, 'Set Builder');
  const overflow = await page.locator('body *').evaluateAll((items) =>
    items
      .filter((item) => {
        const bounds = item.getBoundingClientRect();
        return bounds.width > 0 && (bounds.left < -1 || bounds.right > window.innerWidth + 1);
      })
      .slice(0, 12)
      .map((item) => ({
        element: item.id ? `#${item.id}` : `${item.tagName.toLowerCase()}.${item.className}`,
        name: item.getAttribute('name'),
        type: item.getAttribute('type'),
        bounds: item.getBoundingClientRect().toJSON(),
      })),
  );
  expect(overflow).toEqual([]);
  await expect(page.locator('.saved-sets-panel')).toBeVisible();
  const intention = page.locator('#set-intention');
  const plannerChoices = page.locator('.set-track-planner label > span');
  await expect(plannerChoices).toHaveCount(2);
  const plannerWidths = await plannerChoices.evaluateAll((items) =>
    items.map((item) => item.getBoundingClientRect().width),
  );
  expect(plannerWidths.every((width) => width >= 220)).toBe(true);
  await intention.fill('A melodic Latin warm-up that grows into techno.');

  await page.getByText('Build manually', { exact: true }).click();
  await expect(page.locator('#set-ai-brief')).toBeHidden();
  await expect(page.locator('#set-manual-brief')).toBeVisible();
  await expect(page.locator('#set-planning-mode')).toHaveValue('ai-planned');

  await page.getByText('Deterministic', { exact: true }).click();
  await expect(page.locator('#set-planning-mode')).toHaveValue('classic');
  await page.getByText('Describe what I want', { exact: true }).click();
  await expect(page.locator('#set-ai-brief')).toBeVisible();
  await expect(intention).toHaveValue('A melodic Latin warm-up that grows into techno.');
  await expect(page.locator('#set-planning-mode')).toHaveValue('interpreted');

  await page.evaluate(() => {
    const sections = document.createElement('div');
    sections.id = 'journey-layout-probe';
    sections.className = 'set-journey-sections';
    sections.style.width = '1000px';
    sections.innerHTML = `<article class="set-journey-section">
      <span class="journey-step">1</span>
      <div class="journey-primary">
        <label>Section<input value="Warm-up"></label>
        <label class="journey-duration-label">Duration<input type="number" value="15"><span>%</span></label>
        <label class="journey-energy">Energy <span class="journey-energy-value">4 → 6</span>
          <span class="journey-energy-inputs"><input type="number" value="4"><i>to</i><input type="number" value="6"></span>
        </label>
      </div>
      <div class="journey-details">
        <label class="journey-genres">Genres<input value="disco &amp; funk, latin house"></label>
        <label>Character<input class="journey-characteristics" value="groovy, melodic"></label>
        <label class="journey-purpose">Purpose<input value="Build energy gradually"></label>
      </div>
    </article>`;
    document.querySelector('#set-builder-view').append(sections);
  });
  const journeyProbe = page.locator('#journey-layout-probe .set-journey-section');
  await expect(journeyProbe).toBeVisible();
  const journeyFieldsOverlap = await journeyProbe.evaluateAll((sections) =>
    sections.some((section) => {
      const energy = section.querySelector('.journey-energy-inputs')?.getBoundingClientRect();
      const character = section.querySelector('.journey-characteristics')?.getBoundingClientRect();
      return energy && character && energy.right > character.left + 1;
    }),
  );
  expect(journeyFieldsOverlap).toBe(false);
  await page.locator('#journey-layout-probe').evaluate((node) => node.remove());
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
    const { confirmAction } = await import('/assets/shared/shared-components.js');
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
    const playback = await import('/assets/shared/playback.js');
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
  await expect(focusProbe).toHaveCSS('outline-style', 'solid');
  await expect(focusProbe).toHaveCSS('outline-width', '2px');
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
