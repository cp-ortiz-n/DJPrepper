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
