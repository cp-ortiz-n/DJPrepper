/** Compose durable track feedback with validated replacement behavior. */

import { createTrackDecisionStore } from './track-decision-store.js';
import { createTrackRejectionWorkflow } from './track-rejection.js';

export function createTrackDecisionWorkflow({ state, api, dom, music, policy, lifecycle, preference }) {
  const persistence = createTrackDecisionStore({
    api,
    trackId: music.setTrackId,
    recordingKey: music.setRecordingKey,
    ...preference,
  });
  const rejection = createTrackRejectionWorkflow({ state, dom, music, policy, lifecycle, persistence });
  return Object.freeze({ ...rejection, reconcile: persistence.reconcile });
}
