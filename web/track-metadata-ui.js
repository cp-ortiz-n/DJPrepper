export const LATIN_GENRE_CATEGORIES = [
  'Latin / Reggaeton',
  'Latin / Salsa',
  'Latin / Cumbia',
  'Latin / Merengue',
  'Latin / Zapateado',
  'Latin / Corridos',
  'Latin / Regional Mexican',
  'Latin / Bachata',
  'Latin / Dembow',
  'Latin / Latin Pop',
  'Latin / Latin Jazz',
  'Latin / Bolero',
  'Latin / Vallenato',
  'Latin / Brazilian',
  'Latin / Flamenco',
  'Latin / Latin Rock',
  'Latin / Latin Indie',
  'Latin / Latin Ska',
  'Latin / Latin Hip-Hop',
  'Latin / Latin R&B',
  'Latin / Other',
];

export const ELECTRONIC_GENRE_CATEGORIES = [
  'Electronic / Techno / Techno',
  'Electronic / Techno / Schranz',
  'Electronic / Techno / Hard Techno',
  'Electronic / Techno / Acid Techno',
  'Electronic / Techno / Melodic Techno',
  'Electronic / Techno / Minimal Techno',
  'Electronic / Techno / Industrial Techno',
  'Electronic / Techno / Hypnotic Techno',
  'Electronic / Techno / Peak-Time Techno',
  'Electronic / House / House',
  'Electronic / House / Deep House',
  'Electronic / House / Afro House',
  'Electronic / House / Latin House',
  'Electronic / House / Tech House',
  'Electronic / House / Progressive House',
  'Electronic / House / Melodic House',
  'Electronic / House / Organic House',
  'Electronic / House / Bass House',
  'Electronic / House / Soulful House',
  'Electronic / House / Funky House',
  'Electronic / House / Amapiano',
  'Electronic / Bass / Deep Bass',
  'Electronic / Bass / Future Bass',
  'Electronic / Bass / Dubstep',
  'Electronic / Bass / Moombahton',
  'Electronic / Bass / Phonk',
  'Electronic / Drum & Bass / Drum & Bass',
  'Electronic / Drum & Bass / Liquid',
  'Electronic / Drum & Bass / Jungle',
  'Electronic / Trance / Trance',
  'Electronic / Trance / Psytrance',
  'Electronic / Trance / Hard Trance',
  'Electronic / Garage / Garage',
  'Electronic / Garage / UK Garage',
  'Electronic / Breaks / Breakbeat',
  'Electronic / Breaks / Big Beat',
  'Electronic / Downtempo / Trip Hop',
  'Electronic / Hardcore / Hardcore',
  'Electronic / Hardcore / Gabber',
  'Electronic / Hardcore / Hardstyle',
  'Electronic / General',
  'Electronic / Electronic / Electro',
];

export const GENRE_CATEGORIES = [
  ...ELECTRONIC_GENRE_CATEGORIES,
  'Afro & Amapiano',
  'Hip-Hop & Rap',
  'Hip-Hop & Rap / Crunk',
  'Hip-Hop & Rap / Hyphy',
  'R&B & Soul',
  'Disco & Funk',
  'Rock & Alternative',
  'Pop',
  'Pop / Chanson',
  'Ambient & Chill',
  ...LATIN_GENRE_CATEGORIES,
  'Other',
];

