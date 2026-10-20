import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { createCandidateWaveformEditor } from '../../../web/features/processing/candidate-waveform-editor.js';
import {
  compatibility,
  createLibraryUiState,
  libraryQuery,
  normalizedKey,
} from '../../../web/features/dj-library/model.js';
import { createProcessingJobDetail } from '../../../web/features/processing/processing-job-detail.js';
import { createSearchableSelectController } from '../../../web/shared/searchable-selects.js';
import {
  genreAllocationTargets,
  interpretSetIntention,
  targetSetEnergy,
} from '../../../web/features/set-builder/policy.js';
import { createTrackMetadataUi } from '../../../web/shared/track-metadata-ui.js';

const escapeHtml = (value) => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');

test('composition modules stay within explicit ownership ceilings', () => {
  const ceilings = {
    'app.js': 900,
    'features/processing/candidate-review.js': 425,
    'features/processing/candidate-waveform-editor.js': 425,
    'features/dj-library/index.js': 250,
    'features/dj-library/filters.js': 225,
    'features/dj-library/intelligence.js': 75,
    'features/dj-library/model.js': 275,
    'features/dj-library/selection.js': 375,
    'features/dj-library/view.js': 575,
    'features/set-builder/index.js': 3500,
    'features/set-builder/policy.js': 340,
    'shared/track-metadata-ui.js': 280,
    'features/processing/processing-job-detail.js': 220,
    'shared/searchable-selects.js': 200,
  };
  for (const [name, ceiling] of Object.entries(ceilings)) {
    const path = fileURLToPath(new URL(`../../../web/${name}`, import.meta.url));
    const lines = readFileSync(path, 'utf8').split('\n').length;
    assert.ok(lines <= ceiling, `${name} has ${lines} lines; ownership ceiling is ${ceiling}`);
  }
});

test('Set Builder policy remains deterministic outside the feature controller', () => {
  const interpretation = interpretSetIntention(
    'Start melodic, then cumbia and merengue, and finish with latin techno.',
    ['latin techno', 'cumbia', 'merengue'],
  );
  assert.equal(interpretation.opening, 'melodic');
  assert.deepEqual(interpretation.genreSequence, ['cumbia', 'merengue', 'latin techno']);
  assert.deepEqual(genreAllocationTargets(['cumbia', 'salsa'], { cumbia: 33, salsa: 67 }, 9), {
    cumbia: 3,
    salsa: 6,
  });
  assert.equal(targetSetEnergy(0, 4, { vibe: 'warm-up', curve: 'rise' }), 0.2);
});

test('DJ Library model owns query state and musical compatibility without DOM rendering', () => {
  const state = createLibraryUiState(25);
  state.category = 'latin';
  state.bpmMin = '118';
  const query = libraryQuery(state);
  assert.equal(query.get('category'), 'latin');
  assert.equal(query.get('bpm_min'), '118');
  assert.equal(query.get('page_size'), '25');
  assert.equal(normalizedKey('Db minor'), 'C# minor');
  assert.ok(compatibility({ bpm: 124, key: 'A minor' }, { bpm: 125, key: 'A minor' }).score >= 80);
});

test('track metadata UI owns genre normalization, summaries, and folder rendering', () => {
  const values = new Map();
  const storage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
  };
  const ui = createTrackMetadataUi({
    escapeHtml,
    apiErrorMessage: (_, fallback) => fallback,
    notify() {},
    operationReceiptText: () => '',
    storage,
  });
  assert.equal(ui.normalizedGenreCategory('house'), 'Electronic / House / House');
  assert.deepEqual(ui.detailedGenreSummary('salsa, salsa, merengue, cumbia'), {
    label: 'salsa · merengue +1',
    title: 'salsa, merengue, cumbia',
    empty: false,
  });
  assert.match(ui.genreFolderTree([['Electronic / House / Latin House', 4]], 'filter-downloaded-genre'), /Latin House/);
});

test('processing detail renderer owns arrangement timeline markup and seeking', () => {
  const segments = [];
  const root = {
    innerHTML: '',
    querySelectorAll() {
      const match = this.innerHTML.match(/data-time="([^"]+)"/);
      if (!match) return [];
      const segment = { dataset: { time: match[1] }, onclick: null };
      segments.push(segment);
      return [segment];
    },
  };
  const sought = [];
  const detail = createProcessingJobDetail({ clock: (value) => String(value), escapeHtml });
  detail.renderArrangementTimeline(
    root,
    { arrangement: [{ start: 2, end: 10, label: 'verse', confidence: 0.8 }] },
    20,
    { setTime: (value) => sought.push(value) },
  );
  assert.match(root.innerHTML, /Song section/);
  assert.match(root.innerHTML, /verse/);
  segments[0].onclick();
  assert.deepEqual(sought, [2]);
});

test('candidate waveform editor exposes a narrow controller contract', () => {
  const editor = createCandidateWaveformEditor({});
  assert.deepEqual(Object.keys(editor).sort(), [
    'initializeCustomWaveform',
    'initializeInsertionWaveform',
    'isPreviewing',
    'previewArrangementInsertion',
    'stopArrangementPreview',
    'updateInsertionVisualization',
  ]);
  assert.equal(editor.isPreviewing({}), false);
  assert.doesNotThrow(() => editor.stopArrangementPreview());
});

test('searchable select controller owns observation lifecycle', () => {
  const calls = [];
  const OriginalMutationObserver = globalThis.MutationObserver;
  globalThis.MutationObserver = class {
    observe(...args) {
      calls.push(['observe', ...args]);
    }
    disconnect() {
      calls.push(['disconnect']);
    }
  };
  try {
    const root = { querySelectorAll: () => [] };
    const storageRoot = {};
    const controller = createSearchableSelectController({ root, storageRoot });
    controller.start();
    controller.stop();
    assert.equal(calls[0][0], 'observe');
    assert.deepEqual(calls.at(-1), ['disconnect']);
  } finally {
    globalThis.MutationObserver = OriginalMutationObserver;
  }
});
