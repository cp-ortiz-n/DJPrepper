import test from 'node:test';
import assert from 'node:assert/strict';

import { createDjLibraryFilters } from '../../../../frontend/features/dj-library/filters.js';
import { createDjLibraryIntelligence } from '../../../../frontend/features/dj-library/intelligence.js';
import { createDjLibrarySelection } from '../../../../frontend/features/dj-library/selection.js';
import { createDjLibraryView } from '../../../../frontend/features/dj-library/view.js';
import { createLibraryUiState } from '../../../../frontend/features/dj-library/model.js';
import { createFrontendServices } from '../../../../frontend/core/frontend-services.js';

function classList() {
  const values = new Set();
  return {
    contains: (value) => values.has(value),
    toggle(value, force) {
      if (force) values.add(value);
      else values.delete(value);
    },
  };
}

function control(value = '') {
  return {
    value,
    textContent: '',
    innerHTML: '',
    disabled: false,
    checked: false,
    indeterminate: false,
    options: [],
    selectedIndex: 0,
    replaceChildren(...children) {
      this.options = children;
      if (!children.some((child) => child.value === this.value)) this.value = children[0]?.value || '';
    },
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
  };
}

const option = (value, label) => ({ value, text: label });

test('DJ Library filters own state synchronization, category resets, and pagination requests', () => {
  const originalStorage = globalThis.localStorage;
  globalThis.localStorage = { getItem: () => null, setItem() {} };
  try {
    const state = createLibraryUiState(50);
    state.detailedGenre = 'salsa';
    const controls = new Map();
    for (const id of [
      'library-search',
      'library-role',
      'library-category',
      'library-detailed-genre',
      'library-preset',
      'library-sort',
      'library-result',
      'library-quality',
      'library-bpm-min',
      'library-bpm-max',
      'library-key',
      'library-energy',
      'library-vocals',
      'library-timing',
      'library-page-size',
      'library-key-display',
      'library-reset-filters',
      'library-reset-filters-top',
      'library-pagination',
      'library-pagination-top',
      'library-filter-count',
      'library-active-filter-count',
      'library-filter-chips',
    ])
      controls.set(`#${id}`, control());
    const sidebar = control();
    sidebar.querySelector = () => ({ classList: classList() });
    controls.set('#library-sidebar', sidebar);
    const calls = [];
    const requestState = {
      setPage: (page) => calls.push(['page', page]),
      update: (change) => Object.assign(state, change),
      debounce: (callback) => callback(),
      reset: () => calls.push(['reset']),
    };
    const filters = createDjLibraryFilters({
      $: (selector) => controls.get(selector),
      state,
      requestState,
      option,
      escapeHtml: String,
      syncControlUnlessEditing: (node, value) => (node.value = value),
      captureTextFilter: (node, target) => (target.search = node.value),
      renderTrackPagination: (_root, page, pages, total, changePage) => {
        calls.push(['pagination', page, pages, total]);
        if (!calls.some(([kind]) => kind === 'page-change-tested')) {
          calls.push(['page-change-tested']);
          changePage(2);
        }
      },
      reload: () => calls.push(['reload']),
      storage: { setItem() {} },
      documentRoot: { querySelector: () => ({ scrollIntoView() {} }), querySelectorAll: () => [] },
    });
    filters.bind({
      page: 1,
      total_pages: 3,
      filtered_total: 12,
      total: 20,
      facets: {
        categories: { 'Latin / Salsa': 4 },
        detailed_genres: { salsa: 4 },
        detailed_genres_by_category: { 'Latin / Salsa': { salsa: 4 } },
        presets: ['club'],
        keys: ['A minor'],
      },
    });

    controls.get('#library-category').value = 'latin';
    controls.get('#library-category').onchange();
    assert.equal(state.category, 'latin');
    assert.equal(state.detailedGenre, 'all');
    assert.ok(calls.some(([kind, value]) => kind === 'page' && value === 1));
    assert.ok(calls.some(([kind, value]) => kind === 'page' && value === 2));
    filters.reset();
    assert.ok(calls.some(([kind]) => kind === 'reset'));
  } finally {
    globalThis.localStorage = originalStorage;
  }
});

