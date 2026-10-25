/** AI and deterministic Set Builder planning-session orchestration. */
import {
  aiPlanningContext,
  assignPlanSections,
  catalogIds,
  planningJourney,
} from './planning-request.js';
import {
  createJourneyAllocation,
  deterministicTrackCount,
  ensureRequestedGenreCoverage,
  journeyPlanSnapshot,
  journeySectionFallbacks,
  sectionCandidatePool,
  shortlistJourneyPool,
} from './journey-allocation.js';
import { createSetRegenerationCommand } from './regeneration.js';
export function createSetPlanningSession({ state, dom, clients, policy, transitions, lifecycle, view, progress = {} }) {
  const { $, escapeHtml, notify } = dom;
  const { planningClient, classicPlanner } = clients;
  const {
    genreAllocationTargets,
    intendedGenreForPosition,
    intentionEvaluation,
    setCandidateScore,
    setCatalogTrackId,
    setTrackId,
    songEnergy,
    targetSetEnergy,
    trackMatchesIntendedGenre,
    trackMatchesSetGenre,
  } = policy;
  const { autoOptimizeSetTransitions, improveSetOrder, setHealth, setHealthIssues, stopTransitionPreview } =
    transitions;
  const {
    advancePlanRevision = () => null,
    eligibleSetTracks,
    pushSetHistory,
    renderSetPlan,
    resetSetReviewDraft,
    restoreSetSnapshot,
    setBrief,
    setPlanSnapshot,
  } = lifecycle;
  const { aiObservabilityCards, setProposalMarkup } = view;
  let proposalSwitchNonce = 0;
  let activePlanningJobId = '';
  let planningController = null;
  let planningReceipt = null;

  async function generateDeterministicSetPlan() {
    progress.showEligibilityScan?.();
    const brief = setBrief();
    const journey = planningJourney(brief);
    const eligiblePool = eligibleSetTracks(brief);
    const requiredIds = new Set(state.requiredIds);
    const intendedGenres = [...(brief.identity?.requestedGenres || []), ...(brief.identity?.optionalGenres || [])];
    const coarseScore = (track) =>
      intentionEvaluation(track, brief).score +
      (intendedGenres.some((term) => trackMatchesIntendedGenre(track, term)) ? 40 : 0) -
      Math.abs(songEnergy(track) - targetSetEnergy(0, 2, brief)) * 12;
    const pool = shortlistJourneyPool({ eligiblePool, requiredIds, setTrackId, score: coarseScore });
    if (pool.length < 2) {
      $('#set-builder-message').textContent =
        `Only ${pool.length} analyzed track${pool.length === 1 ? '' : 's'} passed the hard filters. Check BPM, vocals, timing, exclusions, and manually selected genres.`;
      return;
    }
    const protectedCount = new Set([...state.requiredIds, ...state.lockedIds]).size;
    const count = deterministicTrackCount(pool, brief.length, protectedCount);
    const required = pool.filter((track) => state.requiredIds.has(setTrackId(track)));
    const genreTargets = genreAllocationTargets(brief.genres, brief.genreWeights, count);
    const previousPlan = state.plan;
    const allocation = createJourneyAllocation({ journey, count, pool, trackMatchesIntendedGenre, setTrackId });
    const { matchesSection, positionSections } = allocation;
    if (allocation.scarcity) {
      const { section, slots, available } = allocation.scarcity;
      const genres = (section?.genres || []).join(' or ') || 'the section genres';
      $('#set-builder-message').textContent =
        `${section?.name || 'A journey section'} needs ${slots} unique tracks matching ${genres}, but only ${available} analyzed track${available === 1 ? ' is' : 's are'} available. Edit that section, enable related genres, or analyze and retag more matching music.`;
      return;
    }
    const buildVariation = (strategy, generatedTrackIds) => {
      const remaining = new Map(pool.map((track) => [setTrackId(track), track]));
      const nextPlan = [];
      const genreUsage = Object.fromEntries((brief.genres || []).map((genre) => [genre, 0]));
      const previousPlanIds = new Set(previousPlan.map(setTrackId));
      let failed = false;
      const recordGenre = (track) => {
        const matches = (brief.genres || []).filter((genre) => trackMatchesSetGenre(track, genre));
        if (!matches.length) return;
        const genre = matches.sort(
          (a, b) => (genreTargets[b] || 0) - (genreUsage[b] || 0) - ((genreTargets[a] || 0) - (genreUsage[a] || 0)),
        )[0];
        genreUsage[genre] = (genreUsage[genre] || 0) + 1;
      };
      const nextGenre = () => {
        const configuredOrder = state.genreSelectionOrder
          .filter((genre) => (brief.genres || []).includes(genre))
          .concat((brief.genres || []).filter((genre) => !state.genreSelectionOrder.includes(genre)));
        const open = configuredOrder.filter(
          (genre) =>
            (genreUsage[genre] || 0) < (genreTargets[genre] || 0) &&
            [...remaining.values()].some((track) => trackMatchesSetGenre(track, genre)),
        );
        if (!open.length) return '';
        return open.sort((a, b) => {
          const deficitA = (genreTargets[a] || 0) - (genreUsage[a] || 0);
          const deficitB = (genreTargets[b] || 0) - (genreUsage[b] || 0);
          if (brief.genreFlow === 'blend')
            return deficitB / Math.max(1, genreTargets[b] || 0) - deficitA / Math.max(1, genreTargets[a] || 0);
          return configuredOrder.indexOf(a) - configuredOrder.indexOf(b);
        })[0];
      };
      state.generationNonce += 1;
      Array.from({ length: count }, (_, index) => {
        if (failed) return;
        const locked = previousPlan[index];
        if (locked && state.lockedIds.has(setTrackId(locked)) && remaining.has(setTrackId(locked))) {
          remaining.delete(setTrackId(locked));
          nextPlan.push(locked);
          recordGenre(locked);
          return;
        }
        const requiredIndex = required.length ? Math.round((index * (required.length + 1)) / count) - 1 : -1;
        const forced = required[requiredIndex];
        if (forced && remaining.has(setTrackId(forced))) {
          remaining.delete(setTrackId(forced));
          nextPlan.push(forced);
          recordGenre(forced);
          return;
        }
        const previous = nextPlan[index - 1] || null;
        const section = positionSections[index];
        const targetGenre = nextGenre();
        const identityTarget = intendedGenreForPosition(brief.identity, index, count);
        const available = [...remaining.values()];
        const identityTargeted = identityTarget
          ? available.filter((track) => trackMatchesIntendedGenre(track, identityTarget))
          : [];
        const targeted = targetGenre
          ? available.filter((track) => trackMatchesSetGenre(track, targetGenre))
          : available;
        const candidatePool = sectionCandidatePool({
          available,
          section,
          allocation,
          identityTargeted,
          globallyTargeted: targeted,
          setTrackId,
        });
        const ranked = candidatePool
          .map((track) => {
            const id = setTrackId(track);
            const wasSamePosition = Boolean(previousPlan[index]) && setTrackId(previousPlan[index]) === id;
            const wasInPrevious = previousPlanIds.has(id);
            return {
              track,
              score:
                setCandidateScore(track, previous, index, count, brief, strategy, generatedTrackIds) -
                (wasSamePosition ? 12 : wasInPrevious ? 3 : 0),
            };
          })
          .sort((a, b) => b.score - a.score);
        if (!ranked.length) {
          failed = true;
          return;
        }
        const competitive = ranked.filter((item) => item.score >= ranked[0].score - 18).slice(0, 18);
        const weights = competitive.map((item) => Math.exp((item.score - competitive.at(-1).score) / 5));
        const total = weights.reduce((sum, value) => sum + value, 0);
        let pick = Math.abs(Math.sin(state.generationNonce * 9283 + index * 3343)) * total;
        let choice = competitive[0]?.track;
        for (let option = 0; option < competitive.length; option += 1) {
          pick -= weights[option];
          if (pick <= 0) {
            choice = competitive[option].track;
            break;
          }
        }
        if (choice) {
          remaining.delete(setTrackId(choice));
          nextPlan.push(choice);
          recordGenre(choice);
        }
      });
      required.forEach((track) => {
        if (!nextPlan.some((item) => setTrackId(item) === setTrackId(track))) nextPlan.push(track);
      });
      ensureRequestedGenreCoverage({
        plan: nextPlan,
        remaining,
        intendedGenres,
        trackMatchesIntendedGenre,
        coarseScore,
        candidateScore: (track, index) =>
          setCandidateScore(
            track,
            nextPlan[index - 1] || null,
            index,
            count,
            brief,
            strategy,
            generatedTrackIds,
          ),
        canReplace: (track) =>
          !state.lockedIds.has(setTrackId(track)) && !state.requiredIds.has(setTrackId(track)),
        replacementAllowed: (replacement, index) => matchesSection(replacement, positionSections[index]),
        setTrackId,
      });
      assignPlanSections(nextPlan, journey, state.lockedIds, setTrackId);
      return failed ? [] : nextPlan;
    };
    const result = await classicPlanner.generate({
      count,
      minimumHealth: brief.minimumHealth,
      buildVariation,
      improveOrder: (plan) => improveSetOrder(plan, brief),
      evaluate: setHealth,
      trackId: setTrackId,
      snapshot: (plan) => journeyPlanSnapshot(plan, state.lockedIds, setTrackId),
    });
    if (!result.accepted.length) {
      const issues = setHealthIssues(result.best.health, brief.minimumHealth);
      $('#set-builder-message').textContent =
        `No direction was applied. The best search reached ${result.best.health.score}/100, below your ${brief.minimumHealth} target. ${issues.slice(0, 2).join(' · ') || 'Relax a constraint or lower the health floor.'}`;
      return;
    }
    if (state.plan.length) pushSetHistory();
    state.proposals = result.proposals;
    const preferred = result.preferred;
    state.activeProposal = preferred.id;
    restoreSetSnapshot(preferred.snapshot, false);
    assignPlanSections(state.plan, journey, state.lockedIds, setTrackId);
    const sectionFallbacks = journeySectionFallbacks(state.plan, positionSections, matchesSection);
    $('#set-builder-message').textContent =
      `Built ${result.accepted.length} distinct direction${result.accepted.length === 1 ? '' : 's'}. Optimizing transition techniques for ${preferred.label}…`;
    progress.startTransitionOptimization?.();
    await autoOptimizeSetTransitions();
    const planRevision = advancePlanRevision();
    preferred.snapshot = setPlanSnapshot();
    preferred.health = setHealth();
    planningReceipt = {
      version: 1,
      mode: $('#set-planning-mode').value === 'classic' ? 'classic' : 'ai-interpreted',
      provider: brief.identity?.provider || 'offline',
      model: null,
      summary: `${preferred.label} selected from ${result.accepted.length} deterministic direction${result.accepted.length === 1 ? '' : 's'}.`,
      warnings: sectionFallbacks.map(({ index, section }) => ({
        code: 'expanded-genre-match',
        position: index + 1,
        sectionId: section.id,
      })),
      evaluation: null,
      candidatePool: null,
      planningDurationMs: null,
      generatedAt: new Date().toISOString(),
      planRevision,
    };
    renderSetPlan();
    $('#set-builder-message').textContent =
      `${result.accepted.length} distinct direction${result.accepted.length === 1 ? '' : 's'} ready · ${preferred.label} applied at ${preferred.health.score}/100${sectionFallbacks.length ? ` · ${sectionFallbacks.length} related-genre fill${sectionFallbacks.length === 1 ? '' : 's'} disclosed below` : ''}. Switch directions below to compare.`;
  }

  async function cancelAITrackPlan() {
    planningController?.abort();
    planningController = null;
    const jobId = activePlanningJobId;
    activePlanningJobId = '';
    const cancelButton = $('#set-cancel-planning');
    if (cancelButton) cancelButton.hidden = true;
    if (jobId) await planningClient.cancel(jobId).catch(() => null);
  }

  async function loadAIObservability() {
    const status = $('#set-ai-operations-status');
    const root = $('#set-ai-operations-summary');
    if (!status || !root) return;
    try {
      const report = await planningClient.observability();
      status.textContent = `${report.completedCount} completed · ${report.failedCount} failed · ${report.canceledCount} canceled`;
      root.innerHTML = aiObservabilityCards(report, escapeHtml);
    } catch (error) {
      status.textContent = error.message || String(error);
      root.innerHTML = '';
    }
  }

  async function generateAITrackPlan() {
    await cancelAITrackPlan();
    const brief = setBrief();
    const idTools = { setTrackId, setCatalogTrackId };
    const { journey, lockedSections, targetTrackCount } = aiPlanningContext({
      state,
      brief,
      eligiblePool: eligibleSetTracks(brief),
      ...idTools,
    });
    const controller = new AbortController();
    planningController = controller;
    let started;
    try {
      progress.showCandidatePool?.();
      started = await planningClient.start({
        brief,
        journey,
        target_duration_minutes: brief.length,
        target_track_count: targetTrackCount,
        required_track_ids: catalogIds(state.requiredIds, state.library, idTools),
        excluded_track_ids: catalogIds(state.excludedIds, state.library, idTools),
        locked_track_ids: catalogIds(state.lockedIds, state.library, idTools),
        locked_track_sections: lockedSections,
        base_plan_revision: state.planRevision,
        per_section_limit: Math.min(100, Math.max(30, targetTrackCount)),
        total_limit: 100,
      });
    } catch (error) {
      if (planningController === controller) planningController = null;
      throw error;
    }
    activePlanningJobId = started.jobId;
    $('#set-cancel-planning').hidden = false;
    let result;
    try {
      result = await planningClient.wait(started.jobId, {
        signal: controller.signal,
        onProgress: (jobState) => {
          $('#set-builder-message').textContent = `${jobState.stage} · ${jobState.progress || 0}%`;
          progress.updateRemotePlanning?.(jobState.stage, jobState.progress);
        },
      });
    } finally {
      if (activePlanningJobId === started.jobId) activePlanningJobId = '';
      if (planningController === controller) planningController = null;
      if (!activePlanningJobId) $('#set-cancel-planning').hidden = true;
    }
    const byCatalogId = new Map(state.library.map((track) => [setCatalogTrackId(track), track]));
    const selected = result.plan.map((item) => {
      const track = byCatalogId.get(item.id);
      if (!track) throw new Error(`Validated catalog track ${item.id} is not loaded in the browser.`);
      track._aiSelectionReason = item.selectionReason;
      track._candidateReasons = Array.isArray(item.reasons) ? item.reasons : [];
      track._planSectionId = item.sectionId;
      track._candidateMetrics = {
        technicalScore: item.technicalScore || 0,
        preferenceAdjustment: item.preferenceAdjustment || 0,
        baselineRank: item.baselineRank || 0,
        personalizedRank: item.personalizedRank || 0,
        rankDelta: item.rankDelta || 0,
        matchTier: item.matchTier || 'unknown',
      };
      return track;
    });
    if (state.plan.length) pushSetHistory();
    state.plan = improveSetOrder(selected, brief);
    resetSetReviewDraft();
    state.proposals = [];
    state.activeProposal = '';
    state.transitionSettings = {};
    planningReceipt = {
      version: 1,
      mode: result.mode,
      provider: result.provider,
      model: result.model,
      summary: result.summary,
      warnings: result.warnings || [],
      evaluation: result.evaluation || null,
      comparison: result.comparison || null,
      modelRepairs: result.modelRepairs || [],
      candidatePool: result.candidatePool || null,
      fallbackReason: result.fallbackReason || null,
      planningDurationMs: result.planningDurationMs ?? null,
      generatedAt: new Date().toISOString(),
      observability: result.observability || null,
      basePlanRevision: result.basePlanRevision || null,
      planRevision: null,
    };
    void loadAIObservability();
    $('#set-builder-message').textContent = 'Validated track order ready. Optimizing transition techniques…';
    progress.startTransitionOptimization?.();
    await autoOptimizeSetTransitions();
    planningReceipt.planRevision = advancePlanRevision();
    renderSetPlan();
    const mixHealth = setHealth();
    const warningCount = result.warnings?.length || 0;
    const source =
      result.mode === 'ai-planned'
        ? [result.provider, result.model].filter(Boolean).join(' · ') || 'AI planner'
        : 'deterministic safety fallback';
    $('#set-builder-message').textContent =
      mixHealth.score >= brief.minimumHealth
        ? `${result.summary} ${selected.length} tracks · ${source} · ${mixHealth.score}/100 mix health.`
        : `${result.summary} Draft retained for repair · ${mixHealth.score}/100 mix health is below your ${brief.minimumHealth} target · ${warningCount} validation warning${warningCount === 1 ? '' : 's'}.`;
  }

  async function selectSetProposal(id) {
    const next = state.proposals.find((proposal) => proposal.id === id && proposal.accepted);
    if (!next || id === state.activeProposal) return;
    const current = state.proposals.find((proposal) => proposal.id === state.activeProposal);
    if (current) {
      current.snapshot = setPlanSnapshot();
      current.health = setHealth();
    }
    stopTransitionPreview();
    pushSetHistory();
    state.activeProposal = id;
    restoreSetSnapshot(next.snapshot, false);
    const switchNonce = ++proposalSwitchNonce;
    const needsOptimization = !Object.keys(state.transitionSettings).length;
    renderSetPlan();
    $('#set-builder-message').textContent = needsOptimization
      ? `${next.label} applied · ${setHealth().score}/100 health. Optimizing its transitions in the background…`
      : `${next.label} applied · ${setHealth().score}/100 health. Your edits to the other directions are saved.`;
    if (!needsOptimization) return;
    try {
      const optimized = await autoOptimizeSetTransitions();
      if (switchNonce !== proposalSwitchNonce || state.activeProposal !== id) return;
      next.snapshot = setPlanSnapshot();
      next.health = setHealth();
      renderSetPlan();
      $('#set-builder-message').textContent =
        `${next.label} applied · ${next.health.score}/100 health · ${optimized} transition${optimized === 1 ? '' : 's'} optimized. Your edits to the other directions are saved.`;
    } catch (error) {
      if (switchNonce !== proposalSwitchNonce || state.activeProposal !== id) return;
      console.error('Set proposal optimization failed', error);
      $('#set-builder-message').textContent =
        `${next.label} is ready, but automatic transition optimization failed: ${error?.message || error}. You can still edit each mix manually.`;
      notify('The set direction changed, but some transitions could not be optimized.', 'danger');
    }
  }

  function renderSetProposals() {
    const root = $('#set-proposals');
    if (!root) return;
    root.innerHTML = setProposalMarkup(state.proposals, state.activeProposal, escapeHtml);
    root.querySelectorAll('[data-proposal]').forEach((button) => {
      button.onclick = () => selectSetProposal(button.dataset.proposal);
      button.onkeydown = (event) => {
        if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
        event.preventDefault();
        const available = [...root.querySelectorAll('[data-proposal]:not(:disabled)')];
        const offset = ['ArrowRight', 'ArrowDown'].includes(event.key) ? 1 : -1;
        const next = available[(available.indexOf(button) + offset + available.length) % available.length];
        next?.focus();
        next?.click();
      };
    });
  }

  const regenerateUnlocked = createSetRegenerationCommand({
    state,
    snapshot: setPlanSnapshot,
    restore: (snapshot) => restoreSetSnapshot(snapshot, false),
    generate: () =>
      $('#set-planning-mode').value === 'ai-planned' ? generateAITrackPlan() : generateDeterministicSetPlan(),
    render: renderSetPlan,
    getReceipt: () => planningReceipt,
    setReceipt: (receipt) => {
      planningReceipt = receipt;
    },
  });

  return Object.freeze({
    cancelAITrackPlan,
    generateAITrackPlan,
    generateDeterministicSetPlan,
    loadAIObservability,
    regenerateUnlocked,
    receipt: () => planningReceipt,
    renderSetProposals,
    selectSetProposal,
    setReceipt: (value) => {
      planningReceipt = value;
    },
  });
}
