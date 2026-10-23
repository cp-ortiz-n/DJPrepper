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

test('Rekordbox TXT ratings are previewed before exact matches are applied', async ({ page }) => {
  await page.route((url) => url.pathname === '/api/settings/rekordbox-ratings/preview', (route) =>
    route.fulfill({
      json: {
        token: 'rating-preview-1',
        filename: 'collection.txt',
        format: 'txt',
        total_export_tracks: 4,
        unrated_tracks: 1,
        invalid_rows: 0,
        rated_tracks: 3,
        matched_tracks: 2,
        proposed_changes: 1,
        unchanged_values: 1,
        ambiguous_rows: 1,
        unmatched_rows: 0,
        match_methods: { 'catalog-identity': 2 },
        matches: [
          { artist: 'Majestic', title: 'Rasputin', rating: 5, match_method: 'catalog-identity' },
        ],
        ambiguous: [{ artist: 'Lipps Inc', title: 'Funkytown', rating: 3 }],
        unmatched: [],
        review_truncated: false,
      },
    }),
  );
  await page.route((url) => url.pathname === '/api/settings/rekordbox-ratings/apply', (route) =>
    route.fulfill({
      json: {
        changed: 1,
        matched: 2,
        synced_at: '2026-10-22T12:00:00Z',
        status: {
          rated_tracks: 2,
          ratings: { 5: 1, 3: 1 },
          last_synced_at: '2026-10-22T12:00:00Z',
          tracks: [{ artist: 'Majestic', title: 'Rasputin', rating: 5, match_method: 'catalog-identity' }],
        },
      },
    }),
  );

  await openSettings(page);
  await page.locator('.rekordbox-rating-panel > summary').click();
  await page.locator('#rekordbox-rating-file').setInputFiles({
    name: 'collection.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('#\tTrack Title\tArtist\tRating\tTime'),
  });
  await expect(page.locator('#rekordbox-rating-preview')).toContainText('1 rating changes ready');
  await expect(page.locator('#rekordbox-rating-preview')).toContainText('3 rated in TXT');
  await expect(page.locator('#rekordbox-rating-preview')).toContainText('1 ambiguous');
  await page.locator('#apply-rekordbox-ratings').click();
  await page.locator('#app-confirm-accept').click();
  await expect(page.locator('#rekordbox-rating-message')).toContainText('1 ratings updated');
  await expect(page.locator('#rekordbox-rating-status')).toContainText('2 synced ratings');
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

test('deleting the active saved set returns Set Builder to a clean draft', async ({ page }) => {
  const savedSet = {
    id: 'active-plan',
    draftId: 'draft-active-plan',
    planRevision: {
      id: 'revision-active-plan-1',
      number: 1,
      parentId: null,
      createdAt: '2026-10-21T12:00:00.000Z',
    },
    name: 'Active Plan',
    brief: { name: 'Active Plan', authoringMode: 'manual' },
    planningMode: 'classic',
    planningReceipt: { provider: 'offline', validated: true },
    tracks: ['opening.wav'],
    trackDetails: [{ id: 'opening.wav', source_name: 'Opening.wav', artist: 'DJ Test', genre: 'House' }],
    transitions: {},
    locked: [],
    required: [],
    excluded: [],
    updatedAt: '2026-10-21T12:00:00.000Z',
  };
  await page.route((url) => url.pathname === '/api/set-builder/catalog', (route) =>
    route.fulfill({
      json: {
        tracks: [
          {
            downloaded_id: 501,
            recording_code: 'HOU-000501',
            version_code: 'ORG',
            genre: 'House',
            detailed_genre: 'Deep House',
            descriptors: [],
            analysis: {
              source_name: 'Opening.wav',
              title: 'Opening',
              artist: 'DJ Test',
              bpm: 120,
              key: 'Am',
              duration_seconds: 180,
              energy: 0.5,
            },
            job: { id: 501, config_json: '{}', library_path: '/tmp/Opening.wav' },
          },
        ],
      },
    }),
  );
  await page.route((url) => url.pathname === '/api/set-builder/sets', (route) =>
    route.fulfill({ json: { version: 2, sets: [savedSet] } }),
  );
  await page.route((url) => url.pathname === '/api/set-builder/sets/active-plan', (route) =>
    route.fulfill({ json: { deleted: true, id: 'active-plan' } }),
  );
  await page.reload();
  await openView(page, 'Set Builder');

  await page.locator('#saved-set-select').selectOption('active-plan', { force: true });
  await page.locator('#load-set').click();
  await expect(page.locator('#set-result')).toBeVisible();
  await expect(page.locator('#set-result-name')).toHaveValue('Active Plan');

  await page.locator('#delete-set').click();
  await page.locator('#app-confirm-accept').click();

  await expect(page.locator('#set-result')).toBeHidden();
  await expect(page.locator('#saved-set-select')).toHaveValue('');
  await expect(page.locator('#set-name')).toHaveValue('New DJ Set');
  await expect(page.locator('#set-builder-message')).toContainText('Plan deleted');
});

test('Set Builder compact workspace supports inspection, keyboard navigation, and narrow screens', async ({
  page,
}) => {
  const tracks = [
    ['Opening.wav', 'DJ Test', 'Deep House', 120, 'Am', 0.45],
    ['Lift.wav', 'DJ Test', 'House', 124, 'C', 0.68],
    ['Peak.wav', 'DJ Test', 'Techno', 128, 'Gm', 0.84],
  ];
  const savedSet = {
    id: 'workspace-shell-plan',
    draftId: 'draft-workspace-shell',
    planRevision: { id: 'revision-shell-2', number: 2, parentId: 'revision-shell-1' },
    name: 'Workspace Shell Plan',
    brief: { name: 'Workspace Shell Plan', authoringMode: 'manual', minimumHealth: 55 },
    planningMode: 'classic',
    planningReceipt: { provider: 'offline', validated: true },
    tracks: tracks.map(([name]) => name.toLowerCase()),
    trackDetails: tracks.map(([source_name, artist, genre, bpm]) => ({
      id: source_name.toLowerCase(),
      source_name,
      artist,
      genre,
      bpm,
    })),
    transitions: {},
    locked: ['opening.wav'],
    required: [],
    excluded: [],
  };
  let regenerationRequest;
  await page.route((url) => url.pathname === '/api/set-builder/catalog', (route) =>
    route.fulfill({
      json: {
        tracks: tracks.map(([source_name, artist, genre, bpm, key, energy], index) => ({
          downloaded_id: 700 + index,
          recording_code: `TST-00070${index}`,
          version_code: 'ORG',
          genre,
          detailed_genre: genre,
          descriptors: [],
          analysis: { source_name, artist, bpm, key, energy, duration_seconds: 180 },
          job: { id: 700 + index, config_json: '{}', library_path: `/tmp/${source_name}` },
        })),
      },
    }),
  );
  await page.route((url) => url.pathname === '/api/set-builder/sets', (route) =>
    route.fulfill({ json: { version: 2, sets: [savedSet] } }),
  );
  await page.route((url) => url.pathname === '/api/set-builder/plan-tracks', async (route) => {
    regenerationRequest = route.request().postDataJSON();
    await route.fulfill({ status: 202, json: { jobId: 'browser-regeneration', status: 'pending' } });
  });
  await page.route((url) => url.pathname === '/api/set-builder/plan-tracks/browser-regeneration', (route) =>
    route.fulfill({
      json: {
        status: 'complete',
        stage: 'Validated running order ready',
        progress: 100,
        result: {
          mode: 'ai-planned',
          provider: 'ollama',
          model: 'test-model',
          summary: 'Regenerated unlocked tracks.',
          warnings: [],
          basePlanRevision: savedSet.planRevision,
          plan: [
            { id: 'downloaded:700', sectionId: 'section-1' },
            { id: 'downloaded:702', sectionId: 'section-1' },
          ],
        },
      },
    }),
  );
  await page.reload();
  await openView(page, 'Set Builder');
  await page.locator('#saved-set-select').selectOption(savedSet.id, { force: true });
  await page.locator('#load-set').click();

  const result = page.locator('#set-result');
  const rows = page.locator('.set-track-card');
  await expect(rows).toHaveCount(3);
  await expect(page.locator('#set-workspace-state')).toHaveText('Saved plan');
  await expect(page.locator('#set-workspace-revision')).toHaveText('Revision 2');
  await expect(rows.first().locator('.set-track-summary')).toContainText('120.0 BPM');
  await expect(rows.first().locator('.set-track-chips')).toContainText('Locked');
  expect(await page.locator('.set-result-head').evaluate((node) => getComputedStyle(node).position)).toBe('sticky');

  await page.getByText('AI curated', { exact: true }).click();
  await page.locator('#regenerate-set').click();
  await expect(page.locator('#set-revision-comparison')).toContainText('Revision 3');
  await expect(page.locator('#set-revision-comparison')).toContainText('1/1 locked preserved');
  await expect(rows).toHaveCount(2);
  await expect(rows.first()).toContainText('Opening');
  await expect(rows.nth(1)).toContainText('Peak');
  expect(regenerationRequest.base_plan_revision).toEqual(savedSet.planRevision);
  expect(regenerationRequest.locked_track_sections['downloaded:700']).toBeTruthy();
  await page.locator('#set-undo').click();
  await expect(rows).toHaveCount(3);
  await expect(rows.nth(1)).toContainText('Lift');
  await expect(page.locator('#set-workspace-revision')).toHaveText('Revision 2');

  await expect(rows.first().locator('.set-drag-handle')).toBeDisabled();
  await rows.nth(1).locator('.set-drag-handle').dragTo(rows.nth(2));
  await expect(rows.nth(1)).toContainText('Peak');
  await page.locator('#set-undo').evaluate((button) => button.click());
  await expect(rows.nth(1)).toContainText('Lift');

  await rows.first().getByRole('button', { name: 'More' }).click();
  const inspector = page.locator('#set-track-inspector');
  await expect(inspector).toBeVisible();
  await expect(inspector.locator('.set-track-inspector-title')).toHaveText('Opening');
  await expect(inspector.locator('.set-track-meta')).toBeVisible();
  await expect(inspector.locator('.set-row-actions')).toBeVisible();
  await expect(inspector.getByRole('button', { name: 'Close track inspector' })).toBeFocused();
  expect(await inspector.evaluate((node) => getComputedStyle(node).position)).toBe('fixed');
  await page.locator('#set-workspace-state').click();
  await expect(inspector).toBeHidden();
  await rows.first().getByRole('button', { name: 'More' }).click();
  const accessibility = await new AxeBuilder({ page }).include('#set-result').withTags(['wcag2a', 'wcag2aa']).analyze();
  expect(
    accessibility.violations.filter((item) => ['serious', 'critical'].includes(item.impact)),
  ).toEqual([]);
  await page.keyboard.press('Escape');
  await expect(inspector).toBeHidden();
  await expect(rows.first()).toBeFocused();

  await rows.nth(1).getByRole('button', { name: 'More' }).click();
  await inspector.getByRole('button', { name: 'Edit mix' }).click();
  await expect(inspector).toBeHidden();
  const transitionEditor = rows.nth(1).locator('.transition-editor');
  await expect(transitionEditor).toBeVisible();
  await expect(transitionEditor.getByRole('button', { name: 'Close transition editor' })).toBeFocused();
  expect(await transitionEditor.locator('header').evaluate((node) => getComputedStyle(node).position)).toBe('sticky');
  await page.keyboard.press('Escape');
  await expect(transitionEditor).toHaveCount(0);

  await rows.nth(1).focus();
  await page.keyboard.press('ArrowDown');
  await expect(rows.nth(2)).toBeFocused();
  await page.setViewportSize({ width: 390, height: 844 });
  await rows.nth(1).press('Enter');
  await expect(inspector).toBeVisible();
  expect(await result.evaluate((node) => node.scrollWidth <= node.clientWidth + 1)).toBe(true);

  await page.emulateMedia({ reducedMotion: 'reduce' });
  const transitionDuration = await inspector.evaluate((node) => getComputedStyle(node).transitionDuration);
  expect(Number.parseFloat(transitionDuration)).toBeLessThanOrEqual(0.00001);
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
  await expect(page.locator('#set-planning-mode')).toHaveAttribute('type', 'hidden');
  await expect(page.locator('#set-planning-mode-combobox-search')).toHaveCount(0);
  await expect(page.locator('#set-planning-summary')).toHaveText('Direction: AI interpreted · Tracks: AI curated');
  await expect(page.locator('#set-generate')).toHaveText('Build AI-curated set');
  await expect(page.locator('#set-cancel-planning')).toBeHidden();
  const plannerWidths = await plannerChoices.evaluateAll((items) =>
    items.map((item) => item.getBoundingClientRect().width),
  );
  expect(plannerWidths.every((width) => width >= 220)).toBe(true);
  await intention.fill('A melodic Latin warm-up that grows into techno.');

  await page.getByText('Build manually', { exact: true }).click();
  await expect(page.locator('#set-ai-brief')).toBeHidden();
  await expect(page.locator('#set-manual-brief')).toBeVisible();
  await expect(page.locator('#set-planning-mode')).toHaveValue('ai-planned');

  await page.getByText('Rules-based', { exact: true }).click();
  await expect(page.locator('#set-planning-mode')).toHaveValue('classic');
  await expect(page.locator('#set-planning-summary')).toHaveText('Direction: Manual brief · Tracks: Rules-based');
  await expect(page.locator('#set-generate')).toHaveText('Build rules-based set');
  await page.getByText('Describe what I want', { exact: true }).click();
  await expect(page.locator('#set-ai-brief')).toBeVisible();
  await expect(intention).toHaveValue('A melodic Latin warm-up that grows into techno.');
  await expect(page.locator('#set-planning-mode')).toHaveValue('interpreted');
  await expect(page.locator('#set-planning-summary')).toHaveText('Direction: AI interpreted · Tracks: Rules-based');

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
      return (
        energy &&
        character &&
        energy.left < character.right - 1 &&
        energy.right > character.left + 1 &&
        energy.top < character.bottom - 1 &&
        energy.bottom > character.top + 1
      );
    }),
  );
  expect(journeyFieldsOverlap).toBe(false);
  const journeyStructure = await journeyProbe.evaluate((section) => {
    const primary = section.querySelector('.journey-primary').getBoundingClientRect();
    const details = section.querySelector('.journey-details').getBoundingClientRect();
    return {
      stacked: details.top >= primary.bottom - 1,
      aligned: Math.abs(primary.left - details.left) <= 1,
    };
  });
  expect(journeyStructure).toEqual({ stacked: true, aligned: true });
  await page.locator('#journey-layout-probe').evaluate((node) => node.remove());

  await page.evaluate(() => {
    const review = document.createElement('div');
    review.id = 'set-review-style-probe';
    review.className = 'set-track-review';
    review.innerHTML = `<button type="button" class="active">✓ Keep</button><button type="button">× Reject</button><select aria-label="Rejection reason"><option>Reason…</option></select>`;
    document.querySelector('#set-builder-view').append(review);
  });
  const keepButton = page.locator('#set-review-style-probe button.active');
  await expect(keepButton).toHaveText('✓ Keep');
  const keepContrast = await keepButton.evaluate((button) => {
    const style = getComputedStyle(button);
    return { color: style.color, background: style.backgroundColor, width: button.getBoundingClientRect().width };
  });
  expect(keepContrast.color).not.toBe(keepContrast.background);
  expect(keepContrast.width).toBeLessThan(180);
  await page.locator('#set-review-style-probe').evaluate((node) => node.remove());
});