test('DJ Library selection owner keeps bulk controls and card state synchronized', () => {
  const cards = [1, 2].map((id) => ({
    dataset: { downloadedId: String(id), sourceName: `Track ${id}.wav` },
    hidden: false,
    classList: classList(),
  }));
  const boxes = cards.map((card, index) => ({
    value: String(index + 10),
    checked: false,
    closest: () => card,
  }));
  const exportType = { value: 'extended', checked: true };
  const selectionPanel = { classList: classList() };
  const controls = new Map(
    [
      'library-select-all',
      'library-download-selected',
      'library-selection-count',
      'library-genre-value',
      'library-change-genre',
      'library-edit-identity',
      'library-remove-selected',
      'library-reanalyze-selected',
      'library-key-analyze-selected',
    ].map((id) => [`#${id}`, control()]),
  );
  const services = createFrontendServices({
    api: { raw() {}, request() {}, errorMessage: (_payload, fallback) => fallback },
    dom: { $: (selector) => controls.get(selector), $$: () => [] },
    feedback: { notify() {}, confirmAction: async () => true, operationReceiptText: () => '' },
    descriptors: {
      chipsMarkup: () => '',
      editorMarkup: () => '',
      openEditorDialog: () => ({}),
      saveEditor: async () => ({}),
      inferEditor: async () => ({}),
    },
  });
  const selection = createDjLibrarySelection({
    services,
    loadLibrary: async () => {},
    loadDownloadedLibrary: async () => {},
    loadAnalysis: async () => {},
    loadReports: async () => {},
    loadJobs: async () => {},
    showView() {},
    startKeyAnalysis() {},
    setLoadedAt() {},
    invalidateMusicFiles() {},
    documentRoot: {
      querySelectorAll(selector) {
        return selector.includes('library-track-select') ? boxes : [exportType];
      },
      querySelector: () => selectionPanel,
      createElement: () => ({}),
    },
  });

  selection.setVisibleTracks([{ id: 1 }, { id: 2 }]);
  selection.bind();
  assert.equal(controls.get('#library-selection-count').textContent, '0 selected');
  assert.equal(controls.get('#library-download-selected').disabled, true);
  controls.get('#library-select-all').checked = true;
  controls.get('#library-select-all').onchange();
  assert.deepEqual(
    boxes.map((box) => box.checked),
    [true, true],
  );
  assert.equal(controls.get('#library-selection-count').textContent, '2 selected');
  assert.equal(controls.get('#library-download-selected').disabled, false);
  assert.equal(selectionPanel.classList.contains('has-selection'), true);
  assert.equal(
    cards.every((card) => card.classList.contains('is-selected')),
    true,
  );
});

test('DJ Library intelligence owner renders roles and compatibility without catalog orchestration', () => {
  const originalStorage = globalThis.localStorage;
  globalThis.localStorage = { getItem: () => null };
  const roleRoot = control();
  const compatibilityRoot = control();
  const select = control();
  const nodes = new Map([
    ['#role-groups', roleRoot],
    ['#compatibility-source', select],
    ['#compatible-tracks', compatibilityRoot],
  ]);
  const owner = createDjLibraryIntelligence({
    $: (selector) => nodes.get(selector),
    option,
    escapeHtml: String,
    revealTrack() {},
  });
  try {
    owner.render(
      [
        { source_name: 'Alpha.wav', bpm: 124, key: 'A minor', detected_style: 'melodic peak' },
        { source_name: 'Beta.wav', bpm: 125, key: 'A minor', detected_style: 'melodic peak' },
      ],
      new Map([
        ['alpha.wav', { id: 1 }],
        ['beta.wav', { id: 2 }],
      ]),
    );
    assert.match(roleRoot.innerHTML, /Peak-time/);
    select.value = 'Alpha.wav';
    select.onchange();
    assert.match(compatibilityRoot.innerHTML, /Beta\.wav/);
    assert.match(compatibilityRoot.innerHTML, /Tempo 40\/45/);
  } finally {
    globalThis.localStorage = originalStorage;
  }
});

test('DJ Library view owns empty-catalog presentation and selection reset', async () => {
  const list = control();
  const selectAll = control();
  const count = control();
  const download = control();
  const nodes = new Map([
    ['#library-list', list],
    ['#library-select-all', selectAll],
    ['#library-selection-count', count],
    ['#library-download-selected', download],
  ]);
  const services = createFrontendServices({
    api: { raw() {}, request() {}, errorMessage: (_payload, fallback) => fallback },
    dom: { $: (selector) => nodes.get(selector), $$: () => [] },
    feedback: { notify() {}, confirmAction: async () => true, operationReceiptText: () => '' },
    descriptors: {
      chipsMarkup: () => '',
      editorMarkup: () => '',
      openEditorDialog: () => ({}),
      saveEditor: async () => ({}),
      inferEditor: async () => ({}),
    },
  });
  const view = createDjLibraryView({
    services,
    compactAudioIsWithin: () => false,
    selection: { bindIdentityInference() {} },
  });
  await view.render({
    catalog: { total: 0 },
    grouped: new Map(),
    jobs: [],
    analysisByTrack: new Map(),
    downloadedByJob: new Map(),
  });
  assert.match(list.innerHTML, /No completed tracks yet/);
  assert.equal(selectAll.checked, false);
  assert.equal(selectAll.disabled, true);
  assert.equal(count.textContent, '0 selected');
  assert.equal(download.disabled, true);
});
