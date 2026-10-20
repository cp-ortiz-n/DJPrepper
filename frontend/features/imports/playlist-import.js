import { playlistTrackKey } from './import-workspace.js';
import { useFrontendServices } from '../../core/frontend-services.js';

export function creativeCommonsTracks(matches) {
  return matches
    .filter((track) => track.youtube_url)
    .map((track) => ({
      url: track.youtube_url,
      title: track.title,
      artist: track.artist,
      spotify_uri: track.spotify_uri || '',
      genre: track.genre || '',
      genre_category: track.genre_category || 'Other',
      artwork_url: track.artwork_url || '',
    }));
}

export function createPlaylistImportFeature({ services, importApi, runTask, clock, escapeHtml, loadImportFailures }) {
  const { $, $$ } = useFrontendServices(services);
  const permissions = new Map();
  let matches = [];
  let playlistName = 'Imported Playlist';

  function updateSelectionCount() {
    const selected = $$('#spotify-match-results .match-select:checked').length;
    const boxes = $$('#spotify-match-results .match-select');
    $('#spotify-selected-count').textContent = `${selected} selected`;
    $('#spotify-select-all').checked = boxes.length > 0 && selected === boxes.length;
    $('#spotify-select-all').indeterminate = selected > 0 && selected < boxes.length;
  }

  function render(results) {
    matches = results;
    const root = $('#spotify-match-results');
    root.hidden = false;
    root.innerHTML = results
      .map((track, index) => {
        const key = playlistTrackKey(track, index);
        const permission = permissions.get(key) || 'unverified';
        const duration = track.youtube_duration ? clock(track.youtube_duration) : 'unknown length';
        const sourceDuration = track.duration_ms ? clock(track.duration_ms / 1000) : 'unknown source length';
        const match = track.youtube_url
          ? `<a href="${escapeHtml(track.youtube_url)}" target="_blank" rel="noreferrer">Open YouTube ↗</a><button type="button" class="button secondary use-youtube-match" data-url="${escapeHtml(track.youtube_url)}" data-key="${escapeHtml(key)}" ${permission === 'unverified' ? 'disabled' : ''}>Use for authorized import</button>`
          : '<span class="match-missing">No likely match found</span>';
        const details = [track.genre_category, track.genre, track.tempo ? `${track.tempo} BPM` : '']
          .filter(Boolean)
          .join(' · ');
        const quality = track.youtube_url ? `${track.match_score || 0}% match` : 'No reliable match';
        const warnings = (track.match_warnings || []).join(' · ');
        return `<article data-key="${escapeHtml(key)}"><label class="match-check"><input class="match-select" type="checkbox" aria-label="Select ${escapeHtml(track.title)}"></label><span class="match-number">${index + 1}</span><div class="match-copy"><strong>${escapeHtml(track.title)}</strong><small>${escapeHtml(track.artist)}${details ? ` · ${escapeHtml(details)}` : ''} · source ${sourceDuration}</small><p>${track.youtube_title ? escapeHtml(track.youtube_title) : 'No YouTube result'} · YouTube ${duration} · ${quality}</p>${warnings ? `<p class="match-warning">${escapeHtml(warnings)}</p>` : ''}<label class="match-permission-label">Permission<select class="match-permission"><option value="unverified" ${permission === 'unverified' ? 'selected' : ''}>Unverified</option><option value="own-upload" ${permission === 'own-upload' ? 'selected' : ''}>I own this recording</option><option value="creative-commons" ${permission === 'creative-commons' ? 'selected' : ''}>Creative Commons</option><option value="public-domain" ${permission === 'public-domain' ? 'selected' : ''}>Public domain</option><option value="permission" ${permission === 'permission' ? 'selected' : ''}>Direct permission</option></select></label></div><div class="match-actions">${match}</div></article>`;
      })
      .join('');
    $('#spotify-match-toolbar').hidden = false;
    root.querySelectorAll('.match-select').forEach((box) => box.addEventListener('change', updateSelectionCount));
    root.querySelectorAll('.match-permission').forEach((select) =>
      select.addEventListener('change', () => {
        const card = select.closest('article');
        permissions.set(card.dataset.key, select.value);
        const button = card.querySelector('.use-youtube-match');
        if (button) button.disabled = select.value === 'unverified';
      }),
    );
    root.querySelectorAll('.use-youtube-match').forEach((button) =>
      button.addEventListener('click', () => {
        const permission = permissions.get(button.dataset.key) || 'unverified';
        if (permission === 'unverified') return;
        $('#authorized-url').value = button.dataset.url;
        $('#rights-basis').value = permission;
        $('#authorized-url').focus();
        $('#authorized-import-message').textContent =
          'Match and permission copied above. Confirm your rights before importing it.';
        $('#authorized-import-form').scrollIntoView({ behavior: 'smooth', block: 'center' });
      }),
    );
    updateSelectionCount();
  }

  function monitorPlaylist(matchId) {
    runTask({
      key: 'playlist-match',
      load: () => importApi.playlistMatchStatus(matchId),
      update: (state) => {
        const progress = $('#spotify-playlist-progress');
        progress.hidden = false;
        progress.querySelector('span').style.width = `${Math.max(2, Number(state.progress || 0))}%`;
        progress.querySelector('small').textContent = `${state.stage} · ${Math.round(state.progress || 0)}%`;
      },
      complete: (state) => {
        $('#playlist-csv-submit').disabled = false;
        if (state.status === 'complete') {
          playlistName = state.playlist_name || playlistName;
          $('#spotify-playlist-message').textContent =
            `${state.results.length} tracks matched. Verify titles and durations before using any result.`;
          render(state.results);
        } else $('#spotify-playlist-message').textContent = state.error || 'Playlist matching failed.';
      },
      fail: (error) => {
        $('#playlist-csv-submit').disabled = false;
        $('#spotify-playlist-message').textContent = error.message;
      },
    });
  }

  function monitorCreativeCommons(batchId) {
    runTask({
      key: 'creative-commons-import',
      load: () => importApi.creativeCommonsStatus(batchId),
      interval: 1200,
      update: (state) => {
        const root = $('#creative-commons-result');
        const counts = state.counts || {};
        root.hidden = false;
        root.innerHTML = `<strong>${escapeHtml(state.stage)}</strong><span>${Math.round(state.progress || 0)}% · ${counts.downloaded || 0} downloaded · ${counts.already_downloaded || 0} already present · ${counts.skipped_not_creative_commons || 0} not Creative Commons · ${counts.failed || 0} failed</span>`;
      },
      complete: async (state) => {
        const root = $('#creative-commons-result');
        const counts = state.counts || {};
        $('#download-creative-commons').disabled = false;
        if (state.status !== 'complete') {
          root.innerHTML += `<p>${escapeHtml(state.error || 'Creative Commons import failed.')}</p>`;
          return;
        }
        const folders = Object.entries(state.genre_summary || {})
          .map(([genre, count]) => `${genre} (${count})`)
          .join(' · ');
        const name = state.playlist_name || playlistName;
        root.innerHTML += `${folders ? `<span>${escapeHtml(name)} folders: ${escapeHtml(folders)}</span>` : ''}<div><a class="button secondary" href="/api/imports/creative-commons/${batchId}/report">Download ${escapeHtml(name)} report</a>${(counts.downloaded || 0) + (counts.already_downloaded || 0) > 0 ? `<a class="button" href="/api/imports/creative-commons/${batchId}/download">Download ${escapeHtml(name)} WAV ZIP</a>` : ''}</div>`;
        await loadImportFailures();
      },
      fail: (error) => {
        $('#download-creative-commons').disabled = false;
        $('#creative-commons-result').textContent = error.message;
      },
    });
  }

  function bind() {
    $('#spotify-select-all').addEventListener('change', (event) => {
      $$('#spotify-match-results .match-select').forEach((box) => {
        box.checked = event.target.checked;
      });
      updateSelectionCount();
    });
    $('#spotify-apply-permission').addEventListener('click', () => {
      const permission = $('#spotify-bulk-permission').value;
      $$('#spotify-match-results article').forEach((card) => {
        if (!card.querySelector('.match-select').checked) return;
        card.querySelector('.match-permission').value = permission;
        permissions.set(card.dataset.key, permission);
        const button = card.querySelector('.use-youtube-match');
        if (button) button.disabled = permission === 'unverified';
      });
      $('#spotify-playlist-message').textContent =
        `Permission updated for ${$$('#spotify-match-results .match-select:checked').length} selected tracks.`;
    });
    $('#download-creative-commons').addEventListener('click', async () => {
      const tracks = creativeCommonsTracks(matches);
      if (!tracks.length) return;
      const button = $('#download-creative-commons');
      button.disabled = true;
      $('#creative-commons-result').hidden = false;
      $('#creative-commons-result').textContent = `Checking Creative Commons licenses for ${tracks.length} matches…`;
      try {
        const payload = await importApi.startCreativeCommons(tracks, playlistName);
        monitorCreativeCommons(payload.batch_id);
      } catch (error) {
        button.disabled = false;
        $('#creative-commons-result').textContent = error.message;
      }
    });
    $('#playlist-csv-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const file = $('#playlist-csv-file').files[0];
      if (!file) return;
      const button = $('#playlist-csv-submit');
      button.disabled = true;
      $('#spotify-match-results').hidden = true;
      $('#spotify-playlist-message').textContent = `Reading ${file.name}…`;
      const data = new FormData();
      data.append('file', file);
      try {
        const payload = await importApi.startPlaylistMatch(data);
        playlistName = payload.playlist_name || file.name.replace(/\.csv$/i, '') || 'Imported Playlist';
        $('#spotify-playlist-message').textContent =
          `${payload.track_count} tracks loaded from ${playlistName}. Finding YouTube matches…`;
        monitorPlaylist(payload.match_id);
      } catch (error) {
        button.disabled = false;
        $('#spotify-playlist-message').textContent = error.message;
      }
    });
  }

  return Object.freeze({ bind });
}
