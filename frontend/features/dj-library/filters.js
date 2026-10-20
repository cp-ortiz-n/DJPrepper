import { LIBRARY_ROLE_INFO, formatLibraryKey, libraryKeyMode } from './model.js';

export function createDjLibraryFilters({
  $,
  state,
  requestState,
  option,
  escapeHtml,
  syncControlUnlessEditing,
  captureTextFilter,
  renderTrackPagination,
  reload,
  storage = globalThis.localStorage,
  documentRoot = globalThis.document,
}) {
  const request = (page = 1) => {
    requestState.setPage(page);
    reload();
  };

  const fillSelect = (select, values, label, stateKey) => {
    const current = state[stateKey];
    select.replaceChildren(
      option('all', label),
      ...[...new Set(values.filter(Boolean))]
        .sort()
        .map((value) => option(value, value === 'unclassified' ? 'Unclassified' : value)),
    );
    select.value = [...select.options].some((item) => item.value === current) ? current : 'all';
  };

  const reset = () => {
    requestState.reset();
    reload();
  };

  const changePage = (page) => {
    requestState.setPage(page);
    reload();
    documentRoot.querySelector('.library-toolbar')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  function bind(catalog) {
    const controls = {
      search: $('#library-search'),
      role: $('#library-role'),
      category: $('#library-category'),
      detailedGenre: $('#library-detailed-genre'),
      preset: $('#library-preset'),
      sort: $('#library-sort'),
      result: $('#library-result'),
      quality: $('#library-quality'),
      bpmMin: $('#library-bpm-min'),
      bpmMax: $('#library-bpm-max'),
      key: $('#library-key'),
      energy: $('#library-energy'),
      vocals: $('#library-vocals'),
      timing: $('#library-timing'),
    };

    controls.role.replaceChildren(
      option('all', 'All roles'),
      ...Object.keys(LIBRARY_ROLE_INFO).map((value) => option(value, LIBRARY_ROLE_INFO[value][0])),
    );
    controls.role.value = state.role;
    const categories = Object.keys(catalog.facets?.categories || {}).flatMap((name) => {
      const parts = name.split(' / ');
      return parts.map((_, index) =>
        parts
          .slice(0, index + 1)
          .join(' / ')
          .toLowerCase(),
      );
    });
    fillSelect(controls.category, categories, 'All parent genres', 'category');

    const detailedByCategory = catalog.facets?.detailed_genres_by_category || {};
    const detailedCounts =
      state.category === 'all'
        ? catalog.facets?.detailed_genres || {}
        : Object.entries(detailedByCategory).reduce((counts, [category, genres]) => {
            const selected = state.category.toLowerCase();
            if (category.toLowerCase() === selected || category.toLowerCase().startsWith(`${selected} / `)) {
              Object.entries(genres).forEach(([genre, count]) => {
                counts[genre] = (counts[genre] || 0) + Number(count);
              });
            }
            return counts;
          }, {});
    controls.detailedGenre.replaceChildren(
      option('all', state.category === 'all' ? 'All detailed genres' : 'Any detailed genre'),
      ...Object.entries(detailedCounts)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([genre, count]) => option(genre, `${genre} (${count})`)),
    );
    controls.detailedGenre.value = [...controls.detailedGenre.options].some(
      (item) => item.value === state.detailedGenre,
    )
      ? state.detailedGenre
      : 'all';
    if (controls.detailedGenre.value === 'all') state.detailedGenre = 'all';
    fillSelect(controls.preset, catalog.facets?.presets || [], 'All effective presets', 'preset');
    fillSelect(controls.key, catalog.facets?.keys || [], 'All keys', 'key');
    Object.entries(controls).forEach(([name, control]) => {
      if (['category', 'preset', 'key', 'role'].includes(name)) return;
      syncControlUnlessEditing(control, state[name] ?? control.value);
    });

    $('#library-page-size').value = String(state.pageSize);
    $('#library-key-display').value = libraryKeyMode();
    controls.search.oninput = () => {
      captureTextFilter(controls.search, state);
      requestState.debounce(() => request(1));
    };
    Object.entries(controls)
      .filter(([name]) => !['search', 'category'].includes(name))
      .forEach(([name, control]) => {
        control.onchange = () => {
          state[name] = control.value;
          request(1);
        };
      });
    controls.category.onchange = () => {
      state.category = controls.category.value;
      state.detailedGenre = 'all';
      request(1);
    };
    [controls.bpmMin, controls.bpmMax].forEach((input) => {
      input.oninput = () => {
        requestState.debounce(() => {
          requestState.update({ bpmMin: controls.bpmMin.value, bpmMax: controls.bpmMax.value });
          reload();
        });
      };
    });
    $('#library-page-size').onchange = (event) => {
      requestState.update({ pageSize: Number(event.target.value) });
      storage.setItem('dj-library-page-size', String(state.pageSize));
      reload();
    };
    $('#library-key-display').onchange = (event) => {
      storage.setItem('audioextender-key-view', event.target.value);
      documentRoot
        .querySelectorAll('.library-key-value')
        .forEach((node) => (node.textContent = formatLibraryKey(node.dataset.standard, event.target.value)));
    };
    $('#library-reset-filters').onclick = reset;
    $('#library-reset-filters-top').onclick = reset;

    renderTrackPagination(
      $('#library-pagination'),
      catalog.page,
      catalog.total_pages,
      catalog.filtered_total,
      changePage,
    );
    renderTrackPagination(
      $('#library-pagination-top'),
      catalog.page,
      catalog.total_pages,
      catalog.filtered_total,
      changePage,
    );
    $('#library-filter-count').textContent =
      `${catalog.filtered_total} of ${catalog.total} tracks${catalog.total_pages > 1 ? ` · page ${catalog.page}/${catalog.total_pages}` : ''}`;

    const active = [
      state.search,
      state.role !== 'all',
      state.category !== 'all',
      state.detailedGenre !== 'all',
      state.preset !== 'all',
      state.result !== 'all',
      state.quality !== 'all',
      state.bpmMin,
      state.bpmMax,
      state.key !== 'all',
      state.energy !== 'all',
      state.vocals !== 'all',
      state.timing !== 'all',
    ].filter(Boolean).length;
    $('#library-active-filter-count').textContent = active ? `${active} active` : '';
    $('#library-filter-chips').innerHTML = [
      state.role !== 'all' && `Role: ${LIBRARY_ROLE_INFO[state.role]?.[0] || state.role}`,
      state.category !== 'all' && `Parent: ${state.category}`,
      state.detailedGenre !== 'all' && `Detailed: ${state.detailedGenre}`,
      state.preset !== 'all' && `Preset: ${state.preset}`,
      state.quality !== 'all' &&
        `Quality: ${controls.quality.options[controls.quality.selectedIndex]?.text || state.quality}`,
      state.key !== 'all' && `Key: ${formatLibraryKey(state.key)}`,
    ]
      .filter(Boolean)
      .map((label) => `<span>${escapeHtml(label)}</span>`)
      .join('');

    const sidebar = $('#library-sidebar');
    sidebar
      .querySelector('.library-side-all')
      ?.classList.toggle('active', state.role === 'all' && state.category === 'all');
    sidebar
      .querySelectorAll('.library-side-role')
      .forEach((button) => button.classList.toggle('active', state.role === button.dataset.value));
    sidebar
      .querySelectorAll('.library-side-category')
      .forEach((button) => button.classList.toggle('active', state.category === button.dataset.value));
  }

  return Object.freeze({ bind, reset });
}
