import {
  deduplicateSetRecordings,
  recordingVersionAlternatives,
  recordingVersionLabel,
  setCatalogTrackId,
  setRecordingKey,
  setTrackId,
} from './recording-identity.js';

function choiceId(track) {
  return setCatalogTrackId(track) || setTrackId(track);
}

export function recordingVersionCount(track, library) {
  return recordingVersionAlternatives(track, library).length;
}

export function buildVersionAwareReplacementCatalog({
  current,
  library,
  usedRecordingKeys,
  recommendedTracks,
  rankTrack,
}) {
  const currentId = choiceId(current);
  const currentFamily = setRecordingKey(current);
  const available = library.filter(
    (track) => choiceId(track) !== currentId && !usedRecordingKeys.has(setRecordingKey(track)),
  );
  const enrich = (choice) => ({
    ...choice,
    sameRecording: setRecordingKey(choice.track) === currentFamily,
    versionLabel: recordingVersionLabel(choice.track),
  });
  const versionChoices = recordingVersionAlternatives(current, available)
    .map(rankTrack)
    .map(enrich)
    .sort((left, right) => right.score - left.score);
  const recommendedIds = new Set(recommendedTracks.map(setTrackId));
  const recommendedSongs = deduplicateSetRecordings(
    available.filter((track) => setRecordingKey(track) !== currentFamily),
  )
    .map(rankTrack)
    .filter((choice) => recommendedIds.has(setTrackId(choice.track)))
    .map(enrich)
    .sort((left, right) => right.score - left.score)
    .slice(0, 5);
  const searchable = available.map(rankTrack).map(enrich).sort((left, right) => right.score - left.score);
  const genres = [...new Set(searchable.map((choice) => choice.track._genre).filter(Boolean))].sort((left, right) =>
    left.localeCompare(right),
  );
  return { versionChoices, recommendedSongs, searchable, genres };
}

export function searchVersionAwareReplacements(searchable, query, genre) {
  const normalizedQuery = String(query || '').trim().toLowerCase();
  return searchable.filter(({ track, versionLabel }) => {
    const haystack = `${track.source_name || ''} ${track.artist || ''} ${track._genre || ''} ${versionLabel}`.toLowerCase();
    return (!normalizedQuery || haystack.includes(normalizedQuery)) && (!genre || track._genre === genre);
  });
}

export function defaultVersionAwareReplacements(versionChoices, recommendedSongs) {
  return [
    ...versionChoices.map((choice) => ({ ...choice, group: 'Other versions of this song' })),
    ...recommendedSongs.map((choice) => ({ ...choice, group: 'Recommended different songs' })),
  ];
}
