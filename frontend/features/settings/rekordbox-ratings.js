/** Preview and apply public Rekordbox collection-XML ratings. */

export function createRekordboxRatingSync({ api, $, escapeHtml, confirmAction, invalidateCatalogs }) {
  let previewToken = '';

  function stars(value) {
    const rating = Math.max(0, Math.min(5, Number(value || 0)));
    return `${'★'.repeat(rating)}${'☆'.repeat(5 - rating)}`;
  }

  function renderStatus(payload = {}) {
    const root = $('#rekordbox-rating-status');
    if (!root) return;
    const counts = payload.ratings || {};
    root.innerHTML = payload.rated_tracks
      ? `<div><strong>${payload.rated_tracks} synced ratings</strong><span>${[5, 4, 3, 2, 1]
          .filter((rating) => Number(counts[rating] || 0))
          .map((rating) => `${stars(rating)} ${counts[rating]}`)
          .join(
            ' · ',
          )}</span><small>Last sync ${escapeHtml(payload.last_synced_at || 'unknown')}</small></div>${reviewRows('View rated tracks', payload.tracks)}`
      : '<strong>No Rekordbox ratings synced</strong><span>Choose a public collection XML export to preview matches.</span>';
    $('#clear-rekordbox-ratings').disabled = !payload.rated_tracks;
  }

  function reviewRows(title, rows) {
    if (!rows?.length) return '';
    return `<details><summary>${escapeHtml(title)} · ${rows.length}</summary><div class="rekordbox-review-list">${rows
      .slice(0, 20)
      .map(
        (row) =>
          `<span><b>${escapeHtml(row.artist || 'Unknown artist')} — ${escapeHtml(row.title || 'Untitled')}</b><i>${stars(row.rating)}${row.match_method ? ` · ${escapeHtml(row.match_method)}` : ''}</i></span>`,
      )
      .join('')}</div></details>`;
  }

  function renderPreview(payload) {
    previewToken = payload.token || '';
    const root = $('#rekordbox-rating-preview');
    root.hidden = false;
    root.innerHTML = `<div class="rekordbox-preview-summary"><strong>${payload.proposed_changes} rating changes ready</strong><span>${payload.rated_tracks} rated in ${String(payload.format || 'export').toUpperCase()} · ${payload.matched_tracks} exact matches · ${payload.unchanged_values} unchanged</span><small>${payload.ambiguous_rows} ambiguous · ${payload.unmatched_rows} unmatched · ${payload.invalid_rows} invalid · ${payload.unrated_tracks} unrated ignored</small></div>${reviewRows('Matched tracks', payload.matches)}${reviewRows('Needs review — not applied', payload.ambiguous)}${reviewRows('Not found — not applied', payload.unmatched)}${payload.review_truncated ? '<p>Only the first 100 rows of each review category are shown.</p>' : ''}`;
    const apply = $('#apply-rekordbox-ratings');
    apply.disabled = !previewToken;
    apply.textContent = payload.proposed_changes ? `Apply ${payload.proposed_changes} changes` : 'Nothing new to apply';
  }

  async function loadStatus() {
    try {
      const response = await api.raw('/api/settings/rekordbox-ratings', { cache: 'no-store' });
      const payload = await response.json();
      if (response.ok) renderStatus(payload);
    } catch {
      // Settings remains usable when the optional synchronization status is unavailable.
    }
  }

  $('#rekordbox-rating-file')?.addEventListener('change', async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const button = $('#preview-rekordbox-ratings');
    const message = $('#rekordbox-rating-message');
    previewToken = '';
    $('#apply-rekordbox-ratings').disabled = true;
    button.disabled = true;
    button.textContent = 'Matching ratings…';
    message.textContent = 'Reading the collection export and checking exact catalog identities.';
    const body = new FormData();
    body.append('file', file);
    try {
      const response = await api.raw('/api/settings/rekordbox-ratings/preview', { method: 'POST', body });
      const payload = await response.json();
      if (!response.ok) throw new Error(api.errorMessage(payload, 'The Rekordbox ratings could not be previewed.'));
      renderPreview(payload);
      message.textContent = 'Preview ready. Ambiguous and unmatched tracks will not be changed.';
    } catch (error) {
      message.textContent = error.message;
      $('#rekordbox-rating-preview').hidden = true;
    } finally {
      button.disabled = false;
      button.textContent = 'Choose export & preview';
    }
  });

  $('#preview-rekordbox-ratings')?.addEventListener('click', () => $('#rekordbox-rating-file').click());
  $('#apply-rekordbox-ratings')?.addEventListener('click', async () => {
    if (!previewToken) return;
    if (
      !(await confirmAction('Apply only the exact Rekordbox rating matches shown in this preview?', {
        title: 'Sync Rekordbox ratings',
        acceptLabel: 'Apply ratings',
      }))
    )
      return;
    const button = $('#apply-rekordbox-ratings');
    button.disabled = true;
    button.textContent = 'Applying…';
    try {
      const response = await api.raw('/api/settings/rekordbox-ratings/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: previewToken }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(api.errorMessage(payload, 'The Rekordbox ratings could not be applied.'));
      previewToken = '';
      renderStatus(payload.status);
      invalidateCatalogs();
      $('#rekordbox-rating-message').textContent =
        `${payload.changed} ratings updated. Set Builder will use them as bounded preference evidence.`;
      button.textContent = 'Applied';
    } catch (error) {
      $('#rekordbox-rating-message').textContent = error.message;
      button.disabled = false;
      button.textContent = 'Apply ratings';
    }
  });

  $('#clear-rekordbox-ratings')?.addEventListener('click', async () => {
    if (
      !(await confirmAction('Clear only imported Rekordbox ratings? Local Set Builder feedback will be preserved.', {
        title: 'Clear Rekordbox ratings',
        acceptLabel: 'Clear ratings',
        danger: true,
      }))
    )
      return;
    const response = await api.raw('/api/settings/rekordbox-ratings', { method: 'DELETE' });
    const payload = await response.json();
    if (!response.ok) return;
    previewToken = '';
    renderStatus(payload.status);
    invalidateCatalogs();
    $('#rekordbox-rating-preview').hidden = true;
    $('#rekordbox-rating-message').textContent = `${payload.removed} imported ratings cleared.`;
  });

  return Object.freeze({ loadStatus, renderPreview, renderStatus });
}
