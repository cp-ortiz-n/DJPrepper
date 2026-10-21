/** Preference learning, transition review, and calibration ownership for Set Builder. */

export function createSetBuilderFeedback({ state, dom, api, music, planning, review }) {
  const { $, $$, escapeHtml } = dom;
  const { compatibility, setTrackDetailedGenres, setTrackId, setCatalogTrackId, setVocalProfile, songEnergy } = music;
  const { setBrief, getPlanningReceipt, transitionSettings } = planning;
  const { trackReviewDraft, transitionReviewDraft } = review;
  let preferenceProfile = null;
  let transitionProfile = { activeSignals: [] };
  let setDecision = 'unreviewed';

  function preferenceContext() {
    return $('#set-vibe')?.value || 'balanced';
  }

  function preferenceFeatures(track) {
    const energy = songEnergy(track);
    const bpm = Number(track.bpm || 0);
    return {
      genre: [track._genre, ...setTrackDetailedGenres(track)].filter(Boolean),
      descriptor: (track._descriptors || []).map((item) => item.value).filter(Boolean),
      artist: track.artist || '',
      vocals: setVocalProfile(track),
      energy: energy < 0.4 ? 'low' : energy >= 0.7 ? 'high' : 'medium',
      bpm: bpm ? `${Math.floor(bpm / 10) * 10}s` : 'unknown',
    };
  }

  function preferenceAdjustment(track) {
    if (!preferenceProfile?.enabled) return 0;
    const features = preferenceFeatures(track);
    const total = (preferenceProfile.activeSignals || []).reduce((sum, signal) => {
      const values = Array.isArray(features[signal.dimension])
        ? features[signal.dimension]
        : [features[signal.dimension]];
      return values.map((value) => String(value).toLowerCase()).includes(String(signal.value).toLowerCase())
        ? sum + Number(signal.adjustment || 0)
        : sum;
    }, 0);
    return Math.max(-8, Math.min(8, total * 0.5));
  }

  function preferenceEventId() {
    return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }

  async function recordPreference(action, tracks) {
    const items = (Array.isArray(tracks) ? tracks : [tracks]).filter(Boolean);
    if (!items.length) return;
    try {
      const result = await api.recordPreference(
        items.map((track) => ({
          id: preferenceEventId(),
          action,
          trackId: setTrackId(track),
          context: preferenceContext(),
          features: preferenceFeatures(track),
        })),
      );
      preferenceProfile = result.profile;
      renderPreferenceProfile();
    } catch (error) {
      console.warn('Set preference feedback failed:', error);
    }
  }

  function renderPreferenceProfile() {
    const status = $('#set-preference-status');
    const summary = $('#set-preference-summary');
    const toggle = $('#set-personalization-enabled');
    if (!preferenceProfile || !status || !summary || !toggle) return;
    toggle.checked = Boolean(preferenceProfile.enabled);
    const active = preferenceProfile.activeSignals || [];
    const pending = preferenceProfile.pendingSignals || [];
    status.textContent = preferenceProfile.enabled
      ? `${active.length} active · ${preferenceProfile.eventCount} local choices`
      : 'Personalization paused';
    summary.innerHTML = active.length
      ? active
          .slice(0, 8)
          .map(
            (signal) =>
              `<span><b>${escapeHtml(signal.value)}</b> · ${signal.adjustment > 0 ? '+' : ''}${signal.adjustment} ranking · ${signal.evidenceCount} tracks <button type="button" data-dismiss-signal="${escapeHtml(signal.dimension)}" data-signal-value="${escapeHtml(signal.value)}" aria-label="Dismiss ${escapeHtml(signal.value)}">×</button></span>`,
          )
          .join('')
      : `<span>${pending.length ? 'Learning from more distinct tracks before changing rankings.' : 'No feedback recorded yet.'}</span>`;
    summary.querySelectorAll('[data-dismiss-signal]').forEach(
      (button) =>
        (button.onclick = async () => {
          try {
            preferenceProfile = await api.dismissPreference(button.dataset.dismissSignal, button.dataset.signalValue);
            renderPreferenceProfile();
          } catch (error) {
            console.warn('Set preference dismissal failed:', error);
          }
        }),
    );
  }

  async function loadPreferenceProfile() {
    try {
      preferenceProfile = await api.preferenceProfile(preferenceContext());
      renderPreferenceProfile();
    } catch (error) {
      console.warn('Set preference profile failed:', error);
      const status = $('#set-preference-status');
      if (status) status.textContent = 'Local preferences unavailable';
    }
  }

  function transitionReviewFeatures(left, right, index) {
    const match = compatibility(left, right);
    const settings = transitionSettings(index);
    const difference = Number(right.bpm || 0) - Number(left.bpm || 0);
    return {
      bpmMovement: Math.abs(difference) < 2 ? 'steady' : difference > 0 ? 'rising' : 'falling',
      keyCompatibility: match.components.key >= 31 ? 'strong' : match.components.key >= 20 ? 'workable' : 'weak',
      vocalOverlap:
        setVocalProfile(left) === 'vocal-forward' && setVocalProfile(right) === 'vocal-forward'
          ? 'both-vocal'
          : 'spaced',
      energyMovement:
        songEnergy(right) - songEnergy(left) > 0.12
          ? 'rising'
          : songEnergy(left) - songEnergy(right) > 0.12
            ? 'falling'
            : 'steady',
      bars: String(settings.bars || 16),
      technique: settings.technique || 'crossfade',
    };
  }

  function renderCalibrationReport(report) {
    const root = $('#set-calibration-summary');
    if (!root || !report) return;
    const tracks = report.tracks || {};
    transitionProfile = report.transitionProfile || {};
    root.innerHTML = `<p><b>${tracks.reviewed || 0} tracks reviewed</b> · ${tracks.accepted || 0} accepted · ${tracks.rejected || 0} rejected · ${tracks.changedByPersonalization || 0} changed rank</p><p>Personalized acceptance ${tracks.personalizedAcceptanceRate == null ? 'not enough evidence' : `${Math.round(tracks.personalizedAcceptanceRate * 100)}%`} · neutral ${tracks.neutralAcceptanceRate == null ? 'not enough evidence' : `${Math.round(tracks.neutralAcceptanceRate * 100)}%`} · ${transitionProfile.activeSignals?.length || 0} active transition preferences</p>${(report.recommendations || []).map((item) => `<p class="set-relaxation-warning">${escapeHtml(item.message)}</p>`).join('')}`;
  }

  function transitionPreferenceAdjustment(features) {
    return Math.max(
      -8,
      Math.min(
        8,
        (transitionProfile.activeSignals || []).reduce(
          (sum, signal) =>
            String(features[signal.dimension] || '').toLowerCase() === String(signal.value || '').toLowerCase()
              ? sum + Number(signal.adjustment || 0)
              : sum,
          0,
        ),
      ),
    );
  }

  async function loadSetReviewReport() {
    try {
      renderCalibrationReport(await api.reviewReport(preferenceContext()));
    } catch (error) {
      console.warn('Set review report failed:', error);
    }
  }

  async function submitSetReview() {
    if (!state.plan.length) return;
    const button = $('#submit-set-review');
    button.disabled = true;
    button.textContent = 'Saving…';
    const transitions = state.plan.slice(1).map((track, index) => {
      const left = state.plan[index];
      const pairId = `${setCatalogTrackId(left)}→${setCatalogTrackId(track)}`;
      return {
        pairId,
        rating: transitionReviewDraft.get(pairId) || 3,
        features: transitionReviewFeatures(left, track, index + 1),
      };
    });
    const tracks = state.plan.map((track) => {
      const metrics = track._candidateMetrics || {};
      const itemReview = trackReviewDraft.get(setTrackId(track)) || {};
      return {
        trackId: setCatalogTrackId(track),
        title: track.source_name.replace(/\.[^.]+$/, ''),
        decision: itemReview.decision || 'unreviewed',
        reason: itemReview.reason || '',
        features: preferenceFeatures(track),
        technicalScore: metrics.technicalScore || 0,
        preferenceAdjustment: metrics.preferenceAdjustment || 0,
        rankDelta: metrics.rankDelta || 0,
        matchTier: metrics.matchTier || 'unknown',
      };
    });
    const receipt = getPlanningReceipt();
    try {
      const result = await api.submitReview({
        setId: state.activeSavedSetId || state.draftId,
        setName: setBrief().name,
        context: preferenceContext(),
        overallDecision: setDecision,
        notes: $('#set-review-notes').value,
        tracks,
        transitions,
        evaluation: receipt?.evaluation || {},
        comparison: receipt?.comparison || {},
      });
      preferenceProfile = result.preferenceProfile;
      renderPreferenceProfile();
      renderCalibrationReport(result.report);
      $('#set-review-status').textContent = 'Review saved locally and preference evidence updated.';
    } catch (error) {
      $('#set-review-status').textContent = error.message || String(error);
    } finally {
      button.disabled = false;
      button.textContent = 'Save review';
    }
  }

  function resetSetReviewDraft() {
    setDecision = 'unreviewed';
    trackReviewDraft.clear();
    transitionReviewDraft.clear();
    $$('[data-set-decision]').forEach((button) => button.classList.remove('active'));
    const notes = $('#set-review-notes');
    if (notes) notes.value = '';
  }

  function setOverallDecision(value) {
    setDecision = value;
  }

  async function setPersonalizationEnabled(enabled) {
    preferenceProfile = await api.setPersonalization(enabled);
    renderPreferenceProfile();
  }

  async function resetPreferences() {
    preferenceProfile = await api.resetPreferences();
    renderPreferenceProfile();
  }

  return Object.freeze({
    loadPreferenceProfile,
    loadSetReviewReport,
    preferenceAdjustment,
    preferenceFeatures,
    recordPreference,
    renderCalibrationReport,
    renderPreferenceProfile,
    resetPreferences,
    resetSetReviewDraft,
    setOverallDecision,
    setPersonalizationEnabled,
    submitSetReview,
    transitionPreferenceAdjustment,
    transitionReviewFeatures,
  });
}