test('Set Builder explains journey planning and normalizes incomplete energy ranges', async ({ page }) => {
  await page.route('**/api/set-builder/prepare-brief', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 300));
    await route.fulfill({
      json: {
        interpretation: {
          provider: 'ollama',
          model: 'browser-test',
          required: [],
          preferred: ['disco'],
          avoided: [],
          requestedGenres: ['disco & funk'],
          optionalGenres: [],
          genreSequence: ['disco & funk'],
          vibe: 'dance-party',
          curve: 'rise',
          drift: 'moderate',
        },
        journey: {
          evidence: 'ai-planned',
          model: 'browser-test',
          summary: 'A compact disco journey.',
          sections: [
            {
              id: 'opening',
              name: 'Opening',
              durationPercent: 100,
              energyStart: 6,
              energyEnd: '?',
              genres: ['disco & funk'],
              characteristics: ['groovy'],
              purpose: 'Build momentum',
            },
          ],
        },
      },
    });
  });
  await openView(page, 'Set Builder');
  await page.locator('#set-intention').fill('Build a disco set that grows in energy.');
  await page.locator('#interpret-set-intention').click();
  const progress = page.locator('#set-intention-progress');
  await expect(progress).toBeVisible();
  await expect(progress).toContainText('Understanding your set brief');
  await expect(progress.locator('li')).toHaveCount(3);
  await expect(progress).toBeHidden({ timeout: 5000 });
  await expect(page.locator('.journey-energy-value')).toHaveText('6 → 6');
  await expect(page.locator('.journey-energy-end')).toHaveValue('6');
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

