/** Resolve Set Builder playback through durable catalog media before historical job output. */

function positiveInteger(value) {
  const numeric = Number(value);
  return Number.isInteger(numeric) && numeric > 0 ? numeric : null;
}

export function setTrackAudioUrl(track) {
  const downloadedId = positiveInteger(track?._downloadedId);
  if (downloadedId) return `/api/downloaded-library/tracks/${downloadedId}/audio`;

  const jobId = positiveInteger(track?._job?.id);
  return jobId ? `/api/jobs/${jobId}/audio/wav` : '';
}
