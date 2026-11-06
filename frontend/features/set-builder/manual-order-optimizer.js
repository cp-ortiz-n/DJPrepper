/** Pure, constraint-aware ordering policy for manually curated sets. */

const DEFAULT_HEALTH_TOLERANCE = 5;
const DEFAULT_BEAM_WIDTH = 8;
const DEFAULT_MAXIMUM_PASSES = 6;

function fingerprint(plan, trackId) {
  return plan.map(trackId).join('|');
}

function movedCount(plan, originalIds, trackId) {
  return plan.reduce((count, track, index) => count + (trackId(track) === originalIds[index] ? 0 : 1), 0);
}

function compareCandidates(left, right) {
  return (
    right.energyFit - left.energyFit ||
    right.health - left.health ||
    left.movedCount - right.movedCount ||
    left.fingerprint.localeCompare(right.fingerprint)
  );
}

/**
 * Find an energy-aware order without sacrificing the set's transition floor.
 *
 * Manual curation prioritizes the selected energy journey, while locks and
 * journey sections remain hard constraints. The returned order is a preview;
 * the UI controller owns the explicit Apply action.
 */
export function optimizeManualEnergyOrder(
  plan,
  {
    brief = {},
    health,
    energyFit,
    trackId,
    songEnergy,
    targetEnergy,
    isFixed = () => false,
    sectionId = (track) => track?._planSectionId || '',
    minimumHealth = brief.minimumHealth || 0,
    healthTolerance = DEFAULT_HEALTH_TOLERANCE,
    beamWidth = DEFAULT_BEAM_WIDTH,
    maximumPasses = DEFAULT_MAXIMUM_PASSES,
  },
) {
  const current = [...(plan || [])];
  if (current.length < 2) return null;
  const ids = current.map(trackId);
  const fixedPositions = new Set(current.flatMap((track, index) => (isFixed(track, index) ? [index] : [])));
  const currentHealth = Number(health(current)?.score || 0);
  const requestedFloor = Math.max(0, Math.min(100, Number(minimumHealth) || 0));
  const toleranceFloor = Math.max(0, currentHealth - Math.max(0, Number(healthTolerance) || 0));
  const healthGuardrail = Math.min(currentHealth, Math.max(requestedFloor, toleranceFloor));
  const seen = new Map();
  let unsafeEnergyImprovement = false;

  const evaluate = (candidate) => {
    const key = fingerprint(candidate, trackId);
    if (seen.has(key)) return seen.get(key);
    const result = {
      plan: candidate,
      fingerprint: key,
      health: Number(health(candidate)?.score || 0),
      energyFit: Number(energyFit(candidate, brief) || 0),
      movedCount: movedCount(candidate, ids, trackId),
    };
    result.safe = result.health >= healthGuardrail;
    seen.set(key, result);
    return result;
  };

  const currentResult = evaluate(current);
  let best = currentResult;
  const consider = (result) => {
    if (!result.safe && result.energyFit > currentResult.energyFit) unsafeEnergyImprovement = true;
    if (result.safe && compareCandidates(result, best) < 0) best = result;
  };

  const seeded = [...current];
  const groups = new Map();
  current.forEach((track, index) => {
    if (fixedPositions.has(index)) return;
    const key = String(sectionId(track, index) || '');
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(index);
  });
  groups.forEach((positions) => {
    const targetPositions = [...positions].sort(
      (left, right) =>
        Number(targetEnergy(left, current.length, brief)) - Number(targetEnergy(right, current.length, brief)) ||
        left - right,
    );
    const tracks = positions
      .map((index) => current[index])
      .sort(
        (left, right) =>
          Number(songEnergy(left)) - Number(songEnergy(right)) || String(trackId(left)).localeCompare(String(trackId(right))),
      );
    targetPositions.forEach((position, index) => {
      seeded[position] = tracks[index];
    });
  });

  const seedResult = evaluate(seeded);
  consider(seedResult);
  let beam = [currentResult, seedResult].filter(
    (result, index, values) => values.findIndex((item) => item.fingerprint === result.fingerprint) === index,
  );
  const allowedSwap = (candidate, left, right) =>
    !fixedPositions.has(left) &&
    !fixedPositions.has(right) &&
    String(sectionId(candidate[left], left) || '') === String(sectionId(candidate[right], right) || '');

  for (let pass = 0; pass < Math.max(0, Number(maximumPasses) || 0); pass += 1) {
    const neighbors = [];
    beam.forEach(({ plan: candidate }) => {
      for (let left = 0; left < candidate.length - 1; left += 1) {
        for (let right = left + 1; right < candidate.length; right += 1) {
          if (!allowedSwap(candidate, left, right)) continue;
          const swapped = [...candidate];
          [swapped[left], swapped[right]] = [swapped[right], swapped[left]];
          const before = seen.size;
          const result = evaluate(swapped);
          if (seen.size === before) continue;
          consider(result);
          neighbors.push(result);
        }
      }
    });
    if (!neighbors.length) break;
    const safe = neighbors.filter((result) => result.safe).sort(compareCandidates);
    const recovery = [...neighbors]
      .sort(
        (left, right) =>
          right.health - left.health || right.energyFit - left.energyFit || left.movedCount - right.movedCount,
      )
      .slice(0, Math.max(1, Math.floor(beamWidth / 2)));
    beam = [...safe.slice(0, beamWidth), ...recovery]
      .filter((result, index, values) => values.findIndex((item) => item.fingerprint === result.fingerprint) === index)
      .slice(0, Math.max(1, beamWidth));
  }

  const improved =
    best.fingerprint !== currentResult.fingerprint &&
    (best.energyFit > currentResult.energyFit ||
      (best.energyFit === currentResult.energyFit && best.health > currentResult.health));
  return {
    currentHealth,
    suggestedHealth: improved ? best.health : currentHealth,
    currentEnergyFit: currentResult.energyFit,
    suggestedEnergyFit: improved ? best.energyFit : currentResult.energyFit,
    changed: improved,
    currentFingerprint: currentResult.fingerprint,
    suggested: improved ? [...best.plan] : current,
    movedCount: improved ? best.movedCount : 0,
    healthGuardrail,
    noSafeImprovement: !improved && unsafeEnergyImprovement,
  };
}
