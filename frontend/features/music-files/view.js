export function renderMusicFilesFilterChips({ container, filters, onRemove }) {
  container.replaceChildren();
  container.hidden = filters.length === 0;
  for (const filter of filters) {
    const button = container.ownerDocument.createElement('button');
    button.type = 'button';
    button.className = 'downloaded-filter-chip';
    button.dataset.filter = filter.key;
    button.setAttribute('aria-label', `Remove ${filter.label} filter: ${filter.value}`);
    const label = container.ownerDocument.createElement('span');
    label.textContent = filter.label;
    const value = container.ownerDocument.createElement('strong');
    value.textContent = filter.value;
    const remove = container.ownerDocument.createElement('i');
    remove.textContent = '×';
    remove.setAttribute('aria-hidden', 'true');
    button.append(label, value, remove);
    button.onclick = () => onRemove(filter.key);
    container.append(button);
  }
}

export function updateMusicFilesFilterDisclosure({ filterPanel, filterBadge, resetButton, filterCount }) {
  filterPanel.classList.toggle('has-active-filters', filterCount > 0);
  filterBadge.hidden = filterCount === 0;
  filterBadge.textContent = String(filterCount);
  resetButton.hidden = filterCount === 0;
}

export function closeMusicFilesMenus(root, except = null) {
  root.querySelectorAll('details[open]').forEach((details) => {
    if (details !== except && details.matches('.downloaded-filter-panel,.downloaded-maintenance-menu,.downloaded-selection-more')) {
      details.open = false;
    }
  });
}
