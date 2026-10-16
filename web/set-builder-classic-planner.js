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
