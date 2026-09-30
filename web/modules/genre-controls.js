import {escapeHtml} from './ui.js';

export function normalizedGenreCategory(value) {
  const name = String(value || 'Other').trim();
  return ({techno:'Electronic / Techno / Techno',house:'Electronic / House / House',trance:'Electronic / Trance / Trance','drum & bass':'Electronic / Drum & Bass / Drum & Bass',garage:'Electronic / Garage / Garage',breaks:'Electronic / Breaks / Breakbeat',electronic:'Electronic / General','electronic / electronic / electronic':'Electronic / General'})[name.toLowerCase()] || name;
}

export function genreEditorMarkup(current, suggested = '', compact = false, categories = []) {
  const choices = [...new Set([current, suggested, ...categories].filter(Boolean))].sort();
  return `<form class="inline-genre-editor${compact ? ' compact' : ''}" hidden>
    <div><label>Genre<select class="inline-genre-select">${choices.map(name => `<option value="${escapeHtml(name)}"${name === current ? ' selected' : ''}>${escapeHtml(name)}</option>`).join('')}</select></label>
    <label>Or type a custom genre<input class="inline-genre-custom" maxlength="80" placeholder="Custom genre"></label></div>
    ${suggested && suggested !== current ? `<p class="genre-suggestion">Detected from metadata: <b>${escapeHtml(suggested)}</b> <button type="button" class="use-genre-suggestion">Use detected</button></p>` : ''}
    <p class="genre-folder-preview">Folder: ${escapeHtml(current.replace(' / ', '/'))}/</p>
    <div class="inline-genre-actions"><button type="submit">Save & move</button><button type="button" class="button secondary cancel-genre-edit">Cancel</button></div>
  </form>`;
}

export function metadataEditorMarkup(track, position = 1, total = 1, categories = []) {
  const current = track.genre_category || 'Other';
  const choices = [...new Set([current, ...categories].filter(Boolean))].sort();
  const playlist = (track.playlists || [])[0] || 'Imported Singles';
  return `<form class="track-metadata-editor" hidden>
    <header><div><strong>Edit track metadata</strong><span>Updates the WAV, folder, Music Files, and linked Library entry.</span></div><div class="metadata-review-position"><span>${position} of ${total}</span><button type="button" class="button secondary close-metadata-editor" aria-label="Close metadata editor">×</button></div></header>
    <div class="metadata-fields"><label>Title<input name="title" maxlength="300" required value="${escapeHtml(track.title || '')}"></label><label>Artist<input name="artist" maxlength="300" value="${escapeHtml(track.artist || '')}"></label><label>Genre<select name="genre_category">${choices.map(name=>`<option value="${escapeHtml(name)}"${name===current?' selected':''}>${escapeHtml(name)}</option>`).join('')}</select></label><label>Detailed genre tags<input name="genre" maxlength="500" value="${escapeHtml(track.genre || '')}" placeholder="e.g. salsa, merengue"></label><label>Album / source playlist<input name="playlist_name" maxlength="180" required value="${escapeHtml(playlist)}"></label><label>Artwork image URL<input name="artwork_url" type="url" maxlength="1000" value="${escapeHtml(track.artwork_url || '')}" placeholder="Direct Spotify or YouTube cover image URL"></label><label class="metadata-rename"><input name="rename_file" type="checkbox"> Rename WAV to Artist - Title</label></div>
    <p class="metadata-message"></p><div class="metadata-actions"><div class="metadata-navigation"><button type="button" class="button secondary metadata-previous">← Previous</button><button type="button" class="button secondary metadata-next">Next →</button></div><div class="metadata-save-actions"><button type="submit" class="button secondary">Save</button><button type="submit" data-action="next">Save & next →</button></div></div>
  </form>`;
}

export function detailedGenreSummary(rawGenres) {
  const tags = [...new Set(String(rawGenres || '').split(',').map(tag => tag.trim()).filter(Boolean))];
  if (!tags.length) return {label:'No detailed genre', title:'No detailed genre metadata', empty:true};
  const visible = tags.slice(0, 2);
  return {label:`${visible.join(' · ')}${tags.length > 2 ? ` +${tags.length - 2}` : ''}`, title:tags.join(', '), empty:false};
}
