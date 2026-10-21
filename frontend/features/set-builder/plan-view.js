/** Plan rendering and interactive track-editing ownership for Set Builder. */

import {
  buildVersionAwareReplacementCatalog,
  defaultVersionAwareReplacements,
  recordingVersionCount,
  searchVersionAwareReplacements,
} from './version-alternatives.js';
import { compactTrackSummaryMarkup, createSetBuilderWorkspaceShell } from './workspace-shell.js';

export function createSetPlanView({ state, dom, ui, music, policy, transitions, lifecycle, review }) {
  const { $, $$, escapeHtml } = dom;
  const {
    notify,
    descriptorEditorMarkup,
    saveDescriptorEditor,
    inferDescriptorEditor,
    bindCompactAudio,
    compactAudioMarkup,
  } = ui;
  const { compatibility, energyBand, formatLibraryKey, LIBRARY_ROLE_INFO, libraryRoles, songEnergy, timingProfile } =
    music;
  const {
    SET_IDENTITY_STORAGE_KEY,
    deduplicateSetRecordings,
    eligibleSetTracks,
    genreAllocationTargets,
    identityStore,
    intentionEvaluation,
    preferenceAdjustment,
    parseIdentityTerms,
    saveManualTrackIdentity,
    setCatalogTrackId,
    setCandidateScore,
    setRecordingKey,
    setTrackId,
    setVocalProfile,
    targetSetEnergy,
    trackIdentity,
    trackMatchesSetDetailedGenre,
    trackMatchesSetGenre,
  } = policy;
  const {
    auditionTransition,
    closeTransitionEditors,
    openTransitionEditor,
    setHealth,
    setRuntime,
    setSvgCurve,
    transitionSettings,
  } = transitions;
  const {
    editCommands,
    getPlanningReceipt,
    pushSetHistory,
    recordPreference,
    renderSetProposals,
    setBrief,
    setPlanSnapshot,
    updateSetHistoryButtons,
  } = lifecycle;
  const { trackReviewDraft, transitionReviewDraft } = review;
  const workspaceShell = createSetBuilderWorkspaceShell({ state, $, $$, setTrackId });

  function renderSetRules() {
    const byId = new Map(state.library.map((track) => [setTrackId(track), track]));
    const ruleTotal = state.requiredIds.size + state.excludedIds.size;
    $('#set-rule-count').textContent = `${ruleTotal} rule${ruleTotal === 1 ? '' : 's'}`;
    $('#set-rule-chips').innerHTML = [...state.requiredIds]
      .map(
        (id) =>
          `<button type="button" class="required-chip" data-rule="required" data-id="${escapeHtml(id)}">Required · ${escapeHtml(byId.get(id)?.source_name || id)} ×</button>`,
      )
      .concat(
        [...state.excludedIds].map(
          (id) =>
            `<button type="button" class="excluded-chip" data-rule="excluded" data-id="${escapeHtml(id)}">Excluded · ${escapeHtml(byId.get(id)?.source_name || id)} ×</button>`,
        ),
      )
      .join('');
    $('#set-rule-chips')
      .querySelectorAll('button')
      .forEach(
        (button) =>
          (button.onclick = () => {
            (button.dataset.rule === 'required' ? state.requiredIds : state.excludedIds).delete(button.dataset.id);
            renderSetRules();
          }),
      );
  }
  function transitionExplanation(previous, track) {
    if (!previous) return { score: null, text: 'Opening track · establishes the starting mood' };
    const match = compatibility(previous, track);
    const tempo = match.difference <= 0.02 ? 'tempo locked' : `${(match.difference * 100).toFixed(1)}% tempo move`;
    return { score: match.score, text: `${tempo} · ${match.key} · energy ${match.components.energy}/10` };
  }
  function setSelectionExplanation(track, index, brief) {
    const reasons = [];
    const id = setTrackId(track);
    const previous = state.plan[index - 1];
    const next = state.plan[index + 1];
    const energy = songEnergy(track);
    const target = targetSetEnergy(index, state.plan.length, brief);
    const energyDelta = energy - target;
    const matchingGenres = (brief.genres || []).filter((genre) => trackMatchesSetGenre(track, genre));
    const matchingDetailed = (brief.detailedGenres || []).filter((genre) => trackMatchesSetDetailedGenre(track, genre));
    if (track._aiSelectionReason?.text)
      reasons.push({ kind: track._aiSelectionReason.evidence || 'ai-suggested', text: track._aiSelectionReason.text });
    if (state.requiredIds.has(id))
      reasons.push({ kind: 'required', text: 'Selected because it is a must-play track.' });
    const intention = intentionEvaluation(track, brief);
    if (intention.required.length)
      reasons.push({
        kind: 'identity',
        text: `Meets the hard identity requirement: ${intention.required.join(' + ')}.`,
      });
    else if (intention.preferred.length)
      reasons.push({
        kind: 'identity',
        text: `Matches the requested identity through ${intention.preferred.slice(0, 2).join(' + ')}.`,
      });
    if (intention.avoided.length)
      reasons.push({
        kind: 'relaxed',
        text: `Uses a limited characteristic (${intention.avoided.join(' + ')}) only to preserve runtime or flow.`,
      });
    if (matchingDetailed.length)
      reasons.push({
        kind: 'genre',
        text: `Direct detailed-genre match: ${matchingDetailed.slice(0, 2).join(' + ')}.`,
      });
    else if (matchingGenres.length)
      reasons.push({ kind: 'genre', text: `Fits the requested ${matchingGenres.slice(0, 2).join(' + ')} direction.` });
    if (Math.abs(energyDelta) <= 0.1)
      reasons.push({
        kind: 'energy',
        text: `Matches the ${energyBand(target)} target energy for this point in the set.`,
      });
    else if (energyDelta > 0)
      reasons.push({ kind: 'energy', text: `Adds an intentional energy lift toward ${energyBand(energy)}.` });
    else reasons.push({ kind: 'energy', text: `Creates an energy reset before the next build.` });
    if (previous) {
      const incoming = compatibility(previous, track);
      const fromBpm = Number(previous.bpm || 0),
        toBpm = Number(track.bpm || 0);
      reasons.push({
        kind: 'tempo',
        text:
          Math.abs(fromBpm - toBpm) < 0.6
            ? `Keeps the tempo steady near ${toBpm.toFixed(1)} BPM.`
            : `Moves from ${fromBpm.toFixed(1)} to ${toBpm.toFixed(1)} BPM.`,
      });
      if (incoming.components.key >= 20)
        reasons.push({
          kind: 'key',
          text: `Compatible key: ${formatLibraryKey(previous.key)} → ${formatLibraryKey(track.key)} (${incoming.key}).`,
        });
      if (setVocalProfile(previous) === 'vocal-forward' && setVocalProfile(track) !== 'vocal-forward')
        reasons.push({ kind: 'vocals', text: 'Restores vocal space after a vocal-forward track.' });
    } else
      reasons.push({
        kind: 'opening',
        text: `Opens with ${energyBand(energy)} energy and establishes the set direction.`,
      });
    if (next) {
      const outgoing = compatibility(track, next);
      if (outgoing.score >= 70)
        reasons.push({
          kind: 'neighbor',
          text: `Also sets up the next track with a ${outgoing.score}% transition match.`,
        });
    }
    if (timingProfile(track) === 'steady' && reasons.length < 5)
      reasons.push({ kind: 'timing', text: 'Steady timing supports a longer, dependable blend.' });
    return reasons.slice(0, 5);
  }
  function setFallbackTier(track, brief) {
    const verifiedTier = track._candidateMetrics?.matchTier;
    if (verifiedTier) return { direct: 0, identity: 1, bridge: 2, fallback: 4 }[verifiedTier] ?? 3;
    if ((brief.genres || []).some((genre) => trackMatchesSetGenre(track, genre))) return 0;
    const evaluation = intentionEvaluation(track, brief),
      tags = trackIdentity(track);
    if (evaluation.preferred.length >= 2) return 1;
    if (evaluation.preferred.length || tags.includes('latin identity')) return 2;
    if (libraryRoles(track).includes('bridge') || evaluation.score >= 0) return 3;
    return 4;
  }
  function renderSetSelectionSummary(brief) {
    const root = $('#set-selection-summary');
    if (!root) return;
    const targets = genreAllocationTargets(brief.genres, brief.genreWeights, state.plan.length),
      usage = Object.fromEntries((brief.genres || []).map((genre) => [genre, 0])),
      groups = Object.fromEntries((brief.genres || []).map((genre) => [genre, []])),
      unassigned = [];
    state.plan.forEach((track) => {
      const matches = (brief.genres || []).filter((genre) => trackMatchesSetGenre(track, genre));
      if (!matches.length) {
        unassigned.push(track);
        return;
      }
      const genre = matches.sort(
        (a, b) => (targets[b] || 0) - (usage[b] || 0) - ((targets[a] || 0) - (usage[a] || 0)),
      )[0];
      usage[genre] = (usage[genre] || 0) + 1;
      groups[genre].push(track);
    });
    const totalWeight = Math.max(
      1,
      Object.values(brief.genreWeights || {}).reduce((sum, value) => sum + Math.max(0, Number(value || 0)), 0),
    );
    const genreRows = (brief.genres || [])
      .map((genre) => {
        const requested = Math.round((Math.max(0, Number(brief.genreWeights?.[genre] || 0)) / totalWeight) * 1000) / 10,
          actual = usage[genre] || 0,
          names = (groups[genre] || []).map((track) => track.source_name.replace(/\.[^.]+$/, '')).join(', ');
        return `<article class="${actual === (targets[genre] || 0) ? 'met' : 'adjusted'}"><div><strong>${escapeHtml(genre)}</strong><span>${requested}% requested · ${targets[genre] || 0} target · ${actual} chosen</span></div><p>${names ? escapeHtml(names) : 'No track selected for this allocation.'}</p></article>`;
      })
      .join('');
    const mustPlays = state.plan.filter((track) => state.requiredIds.has(setTrackId(track)));
    const tierLabels = [
      'Direct matches',
      'Identity matches',
      'Adjacent genres',
      'Neutral bridges',
      'Flow-only foundations',
    ];
    const tierCounts = state.plan.reduce((counts, track) => {
      const tier = setFallbackTier(track, brief);
      counts[tier] = (counts[tier] || 0) + 1;
      return counts;
    }, {});
    const relaxed = state.plan.filter((track) => intentionEvaluation(track, brief).avoided.length);
    const intentionRows = brief.identity?.text
      ? `<section class="set-intention-outcome"><strong>Intention fulfillment</strong><p>${escapeHtml(brief.identity.text)}</p><div>${tierLabels.map((label, index) => `<span class="${index > 1 && tierCounts[index] ? 'adjusted' : ''}"><b>${tierCounts[index] || 0}</b>${label}</span>`).join('')}</div>${relaxed.length ? `<p class="set-relaxation-warning">${relaxed.length} track${relaxed.length === 1 ? '' : 's'} relaxed a “limit or avoid” preference to preserve runtime or transition flow. No hard requirement was relaxed.</p>` : '<p>No stated preference was relaxed.</p>'}</section>`
      : '';
    const fallback = unassigned.length
      ? `<article class="adjusted"><div><strong>Manual or bridge tracks</strong><span>${unassigned.length} outside the weighted genres</span></div><p>${escapeHtml(unassigned.map((track) => track.source_name.replace(/\.[^.]+$/, '')).join(', '))}</p></article>`
      : '';
    const receipt = getPlanningReceipt(),
      evaluation = receipt?.evaluation,
      comparison = receipt?.comparison;
    const receiptRows = receipt
      ? `<section class="set-planning-receipt"><strong>${escapeHtml(receipt.mode === 'ai-planned' ? 'AI Planned' : receipt.mode === 'deterministic-fallback' ? 'Catalog-safe fallback' : receipt.mode === 'ai-interpreted' ? 'AI Interpreted' : 'Classic rules')}</strong><span>${escapeHtml(receipt.provider || 'offline')}${receipt.model ? ` · ${escapeHtml(receipt.model)}` : ''}${receipt.planningDurationMs != null ? ` · ${(receipt.planningDurationMs / 1000).toFixed(1)}s` : ''}</span><p>${escapeHtml(receipt.summary || '')}</p>${receipt.mode === 'deterministic-fallback' ? '<p>Catalog, constraint, duration, and journey checks passed. Mix health is evaluated separately below.</p>' : ''}${receipt.modelRepairs?.length ? `<p>${receipt.modelRepairs.length} structural model selection${receipt.modelRepairs.length === 1 ? ' was' : 's were'} repaired before validation.</p>` : ''}${comparison ? `<p><strong>AI ${comparison.ai?.qualityScore ?? '—'} · Baseline ${comparison.deterministic?.qualityScore ?? '—'}</strong> — ${escapeHtml(comparison.reason || '')}</p>` : ''}${evaluation?.disclosures?.map((text) => `<p>${escapeHtml(text)}</p>`).join('') || ''}${receipt.fallbackReason ? '<p class="set-relaxation-warning">The AI result was replaced by the deterministic safety fallback.</p>' : ''}</section>`
      : '';
    root.querySelector('div').innerHTML =
      `<p class="set-selection-overview">${state.plan.length} songs chosen by allocating the requested genre balance first, then ranking candidates for musical identity, energy shape, BPM and key compatibility, vocal spacing, timing, and transition health.${mustPlays.length ? ` ${mustPlays.length} must-play track${mustPlays.length === 1 ? ' was' : 's were'} preserved.` : ''}</p>${receiptRows}${intentionRows}<div class="set-selection-groups">${genreRows}${fallback}</div><p class="set-selection-note">Open “Why this track” on any song for its position-specific explanation. Counts may differ only when a locked, required, manually added, or unavailable genre track prevents the requested allocation. Any expansion beyond direct matches is disclosed above.</p>`;
  }
  function renderSetPlan() {
    const result = $('#set-result');
    workspaceShell.beforeRender();
    result.hidden = !state.plan.length;
    if (!state.plan.length) return;
    closeTransitionEditors();
    result.classList.toggle('compact-planning', state.compactMode);
    $('#set-compact').textContent = state.compactMode ? 'Comfortable view' : 'Compact view';
    updateSetHistoryButtons();
    const activeProposal = state.proposals.find((proposal) => proposal.id === state.activeProposal);
    if (activeProposal) {
      activeProposal.snapshot = setPlanSnapshot();
      activeProposal.health = setHealth();
    }
    renderSetProposals();
    const brief = setBrief();
    const runtime = setRuntime();
    const resultName = $('#set-result-name');
    if (document.activeElement !== resultName) resultName.value = brief.name;
    const genreSummary = (brief.detailedGenres || []).length
      ? brief.detailedGenres.join(' + ')
      : brief.genres.length
        ? brief.genres.join(' + ')
        : 'open genre mix';
    $('#set-result-summary').textContent =
      `${state.plan.length} tracks · approximately ${Math.round(runtime / 60)} minutes · ${genreSummary} · ${brief.genreFlow.replace('-', ' ')} · ${brief.curve.replace('-', ' ')}`;
    renderSetSelectionSummary(brief);
    const exportStatus = $('#set-export-status');
    exportStatus.className = 'set-export-status';
    exportStatus.innerHTML = '<span>Rekordbox paths will be checked before export.</span>';
    const health = setHealth();
    const healthThreshold = brief.minimumHealth;
    const healthAccepted = health.score >= healthThreshold;
    const weak = health.transitions.filter((item) => item.score < healthThreshold).sort((a, b) => a.score - b.score);
    const healthDetail = weak.length
      ? weak
          .slice(0, 8)
          .map(
            (item) =>
              `<button type="button" data-transition="${item.to}"><b>${item.from + 1} → ${item.to + 1}</b><span>${item.score}% · ${escapeHtml(item.key)} · tempo ${item.components.tempo}/45</span></button>`,
          )
          .join('')
      : healthAccepted
        ? `<p>Health target met. No transitions fall below ${healthThreshold}.</p>`
        : `<p>${health.vocalClashes} vocal-forward pairing${health.vocalClashes === 1 ? ' is' : 's are'} lowering the overall health below ${healthThreshold}. Regenerate or replace those tracks.</p>`;
    $('#set-health').className =
      `set-health ${healthAccepted ? 'good' : health.score >= healthThreshold - 10 ? 'fair' : 'weak'}`;
    $('#set-health').innerHTML =
      `<summary><strong>${health.score}</strong><span><b>Mix health</b><em>${healthAccepted ? 'Performance-ready' : 'Draft · repair needed'}</em></span><small>Target ${healthThreshold} · ${weak.length} transition${weak.length === 1 ? '' : 's'} below target · ${health.vocalClashes} vocal clash${health.vocalClashes === 1 ? '' : 'es'}</small></summary><div>${healthDetail}</div>`;
    $('#set-health')
      .querySelectorAll('[data-transition]')
      .forEach(
        (button) =>
          (button.onclick = () =>
            document
              .querySelector(`.set-track-card[data-index="${button.dataset.transition}"]`)
              ?.scrollIntoView({ behavior: 'smooth', block: 'center' })),
      );
    ['#save-set', '#export-set-csv', '#export-set-m3u'].forEach((selector) => {
      const button = $(selector);
      button.disabled = !healthAccepted;
      button.title = healthAccepted ? '' : `Set health must reach ${healthThreshold} before saving or exporting.`;
    });
    $('#set-track-list').innerHTML = state.plan
      .map((track, index) => {
        const transition = transitionExplanation(state.plan[index - 1], track);
        const id = setTrackId(track);
        const locked = state.lockedIds.has(id);
        const selectionReasons = setSelectionExplanation(track, index, brief);
        const preview = track._job?.id
          ? compactAudioMarkup(`/api/jobs/${track._job.id}/audio/wav`, track.duration_seconds, true)
          : '';
        const review = trackReviewDraft.get(id) || {},
          metrics = track._candidateMetrics || {};
        const alternateVersionCount = recordingVersionCount(track, state.library);
        const pairId = index ? `${setCatalogTrackId(state.plan[index - 1])}→${setCatalogTrackId(track)}` : '';
        return `<article class="set-track-card${locked ? ' locked' : ''}" draggable="${locked ? 'false' : 'true'}" data-index="${index}"><span class="set-position">${index + 1}</span><div class="set-track-title"><strong>${escapeHtml(track.source_name.replace(/\.[^.]+$/, ''))}</strong><span>${track.artist ? `${escapeHtml(track.artist)} · ` : ''}${escapeHtml(track._genre)} · ${libraryRoles(
          track,
        )
          .map((role) => LIBRARY_ROLE_INFO[role]?.[0] || role)
          .join(
            ', ',
          )}</span>${preview}</div>${compactTrackSummaryMarkup({ track, transition, locked, review, formatKey: formatLibraryKey, energyLabel: energyBand(songEnergy(track)), healthThreshold, escapeHtml })}<div class="set-track-meta"><strong>${Number(track.bpm || 0).toFixed(1)} BPM · ${escapeHtml(formatLibraryKey(track.key))}</strong><span>${energyBand(songEnergy(track))} energy · ${setVocalProfile(track)} · ${timingProfile(track)}</span><span>${track._hasExtended ? 'Extended edit available' : 'Original analyzed track'}${metrics.preferenceAdjustment ? ` · preference ${metrics.preferenceAdjustment > 0 ? '+' : ''}${metrics.preferenceAdjustment} · rank ${metrics.rankDelta > 0 ? '+' : ''}${metrics.rankDelta}` : ''}</span><details class="set-selection-reasons"><summary>Why this track</summary><ul>${selectionReasons
          .map((reason) => {
            const label = ['verified', 'estimated', 'ai-suggested'].includes(reason.kind)
              ? `<em>${escapeHtml(reason.kind)}</em>`
              : '';
            return `<li data-reason="${reason.kind}">${label}${escapeHtml(reason.text)}</li>`;
          })
          .join(
            '',
          )}</ul></details><div class="set-track-review"><button type="button" data-track-review="accept" class="${review.decision === 'accept' ? 'active' : ''}">✓ Keep</button><button type="button" data-track-review="reject" class="${review.decision === 'reject' ? 'active' : ''}">× Reject</button><select class="set-reject-reason" aria-label="Rejection reason"><option value="">Reason…</option><option value="wrong-genre">Wrong genre</option><option value="wrong-energy">Wrong energy</option><option value="weak-transition">Weak transition</option><option value="too-familiar">Too familiar</option><option value="not-familiar-enough">Not familiar enough</option><option value="other">Other</option></select></div></div><div class="set-transition ${transition.score != null && transition.score < healthThreshold ? 'warning' : 'good'}"><b>${transition.score == null ? 'OPEN' : `${transition.score}% match`}</b><span><i>Why this transition:</i> ${escapeHtml(transition.text)}</span>${index ? `<button type="button" class="set-audition">Mix transition</button><button type="button" class="edit-transition">Edit mix</button><label class="set-transition-rating">Your rating<select data-pair-id="${escapeHtml(pairId)}"><option value="3">Not rated</option><option value="5">5 · Excellent</option><option value="4">4 · Good</option><option value="2">2 · Weak</option><option value="1">1 · Bad</option></select></label>` : ''}</div><div class="set-row-actions"><button type="button" class="set-move-up" ${index === 0 ? 'disabled' : ''}>↑ Earlier</button><button type="button" class="set-move-down" ${index === state.plan.length - 1 ? 'disabled' : ''}>↓ Later</button><button type="button" class="set-lock">${locked ? 'Unlock' : 'Lock'}</button><button type="button" class="set-remove">Remove</button><button type="button" class="set-add-after">Add after</button><button type="button" class="set-alternative">${alternateVersionCount ? `Alternatives · ${alternateVersionCount} other version${alternateVersionCount === 1 ? '' : 's'}` : 'Find alternative'}</button><button type="button" class="set-identity">Identity tags</button></div><div class="set-track-quick-actions"><button type="button" class="set-quick-lock">${locked ? 'Unlock' : 'Lock'}</button><button type="button" class="set-quick-alternative">Replace</button><button type="button" class="set-inspect-track">More</button></div></article>`;
      })
      .join('');
    bindSetRows();
    bindCompactAudio($('#set-track-list'));
    workspaceShell.bindRows();
    setSvgCurve('#set-energy-curve', state.plan.map(songEnergy), '#d6ff44');
    setSvgCurve(
      '#set-bpm-curve',
      state.plan.map((track) => Number(track.bpm || 0)),
      '#ffb45c',
    );
    const warnings = [];
    state.plan.slice(1).forEach((track, index) => {
      const match = compatibility(state.plan[index], track);
      if (match.score < healthThreshold) {
        const weakest = Object.entries(match.components).sort((a, b) => a[1] - b[1])[0]?.[0] || 'compatibility';
        warnings.push(
          `Transition ${index + 1} → ${index + 2}: ${match.score}% is below the ${healthThreshold}% target; weakest area is ${weakest}${match.key === 'distant key' ? ' with distant keys' : ''}.`,
        );
      }
      if (setVocalProfile(state.plan[index]) === 'vocal-forward' && setVocalProfile(track) === 'vocal-forward')
        warnings.push(
          `Transition ${index + 1} → ${index + 2}: both tracks are vocal-forward; avoid overlapping verses.`,
        );
    });
    const serverWarnings = (getPlanningReceipt()?.warnings || []).map((warning) => {
      const labels = {
        'large-bpm-jump': 'Large BPM jump',
        'weak-key-transition': 'Weak harmonic transition',
        'vocal-collision': 'Possible vocal collision',
        'expanded-genre-match': 'Expanded genre match',
      };
      return `${labels[warning.code] || warning.code}${warning.position ? ` at position ${warning.position}` : ''}${warning.from && warning.to ? ` · ${warning.from} → ${warning.to}` : ''}.`;
    });
    warnings.push(...serverWarnings);
    $('#set-warnings').innerHTML = warnings.length
      ? warnings.map((text) => `<p>${escapeHtml(text)}</p>`).join('')
      : `<p class="set-ready">Set health target ${healthThreshold} met with no transition warnings. Listen through the plan before performing it live.</p>`;
  }
  function moveSetTrack(from, to) {
    if (editCommands.move(from, to)) updateSetHistoryButtons();
  }
  function bindSetRows() {
    let dragging = null;
    $$('.set-track-card').forEach((card) => {
      const index = Number(card.dataset.index);
      card.querySelector('.set-move-up').onclick = () => moveSetTrack(index, index - 1);
      card.querySelector('.set-move-down').onclick = () => moveSetTrack(index, index + 1);
      const toggleLock = () => {
        pushSetHistory();
        const track = state.plan[index],
          id = setTrackId(track),
          locking = !state.lockedIds.has(id);
        locking ? state.lockedIds.add(id) : state.lockedIds.delete(id);
        if (locking) void recordPreference('lock', track);
        renderSetPlan();
      };
      card.querySelectorAll('.set-lock, .set-quick-lock').forEach((button) => (button.onclick = toggleLock));
      card.querySelector('.set-remove').onclick = () => {
        pushSetHistory();
        const track = state.plan[index];
        state.lockedIds.delete(setTrackId(track));
        state.plan.splice(index, 1);
        void recordPreference('remove', track);
        renderSetPlan();
      };
      card.querySelector('.set-add-after').onclick = () => addSetTrack(index + 1, card);
      card.querySelector('.set-alternative').onclick = () => replaceSetTrack(index);
      card.querySelector('.set-quick-alternative').onclick = () => replaceSetTrack(index);
      card.querySelector('.set-identity').onclick = () => openTrackIdentityEditor(index, card);
      card.querySelectorAll('[data-track-review]').forEach(
        (button) =>
          (button.onclick = () => {
            const track = state.plan[index],
              reason = card.querySelector('.set-reject-reason').value;
            trackReviewDraft.set(setTrackId(track), {
              decision: button.dataset.trackReview,
              reason: button.dataset.trackReview === 'reject' ? reason : '',
            });
            renderSetPlan();
          }),
      );
      const rejectReason = card.querySelector('.set-reject-reason');
      rejectReason.value = trackReviewDraft.get(setTrackId(state.plan[index]))?.reason || '';
      rejectReason.onchange = (event) => {
        const track = state.plan[index],
          current = trackReviewDraft.get(setTrackId(track));
        if (current?.decision === 'reject')
          trackReviewDraft.set(setTrackId(track), { ...current, reason: event.currentTarget.value });
      };
      const rating = card.querySelector('.set-transition-rating select');
      if (rating) {
        rating.value = String(transitionReviewDraft.get(rating.dataset.pairId) || 3);
        rating.onchange = (event) =>
          transitionReviewDraft.set(event.currentTarget.dataset.pairId, Number(event.currentTarget.value));
      }
      card
        .querySelector('.set-audition')
        ?.addEventListener('click', (event) => auditionTransition(index, event.currentTarget));
      card.querySelector('.edit-transition')?.addEventListener('click', () => openTransitionEditor(index, card));
      card.ondragstart = (event) => {
        if (event.target.closest('input,select,button,audio,.transition-editor,.set-compact-audio')) {
          event.preventDefault();
          return;
        }
        dragging = index;
        card.classList.add('dragging');
      };
      card.ondragend = () => card.classList.remove('dragging');
      card.ondragover = (event) => event.preventDefault();
      card.ondrop = (event) => {
        event.preventDefault();
        moveSetTrack(dragging, index);
      };
    });
  }
  function openTrackIdentityEditor(index, card) {
    card.querySelector('.set-identity-editor')?.remove();
    const track = state.plan[index],
      host = document.createElement('section');
    host.className = 'set-identity-editor';
    host.innerHTML = descriptorEditorMarkup(track._descriptors || []);
    card.append(host);
    const editor = host.querySelector('.track-descriptor-editor');
    editor.hidden = false;
    const close = () => host.remove();
    editor.querySelector('.cancel-descriptors').onclick = close;
    editor.querySelector('.close-descriptor-editor').onclick = close;
    editor.querySelector('.infer-descriptors').onclick = async (event) => {
      if (!track._downloadedId) {
        notify('Catalog this track before inferring identity tags.', 'danger');
        return;
      }
      const action = event.currentTarget,
        original = action.textContent;
      action.disabled = true;
      action.textContent = 'Inferring…';
      try {
        await inferDescriptorEditor(editor, [track._downloadedId]);
      } catch (error) {
        notify(error.message, 'danger');
      } finally {
        action.disabled = false;
        action.textContent = original;
      }
    };
    editor.querySelector('.save-descriptors').onclick = async (event) => {
      const action = event.currentTarget;
      action.disabled = true;
      action.textContent = 'Saving…';
      try {
        if (track._downloadedId) {
          const result = await saveDescriptorEditor(editor, [track._downloadedId]);
          track._descriptors = result.values || [];
          track._manualIdentity = track._descriptors.map((item) => item.value);
          const store = identityStore();
          delete store[setTrackId(track)];
          localStorage.setItem(SET_IDENTITY_STORAGE_KEY, JSON.stringify(store));
        } else {
          const terms = [...editor.querySelectorAll('[data-descriptor-category]')].flatMap((input) =>
            parseIdentityTerms(input.value),
          );
          saveManualTrackIdentity(track, terms);
        }
        renderSetPlan();
        $('#set-builder-message').textContent =
          `Identity tags saved for ${track.source_name.replace(/\.[^.]+$/, '')} in the persistent track catalog.`;
      } catch (error) {
        notify(error.message, 'danger');
        action.disabled = false;
        action.textContent = 'Save changes';
      }
    };
    editor.querySelector('input')?.focus();
  }
  function addSetTrack(insertIndex = state.plan.length, anchor = null) {
    document.querySelectorAll('.set-add-track-panel').forEach((item) => item.remove());
    const used = new Set(state.plan.map(setRecordingKey));
    const brief = setBrief();
    const previous = state.plan[insertIndex - 1];
    const next = state.plan[insertIndex];
    const available = deduplicateSetRecordings(state.library)
      .filter((track) => !used.has(setRecordingKey(track)))
      .map((track) => ({
        track,
        score:
          setCandidateScore(track, previous, insertIndex, state.plan.length + 1, brief) +
          (next ? compatibility(track, next).score * 0.3 : 0),
      }))
      .sort((a, b) => b.score - a.score);
    const panel = document.createElement('section');
    panel.className = 'set-alternative-panel set-add-track-panel';
    const genres = [...new Set(available.map((choice) => choice.track._genre).filter(Boolean))].sort((a, b) =>
      a.localeCompare(b),
    );
    panel.innerHTML = `<header><div><strong>${insertIndex >= state.plan.length ? 'Add a track to the end' : `Add a track at position ${insertIndex + 1}`}</strong><span>Search any unused song in your DJ Library.</span></div><button type="button" class="close-alternatives" aria-label="Close track browser">×</button></header><div class="set-alternative-tools"><label><span>Song, artist, or genre</span><input class="alternative-search" type="search" placeholder="Search your library…" autocomplete="off"></label><label><span>Genre</span><select class="alternative-genre"><option value="">All genres</option>${genres.map((genre) => `<option value="${escapeHtml(genre)}">${escapeHtml(genre)}</option>`).join('')}</select></label></div><div class="set-alternative-status" aria-live="polite"></div><div class="set-alternative-list"></div>`;
    const list = panel.querySelector('.set-alternative-list');
    const status = panel.querySelector('.set-alternative-status');
    const renderChoices = () => {
      const query = panel.querySelector('.alternative-search').value.trim().toLowerCase();
      const genre = panel.querySelector('.alternative-genre').value;
      const matches = available.filter(({ track }) => {
        const haystack = `${track.source_name || ''} ${track.artist || ''} ${track._genre || ''}`.toLowerCase();
        return (!query || haystack.includes(query)) && (!genre || track._genre === genre);
      });
      const choices = matches.slice(0, query || genre ? 30 : 5);
      status.textContent = `${matches.length} available track${matches.length === 1 ? '' : 's'} · showing ${choices.length}${query || genre ? '' : ' best fits'}`;
      list.innerHTML = choices.length
        ? choices
            .map((choice, choiceIndex) => {
              const track = choice.track;
              const preview = track._job?.id
                ? compactAudioMarkup(`/api/jobs/${track._job.id}/audio/wav`, track.duration_seconds, true)
                : '';
              return `<article data-choice="${choiceIndex}"><div><strong>${escapeHtml(track.source_name.replace(/\.[^.]+$/, ''))}</strong><span>${track.artist ? `${escapeHtml(track.artist)} · ` : ''}${escapeHtml(track._genre)} · ${Number(track.bpm || 0).toFixed(1)} BPM · ${escapeHtml(formatLibraryKey(track.key))} · ${Math.round(choice.score)} fit</span></div>${preview}<button type="button" class="use-alternative">Add to set</button></article>`;
            })
            .join('')
        : '<p class="empty">No unused tracks match that search.</p>';
      list.querySelectorAll('.use-alternative').forEach(
        (button) =>
          (button.onclick = () => {
            const choice = choices[Number(button.closest('article').dataset.choice)];
            if (!choice) return;
            pushSetHistory();
            state.plan.splice(Math.min(insertIndex, state.plan.length), 0, choice.track);
            void recordPreference('replace-in', choice.track);
            renderSetPlan();
          }),
      );
      bindCompactAudio(list);
    };
    (anchor || $('#set-add-track-panel-host')).append(panel);
    panel.querySelector('.close-alternatives').onclick = () => panel.remove();
    panel.querySelector('.alternative-search').oninput = renderChoices;
    panel.querySelector('.alternative-genre').onchange = renderChoices;
    renderChoices();
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    panel.querySelector('.alternative-search').focus();
  }
  function replaceSetTrack(index) {
    const used = new Set(state.plan.filter((_, position) => position !== index).map(setRecordingKey));
    const brief = setBrief();
    const current = state.plan[index];
    const previous = state.plan[index - 1];
    const next = state.plan[index + 1];
    const rankTrack = (track) => ({
      track,
      score:
        setCandidateScore(track, previous, index, state.plan.length, brief) +
        (next ? compatibility(track, next).score * 0.3 : 0),
    });
    const { versionChoices, recommendedSongs, searchable, genres } = buildVersionAwareReplacementCatalog({
      current,
      library: state.library,
      usedRecordingKeys: used,
      recommendedTracks: eligibleSetTracks(brief),
      rankTrack,
    });
    const card = $(`.set-track-card[data-index="${index}"]`);
    if (!card) return;
    card.querySelector('.set-alternative-panel')?.remove();
    const panel = document.createElement('section');
    panel.className = 'set-alternative-panel';
    panel.innerHTML = `<header><div><strong>Choose an alternative</strong><span>Use another version of this song or replace it with a different recording. Only one version can remain in the set.</span></div><button type="button" class="close-alternatives" aria-label="Close alternatives">×</button></header><div class="set-alternative-tools"><label><span>Song, artist, version, or genre</span><input class="alternative-search" type="search" placeholder="Search your library…" autocomplete="off"></label><label><span>Genre</span><select class="alternative-genre"><option value="">All genres</option>${genres.map((genre) => `<option value="${escapeHtml(genre)}">${escapeHtml(genre)}</option>`).join('')}</select></label></div><div class="set-alternative-status" aria-live="polite"></div><div class="set-alternative-list"></div>`;
    const list = panel.querySelector('.set-alternative-list');
    const status = panel.querySelector('.set-alternative-status');
    const renderChoices = () => {
      const query = panel.querySelector('.alternative-search').value.trim().toLowerCase();
      const genre = panel.querySelector('.alternative-genre').value;
      const searching = Boolean(query || genre);
      const matches = searchVersionAwareReplacements(searchable, query, genre);
      const choices = searching
        ? matches.slice(0, 30).map((choice) => ({ ...choice, group: 'Search results' }))
        : defaultVersionAwareReplacements(versionChoices, recommendedSongs);
      status.textContent = searching
        ? `${matches.length} matching unused track${matches.length === 1 ? '' : 's'} · showing ${choices.length}`
        : `${versionChoices.length} other version${versionChoices.length === 1 ? '' : 's'} · ${recommendedSongs.length} recommended different song${recommendedSongs.length === 1 ? '' : 's'}`;
      list.innerHTML = choices.length
        ? choices
            .map((choice, choiceIndex, items) => {
              const track = choice.track;
              const preview = track._job?.id
                ? compactAudioMarkup(`/api/jobs/${track._job.id}/audio/wav`, track.duration_seconds, true)
                : '';
              const heading = !choiceIndex || items[choiceIndex - 1].group !== choice.group
                ? `<h4>${escapeHtml(choice.group)}</h4>`
                : '';
              return `${heading}<article data-choice="${choiceIndex}" class="${choice.sameRecording ? 'same-recording-version' : ''}"><div><em class="set-alternative-kind">${choice.sameRecording ? escapeHtml(choice.versionLabel) : 'Different song'}</em><strong>${escapeHtml(track.source_name.replace(/\.[^.]+$/, ''))}</strong><span>${track.artist ? `${escapeHtml(track.artist)} · ` : ''}${escapeHtml(track._genre)} · ${Number(track.bpm || 0).toFixed(1)} BPM · ${escapeHtml(formatLibraryKey(track.key))} · ${Math.round(choice.score)} fit</span></div>${preview}<button type="button" class="use-alternative">${choice.sameRecording ? 'Use this version' : 'Use this track'}</button></article>`;
            })
            .join('')
        : '<p class="empty">No unused tracks match that search.</p>';
      list.querySelectorAll('.use-alternative').forEach(
        (button) =>
          (button.onclick = () => {
            const choice = choices[Number(button.closest('article').dataset.choice)];
            if (!choice) return;
            pushSetHistory();
            const replaced = state.plan[index];
            state.lockedIds.delete(setTrackId(replaced));
            state.plan[index] = choice.track;
            void recordPreference('replace-out', replaced);
            void recordPreference('replace-in', choice.track);
            renderSetPlan();
          }),
      );
      bindCompactAudio(list);
    };
    card.append(panel);
    panel.querySelector('.close-alternatives').onclick = () => panel.remove();
    panel.querySelector('.alternative-search').oninput = renderChoices;
    panel.querySelector('.alternative-genre').onchange = renderChoices;
    renderChoices();
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    panel.querySelector('.alternative-search').focus();
  }

  return Object.freeze({
    addSetTrack,
    bindSetRows,
    moveSetTrack,
    openTrackIdentityEditor,
    renderSetPlan,
    renderSetRules,
    replaceSetTrack,
  });
}
