import { createSetPlanningClient } from './planning-client.js';

export function createSetBuilderApi({ api, planningClient = createSetPlanningClient() }) {
  const get = (path, fallback) => api.get(path, { cache: 'no-store' }, fallback);
  const post = (path, body, fallback) => api.post(path, body, {}, fallback);

  return Object.freeze({
    catalog: () => get('/api/set-builder/catalog', 'Set Builder catalog could not be loaded.'),
    providerStatus: () => get('/api/set-builder/intention-provider', 'Provider status unavailable.'),
    prepareBrief: ({ brief, catalogVocabulary, durationMinutes }) =>
      post(
        '/api/set-builder/prepare-brief',
        {
          brief,
          catalog_vocabulary: catalogVocabulary,
          duration_minutes: durationMinutes,
        },
        'Set direction could not be prepared.',
      ),
    interpretIntention: (brief, catalogVocabulary) =>
      post(
        '/api/set-builder/interpret-intention',
        { brief, catalog_vocabulary: catalogVocabulary },
        'AI provider unavailable.',
      ),
    planJourney: ({ brief, interpretedIntention, catalogVocabulary, durationMinutes }) =>
      post(
        '/api/set-builder/plan-journey',
        {
          brief,
          interpreted_intention: interpretedIntention,
          catalog_vocabulary: catalogVocabulary,
          duration_minutes: durationMinutes,
        },
        'Journey planner unavailable.',
      ),
    preferenceProfile: (context) =>
      get(`/api/set-builder/preferences?context=${encodeURIComponent(context)}`, 'Profile unavailable.'),
    recordPreference: (events) => post('/api/set-builder/preferences/events', { events }, 'Feedback was not recorded.'),
    dismissPreference: (dimension, value) =>
      api.delete(
        '/api/set-builder/preferences/signals',
        {
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ dimension, value }),
        },
        'Preference could not be dismissed.',
      ),
    setPersonalization: (enabled) =>
      api.put('/api/set-builder/preferences/enabled', { enabled }, {}, 'Personalization could not be updated.'),
    resetPreferences: () => api.delete('/api/set-builder/preferences', {}, 'Preferences could not be reset.'),
    reviewReport: (context) =>
      get(`/api/set-builder/reviews?context=${encodeURIComponent(context)}`, 'Review report unavailable.'),
    submitReview: (review) => post('/api/set-builder/reviews', review, 'Review could not be saved.'),
    waveform: (jobId) => get(`/api/jobs/${jobId}/waveform/wav`, 'Waveform unavailable.'),
    savePlaylist: (playlist) => post('/api/set-builder/save-playlist', playlist, 'Playlist file could not be saved.'),
    savedSets: () => get('/api/set-builder/sets', 'Saved sets could not be loaded.'),
    saveSet: (record) =>
      api.put(`/api/set-builder/sets/${encodeURIComponent(record.id)}`, { record }, {}, 'Set could not be saved.'),
    deleteSet: (setId) =>
      api.delete(`/api/set-builder/sets/${encodeURIComponent(setId)}`, {}, 'Set could not be deleted.'),
    migrateSavedSets: (records) =>
      post('/api/set-builder/sets/migrate-v1', { records }, 'Saved sets could not be migrated.'),
    exportPreflight: (paths) =>
      post('/api/set-builder/export-preflight', { paths }, 'Playlist paths could not be validated.'),
    planning: planningClient,
  });
}
