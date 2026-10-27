import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { beginButtonAction } from '../../../../frontend/features/set-builder/ui-state.js';

function fakeButton({ disabled = false, text = 'Run', attributes = {} } = {}) {
  const values = new Map(Object.entries(attributes));
  return {
    disabled,
    textContent: text,
    getAttribute: (name) => values.get(name) ?? null,
    removeAttribute: (name) => values.delete(name),
    setAttribute: (name, value) => values.set(name, String(value)),
  };
}

test('Set Builder async button state is accessible and restores exactly once', () => {
  const button = fakeButton({ attributes: { 'aria-label': 'Regenerate unlocked' } });
  const restore = beginButtonAction(button, 'Regenerating unlocked tracks…');

  assert.equal(button.disabled, true);
  assert.equal(button.textContent, 'Regenerating unlocked tracks…');
  assert.equal(button.getAttribute('aria-busy'), 'true');
  assert.equal(button.getAttribute('aria-label'), 'Regenerating unlocked tracks…');

  restore();
  restore();
  assert.equal(button.disabled, false);
  assert.equal(button.textContent, 'Run');
  assert.equal(button.getAttribute('aria-busy'), null);
  assert.equal(button.getAttribute('aria-label'), 'Regenerate unlocked');
});

test('Set Builder async button state preserves pre-existing disabled and ARIA state', () => {
  const button = fakeButton({
    disabled: true,
    text: 'Unavailable',
    attributes: { 'aria-busy': 'false' },
  });
  const restore = beginButtonAction(button);
  restore();

  assert.equal(button.disabled, true);
  assert.equal(button.textContent, 'Unavailable');
  assert.equal(button.getAttribute('aria-busy'), 'false');
  assert.equal(button.getAttribute('aria-label'), null);
  assert.doesNotThrow(() => beginButtonAction(null)());
});

test('Set Builder presentation uses shared action hierarchy and readable type tokens', () => {
  const html = readFileSync('frontend/index.html', 'utf8');
  const planView = readFileSync('frontend/features/set-builder/plan-view.js', 'utf8');
  const transitionEditor = readFileSync('frontend/features/set-builder/transition-editor.js', 'utf8');
  const sharedSelects = readFileSync('frontend/styles/shared/11-shared-searchable-select.css', 'utf8');
  const styleFiles = [
    'frontend/styles/features/set-builder/60-set-builder-brief.css',
    'frontend/styles/features/set-builder/61-set-builder-workspace.css',
    'frontend/styles/features/set-builder/62-set-builder-shell.css',
  ].map((path) => readFileSync(path, 'utf8'));

  for (const id of ['set-generate', 'save-set', 'submit-set-review', 'review-set-action']) {
    assert.match(html, new RegExp(`id="${id}"[^>]*class="[^"]*button (?:primary|secondary|tertiary|destructive)`));
  }
  assert.match(html, /class="button destructive confirm-track-rejection"/);
  assert.match(planView, /class="button destructive set-remove"/);
  assert.match(planView, /class="button tertiary set-inspect-track"/);
  assert.match(transitionEditor, /class="button primary preview-transition"/);
  assert.match(transitionEditor, /class="button secondary close-transition-editor-bottom"/);

  assert.match(styleFiles[0], /--set-type-label: var\(--type-label\)/);
  assert.match(styleFiles[0], /--set-type-body: var\(--type-body\)/);
  styleFiles.forEach((css) => assert.doesNotMatch(css, /font-size:\s*(?:[1-9]|10|11)px/));
  assert.match(sharedSelects, /\.select-combobox-menu/);
  assert.doesNotMatch(styleFiles.join('\n'), /\.select-combobox-menu/);
});
