import { useFrontendServices } from './frontend-services.js';

export const SUPPORTED_LOCAL_AUDIO = /\.(mp3|m4a|aac|flac|ogg|opus|wav|aiff?|aif)$/i;

export function sourceUrlType(value) {
  try {
    const host = new URL(value).hostname.toLowerCase();
    if (host === 'open.spotify.com' || host.endsWith('.spotify.com')) return 'spotify';
    if (host === 'youtu.be' || host === 'youtube.com' || host.endsWith('.youtube.com')) return 'youtube';
    if (host === 'soundcloud.com' || host.endsWith('.soundcloud.com')) return 'soundcloud';
  } catch (_) {}
  return 'unknown';
}

export function authorizedSourceUrls(value) {
  return [
    ...new Set(
      String(value || '')
        .split(/\r?\n/)
        .map((url) => url.trim())
        .filter(Boolean),
    ),
  ];
}

export function addLocalAudioFiles(current, files) {
  const result = [...current];
  const known = new Set(result.map((file) => `${file.name}|${file.size}|${file.lastModified}`));
  [...files]
    .filter((file) => SUPPORTED_LOCAL_AUDIO.test(file.name))
    .forEach((file) => {
      const key = `${file.name}|${file.size}|${file.lastModified}`;
      if (!known.has(key)) {
        result.push(file);
        known.add(key);
      }
    });
  return result;
}

export function playlistTrackKey(track, index) {
  return track.spotify_uri || track.youtube_url || `${track.artist || ''}|${track.title || ''}|${index}`;
}

export function createImportWorkspaceApi(api) {
  const get = (path, fallback) => api.get(path, { cache: 'no-store' }, fallback);
  return Object.freeze({
    matchSource: (url) => api.post('/api/imports/source-match', { url }, {}, 'The source could not be matched.'),
    authorizedStatus: (importId) => get(`/api/imports/${importId}`, 'Import status could not be loaded.'),
    localStatus: (batchId) => get(`/api/imports/local-audio/${batchId}`, 'Local import status could not be loaded.'),
    startLocal: (formData) =>
      api.request('/api/imports/local-audio', { method: 'POST', body: formData }, 'Could not start the local import.'),
    creativeCommonsStatus: (batchId) =>
      get(`/api/imports/creative-commons/${batchId}`, 'Import status could not be loaded.'),
    startCreativeCommons: (tracks, playlistName) =>
      api.post(
        '/api/imports/creative-commons',
        { tracks, playlist_name: playlistName },
        {},
        'Could not start Creative Commons import.',
      ),
    playlistMatchStatus: (matchId) =>
      get(`/api/imports/playlist-matches/${matchId}`, 'Playlist matching status could not be loaded.'),
    startPlaylistMatch: (formData) =>
      api.request(
        '/api/imports/playlist-file/matches',
        { method: 'POST', body: formData },
        'Could not match this playlist.',
      ),
  });
}

