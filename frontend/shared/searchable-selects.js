export function createSearchableSelectController({ root = document, storageRoot = document.documentElement } = {}) {
  let refreshQueued = false;
  let generatedSelectId = 0;

  function enhance(select) {
    if (!select.id) select.id = `app-select-${++generatedSelectId}`;
    const id = select.id;
    let search = root.getElementById(`${id}-combobox-search`);
    const eligible = !select.hidden && select.getAttribute('aria-hidden') !== 'true';
    if (!eligible) {
      if (search) {
        search.hidden = true;
        const menu = root.getElementById(`${id}-combobox-menu`);
        if (menu) menu.hidden = true;
      }
      return;
    }
    if (!search) {
      let container = select.closest('label');
      if (!container) {
        container = document.createElement('span');
        container.className = 'select-combobox-shell';
        select.before(container);
        container.append(select);
      }
      container.classList.add('has-searchable-select');
      search = document.createElement('input');
      search.id = `${id}-combobox-search`;
      search.type = 'text';
      search.className = 'select-search-input';
      search.autocomplete = 'off';
      search.spellcheck = false;
      search.placeholder = 'Type to search…';
      search.setAttribute(
        'aria-label',
        `Search ${select.closest('label')?.childNodes[0]?.textContent?.trim() || 'options'}`,
      );
      search.setAttribute('role', 'combobox');
      search.setAttribute('aria-autocomplete', 'list');
      search.setAttribute('aria-expanded', 'false');
      select.before(search);
      const menu = document.createElement('div');
      menu.id = `${id}-combobox-menu`;
      menu.className = 'select-combobox-menu';
      menu.setAttribute('role', 'listbox');
      menu.hidden = true;
      search.setAttribute('aria-controls', menu.id);
      search.after(menu);
      let activeIndex = -1;
      const selectedLabel = () => {
        const selected = [...select.selectedOptions].filter((option) => option.value !== 'all');
        if (!select.multiple || selected.length <= 1)
          return selected[0]?.textContent || select.selectedOptions[0]?.textContent || '';
        return `${selected.length} genres selected`;
      };
      const closeMenu = () => {
        menu.hidden = true;
        activeIndex = -1;
        search.setAttribute('aria-expanded', 'false');
        search.removeAttribute('aria-activedescendant');
      };
      const chooseOption = (selectedOption) => {
        if (select.multiple) {
          const any = select.querySelector('option[value="all"]');
          if (selectedOption.value === 'all') {
            [...select.options].forEach((item) => {
              item.selected = item.value === 'all';
            });
          } else {
            if (any) any.selected = false;
            selectedOption.selected = !selectedOption.selected;
            if (![...select.selectedOptions].some((item) => item.value !== 'all') && any) any.selected = true;
          }
        } else select.value = selectedOption.value;
        search.value = selectedLabel();
        select.dispatchEvent(new Event('change', { bubbles: true }));
        if (select.multiple) search.value = '';
        closeMenu();
      };
      const renderMenu = () => {
        const entered = search.value.trim();
        const query = entered === selectedLabel() ? '' : entered.toLocaleLowerCase();
        const matches = [...select.options].filter(
          (item) => !query || item.textContent.toLocaleLowerCase().includes(query),
        );
        search.classList.toggle('no-results', Boolean(query) && matches.length === 0);
        menu.replaceChildren();
        activeIndex = matches.length ? 0 : -1;
        matches.slice(0, 20).forEach((item, index) => {
          const button = document.createElement('button');
          button.type = 'button';
          button.id = `${id}-combobox-option-${index}`;
          button.className = index === activeIndex ? 'active' : '';
          button.setAttribute('role', 'option');
          button.setAttribute('aria-selected', String(item.value === select.value));
          button.textContent = item.textContent;
          button.addEventListener('mousedown', (event) => event.preventDefault());
          button.addEventListener('click', () => chooseOption(item));
          menu.append(button);
        });
        const summary = document.createElement('small');
        summary.textContent = matches.length
          ? `${matches.length} option${matches.length === 1 ? '' : 's'}${matches.length > 20 ? ' · keep typing to narrow the list' : ''}`
          : 'No matching options';
        menu.append(summary);
        menu.hidden = false;
        search.setAttribute('aria-expanded', 'true');
        if (activeIndex >= 0) search.setAttribute('aria-activedescendant', `${id}-combobox-option-${activeIndex}`);
      };
      const moveActive = (direction) => {
        const items = [...menu.querySelectorAll('button')];
        if (!items.length) return;
        activeIndex = (activeIndex + direction + items.length) % items.length;
        items.forEach((item, index) => item.classList.toggle('active', index === activeIndex));
        search.setAttribute('aria-activedescendant', items[activeIndex].id);
        items[activeIndex].scrollIntoView({ block: 'nearest' });
      };
      search.addEventListener('focus', () => {
        if (select.multiple) search.value = '';
        else search.select();
        renderMenu();
      });
      search.addEventListener('click', () => {
        if (select.multiple && search.value === selectedLabel()) {
          search.value = '';
          renderMenu();
        }
      });
      search.addEventListener('input', renderMenu);
      search.addEventListener('blur', () =>
        setTimeout(() => {
          search.value = selectedLabel();
          search.classList.remove('no-results');
          closeMenu();
        }, 120),
      );
      search.addEventListener('keydown', (event) => {
        if (event.key === 'ArrowDown') {
          event.preventDefault();
          if (menu.hidden) renderMenu();
          else moveActive(1);
        } else if (event.key === 'ArrowUp') {
          event.preventDefault();
          if (menu.hidden) renderMenu();
          else moveActive(-1);
        } else if (event.key === 'Enter' && !menu.hidden && activeIndex >= 0) {
          event.preventDefault();
          menu.querySelectorAll('button')[activeIndex]?.click();
        } else if (event.key === 'Escape') {
          event.preventDefault();
          search.value = selectedLabel();
          closeMenu();
        }
      });
      select.addEventListener('change', () => {
        search.value = selectedLabel();
        search.classList.remove('no-results');
        closeMenu();
      });
      search.value = selectedLabel();
    }
    const shouldShow = select.options.length > 0;
    search.hidden = !shouldShow;
    select.classList.toggle('searchable-native-select', shouldShow);
    if (shouldShow && document.activeElement !== search) search.value = select.selectedOptions[0]?.textContent || '';
    if (!shouldShow) {
      search.value = '';
      search.nextElementSibling.hidden = true;
    }
  }

  function refresh() {
    root.querySelectorAll('select[data-searchable]').forEach(enhance);
  }

  const observer = new MutationObserver(() => {
    if (refreshQueued) return;
    refreshQueued = true;
    queueMicrotask(() => {
      refreshQueued = false;
      refresh();
    });
  });

  return {
    start() {
      observer.observe(storageRoot, { childList: true, subtree: true });
      refresh();
    },
    refresh,
    stop() {
      observer.disconnect();
    },
  };
}
