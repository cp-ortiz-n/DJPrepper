import { useFrontendServices } from '../../core/frontend-services.js';

export function importFailureKind(error) {
  const value = String(error || '').toLowerCase();
  if (value.includes('age') || value.includes('sign in')) return ['Age-restricted source', 'Restricted'];
  if (value.includes('403') || value.includes('forbidden')) return ['Source blocked the download', 'Blocked'];
  if (value.includes('unavailable') || value.includes('removed')) return ['Source is unavailable', 'Unavailable'];
  if (value.includes('no reliable') || value.includes('no youtube')) return ['No reliable source match', 'No match'];
  return ['Download could not complete', 'Failed'];
}

export function createImportIssuesFeature({ services, escapeHtml }) {
  const { api, $, $$ } = useFrontendServices(services);
  let failures = [];

  async function retry(ids) {
    if (!ids.length) return;
    const status = $('#import-retry-status');
    status.hidden = false;
    status.querySelector('strong').textContent = `Preparing ${ids.length} retr${ids.length === 1 ? 'y' : 'ies'}`;
    status.querySelector('span').textContent = '0%';
    status.querySelector('progress').value = 0;
    status.querySelector('p').textContent = 'Searching for a fresh source before downloading again.';
    $$('#import-failure-toolbar button,.retry-import-failure').forEach((button) => {
      button.disabled = true;
    });
    try {
      const payload = await api.post('/api/imports/failures/retry', { failure_ids: ids }, {}, 'Try again later.');
      pollRetry(payload.batch_id, status);
    } catch (error) {
      status.querySelector('strong').textContent = 'Retry could not start';
      status.querySelector('p').textContent = error.message;
      await load();
    }
  }

  function pollRetry(batchId, status) {
    const poll = async () => {
      try {
        const state = await api.get(
          `/api/imports/creative-commons/${batchId}`,
          { cache: 'no-store' },
          'The retry status could not be loaded.',
        );
        status.querySelector('strong').textContent = state.stage || 'Retrying imports';
        status.querySelector('span').textContent = `${Math.round(Number(state.progress || 0))}%`;
        status.querySelector('progress').value = Number(state.progress || 0);
        const counts = state.counts || {};
        status.querySelector('p').textContent =
          `${counts.downloaded || 0} imported · ${counts.already_downloaded || 0} already present · ${counts.failed || 0} still need attention`;
        if (state.status === 'processing') {
          setTimeout(poll, 1000);
          return;
        }
        await load();
        status.querySelector('strong').textContent = state.status === 'complete' ? 'Retry complete' : 'Retry stopped';
        if (state.status !== 'complete')
          status.querySelector('p').textContent = state.error || 'The retry could not finish.';
      } catch (error) {
        status.querySelector('strong').textContent = 'Retry interrupted';
        status.querySelector('span').textContent = '';
        status.querySelector('p').textContent =
          error.status === 404
            ? 'This retry was interrupted by an app restart. Your completed imports were kept; start Retry all again for the remaining tracks.'
            : error.message || 'Reload the import issues and try again.';
        await load();
      }
    };
    void poll();
  }

  function render() {
    const root = $('#import-failures-list');
    const empty = $('#import-failures-empty');
    const query = $('#import-failure-search').value.trim().toLowerCase();
    const selected = new Set($$('.failure-select:checked').map((input) => Number(input.value)));
    const visible = failures.filter(
      (item) =>
        !query || `${item.title} ${item.artist} ${item.playlist_name} ${item.error}`.toLowerCase().includes(query),
    );
    empty.hidden = Boolean(visible.length);
    empty.textContent = failures.length ? 'No import issues match this search.' : 'No unresolved import failures.';
    root.innerHTML = visible
      .map((item) => {
        const spotifyId = String(item.spotify_uri || '').startsWith('spotify:track:')
          ? String(item.spotify_uri).split(':').pop()
          : '';
        const spotifyUrl = spotifyId ? `https://open.spotify.com/track/${encodeURIComponent(spotifyId)}` : '';
        const source = item.youtube_url || spotifyUrl;
        const [summary, badge] = importFailureKind(item.error);
        const attempts = Number(item.attempts || 1);
        return `<article class="import-failure-row" data-id="${item.id}"><input class="failure-select" type="checkbox" value="${item.id}" aria-label="Select ${escapeHtml(item.title || 'track')}"${selected.has(Number(item.id)) ? ' checked' : ''}><div><strong>${escapeHtml(item.title || 'Unknown track')}</strong><span>${escapeHtml(item.artist || 'Unknown artist')} · ${escapeHtml(item.playlist_name || 'Imported playlist')}</span></div><div><div class="failure-summary"><b>${escapeHtml(summary)}</b><em>${escapeHtml(badge)}</em></div><small>${attempts} attempt${attempts === 1 ? '' : 's'} · ${escapeHtml(item.updated_at || '')}</small><details class="failure-error"><summary>Technical details</summary><p>${escapeHtml(item.error || 'Download failed')}</p></details></div><div class="import-failure-actions"><button type="button" class="retry-import-failure">Retry</button>${source ? `<a class="button secondary" href="${escapeHtml(source)}" target="_blank" rel="noopener">Open source</a>` : ''}<button type="button" class="button secondary dismiss-import-failure">Dismiss</button></div></article>`;
      })
      .join('');
    const boxes = $$('.failure-select');
    const updateSelection = () => {
      const checked = $$('.failure-select:checked');
      $('#retry-selected-imports').disabled = !checked.length;
      $('#retry-selected-imports').textContent = checked.length
        ? `Retry selected (${checked.length})`
        : 'Retry selected';
      $('#import-failure-select-all').checked = boxes.length > 0 && boxes.every((box) => box.checked);
      $('#import-failure-select-all').indeterminate =
        boxes.some((box) => box.checked) && !$('#import-failure-select-all').checked;
    };
    boxes.forEach((box) => {
      box.onchange = updateSelection;
    });
    updateSelection();
    root.querySelectorAll('.retry-import-failure').forEach((button) => {
      button.onclick = () => retry([Number(button.closest('.import-failure-row').dataset.id)]);
    });
    root.querySelectorAll('.dismiss-import-failure').forEach((button) => {
      button.onclick = async () => {
        const row = button.closest('.import-failure-row');
        button.disabled = true;
        try {
          await api.delete(`/api/imports/failures/${row.dataset.id}`, {}, 'Import issue could not be dismissed.');
          await load();
        } catch (_) {
          button.disabled = false;
        }
      };
    });
  }

  async function load() {
    const panel = $('#import-failures-panel');
    const root = $('#import-failures-list');
    const empty = $('#import-failures-empty');
    const counter = $('#import-failure-count');
    const toolbar = $('#import-failure-toolbar');
    if (!panel || !root) return;
    try {
      const payload = await api.get(
        '/api/imports/failures',
        { cache: 'no-store' },
        'Import issues could not be loaded.',
      );
      failures = payload.failures || [];
      counter.textContent = String(failures.length);
      empty.hidden = Boolean(failures.length);
      toolbar.hidden = !failures.length;
      $('#import-failure-search').oninput = render;
      $('#import-failure-select-all').onchange = (event) => {
        $$('.failure-select').forEach((box) => {
          box.checked = event.target.checked;
        });
        root.querySelector('.failure-select')?.dispatchEvent(new Event('change'));
      };
      $('#retry-selected-imports').onclick = () =>
        retry($$('.failure-select:checked').map((input) => Number(input.value)));
      $('#retry-all-imports').onclick = () => retry(failures.map((item) => Number(item.id)));
      render();
    } catch (error) {
      counter.textContent = '!';
      toolbar.hidden = true;
      empty.hidden = false;
      empty.textContent = error.message;
      root.replaceChildren();
    }
  }

  return Object.freeze({ load, retry });
}