export function createAuthorizedImportFeature({ services, importApi, Queue, clock, loadJobs, stopTask, escapeHtml }) {
  const { $ } = useFrontendServices(services);
  let timer = null;
  let metadata = null;
  const urls = () => authorizedSourceUrls($('#authorized-url').value);
  async function inspect(url, type) {
    const root = $('#source-match-result');
    metadata = null;
    root.hidden = false;
    root.innerHTML = `<p>${type === 'spotify' ? 'Finding Spotify metadata and ranking YouTube matches…' : 'Reading SoundCloud track or mix metadata…'}</p>`;
    try {
      metadata = await importApi.matchSource(url);
      if (type === 'spotify') {
        if (!metadata.youtube_url) {
          root.innerHTML = `<div class="source-match-copy"><span class="source-match-label">Spotify track</span><strong>${escapeHtml(metadata.title)}</strong><p>${escapeHtml(metadata.artist || 'Artist unavailable')}</p><small>No reliable YouTube match was selected.</small></div>`;
          return;
        }
        const warning = (metadata.match_warnings || []).join(' · ');
        root.innerHTML = `${metadata.thumbnail_url ? `<img src="${escapeHtml(metadata.thumbnail_url)}" alt="" loading="lazy">` : '<span class="source-match-art">♫</span>'}<div class="source-match-copy"><span class="source-match-label">Spotify track</span><strong>${escapeHtml(metadata.title)}</strong><p>${escapeHtml(metadata.artist || 'Artist unavailable')}</p><small>Best YouTube match · ${metadata.match_score || 0}% confidence</small><b>${escapeHtml(metadata.youtube_title || '')}</b>${warning ? `<em>${escapeHtml(warning)}</em>` : ''}</div><button type="button" id="use-source-match" class="button secondary">Use match</button>`;
        $('#use-source-match').onclick = () => {
          $('#authorized-url').value = metadata.youtube_url;
          $('#source-url-guidance').textContent =
            'Matched from Spotify. Confirm the recording authorization, then import it as WAV.';
          $('#authorized-url').focus();
        };
      } else
        root.innerHTML = `${metadata.thumbnail_url ? `<img src="${escapeHtml(metadata.thumbnail_url)}" alt="" loading="lazy">` : '<span class="source-match-art">♫</span>'}<div class="source-match-copy"><span class="source-match-label">SoundCloud ${Number(metadata.duration || 0) > 1200 ? 'mix' : 'track'}</span><strong>${escapeHtml(metadata.title || 'Untitled')}</strong><p>${escapeHtml(metadata.artist || 'Uploader unavailable')}</p><small>${metadata.duration ? clock(metadata.duration) : 'Duration unavailable'} · authorization required</small></div>`;
    } catch (error) {
      root.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
    }
  }
  async function wait(importId, url, onProgress) {
    while (true) {
      const state = await importApi.authorizedStatus(importId);
      onProgress(Number(state.progress || 0), state.stage || 'Importing');
      if (state.status !== 'processing') return { url, importId, ...state };
      await new Promise((resolve) => setTimeout(resolve, 900));
    }
  }
  const queue = new Queue({
    select: $,
    escapeHtml,
    waitForImport: wait,
    onComplete: async (state) => {
      const complete = state.items.filter((item) => item.status === 'complete'),
        failed = state.items.filter((item) => item.status !== 'complete');
      $('#authorized-import-message').innerHTML =
        `<strong>${complete.length} of ${state.items.length} sources imported.</strong>${failed.length ? `<span>${failed.length} failed or canceled. Use Retry in the queue when ready.</span>` : ''}${complete.length === 1 ? ` <a href="/api/imports/${complete[0].importId}/download">Download WAV</a>` : ''}`;
      $('#authorized-import-submit').disabled = false;
      if (!failed.length) $('#authorized-import-form').reset();
      await loadJobs();
    },
  });
  function bind() {
    $('#authorized-url').addEventListener('input', (event) => {
      clearTimeout(timer);
      const values = authorizedSourceUrls(event.target.value),
        type = values.length === 1 ? sourceUrlType(values[0]) : 'bulk',
        guidance = $('#source-url-guidance');
      if (values.length > 1) {
        metadata = null;
        $('#source-match-result').hidden = true;
        guidance.textContent = `${values.length} unique URLs queued · ${values.filter((url) => ['youtube', 'soundcloud'].includes(sourceUrlType(url))).length} downloadable sources recognized.`;
        return;
      }
      if (type === 'spotify') {
        guidance.textContent =
          'Spotify source detected. Looking up its metadata and searching for a matching YouTube recording…';
        timer = setTimeout(() => inspect(values[0], type), 500);
      } else if (type === 'soundcloud') {
        guidance.textContent = 'SoundCloud source detected. Reading its track or mix metadata…';
        timer = setTimeout(() => inspect(values[0], type), 500);
      } else
        guidance.textContent =
          type === 'youtube'
            ? 'YouTube source detected. The recording can be imported after you confirm its download authorization.'
            : 'Paste a Spotify link or an authorized YouTube or SoundCloud recording.';
    });
    $('#authorized-import-pause').onclick = () => queue.togglePause();
    $('#authorized-import-retry').onclick = () => queue.retryFailed();
    $('#authorized-import-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const values = urls();
      if (!values.length) return;
      if (values.length > 100) {
        $('#authorized-import-message').textContent = 'Import at most 100 URLs in one batch.';
        return;
      }
      const unsupported = values.filter((url) => !['youtube', 'soundcloud'].includes(sourceUrlType(url)));
      if (unsupported.length) {
        $('#authorized-import-message').textContent =
          `${unsupported.length} URL${unsupported.length === 1 ? ' is' : 's are'} unsupported. Spotify supplies metadata only; bulk imports require direct YouTube or SoundCloud URLs.`;
        return;
      }
      stopTask('authorized-import');
      $('#authorized-import-submit').disabled = true;
      $('#authorized-import-message').textContent =
        `Preparing ${values.length} authorized source${values.length === 1 ? '' : 's'}…`;
      const extra =
        values.length === 1
          ? {
              title: metadata?.title || '',
              artist: metadata?.artist || '',
              spotify_uri: metadata?.spotify_uri || '',
              artwork_url: metadata?.thumbnail_url || '',
            }
          : {};
      await queue.start(
        values,
        {
          rights_basis: $('#rights-basis').value,
          confirmation: $('#rights-confirmation').checked,
          process_with_extender: $('#process-import-with-extender').checked,
        },
        extra,
      );
    });
  }
  return Object.freeze({ bind });
}
