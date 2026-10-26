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
  if (!artist && !title) {
    const catalogId = setCatalogTrackId(track);
    const trackId = setTrackId(track);
    return `track:${catalogId || trackId}`;
  }
  return `metadata:${artist}|${title}`;
}

/**
 * Select one stable representative for every recording family.
 *
 * The function is deliberately pure so planning, editing, recovery, and export
 * can share exactly the same invariant. Explicitly preferred tracks win over an
 * earlier family member; otherwise the original plan order is preserved.
 */
export function reconcileSetRecordingFamilies(
  tracks,
  {
    preferredTrackIds = new Set(),
    trackId = setTrackId,
    recordingKey = setRecordingKey,
  } = {},
) {
  const source = Array.isArray(tracks) ? tracks.filter(Boolean) : [];
  const winners = new Map();
  const duplicateFamilies = new Map();
  source.forEach((track, index) => {
    const id = String(trackId(track) || '');
    const family = String(recordingKey(track) || `track:${id}`);
    const contender = { track, id, family, index, preferred: preferredTrackIds.has(id) };
    const current = winners.get(family);
    if (!current) {
      winners.set(family, contender);
      return;
    }
    const duplicates = duplicateFamilies.get(family) || [current];
    duplicates.push(contender);
    duplicateFamilies.set(family, duplicates);
    if (!current.preferred && contender.preferred) winners.set(family, contender);
  });
  const selected = new Set([...winners.values()].map(({ track }) => track));
  const plan = source.filter((track) => selected.has(track));
  const removed = source.filter((track) => !selected.has(track));
  return {
    plan,
    removed,
    duplicateFamilies: [...duplicateFamilies.entries()].map(([recordingKeyValue, members]) => ({
      recordingKey: recordingKeyValue,
      keptTrackId: winners.get(recordingKeyValue)?.id || '',
      removedTrackIds: members
        .filter(({ track }) => !selected.has(track))
        .map(({ id }) => id),
      preferredTrackIds: members.filter(({ preferred }) => preferred).map(({ id }) => id),
    })),
    valid: removed.length === 0,
  };
}

export function deduplicateSetRecordings(tracks, preferredTrackIds = new Set()) {
  return reconcileSetRecordingFamilies(tracks, { preferredTrackIds }).plan;
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