export function createTrackMetadataUi({
  escapeHtml,
  apiErrorMessage,
  notify,
  operationReceiptText,
  storage = localStorage,
  fetchImpl = fetch,
} = {}) {
  const collapsedGenreFolders = new Set(JSON.parse(storage.getItem('dj-collapsed-genre-folders') || '[]'));

  function normalizedGenreCategory(value) {
    const name = String(value || 'Other').trim();
    return (
      {
        techno: 'Electronic / Techno / Techno',
        house: 'Electronic / House / House',
        trance: 'Electronic / Trance / Trance',
        'drum & bass': 'Electronic / Drum & Bass / Drum & Bass',
        garage: 'Electronic / Garage / Garage',
        breaks: 'Electronic / Breaks / Breakbeat',
        electronic: 'Electronic / General',
        'electronic / electronic / electronic': 'Electronic / General',
      }[name.toLowerCase()] || name
    );
  }

  function genreFolderTree(entries, buttonClass) {
    const root = { children: new Map(), count: 0, selfCount: 0 };
    entries.forEach(([name, count]) => {
      let node = root;
      node.count += Number(count);
      String(name)
        .split(' / ')
        .forEach((part) => {
          if (!node.children.has(part))
            node.children.set(part, { children: new Map(), count: 0, selfCount: 0, value: '' });
          node = node.children.get(part);
          node.count += Number(count);
        });
      node.value = name;
      node.selfCount += Number(count);
    });
    const render = (node, path = [], depth = 0) =>
      [...node.children.entries()]
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([label, child]) => {
          const nextPath = [...path, label];
          const key = nextPath.join(' / ');
          if (!child.children.size) {
            const value = buttonClass === 'library-side-category' ? child.value.toLowerCase() : child.value;
            return `<button type="button" class="${buttonClass}${depth ? ' nested' : ''}" data-depth="${depth}" data-value="${escapeHtml(value)}"><span>${escapeHtml(label)}</span><b>${child.count}</b></button>`;
          }
          const open = collapsedGenreFolders.has(key) ? '' : ' open';
          const parentValue = buttonClass === 'library-side-category' ? key.toLowerCase() : key;
          const generalValue = buttonClass === 'library-side-category' ? child.value.toLowerCase() : child.value;
          const general = child.selfCount
            ? `<button type="button" class="${buttonClass} nested" data-depth="${depth + 1}" data-value="${escapeHtml(generalValue)}"><span>General</span><b>${child.selfCount}</b></button>`
            : '';
          return `<details class="genre-folder-group" data-folder="${escapeHtml(key)}"${open}><summary><button type="button" class="${buttonClass} genre-folder-parent-filter" data-value="${escapeHtml(parentValue)}"><span>${escapeHtml(label)}</span><b>${child.count}</b></button><i aria-hidden="true">›</i></summary><div>${general}${render(child, nextPath, depth + 1)}</div></details>`;
        })
        .join('');
    return render(root);
  }

  function bindGenreFolderState(scope) {
    scope.querySelectorAll('.genre-folder-parent-filter').forEach((button) =>
      button.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
      }),
    );
    scope.querySelectorAll('.genre-folder-group').forEach((folder) =>
      folder.addEventListener('toggle', () => {
        if (folder.open) collapsedGenreFolders.delete(folder.dataset.folder);
        else collapsedGenreFolders.add(folder.dataset.folder);
        storage.setItem('dj-collapsed-genre-folders', JSON.stringify([...collapsedGenreFolders]));
      }),
    );
  }

  function genreEditorMarkup(current, suggested = '', compact = false) {
    const choices = [...new Set([current, suggested, ...GENRE_CATEGORIES].filter(Boolean))].sort();
    return `<form class="inline-genre-editor${compact ? ' compact' : ''}" hidden>
      <div><label>Genre<select class="inline-genre-select">${choices.map((name) => `<option value="${escapeHtml(name)}"${name === current ? ' selected' : ''}>${escapeHtml(name)}</option>`).join('')}</select></label>
      <label>Or type a custom genre<input class="inline-genre-custom" maxlength="80" placeholder="Custom genre"></label></div>
      ${suggested && suggested !== current ? `<p class="genre-suggestion">Detected from metadata: <b>${escapeHtml(suggested)}</b> <button type="button" class="use-genre-suggestion">Use detected</button></p>` : ''}
      <p class="genre-folder-preview">Folder: ${escapeHtml(current.replace(' / ', '/'))}/</p>
      <div class="inline-genre-actions"><button type="submit">Save & move</button><button type="button" class="button secondary cancel-genre-edit">Cancel</button></div>
    </form>`;
  }

  function metadataEditorMarkup(track, position = 1, total = 1) {
    const current = track.genre_category || 'Other';
    const choices = [...new Set([current, ...GENRE_CATEGORIES].filter(Boolean))].sort();
    const playlist = (track.playlists || [])[0] || 'Imported Singles';
    return `<form class="track-metadata-editor" hidden>
      <header><div><strong>Edit track metadata</strong><span>Updates the WAV, folder, Music Files, and linked Library entry.</span></div><div class="metadata-review-position"><span>${position} of ${total}</span><button type="button" class="button secondary close-metadata-editor" aria-label="Close metadata editor">×</button></div></header>
      <div class="metadata-fields"><label>Title<input name="title" maxlength="300" required value="${escapeHtml(track.title || '')}"></label><label>Artist<input name="artist" maxlength="300" value="${escapeHtml(track.artist || '')}"></label><label>Genre<select name="genre_category">${choices.map((name) => `<option value="${escapeHtml(name)}"${name === current ? ' selected' : ''}>${escapeHtml(name)}</option>`).join('')}</select></label><label>Detailed genre tags<input name="genre" maxlength="500" value="${escapeHtml(track.genre || '')}" placeholder="e.g. salsa, merengue"></label><label>Album / source playlist<input name="playlist_name" maxlength="180" required value="${escapeHtml(playlist)}"></label><label>Artwork image URL<input name="artwork_url" type="url" maxlength="1000" value="${escapeHtml(track.artwork_url || '')}" placeholder="Direct Spotify or YouTube cover image URL"></label><label class="metadata-rename"><input name="rename_file" type="checkbox"> Rename WAV to Artist - Title</label></div>
      <p class="metadata-message"></p><div class="metadata-actions"><div class="metadata-navigation"><button type="button" class="button secondary metadata-previous">← Previous</button><button type="button" class="button secondary metadata-next">Next →</button></div><div class="metadata-save-actions"><button type="submit" class="button secondary">Save</button><button type="submit" data-action="next">Save & next →</button></div></div>
    </form>`;
  }

  function detailedGenreSummary(rawGenres) {
    const tags = [
      ...new Set(
        String(rawGenres || '')
          .split(',')
          .map((tag) => tag.trim())
          .filter(Boolean),
      ),
    ];
    if (!tags.length) return { label: 'No detailed genre', title: 'No detailed genre metadata', empty: true };
    const visible = tags.slice(0, 2);
    return {
      label: `${visible.join(' · ')}${tags.length > 2 ? ` +${tags.length - 2}` : ''}`,
      title: tags.join(', '),
      empty: false,
    };
  }

  function bindGenreEditor(editor, trackIds, afterSave) {
    const select = editor.querySelector('.inline-genre-select');
    const custom = editor.querySelector('.inline-genre-custom');
    const preview = editor.querySelector('.genre-folder-preview');
    const value = () => custom.value.trim() || select.value;
    const sync = () => {
      preview.textContent = `Folder: ${value().replace(' / ', '/')}/`;
    };
    select.onchange = () => {
      custom.value = '';
      sync();
    };
    custom.oninput = sync;
    editor.querySelector('.use-genre-suggestion')?.addEventListener('click', (event) => {
      select.value = event.currentTarget.closest('.genre-suggestion').querySelector('b').textContent;
      custom.value = '';
      sync();
    });
    editor.querySelector('.cancel-genre-edit').onclick = () => {
      editor.hidden = true;
    };
    editor.onsubmit = async (event) => {
      event.preventDefault();
      const genre = value();
      if (!genre || !trackIds().length) return;
      const save = editor.querySelector('[type="submit"]');
      save.disabled = true;
      save.textContent = 'Moving…';
      try {
        const response = await fetchImpl('/api/downloaded-library/genre', {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ track_ids: trackIds(), genre_category: genre }),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(apiErrorMessage(payload, 'Could not change genre.'));
        notify(operationReceiptText(payload.receipt), payload.receipt?.failures?.length ? 'danger' : 'success', {
          timeout: 9000,
        });
        await afterSave(payload);
      } catch (error) {
        alert(error.message);
        save.disabled = false;
        save.textContent = 'Save & move';
      }
    };
  }

  return {
    bindGenreEditor,
    bindGenreFolderState,
    collapsedGenreFolders,
    detailedGenreSummary,
    genreEditorMarkup,
    genreFolderTree,
    metadataEditorMarkup,
    normalizedGenreCategory,
  };
}