test('Music Files separates filters, maintenance, and selection actions', async ({ browser }) => {
  const page = await browser.newPage();
  await page.route('**/api/downloaded-library?*', (route) =>
    route.fulfill({
      json: {
        tracks: [
          {
            id: 701,
            filename: 'night-drive.wav',
            title: 'Night Drive',
            artist: 'Test Artist',
            genre_category: 'Electronic / House',
            genre: 'Disco House',
            playlists: ['Browser Fixture'],
            available: true,
            artwork_available: false,
            analysis_status: 'complete',
            duration_seconds: 241,
            recording_code: 'HOU-000701',
            version_code: 'ORG',
            descriptors: [],
          },
        ],
        pagination: {
          page: 1,
          page_size: 50,
          filtered_total: 1,
          catalog_total: 1,
          total_pages: 1,
          analyzable_total: 0,
        },
        genres: { 'Electronic / House': 1 },
        detailed_genres: { 'Disco House': 1 },
        detailed_genres_by_category: { 'Electronic / House': { 'Disco House': 1 } },
        playlists: { 'Browser Fixture': 1 },
        review_states: { missing_artwork: 1, needs_attention: 1 },
      },
    }),
  );
  await page.goto('http://127.0.0.1:4173/');
  await openView(page, 'Music Files');

  const filters = page.locator('#downloaded-filter-panel');
  const maintenance = page.locator('#downloaded-maintenance-menu');
  await expect(filters).not.toHaveAttribute('open', '');
  await expect(maintenance).not.toHaveAttribute('open', '');

  await filters.locator('summary').click();
  await expect(filters).toHaveAttribute('open', '');
  const filterLayout = await page.evaluate(() => {
    const toolbar = document.querySelector('.downloaded-toolbar').getBoundingClientRect();
    const drawer = document.querySelector('.downloaded-filters').getBoundingClientRect();
    const summary = document.querySelector('.downloaded-filter-summary').getBoundingClientRect();
    return {
      alignedLeft: drawer.left >= toolbar.left - 1,
      alignedRight: drawer.right <= toolbar.right + 1,
      clearsSummary: drawer.bottom <= summary.top + 1,
    };
  });
  expect(filterLayout).toEqual({ alignedLeft: true, alignedRight: true, clearsSummary: true });
  await page.locator('#downloaded-analysis').evaluate((select) => {
    select.value = 'complete';
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await expect(page.locator('#downloaded-filter-badge')).toHaveText('1');
  await expect(page.locator('.downloaded-filter-chip')).toContainText('Analyzed');

  await maintenance.locator('summary').click();
  await expect(maintenance).toHaveAttribute('open', '');
  await expect(filters).not.toHaveAttribute('open', '');
  await expect(maintenance.getByRole('button', { name: 'Review vocabulary' })).toBeVisible();

  await page.getByLabel('Select Night Drive').check();
  const selection = page.locator('.downloaded-selection');
  await expect(selection).toHaveClass(/has-selection/);
  await expect(selection).toContainText('1 selected · 1 need artwork');
  await expect(selection.getByRole('button', { name: 'Edit identity' })).toBeVisible();
  await selection.locator('.downloaded-selection-more > summary').click();
  await expect(selection.getByRole('button', { name: 'Sync artwork' })).toBeVisible();

  await page.locator('.downloaded-filter-chip').click();
  await expect(page.locator('#downloaded-filter-badge')).toBeHidden();
  await page.close();
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
