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
