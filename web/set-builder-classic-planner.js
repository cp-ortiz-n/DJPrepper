export function optimizePlanOrder(plan, { fitness, isFixed = () => false, maximumPasses = 16 }) {
  const improved = [...plan];
  let current = fitness(improved);
  for (let pass = 0; pass < Math.min(maximumPasses, Math.max(1, improved.length)); pass += 1) {
    let best = current;
    let bestSwap = null;
    for (let left = 0; left < improved.length - 1; left += 1) {
      if (isFixed(improved[left], left)) continue;
      for (let right = left + 1; right < improved.length; right += 1) {
        if (isFixed(improved[right], right)) continue;
        [improved[left], improved[right]] = [improved[right], improved[left]];
        const score = fitness(improved);
        [improved[left], improved[right]] = [improved[right], improved[left]];
        if (score > best + 0.01) {
          best = score;
          bestSwap = [left, right];
        }
      }
    }
    if (!bestSwap) break;
    [improved[bestSwap[0]], improved[bestSwap[1]]] = [improved[bestSwap[1]], improved[bestSwap[0]]];
    current = best;
  }
  return improved;
}

export function createClassicSetPlanner({ strategies, schedule = () => Promise.resolve() }) {
  async function generate({ count, minimumHealth, buildVariation, improveOrder, evaluate, trackId, snapshot }) {
    const generatedTrackIds = new Set();
    const proposals = [];

    for (const strategy of strategies) {
      await schedule();
      let bestPlan = [];
      let bestHealth = { score: -1, transitions: [], vocalClashes: 0 };
      let attempts = 0;
      for (; attempts < 10; attempts += 1) {
        const candidate = buildVariation(strategy.id, generatedTrackIds);
        if (candidate.length < count) continue;
        const repaired = improveOrder(candidate);
        const health = evaluate(repaired);
        const overlap =
          repaired.filter((track) => generatedTrackIds.has(trackId(track))).length / Math.max(1, repaired.length);
        const distinctBonus = strategy.id === 'adventurous' ? (1 - overlap) * 12 : 0;
        const rank = health.score + distinctBonus;
        if (rank > (bestHealth.rank ?? -1)) {
          bestPlan = repaired;
          bestHealth = { ...health, rank };
        }
        if (health.score >= minimumHealth && attempts >= 3) {
          attempts += 1;
          break;
        }
      }
      const accepted = bestPlan.length >= count && bestHealth.score >= minimumHealth;
      if (accepted) bestPlan.forEach((track) => generatedTrackIds.add(trackId(track)));
      proposals.push({ ...strategy, accepted, attempts, health: bestHealth, snapshot: snapshot(bestPlan) });
    }

    const accepted = proposals.filter((proposal) => proposal.accepted);
    const preferred =
      proposals.find((proposal) => proposal.id === 'safe' && proposal.accepted) ||
      [...accepted].sort((left, right) => right.health.score - left.health.score)[0] ||
      null;
    const best = [...proposals].sort((left, right) => right.health.score - left.health.score)[0] || null;
    return { proposals, accepted, preferred, best };
  }

  return Object.freeze({ generate });
}
