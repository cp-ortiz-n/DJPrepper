/** Stable catalog-row and same-recording identities used across Set Builder. */

export function setTrackId(track) {
  return String(track.source_name || '').toLowerCase();
}

export function setCatalogTrackId(track) {
  if (track?._downloadedId != null) return `downloaded:${track._downloadedId}`;
  return track?._job?.id != null ? `job:${track._job.id}` : '';
}

function normalizeRecordingText(value) {
  return String(value || '')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

function canonicalRecordingTitle(title, artist) {
  let value = String(title || '').replace(/\.[^.]+$/, '');
  const parts = value.split(/\s+[-–—]\s+/);
  if (parts.length > 1) {
    const suffix = normalizeRecordingText(parts.at(-1));
    const normalizedArtist = normalizeRecordingText(artist);
    let remainder = suffix;
    if (normalizedArtist && (suffix === normalizedArtist || suffix.startsWith(`${normalizedArtist} `))) {
      remainder = suffix.slice(normalizedArtist.length).trim();
    }
    const versionWords = new Set(['club', 'mix', 'edit', 'version', 'extended', 'radio', 'original']);
    if (remainder && remainder.split(' ').every((word) => versionWords.has(word))) {
      value = parts.slice(0, -1).join(' - ');
    }
  }
  return normalizeRecordingText(value)
    .replace(/\b(?:remix|rework|bootleg|extended|club mix|radio edit|version)\b/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replaceAll(' ', '');
}

export function setRecordingKey(track) {
  const code = String(track?._recordingCode || '').trim().toUpperCase();
  if (code) return `recording:${code}`;
  const artist = normalizeRecordingText(track?.artist);
  const title = canonicalRecordingTitle(track?.title || track?.source_name, track?.artist);
  return `metadata:${artist}|${title}`;
}

export function deduplicateSetRecordings(tracks, preferredTrackIds = new Set()) {
  const groups = new Map();
  (tracks || []).forEach((track) => {
    const key = setRecordingKey(track) || `track:${setTrackId(track)}`;
    const current = groups.get(key);
    if (!current || (!preferredTrackIds.has(setTrackId(current)) && preferredTrackIds.has(setTrackId(track)))) {
      groups.set(key, track);
    }
  });
  const selected = new Set(groups.values());
  return (tracks || []).filter((track) => selected.has(track));
}

export function recordingVersionAlternatives(track, tracks) {
  const familyKey = setRecordingKey(track);
  const selectedId = setCatalogTrackId(track) || setTrackId(track);
  return (tracks || []).filter((candidate) => {
    const candidateId = setCatalogTrackId(candidate) || setTrackId(candidate);
    return candidateId !== selectedId && setRecordingKey(candidate) === familyKey;
  });
}

export function recordingVersionLabel(track) {
  const code = String(track?._versionCode || '').trim().toUpperCase();
  const kind = code.replace(/\d+$/, '');
  return (
    {
      ORG: 'Original',
      RMX: 'Remix',
      EXT: 'Extended mix',
      RADIO: 'Radio edit',
      LIVE: 'Live version',
      INST: 'Instrumental',
      ACAP: 'Acapella',
      REM: 'Remaster',
    }[kind] || 'Alternate version'
  );
}
